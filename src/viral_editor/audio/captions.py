"""Caption script splitting and reading-speed presets."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from viral_editor.models import CaptionChunk, CaptionWord, StorySlot

_TOKEN_RE = re.compile(r"\S+")


@dataclass(frozen=True)
class WpsPreset:
    words_per_second: float
    label: str


WPS_PRESETS: tuple[WpsPreset, ...] = (
    WpsPreset(3.0, "Accessible"),
    WpsPreset(4.0, "Comfortable"),
    WpsPreset(5.0, "Recommended"),
    WpsPreset(6.0, "Energetic"),
    WpsPreset(7.5, "Hype"),
)

DEFAULT_WORDS_PER_SECOND = 5.0
PHRASE_MIN_WORDS = 2
PHRASE_MAX_WORDS = 4

# Floor on per-chunk on-screen duration. Bounds how many drawtext overlays a
# single slot can ever produce, independent of how the words got there
# (auto-allocation overflow or a manual per-slot caption override with far
# more text than the slot's duration can display). Without this, an oversized
# script text turns into hundreds of chained drawtext filters for one slot,
# which bloats the composite -filter_complex argument enough to break preview
# rendering.
MIN_CHUNK_DURATION_S = 0.25


def suggested_word_count(duration_s: float, words_per_second: float) -> int:
    """Return the suggested word budget for a slot at the given reading speed."""
    return max(0, int(round(duration_s * words_per_second)))


def tokenize_script(script_text: str) -> list[str]:
    """Split script text into word tokens."""
    return _TOKEN_RE.findall(script_text.strip())


_SMART_QUOTES = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
})
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.!?;:])")


def cleanup_script_text(script_text: str) -> str:
    """Normalize a pasted/transcribed script before auto-allocating it to slots.

    Straightens smart quotes/dashes, collapses stray whitespace, drops
    leftover spaces before punctuation, and trims blank lines so the word
    tokenizer used by :func:`distribute_script_to_slot_overrides` sees clean
    tokens instead of formatting artifacts.
    """
    text = script_text.translate(_SMART_QUOTES)
    lines = [_MULTI_SPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = _MULTI_BLANK_LINE_RE.sub("\n\n", text)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    return text.strip()


def split_script_into_chunks(
    script_text: str,
    slots: list[StorySlot],
    *,
    words_per_second: float = DEFAULT_WORDS_PER_SECOND,
    slot_overrides: dict[str, str] | None = None,
    word_timing_overrides: dict[str, list[dict[str, float | str]]] | None = None,
    emphasis_words: set[str] | frozenset[str] | None = None,
) -> dict[str, list[CaptionChunk]]:
    """Distribute script words across storyboard slots and group into phrase chunks."""
    overrides = slot_overrides or {}
    timing_overrides = word_timing_overrides or {}
    emphasis = {word.lower() for word in (emphasis_words or ())}
    ordered = sorted(slots, key=lambda slot: slot.order)
    if not ordered:
        return {}

    override_slot_ids = {slot_id for slot_id, text in overrides.items() if text.strip()}
    auto_slots = [slot for slot in ordered if slot.id not in override_slot_ids]
    auto_budgets = {
        slot.id: suggested_word_count(slot.target_duration_s, words_per_second)
        for slot in auto_slots
    }
    total_auto_budget = sum(auto_budgets.values())
    tokens = tokenize_script(script_text)
    auto_tokens = list(tokens)
    result: dict[str, list[CaptionChunk]] = {}

    if total_auto_budget > 0 and auto_tokens:
        allocations = _allocate_tokens(auto_tokens, auto_slots, auto_budgets)
        for slot in auto_slots:
            slot_tokens = allocations.get(slot.id, [])
            result[slot.id] = _tokens_to_chunks(
                slot_tokens,
                slot.target_duration_s,
                emphasis,
            )
    elif auto_slots:
        for slot in auto_slots:
            result[slot.id] = []

    for slot in ordered:
        if slot.id in override_slot_ids:
            override_text = overrides[slot.id]
            stored_timing = timing_overrides.get(slot.id)
            if stored_timing and _timing_override_matches_text(stored_timing, override_text):
                timed_words = _words_from_timing_override(stored_timing, emphasis)
                result[slot.id] = _words_to_chunks_with_timing(timed_words)
            else:
                override_tokens = tokenize_script(override_text)
                result[slot.id] = _tokens_to_chunks(
                    override_tokens,
                    slot.target_duration_s,
                    emphasis,
                )

    return result


def _distribute_by_budget(
    items: list,
    slots: list[StorySlot],
    budgets: dict[str, int],
) -> dict[str, list]:
    """Split a list across slots proportionally to per-slot word budgets.

    Every item is placed somewhere — none are dropped for exceeding a slot's
    reading-speed budget. Budgets only steer the *proportions*; a script far
    longer than the storyboard's total reading-speed budget still lands in
    full across the slots (weighted toward the ones with more room), instead
    of being silently truncated at the sum of the budgets. The actual
    duration-safe cap per slot is enforced later, per slot, by
    `_tokens_to_chunks` (bounded by `MIN_CHUNK_DURATION_S`), which is the
    real constraint on how much text a single clip can render.
    """
    if not items:
        return {slot.id: [] for slot in slots}
    if not slots:
        return {}

    total_budget = sum(budgets.values())
    allocations: dict[str, list] = {slot.id: [] for slot in slots}
    cursor = 0
    remaining_items = len(items)
    remaining_budget = total_budget

    for index, slot in enumerate(slots):
        budget = budgets.get(slot.id, 0)
        is_last = index == len(slots) - 1
        if is_last or remaining_budget <= 0:
            take = remaining_items
        else:
            share = round(remaining_items * (budget / remaining_budget))
            take = max(0, min(remaining_items, share))
        allocations[slot.id] = items[cursor : cursor + take]
        cursor += take
        remaining_items -= take
        remaining_budget -= budget

    return allocations


def _allocate_tokens(
    tokens: list[str],
    slots: list[StorySlot],
    budgets: dict[str, int],
) -> dict[str, list[str]]:
    """Split tokens proportionally to per-slot word budgets."""
    return _distribute_by_budget(tokens, slots, budgets)


def _allocate_items(
    items: list,
    slots: list[StorySlot],
    budgets: dict[str, int],
) -> dict[str, list]:
    """Split a list proportionally to per-slot word budgets."""
    return _distribute_by_budget(items, slots, budgets)


def transcribed_script_in_window(
    words: list[CaptionWord],
    *,
    music_start_s: float,
    music_end_s: float,
) -> str:
    """Join transcribed words whose midpoint falls inside the selected music window."""
    parts: list[str] = []
    for word in words:
        midpoint_s = (word.start_s + word.end_s) / 2.0
        if music_start_s <= midpoint_s < music_end_s:
            parts.append(word.text)
    return " ".join(parts)


def assign_transcribed_words_to_slot_overrides(
    words: list[CaptionWord],
    slots: list[StorySlot],
    *,
    music_start_s: float,
    music_end_s: float,
) -> dict[str, str]:
    """Map word-level ASR timestamps into per-slot override text."""
    ordered = sorted(slots, key=lambda slot: slot.order)
    if not ordered:
        return {}

    buckets: dict[str, list[str]] = {slot.id: [] for slot in ordered}
    for word in words:
        midpoint_s = (word.start_s + word.end_s) / 2.0
        if midpoint_s < music_start_s or midpoint_s >= music_end_s:
            continue
        storyboard_t = midpoint_s - music_start_s
        matched_slot = _match_word_to_slot(storyboard_t, ordered)
        if matched_slot is not None:
            buckets[matched_slot.id].append(word.text)

    return {
        slot_id: " ".join(tokens)
        for slot_id, tokens in buckets.items()
        if tokens
    }


def _match_word_to_slot(
    storyboard_t: float,
    ordered: list[StorySlot],
) -> StorySlot | None:
    matched_slot: StorySlot | None = None
    for slot in ordered:
        if slot.out_start_s <= storyboard_t + 1e-6 and storyboard_t < slot.out_end_s - 1e-6:
            matched_slot = slot
            break
    if matched_slot is None and ordered and storyboard_t >= ordered[-1].out_start_s - 1e-6:
        matched_slot = ordered[-1]
    return matched_slot


def _rebase_word_to_slot_local(
    word: CaptionWord,
    *,
    slot: StorySlot,
    time_offset_s: float,
) -> CaptionWord:
    start_s = max(0.0, min(slot.target_duration_s, word.start_s - time_offset_s))
    end_s = max(0.0, min(slot.target_duration_s, word.end_s - time_offset_s))
    if end_s < start_s:
        end_s = start_s
    return CaptionWord(
        text=word.text,
        start_s=round(start_s, 4),
        end_s=round(end_s, 4),
        emphasis=word.emphasis,
    )


def assign_transcribed_words_with_timing_to_slots(
    words: list[CaptionWord],
    slots: list[StorySlot],
    *,
    music_start_s: float,
    music_end_s: float,
) -> dict[str, list[CaptionWord]]:
    """Map ASR words into per-slot timed word lists in slot-local coordinates."""
    ordered = sorted(slots, key=lambda slot: slot.order)
    if not ordered:
        return {}

    buckets: dict[str, list[CaptionWord]] = {slot.id: [] for slot in ordered}
    for word in words:
        midpoint_s = (word.start_s + word.end_s) / 2.0
        if midpoint_s < music_start_s or midpoint_s >= music_end_s:
            continue
        storyboard_t = midpoint_s - music_start_s
        matched_slot = _match_word_to_slot(storyboard_t, ordered)
        if matched_slot is None:
            continue
        offset = music_start_s + matched_slot.out_start_s
        buckets[matched_slot.id].append(
            _rebase_word_to_slot_local(word, slot=matched_slot, time_offset_s=offset)
        )

    return {slot_id: bucket for slot_id, bucket in buckets.items() if bucket}


def serialize_word_timing(words: list[CaptionWord]) -> list[dict[str, float | str]]:
    return [
        {"text": word.text, "start_s": word.start_s, "end_s": word.end_s}
        for word in words
    ]


def distribute_words_with_timing_to_slots(
    words: list[CaptionWord],
    slots: list[StorySlot],
    *,
    words_per_second: float = DEFAULT_WORDS_PER_SECOND,
) -> tuple[dict[str, str], dict[str, list[dict[str, float | str]]]]:
    """Allocate transcribed words across slots preserving per-word timing."""
    ordered = sorted(slots, key=lambda slot: slot.order)
    if not ordered or not words:
        return {}, {}

    budgets = {
        slot.id: suggested_word_count(slot.target_duration_s, words_per_second)
        for slot in ordered
    }
    allocations = _allocate_items(words, ordered, budgets)

    slot_overrides: dict[str, str] = {}
    word_timing_overrides: dict[str, list[dict[str, float | str]]] = {}
    for slot in ordered:
        slot_words = allocations.get(slot.id, [])
        if not slot_words:
            continue
        base_start = slot_words[0].start_s
        rebased = [
            _rebase_word_to_slot_local(
                word,
                slot=slot,
                time_offset_s=base_start,
            )
            for word in slot_words
        ]
        slot_overrides[slot.id] = " ".join(word.text for word in rebased)
        word_timing_overrides[slot.id] = serialize_word_timing(rebased)

    return slot_overrides, word_timing_overrides


def rebase_clip_words_to_slot_local(
    words: list[CaptionWord],
    *,
    slot: StorySlot,
    speed_factor: float,
) -> list[CaptionWord]:
    """Convert extraction-relative ASR timing into slot-local output time."""
    if speed_factor <= 0:
        speed_factor = 1.0
    rebased: list[CaptionWord] = []
    for word in words:
        rebased.append(
            CaptionWord(
                text=word.text,
                start_s=round(
                    max(0.0, min(slot.target_duration_s, word.start_s / speed_factor)),
                    4,
                ),
                end_s=round(
                    max(0.0, min(slot.target_duration_s, word.end_s / speed_factor)),
                    4,
                ),
                emphasis=word.emphasis,
            )
        )
    return rebased


def distribute_script_to_slot_overrides(
    script_text: str,
    slots: list[StorySlot],
    *,
    words_per_second: float = DEFAULT_WORDS_PER_SECOND,
) -> dict[str, str]:
    """Allocate a full script across slots using each slot's reading-speed budget."""
    ordered = sorted(slots, key=lambda slot: slot.order)
    if not ordered:
        return {}

    tokens = tokenize_script(script_text)
    if not tokens:
        return {}

    budgets = {
        slot.id: suggested_word_count(slot.target_duration_s, words_per_second)
        for slot in ordered
    }
    allocations = _allocate_tokens(tokens, ordered, budgets)
    return {
        slot_id: " ".join(slot_tokens)
        for slot_id, slot_tokens in allocations.items()
        if slot_tokens
    }


