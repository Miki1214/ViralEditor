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


def suggested_word_count(duration_s: float, words_per_second: float) -> int:
    """Return the suggested word budget for a slot at the given reading speed."""
    return max(0, int(round(duration_s * words_per_second)))


def tokenize_script(script_text: str) -> list[str]:
    """Split script text into word tokens."""
    return _TOKEN_RE.findall(script_text.strip())


def split_script_into_chunks(
    script_text: str,
    slots: list[StorySlot],
    *,
    words_per_second: float = DEFAULT_WORDS_PER_SECOND,
    slot_overrides: dict[str, str] | None = None,
    emphasis_words: set[str] | frozenset[str] | None = None,
) -> dict[str, list[CaptionChunk]]:
    """Distribute script words across storyboard slots and group into phrase chunks."""
    overrides = slot_overrides or {}
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
            override_tokens = tokenize_script(overrides[slot.id])
            result[slot.id] = _tokens_to_chunks(
                override_tokens,
                slot.target_duration_s,
                emphasis,
            )

    return result


def _allocate_tokens(
    tokens: list[str],
    slots: list[StorySlot],
    budgets: dict[str, int],
) -> dict[str, list[str]]:
    """Split tokens proportionally to per-slot word budgets."""
    total_budget = sum(budgets.values())
    if total_budget <= 0 or not tokens:
        return {slot.id: [] for slot in slots}

    allocations: dict[str, list[str]] = {slot.id: [] for slot in slots}
    cursor = 0
    remaining = len(tokens)

    for index, slot in enumerate(slots):
        budget = budgets[slot.id]
        if index == len(slots) - 1:
            take = remaining
        else:
            take = min(remaining, budget)
        allocations[slot.id] = tokens[cursor : cursor + take]
        cursor += take
        remaining -= take

    return allocations


def _tokens_to_chunks(
    tokens: list[str],
    slot_duration_s: float,
    emphasis: set[str],
) -> list[CaptionChunk]:
    """Group tokens into 2–4 word phrase chunks with even sub-timing."""
    if not tokens:
        return []

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
        emphasis_words=emphasis,
    )
