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