def _tokens_to_chunks(
    tokens: list[str],
    slot_duration_s: float,
    emphasis: set[str],
) -> list[CaptionChunk]:
    """Group tokens into 2–4 word phrase chunks with even sub-timing."""
    if not tokens:
        return []

    max_chunks = max(1, int(slot_duration_s / MIN_CHUNK_DURATION_S))
    max_tokens = max_chunks * PHRASE_MAX_WORDS
    if len(tokens) > max_tokens:
        tokens = tokens[:max_tokens]

    phrase_groups = _group_into_phrases(tokens)
    chunk_count = len(phrase_groups)
    chunk_duration = slot_duration_s / chunk_count if chunk_count else slot_duration_s
    chunks: list[CaptionChunk] = []

    for index, group in enumerate(phrase_groups):
        chunk_start = index * chunk_duration
        chunk_end = (index + 1) * chunk_duration if index < chunk_count - 1 else slot_duration_s
        word_count = len(group)
        word_duration = (chunk_end - chunk_start) / word_count if word_count else 0.0
        words: list[CaptionWord] = []
        for word_index, text in enumerate(group):
            word_start = chunk_start + word_index * word_duration
            word_end = chunk_start + (word_index + 1) * word_duration
            if word_index == word_count - 1:
                word_end = chunk_end
            words.append(
                CaptionWord(
                    text=text,
                    start_s=round(word_start, 4),
                    end_s=round(word_end, 4),
                    emphasis=text.lower().strip(".,!?") in emphasis,
                )
            )
        chunks.append(
            CaptionChunk(
                words=words,
                start_s=round(chunk_start, 4),
                end_s=round(chunk_end, 4),
            )
        )

    return chunks


