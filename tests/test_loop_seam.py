"""Tests for render-grade loop seam helpers."""

from __future__ import annotations

from viral_editor.audio.loop_seam import (
    build_loop_audition_filter,
    build_loop_seam_only_filter,
)
from viral_editor.audio.preview import ensure_loop_seam_audio, preview_cache_path


def test_build_loop_audition_filter_uses_equal_power_crossfade() -> None:
    graph = build_loop_audition_filter(10.0, 30.0, crossfade_s=0.04)
    assert "acrossfade" in graph
    assert "c1=tri:c2=tri" in graph
    assert "atrim=start=10.000000:duration=30.000000" in graph


def test_build_loop_seam_only_filter_wraps_tail_to_head() -> None:
    graph = build_loop_seam_only_filter(10.0, 40.0, crossfade_s=0.04)
    assert "acrossfade" in graph
    assert "atrim=start=" in graph
    assert "apad=pad_dur=" in graph


def test_preview_cache_distinguishes_loop_and_seam_only(tmp_path) -> None:
    loop_path = preview_cache_path(tmp_path, start_s=1.0, end_s=10.0, loop_only=False)
    seam_path = preview_cache_path(tmp_path, start_s=1.0, end_s=10.0, loop_only=True)
    assert loop_path != seam_path


def test_ensure_loop_seam_audio_delegates_to_loop_preview(
    tmp_path,
    monkeypatch,
) -> None:
    calls: list[tuple] = []

    def _fake_render(audio_path, output_path, *, start_s, end_s, crossfade_s=0.04):
        calls.append((audio_path, output_path, start_s, end_s))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"wav")
        return output_path

    monkeypatch.setattr(
        "viral_editor.audio.preview.render_loop_preview",
        _fake_render,
    )
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"mp3")
    out = ensure_loop_seam_audio(audio, start_s=5.0, end_s=15.0, temp_dir=tmp_path)
    assert out.is_file()
    assert calls
    assert calls[0][2:4] == (5.0, 15.0)
