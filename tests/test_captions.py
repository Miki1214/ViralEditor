"""Tests for caption splitting and reading-speed presets."""

from __future__ import annotations

from viral_editor.audio.captions import (
    WPS_PRESETS,
    assign_transcribed_words_to_slot_overrides,
    assign_transcribed_words_with_timing_to_slots,
    cleanup_slot_overrides,
    distribute_script_to_slot_overrides,
    distribute_script_with_timing_to_slots,
    reconcile_word_timing_override,
    suggested_word_count,
    split_script_into_chunks,
    sync_captions_to_asr,
    transcribed_script_in_window,
)
from viral_editor.models import CaptionWord, StorySlot


def _slot(slot_id: str, order: int, duration: float) -> StorySlot:
    return StorySlot(
        id=slot_id,
        order=order,
        label=f"Slot {order}",
        out_start_s=order * duration,
        out_end_s=(order + 1) * duration,
        target_duration_s=duration,
    )


def test_suggested_word_count_scales_with_duration_and_wps() -> None:
    assert suggested_word_count(3.0, 5.0) == 15
    assert suggested_word_count(2.0, 4.0) == 8


def test_wps_presets_include_recommended_default() -> None:
    values = [preset.words_per_second for preset in WPS_PRESETS]
    assert 5.0 in values
    recommended = next(p for p in WPS_PRESETS if p.words_per_second == 5.0)
    assert "Recommended" in recommended.label


def test_cleanup_slot_overrides_normalizes_whitespace() -> None:
    cleaned = cleanup_slot_overrides(
        {
            "slot_a": "  hello ,  world  ",
            "slot_b": "",
        }
    )
    assert cleaned["slot_a"] == "hello, world"
    assert "slot_b" not in cleaned


def test_cleanup_caption_texts_normalizes_script_and_populates_slot_overrides() -> None:
    from viral_editor.audio.captions import cleanup_caption_texts

    slots = [_slot("a", 0, 3.0), _slot("b", 1, 2.0)]
    script, overrides = cleanup_caption_texts(
        script_text="one  two   three four five six seven eight nine ten",
        slot_overrides={},
        slots=slots,
        words_per_second=5.0,
    )
    assert script == "one two three four five six seven eight nine ten"
    assert sum(len(text.split()) for text in overrides.values()) == 10


def test_cleanup_caption_texts_cleans_explicit_slot_overrides() -> None:
    from viral_editor.audio.captions import cleanup_caption_texts

    slots = [_slot("a", 0, 3.0)]
    _, overrides = cleanup_caption_texts(
        script_text="hello world",
        slot_overrides={"a": "  hello ,  world  "},
        slots=slots,
        words_per_second=5.0,
    )
    assert overrides["a"] == "hello, world"


def test_sync_captions_to_asr_maps_words_by_storyboard_time() -> None:
    slots = [_slot("a", 0, 3.0), _slot("b", 1, 2.0)]
    words = [
        CaptionWord(text="hello", start_s=0.5, end_s=0.8),
        CaptionWord(text="world", start_s=1.0, end_s=1.3),
        CaptionWord(text="tail", start_s=3.2, end_s=3.5),
    ]
    script_text, overrides, timing = sync_captions_to_asr(
        words,
        slots,
        music_start_s=0.0,
        music_end_s=6.0,
    )
    assert script_text == "hello world tail"
    assert "hello" in overrides["a"]
    assert "tail" in overrides["b"]
    assert timing["a"][0]["start_s"] == 0.5
    assert timing["b"][-1]["text"] == "tail"


def test_split_script_distributes_words_by_slot_duration() -> None:
    slots = [_slot("a", 0, 3.0), _slot("b", 1, 2.0)]
    script = " ".join(f"word{i}" for i in range(25))
    chunks_by_slot = split_script_into_chunks(
        script,
        slots,
        words_per_second=5.0,
        slot_overrides={},
    )
    words_a = sum(len(chunk.words) for chunk in chunks_by_slot["a"])
    words_b = sum(len(chunk.words) for chunk in chunks_by_slot["b"])
    assert words_a == 15
    assert words_b == 10