def _timing_override_matches_text(
    timing: list[dict[str, float | str]],
    override_text: str,
) -> bool:
    stored_text = " ".join(str(word["text"]) for word in timing)
    return stored_text.strip() == override_text.strip()


def _words_from_timing_override(
    timing: list[dict[str, float | str]],
    emphasis: set[str],
) -> list[CaptionWord]:
    words: list[CaptionWord] = []
    for entry in timing:
        text = str(entry["text"])
        words.append(
            CaptionWord(
                text=text,
                start_s=round(float(entry["start_s"]), 4),
                end_s=round(float(entry["end_s"]), 4),
                emphasis=text.lower().strip(".,!?") in emphasis,
            )
        )
    return words


def _words_to_chunks_with_timing(words: list[CaptionWord]) -> list[CaptionChunk]:
    if not words:
        return []

    texts = [word.text for word in words]
    phrase_groups = _group_into_phrases(texts)
    chunks: list[CaptionChunk] = []
    cursor = 0
    for group in phrase_groups:
        group_words = words[cursor : cursor + len(group)]
        cursor += len(group)
        if not group_words:
            continue
        chunks.append(
            CaptionChunk(
                words=group_words,
                start_s=group_words[0].start_s,
                end_s=group_words[-1].end_s,
            )
        )
    return chunks


