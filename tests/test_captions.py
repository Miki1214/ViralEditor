"""Tests for caption splitting and reading-speed presets."""

from __future__ import annotations

from viral_editor.audio.captions import (
    WPS_PRESETS,
    suggested_word_count,
    split_script_into_chunks,
)
from viral_editor.models import StorySlot


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