def test_split_script_groups_into_phrase_chunks_of_two_to_four_words() -> None:
    slots = [_slot("a", 0, 3.0)]
    script = "one two three four five six seven eight nine ten eleven twelve"
    chunks_by_slot = split_script_into_chunks(
        script,
        slots,
        words_per_second=4.0,
        slot_overrides={},
    )
    chunks = chunks_by_slot["a"]
    assert len(chunks) >= 3
    for chunk in chunks:
        assert 2 <= len(chunk.words) <= 4


def test_split_script_honors_slot_override_text() -> None:
    slots = [_slot("a", 0, 3.0), _slot("b", 1, 2.0)]
    script = " ".join(f"word{i}" for i in range(25))
    chunks_by_slot = split_script_into_chunks(
        script,
        slots,
        words_per_second=5.0,
        slot_overrides={"b": "custom override text here"},
    )
    words_b = " ".join(w.text for chunk in chunks_by_slot["b"] for w in chunk.words)
    assert "custom" in words_b
    assert "override" in words_b


def test_assign_transcribed_words_to_slot_overrides_maps_by_storyboard_time() -> None:
    slots = [_slot("a", 0, 3.0), _slot("b", 1, 2.0)]
    words = [
        CaptionWord(text="hello", start_s=10.5, end_s=10.8),
        CaptionWord(text="hook", start_s=11.0, end_s=11.3),
        CaptionWord(text="middle", start_s=13.2, end_s=13.5),
        CaptionWord(text="clip", start_s=13.8, end_s=14.1),
        CaptionWord(text="tail", start_s=14.6, end_s=14.9),
    ]
    overrides = assign_transcribed_words_to_slot_overrides(
        words,
        slots,
        music_start_s=10.0,
        music_end_s=15.0,
    )
    assert overrides["a"] == "hello hook"
    assert overrides["b"] == "middle clip tail"


def test_assign_transcribed_words_marks_silent_slots_explicit_empty() -> None:
    slots = [_slot("a", 0, 3.0), _slot("b", 1, 3.0), _slot("c", 2, 3.0)]
    words = [
        CaptionWord(text="hello", start_s=0.5, end_s=0.8),
        CaptionWord(text="world", start_s=1.0, end_s=1.3),
    ]
    overrides = assign_transcribed_words_to_slot_overrides(
        words,
        slots,
        music_start_s=0.0,
        music_end_s=9.0,
    )
    assert overrides == {"a": "hello world", "b": "", "c": ""}

    chunks_by_slot = split_script_into_chunks(
        "hello world",
        slots,
        slot_overrides=overrides,
    )
    assert [word.text for chunk in chunks_by_slot["a"] for word in chunk.words] == [
        "hello",
        "world",
    ]
    assert chunks_by_slot["b"] == []
    assert chunks_by_slot["c"] == []


def test_assign_transcribed_words_with_timing_to_slots_rebases_to_slot_local_time() -> None:
    slots = [_slot("a", 0, 3.0), _slot("b", 1, 2.0)]
    words = [
        CaptionWord(text="hello", start_s=10.5, end_s=10.8),
        CaptionWord(text="hook", start_s=11.0, end_s=11.3),
        CaptionWord(text="middle", start_s=13.2, end_s=13.5),
        CaptionWord(text="clip", start_s=13.8, end_s=14.1),
        CaptionWord(text="tail", start_s=14.6, end_s=14.9),
    ]
    timed = assign_transcribed_words_with_timing_to_slots(
        words,
        slots,
        music_start_s=10.0,
        music_end_s=15.0,
    )
    assert timed["a"][0].start_s >= 0.0
    assert timed["a"][0].end_s <= 3.0
    assert timed["b"][0].start_s >= 0.0
    assert timed["b"][-1].end_s <= 2.0