def _group_into_phrases(tokens: list[str]) -> list[list[str]]:
    """Split tokens into groups of PHRASE_MIN_WORDS..PHRASE_MAX_WORDS words."""
    if not tokens:
        return []

    group_count = max(1, math.ceil(len(tokens) / PHRASE_MAX_WORDS))
    base_size = len(tokens) // group_count
    remainder = len(tokens) % group_count

    groups: list[list[str]] = []
    cursor = 0
    for group_index in range(group_count):
        size = base_size + (1 if group_index < remainder else 0)
        size = max(PHRASE_MIN_WORDS, min(PHRASE_MAX_WORDS, size))
        if group_index == group_count - 1:
            group = tokens[cursor:]
        else:
            group = tokens[cursor : cursor + size]
            cursor += size
        if group:
            groups.append(group)

    if groups and sum(len(group) for group in groups) < len(tokens):
        leftover = tokens[cursor:]
        if leftover:
            groups[-1].extend(leftover)

    # Re-balance any group outside 2–4 words by merging/splitting.
    balanced: list[list[str]] = []
    pending: list[str] = []
    for token in tokens:
        pending.append(token)
        if len(pending) >= PHRASE_MAX_WORDS:
            balanced.append(pending[:PHRASE_MAX_WORDS])
            pending = pending[PHRASE_MAX_WORDS:]
        elif len(pending) >= PHRASE_MIN_WORDS and len(tokens) - sum(
            len(group) for group in balanced
        ) - len(pending) <= PHRASE_MIN_WORDS:
            balanced.append(pending)
            pending = []

    if pending:
        if balanced and len(pending) < PHRASE_MIN_WORDS:
            balanced[-1].extend(pending)
        else:
            balanced.append(pending)

    return balanced or groups


def build_caption_chunks_for_slots(
    caption_config,
    slots: list[StorySlot],
    *,
    emphasis_words: list[str] | None = None,
) -> dict[str, list[CaptionChunk]]:
    """Build per-slot caption chunks from a caption config and ordered slots."""
    emphasis = {word.lower() for word in (emphasis_words or ())}
    return split_script_into_chunks(
        caption_config.script_text,
        slots,
        words_per_second=caption_config.words_per_second,
        slot_overrides=caption_config.slot_overrides,
        word_timing_overrides=caption_config.word_timing_overrides,
        emphasis_words=emphasis,
    )
