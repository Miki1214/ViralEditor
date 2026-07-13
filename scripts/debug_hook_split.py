#!/usr/bin/env python3
"""Print hook segment debug table and optionally ffprobe a composite render."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from viral_editor.api.storyboard import (  # noqa: E402
    clip_media_for_storyboard,
    load_storyboard,
    storyboard_segments_debug_payload,
)
from viral_editor.audio.storyboard import storyboard_to_segments  # noqa: E402
from viral_editor.config import JobConfig  # noqa: E402
from viral_editor.utils.ffmpeg import ffmpeg_available, run_ffprobe_json  # noqa: E402
from viral_editor.video.proxy_render import composite_output_duration_s, render_composite  # noqa: E402


def _load_job_config(workspace: Path) -> JobConfig:
    job_json = workspace / "job.json"
    if not job_json.is_file():
        raise FileNotFoundError(f"Missing {job_json}")
    return JobConfig.model_validate_json(job_json.read_text(encoding="utf-8"))


def _print_table(payload: dict[str, object]) -> None:
    summary = payload["summary"]
    print("=== Hook speed summary ===")
    print(json.dumps(summary, indent=2))
    print("\n=== Per-slot segments ===")
    print(f"{'role':<12} {'src':>18} {'target':>8} {'speed':>8} {'label':>8}")
    print("-" * 60)
    for row in payload["slots"]:
        src = f"{row['src_start_s']:.2f}→{row['src_end_s']:.2f}"
        label = row["unified_label_speed"]
        label_s = f"{label:.2f}×" if label is not None else "—"
        delta = ""
        if label is not None:
            diff = abs(float(label) - float(row["speed_factor"]))
            if diff > 0.02:
                delta = f"  ⚠ Δ={diff:.3f}"
        print(
            f"{row['role']:<12} {src:>18} "
            f"{row['target_duration_s']:>7.2f}s "
            f"{row['speed_factor']:>7.2f}× "
            f"{label_s:>8}{delta}"
        )


def _render_and_probe(
    workspace: Path,
    config: JobConfig,
    storyboard,
    clip_media,
    out_path: Path,
) -> None:
    if not ffmpeg_available():
        print("\nffmpeg/ffprobe not available — skipping render probe")
        return

    segments, roles, slot_ids = storyboard_to_segments(storyboard, clip_media)
    if not segments:
        print("\nNo segments to render")
        return

    clips_by_id = {clip.id: clip for clip in config.clips}
    clip_paths = {
        clip_id: clips_by_id[clip_id].path
        for clip_id in {segment.source_id for segment in segments if segment.source_id}
        if clip_id in clips_by_id and clips_by_id[clip_id].path.is_file()
    }
    missing = {segment.source_id for segment in segments if segment.source_id} - set(clip_paths)
    if missing:
        print(f"\nMissing clip files for render: {', '.join(sorted(missing))}")
        return

    slots_by_id = {slot.id: slot for slot in storyboard.slots}
    ordered_slots = [slots_by_id[sid] for sid in slot_ids]
    transitions = [slot.transition_in for slot in ordered_slots]
    clip_durations = {clip_id: info.duration_s for clip_id, info in clip_media.items()}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    render_composite(
        config.audio_path,
        segments,
        transitions,
        clip_paths=clip_paths,
        clip_durations=clip_durations,
        music_start_s=config.music.start_s,
        music_end_s=config.music.end_s,
        out_path=out_path,
        temp_dir=workspace / "temp",
        segment_roles=roles,
        hook_start_mask=(
            config.teaser.mask
            if config.teaser.enabled and config.teaser.mask != "none"
            else None
        ),
        fx_seed=config.seed,
        fx_intensity=config.spatial_fx.intensity,
    )

    expected = composite_output_duration_s(segments, transitions=transitions)
    probed = float(
        run_ffprobe_json(["-show_entries", "format=duration", str(out_path)])["format"]["duration"]
    )
    print(f"\n=== Render probe ===")
    print(f"output: {out_path}")
    print(f"expected duration: {expected:.3f}s")
    print(f"probed duration:   {probed:.3f}s")
    print(f"delta:             {abs(probed - expected):.3f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug hook crop / speed contract for a job")
    parser.add_argument(
        "job_id",
        nargs="?",
        help="Job id under temp/jobs/ (optional if --synthetic)",
    )
    parser.add_argument(
        "--jobs-root",
        type=Path,
        default=ROOT / "temp" / "jobs",
        help="Root directory containing job workspaces",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Render composite preview and ffprobe output duration",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path for --render (default: job temp/previews/debug_composite.mp4)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON payload only",
    )
    args = parser.parse_args()

    if args.job_id is None:
        parser.error("job_id is required")

    workspace = args.jobs_root / args.job_id
    temp_dir = workspace / "temp"
    storyboard = load_storyboard(temp_dir)
    if storyboard is None:
        print(f"No storyboard at {temp_dir / 'storyboard.json'}", file=sys.stderr)
        return 1

    config = _load_job_config(workspace)
    clip_media = clip_media_for_storyboard(config, storyboard)
    payload = storyboard_segments_debug_payload(storyboard, clip_media)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_table(payload)

    if args.render:
        out = args.out or (temp_dir / "previews" / "debug_composite.mp4")
        _render_and_probe(workspace, config, storyboard, clip_media, out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