def test_split_script_into_chunks_prefers_valid_word_timing_override() -> None:
    slots = [_slot("a", 0, 3.0)]
    timing = [
        {"text": "one", "start_s": 0.1, "end_s": 0.4},
        {"text": "two", "start_s": 0.9, "end_s": 1.2},
        {"text": "three", "start_s": 1.8, "end_s": 2.1},
    ]
    chunks_by_slot = split_script_into_chunks(
        "",
        slots,
        slot_overrides={"a": "one two three"},
        word_timing_overrides={"a": timing},
    )
    words = [word for chunk in chunks_by_slot["a"] for word in chunk.words]
    assert len(chunks_by_slot["a"]) == 1
    assert words[0].start_s == 0.1
    assert words[1].start_s == 0.9
    assert words[2].start_s == 1.8


def test_words_to_chunks_split_at_large_timing_gap() -> None:
    slots = [_slot("a", 0, 10.0)]
    timing = [
        {"text": "one", "start_s": 0.0, "end_s": 0.15},
        {"text": "two", "start_s": 0.15, "end_s": 0.30},
        {"text": "three", "start_s": 0.30, "end_s": 0.45},
        {"text": "four", "start_s": 0.45, "end_s": 0.70},
        {"text": "five", "start_s": 5.70, "end_s": 5.90},
    ]
    chunks_by_slot = split_script_into_chunks(
        "",
        slots,
        slot_overrides={"a": "one two three four five"},
        word_timing_overrides={"a": timing},
    )
    chunks = chunks_by_slot["a"]
    assert len(chunks) == 2
    assert len(chunks[0].words) == 4
    assert len(chunks[1].words) == 1
    assert chunks[0].start_s == 0.0
    assert chunks[0].end_s == 0.70
    assert chunks[1].start_s == 5.70
    assert chunks[1].end_s == 5.90


def test_reconcile_word_timing_preserves_timestamps_on_typo() -> None:
    timing = [
        {"text": "trust", "start_s": 0.1, "end_s": 0.4},
        {"text": "the", "start_s": 0.42, "end_s": 0.8},
        {"text": "Emperor", "start_s": 0.9, "end_s": 1.2},
    ]
    reconciled = reconcile_word_timing_override(
        timing,
        "trust the Emperor",
        "trust the Emperer",
    )
    assert reconciled is not None
    assert reconciled[0]["start_s"] == 0.1
    assert reconciled[1]["start_s"] == 0.42
    assert reconciled[2]["text"] == "Emperer"
    assert reconciled[2]["start_s"] == 0.9


def test_reconcile_word_timing_handles_single_word_insert() -> None:
    timing = [
        {"text": "hello", "start_s": 0.1, "end_s": 0.4},
        {"text": "world", "start_s": 0.9, "end_s": 1.2},
    ]
    reconciled = reconcile_word_timing_override(
        timing,
        "hello world",
        "hello big world",
    )
    assert reconciled is not None
    assert len(reconciled) == 3
    assert reconciled[0]["start_s"] == 0.1
    assert reconciled[2]["start_s"] == 0.9
    assert reconciled[1]["text"] == "big"
    assert float(reconciled[1]["start_s"]) >= float(reconciled[0]["end_s"])
    assert float(reconciled[1]["end_s"]) <= float(reconciled[2]["start_s"])


def test_reconcile_word_timing_returns_none_on_major_rewrite() -> None:
    timing = [
        {"text": "old", "start_s": 0.1, "end_s": 0.4},
        {"text": "text", "start_s": 0.9, "end_s": 1.2},
    ]
    reconciled = reconcile_word_timing_override(
        timing,
        "old text",
        "completely different words now",
    )
    assert reconciled is None


def test_split_script_into_chunks_uses_reconciled_timing() -> None:
    slots = [_slot("a", 0, 3.0)]
    timing = [
        {"text": "one", "start_s": 0.1, "end_s": 0.4},
        {"text": "two", "start_s": 0.9, "end_s": 1.2},
        {"text": "three", "start_s": 1.8, "end_s": 2.1},
    ]
    reconciled = reconcile_word_timing_override(timing, "one two three", "one too three")
    assert reconciled is not None
    chunks_by_slot = split_script_into_chunks(
        "",
        slots,
        slot_overrides={"a": "one too three"},
        word_timing_overrides={"a": reconciled},
    )
    words = [word for chunk in chunks_by_slot["a"] for word in chunk.words]
    assert words[1].text == "too"
    assert words[1].start_s == 0.9


def test_split_script_into_chunks_honors_explicit_empty_override() -> None:
    slots = [_slot("a", 0, 3.0), _slot("b", 1, 2.0)]
    chunks_by_slot = split_script_into_chunks(
        "hello world again",
        slots,
        slot_overrides={"a": ""},
    )
    assert chunks_by_slot["a"] == []
    assert sum(len(chunk.words) for chunk in chunks_by_slot["b"]) == 3


def test_split_script_into_chunks_falls_back_when_timing_override_is_stale() -> None:
    slots = [_slot("a", 0, 3.0)]
    timing = [
        {"text": "old", "start_s": 0.1, "end_s": 0.4},
        {"text": "text", "start_s": 0.9, "end_s": 1.2},
    ]
    chunks_by_slot = split_script_into_chunks(
        "",
        slots,
        slot_overrides={"a": "new edited text"},
        word_timing_overrides={"a": timing},
    )
    words = [word for chunk in chunks_by_slot["a"] for word in chunk.words]
    assert words[0].start_s == 0.0


def test_transcribed_script_in_window_filters_outside_music_block() -> None:
    words = [
        CaptionWord(text="before", start_s=1.0, end_s=1.2),
        CaptionWord(text="inside", start_s=10.5, end_s=10.8),
        CaptionWord(text="after", start_s=20.5, end_s=20.8),
    ]
    script = transcribed_script_in_window(words, music_start_s=10.0, music_end_s=15.0)
    assert script == "inside"


def test_distribute_script_to_slot_overrides_matches_reading_speed_budgets() -> None:
    slots = [_slot("a", 0, 3.0), _slot("b", 1, 2.0)]
    script = " ".join(f"word{i}" for i in range(25))
    overrides = distribute_script_to_slot_overrides(script, slots, words_per_second=5.0)
    assert overrides["a"] == " ".join(f"word{i}" for i in range(15))
    assert overrides["b"] == " ".join(f"word{i}" for i in range(15, 25))


def test_distribute_script_to_slot_overrides_does_not_drop_overflow_words() -> None:
    # Budgets (a=15, b=10) sum to 25, but the script has 60 words. Every word
    # must still land somewhere instead of being truncated at the budget sum.
    slots = [_slot("a", 0, 3.0), _slot("b", 1, 2.0)]
    script = " ".join(f"word{i}" for i in range(60))
    overrides = distribute_script_to_slot_overrides(script, slots, words_per_second=5.0)
    total_words = sum(len(text.split()) for text in overrides.values())
    assert total_words == 60
    assert overrides["a"].split()[0] == "word0"
    assert overrides["b"].split()[-1] == "word59"


def test_distribute_script_with_timing_preserves_asr_times_on_auto_allocate() -> None:
    slots = [_slot("a", 0, 3.0), _slot("b", 1, 2.0)]
    script = "hello hook middle clip tail"
    word_timing = {
        "a": [
            {"text": "hello", "start_s": 0.1, "end_s": 0.4},
            {"text": "hook", "start_s": 0.9, "end_s": 1.2},
        ],
        "b": [
            {"text": "middle", "start_s": 0.2, "end_s": 0.5},
            {"text": "clip", "start_s": 0.8, "end_s": 1.1},
            {"text": "tail", "start_s": 1.5, "end_s": 1.8},
        ],
    }
    overrides, timing = distribute_script_with_timing_to_slots(
        script,
        slots,
        words_per_second=5.0,
        word_timing_overrides=word_timing,
    )
    assert "hello" in overrides["a"]
    assert "tail" in overrides["b"]
    assert timing["a"][0]["start_s"] == 0.1
    assert timing["a"][2]["start_s"] == 2.2
    assert all(float(word["end_s"]) > float(word["start_s"]) for words in timing.values() for word in words)


def test_distribute_script_with_timing_clears_stale_timing_when_script_edited() -> None:
    slots = [_slot("a", 0, 3.0)]
    overrides, timing = distribute_script_with_timing_to_slots(
        "completely different words",
        slots,
        words_per_second=5.0,
        word_timing_overrides={
            "a": [{"text": "old", "start_s": 0.1, "end_s": 0.4}],
        },
    )
    assert overrides["a"] == "completely different words"
    assert timing == {}


def test_distribute_script_with_timing_rebases_reallocated_words_without_zero_duration() -> None:
    """Budget reallocation must not zero ASR timestamps by subtracting slot.out_start_s."""
    slots = [
        StorySlot(
            id="hook",
            order=0,
            label="Hook",
            out_start_s=0.0,
            out_end_s=1.5,
            target_duration_s=1.5,
        ),
        StorySlot(
            id="clip",
            order=1,
            label="Clip",
            out_start_s=1.5,
            out_end_s=6.5,
            target_duration_s=5.0,
        ),
    ]
    script = "one two three four five six seven eight nine ten"
    word_timing = {
        "hook": [
            {"text": "one", "start_s": 0.1, "end_s": 0.3},
            {"text": "two", "start_s": 0.4, "end_s": 0.6},
        ],
        "clip": [
            {"text": "three", "start_s": 0.2, "end_s": 0.4},
            {"text": "four", "start_s": 0.5, "end_s": 0.7},
            {"text": "five", "start_s": 0.8, "end_s": 1.0},
            {"text": "six", "start_s": 1.1, "end_s": 1.3},
            {"text": "seven", "start_s": 1.4, "end_s": 1.6},
            {"text": "eight", "start_s": 1.7, "end_s": 1.9},
            {"text": "nine", "start_s": 2.0, "end_s": 2.2},
            {"text": "ten", "start_s": 2.3, "end_s": 2.5},
        ],
    }
    overrides, timing = distribute_script_with_timing_to_slots(
        script,
        slots,
        words_per_second=5.0,
        word_timing_overrides=word_timing,
    )
    assert sum(len(text.split()) for text in overrides.values()) == 10
    for slot_words in timing.values():
        for word in slot_words:
            assert float(word["end_s"]) > float(word["start_s"])


def test_caption_filter_chain_uses_storyboard_slot_offsets_not_packed_video_time(
    monkeypatch,
) -> None:
    from viral_editor.models import CaptionChunk, CaptionWord, CaptionStyle, SpeedSegment
    from viral_editor.video.filter_builders import build_caption_filter_chain

    monkeypatch.setattr(
        "viral_editor.video.filter_builders.resolve_font_for_ffmpeg",
        lambda family: "C\\:/Windows/Fonts/arial.ttf",
    )
    style = CaptionStyle(fill_color="#FFFFFF", position="bottom", karaoke_enabled=False)
    chunks = {
        "late_slot": [
            CaptionChunk(
                words=[CaptionWord(text="synced", start_s=0.2, end_s=0.8)],
                start_s=0.2,
                end_s=0.8,
            )
        ]
    }
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=2.0,
            speed_factor=1.0,
            source_id="clip_a",
        ),
        SpeedSegment(
            out_start_s=2.0,
            out_end_s=4.0,
            src_start_s=0.0,
            src_end_s=2.0,
            speed_factor=1.0,
            source_id="clip_b",
        ),
    ]
    parts: list[str] = []
    build_caption_filter_chain(
        parts,
        "[bodyv]",
        chunks_by_slot=chunks,
        segments=segments,
        slot_ids=["early_slot", "late_slot"],
        style=style,
        label_prefix="cap",
        width=360,
        height=640,
        slot_offsets={"early_slot": 0.0, "late_slot": 5.0},
    )
    graph = ";".join(parts)
    assert "between(t\\,5.200000\\,5.800000)" in graph


def test_build_caption_filter_chain_emits_timed_drawtext(monkeypatch) -> None:
    from viral_editor.models import CaptionChunk, CaptionWord, CaptionStyle, SpeedSegment
    from viral_editor.video.filter_builders import build_caption_filter_chain

    monkeypatch.setattr(
        "viral_editor.video.filter_builders.resolve_font_for_ffmpeg",
        lambda family: "C\\:/Windows/Fonts/arial.ttf",
    )
    style = CaptionStyle(fill_color="#FFFFFF", position="bottom", outline_enabled=True)
    chunks = {
        "slot0": [
            CaptionChunk(
                words=[
                    CaptionWord(text="hello", start_s=0.0, end_s=0.5),
                    CaptionWord(text="world", start_s=0.5, end_s=1.0),
                ],
                start_s=0.0,
                end_s=1.0,
            )
        ]
    }
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=2.0,
            speed_factor=1.0,
            source_id="clip_a",
        )
    ]
    parts: list[str] = []
    build_caption_filter_chain(
        parts,
        "[slot0norm]",
        chunks_by_slot=chunks,
        segments=segments,
        slot_ids=["slot0"],
        style=style,
        label_prefix="cap",
        width=360,
        height=640,
    )
    graph = ";".join(parts)
    assert "drawtext" in graph
    assert "enable='between(t\\," in graph
    assert "hello world" in graph or "hello\\\\ world" in graph or "hello world" in graph.replace("\\", "")


def test_build_caption_filter_chain_wraps_long_phrase_to_two_lines() -> None:
    from viral_editor.models import CaptionChunk, CaptionWord, CaptionStyle, SpeedSegment
    from viral_editor.utils.fonts import resolve_font_path
    from viral_editor.video.filter_builders import build_caption_filter_chain

    if resolve_font_path("Montserrat Black") is None:
        pytest.skip("No font available for layout test")

    style = CaptionStyle(fill_color="#FFFFFF", position="bottom", size_scale=1.6)
    chunk_words = [
        CaptionWord(text=w, start_s=i * 0.25, end_s=(i + 1) * 0.25)
        for i, w in enumerate(["this", "is", "a", "very", "long", "caption"])
    ]
    chunks = {
        "slot0": [
            CaptionChunk(words=chunk_words, start_s=0.0, end_s=1.5),
        ]
    }
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=2.0,
            speed_factor=1.0,
            source_id="clip_a",
        )
    ]
    parts: list[str] = []
    build_caption_filter_chain(
        parts,
        "[slot0norm]",
        chunks_by_slot=chunks,
        segments=segments,
        slot_ids=["slot0"],
        style=style,
        label_prefix="cap",
        width=360,
        height=640,
    )
    graph = ";".join(parts)
    assert "cap0l0" in graph
    assert "cap0l1" in graph
    assert "fix_bounds=1" in graph


def test_build_caption_filter_chain_karaoke_uses_per_line_offsets() -> None:
    from viral_editor.models import CaptionChunk, CaptionWord, CaptionStyle, SpeedSegment
    from viral_editor.utils.fonts import resolve_font_path
    from viral_editor.utils.text_metrics import layout_caption_chunk
    from viral_editor.video.filter_builders import (
        _max_caption_width_px,
        build_caption_filter_chain,
    )

    font_path = resolve_font_path("Montserrat Black")
    if font_path is None:
        pytest.skip("No font available for layout test")

    style = CaptionStyle(
        fill_color="#FFFFFF",
        emphasis_color="#FFFF00",
        position="bottom",
        karaoke_enabled=True,
        size_scale=1.6,
    )
    word_texts = ["this", "is", "a", "very", "long", "caption"]
    chunk_words = [
        CaptionWord(text=w, start_s=i * 0.25, end_s=(i + 1) * 0.25)
        for i, w in enumerate(word_texts)
    ]
    layouts, _ = layout_caption_chunk(
        word_texts,
        font_path=font_path,
        base_font_size=46,
        max_width_px=_max_caption_width_px(360, style),
        max_lines=2,
    )
    assert len(layouts) >= 2

    chunks = {"slot0": [CaptionChunk(words=chunk_words, start_s=0.0, end_s=1.5)]}
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=2.0,
            speed_factor=1.0,
            source_id="clip_a",
        )
    ]
    parts: list[str] = []
    build_caption_filter_chain(
        parts,
        "[slot0norm]",
        chunks_by_slot=chunks,
        segments=segments,
        slot_ids=["slot0"],
        style=style,
        label_prefix="cap",
        width=360,
        height=640,
    )
    graph = ";".join(parts)
    line0_width = layouts[0].line_width_px
    assert f":x=(w-{line0_width:.2f})/2:" in graph
    assert f"(w-{line0_width:.2f})/2+" in graph
    assert "fontcolor=0xFFFF00" in graph or "fontcolor=#FFFF00" in graph


def test_captions_overlay_after_spatial_fx_for_steady_text() -> None:
    from viral_editor.models import CaptionChunk, CaptionWord, CaptionStyle, FxEvent, SpeedSegment
    from viral_editor.video.filter_builders import build_composite_filtergraph

    style = CaptionStyle(karaoke_enabled=False)
    chunks = {
        "slot0": [
            CaptionChunk(
                words=[CaptionWord(text="steady", start_s=0.0, end_s=0.5)],
                start_s=0.0,
                end_s=0.5,
            )
        ]
    }
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=2.0,
            speed_factor=1.0,
            source_id="clip_a",
        )
    ]
    fx_events = [
        FxEvent(timestamp_s=0.5, kind="zoom", magnitude=1.1, decay_frames=4),
        FxEvent(timestamp_s=1.0, kind="translate", magnitude=0.8, decay_frames=4, direction=1),
    ]
    graph = build_composite_filtergraph(
        segments,
        ["cut"],
        clip_input_index={"clip_a": 0},
        clip_durations={"clip_a": 10.0},
        caption_chunks_by_slot=chunks,
        caption_style=style,
        slot_ids=["slot0"],
        fx_events=fx_events,
    )
    motion_idx = graph.find("copy[motionv]")
    caption_idx = graph.find("[motionv]")
    cap_drawtext_idx = graph.find("cap0")
    assert motion_idx != -1
    assert cap_drawtext_idx != -1
    assert motion_idx < cap_drawtext_idx
    assert caption_idx < cap_drawtext_idx
    assert graph.endswith("copy[outv]")


def test_hook_title_overlay_after_spatial_fx_for_steady_text(monkeypatch) -> None:
    from viral_editor.models import CaptionStyle, FxEvent, SpeedSegment
    from viral_editor.video.filter_builders import build_composite_filtergraph

    monkeypatch.setattr(
        "viral_editor.video.filter_builders.resolve_font_for_ffmpeg",
        lambda family: "C\\:/Windows/Fonts/arial.ttf",
    )
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.5,
            src_start_s=0.0,
            src_end_s=2.5,
            speed_factor=1.0,
            source_id="clip_a",
        ),
        SpeedSegment(
            out_start_s=2.5,
            out_end_s=5.0,
            src_start_s=0.0,
            src_end_s=2.5,
            speed_factor=1.0,
            source_id="clip_b",
        ),
    ]
    fx_events = [
        FxEvent(timestamp_s=1.0, kind="zoom", magnitude=1.1, decay_frames=4),
    ]
    graph = build_composite_filtergraph(
        segments,
        ["cut", "cut"],
        clip_input_index={"clip_a": 0, "clip_b": 1},
        clip_durations={"clip_a": 10.0, "clip_b": 10.0},
        hook_text="Steady Hook",
        hook_style=CaptionStyle(position="top"),
        segment_roles=["hook_start", "clip"],
        fx_events=fx_events,
    )
    motion_idx = graph.find("copy[motionv]")
    hook_idx = graph.find("Hello hook")
    hook_drawtext_idx = graph.find("Steady Hook")
    assert motion_idx != -1
    assert hook_drawtext_idx != -1
    assert motion_idx < hook_drawtext_idx
    assert "slot0titled" not in graph
    assert "enable='between(t\\,0.000000\\,2.500000)'" in graph
    assert hook_idx == -1


def test_hook_title_emphasis_adds_colored_word_overlays() -> None:
    from viral_editor.models import CaptionStyle, SpeedSegment
    from viral_editor.utils.fonts import resolve_font_path
    from viral_editor.video.filter_builders import build_composite_filtergraph

    font_path = resolve_font_path("Montserrat Black") or resolve_font_path("Arial")
    if font_path is None:
        pytest.skip("No font for emphasis layout test")

    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.5,
            src_start_s=0.0,
            src_end_s=2.5,
            speed_factor=1.0,
            source_id="clip_a",
        ),
    ]
    style = CaptionStyle(
        fill_color="#00FFCC",
        emphasis_color="#FF00AA",
        position="top",
    )
    graph = build_composite_filtergraph(
        segments,
        ["cut"],
        clip_input_index={"clip_a": 0},
        clip_durations={"clip_a": 10.0},
        hook_text="I built this in 30 days",
        hook_style=style,
        hook_emphasis_words=["30", "days"],
        segment_roles=["hook"],
    )
    assert "I built this in 30 days" in graph
    assert "fontcolor=0xFF00AA" in graph
    assert "hooktitlee0w" in graph


def test_single_line_caption_uses_top_line_slot_in_two_line_block() -> None:
    from viral_editor.models import CaptionChunk, CaptionWord, CaptionStyle, SpeedSegment
    from viral_editor.utils.fonts import resolve_font_path
    from viral_editor.video.filter_builders import (
        CAPTION_MAX_LINES,
        _caption_block_y_base_px,
        _caption_line_spacing_px,
        _base_font_size,
        build_caption_filter_chain,
    )

    if resolve_font_path("Montserrat Black") is None:
        pytest.skip("No font available for layout test")

    style = CaptionStyle(fill_color="#FFFFFF", position="bottom", size_scale=1.2)
    short_words = [
        CaptionWord(text="short", start_s=0.0, end_s=0.5),
        CaptionWord(text="line", start_s=0.5, end_s=1.0),
    ]
    long_words = [
        CaptionWord(text=w, start_s=i * 0.2, end_s=(i + 1) * 0.2)
        for i, w in enumerate(["this", "is", "a", "much", "longer", "phrase"])
    ]
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=2.0,
            speed_factor=1.0,
            source_id="clip_a",
        )
    ]
    fontsize = _base_font_size(style, 640)
    line_spacing = _caption_line_spacing_px(fontsize)
    expected_top_y = _caption_block_y_base_px(
        style,
        height=640,
        fontsize=fontsize,
        num_lines=CAPTION_MAX_LINES,
        line_spacing=line_spacing,
    )

    parts: list[str] = []
    build_caption_filter_chain(
        parts,
        "[slot0norm]",
        chunks_by_slot={
            "slot0": [CaptionChunk(words=short_words, start_s=0.0, end_s=1.0)],
        },
        segments=segments,
        slot_ids=["slot0"],
        style=style,
        label_prefix="cap",
        width=360,
        height=640,
    )
    short_graph = ";".join(parts)
    assert f":y={expected_top_y:.2f}" in short_graph

    parts = []
    build_caption_filter_chain(
        parts,
        "[slot0norm]",
        chunks_by_slot={
            "slot0": [CaptionChunk(words=long_words, start_s=0.0, end_s=1.2)],
        },
        segments=segments,
        slot_ids=["slot0"],
        style=style,
        label_prefix="cap",
        width=360,
        height=640,
    )
    long_graph = ";".join(parts)
    assert "cap0l0" in long_graph
    assert "cap0l1" in long_graph
    assert f"cap0l0" in long_graph and f":y={expected_top_y:.2f}" in long_graph.split("cap0l0", 1)[1]
