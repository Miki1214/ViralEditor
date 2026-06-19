"""Load analysis artifacts and refresh music block selection."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from viral_editor.audio.block_planner import apply_block_selection, selected_block, suggest_music_blocks
from viral_editor.audio.features import BeatSyncFeatures, load_features
from viral_editor.audio.loop_planner import suggest_music_blocks_advanced
from viral_editor.audio.structure import analyze_structure
from viral_editor.config import JobConfig
from viral_editor.models import AudioTimeline, MusicBlockPlan, MusicStructurePlan, write_artifact


def load_audio_timeline(temp_dir: Path) -> AudioTimeline:
    path = temp_dir / "audio_timeline.json"
    if not path.is_file():
        raise FileNotFoundError("audio_timeline.json not found — run audio analysis first")
    return AudioTimeline.model_validate_json(path.read_text(encoding="utf-8"))


def load_onset_envelope(temp_dir: Path) -> np.ndarray:
    path = temp_dir / "onset_envelope.npy"
    if not path.is_file():
        raise FileNotFoundError("onset_envelope.npy not found — run audio analysis first")
    return np.load(path)


def load_chroma(temp_dir: Path) -> np.ndarray | None:
    path = temp_dir / "chroma.npy"
    if not path.is_file():
        return None
    return np.load(path)


def load_beat_features(temp_dir: Path) -> BeatSyncFeatures | None:
    path = temp_dir / "features.npz"
    if not path.is_file():
        return None
    return load_features(path)


def load_music_structure(temp_dir: Path) -> MusicStructurePlan | None:
    path = temp_dir / "music_structure.json"
    if not path.is_file():
        return None
    return MusicStructurePlan.model_validate_json(path.read_text(encoding="utf-8"))


def load_music_blocks(temp_dir: Path) -> MusicBlockPlan:
    path = temp_dir / "music_blocks.json"
    if not path.is_file():
        raise FileNotFoundError("music_blocks.json not found — run audio analysis first")
    return MusicBlockPlan.model_validate_json(path.read_text(encoding="utf-8"))


def suggest_blocks_from_artifacts(
    temp_dir: Path,
    timeline: AudioTimeline,
    envelope: np.ndarray,
    *,
    target_duration_s: float,
    selected_block_id: str | None = None,
) -> MusicBlockPlan:
    """Use beat-sync planner when ``features.npz`` exists, else legacy planner."""
    features = load_beat_features(temp_dir)
    if features is not None:
        structure = load_music_structure(temp_dir)
        sections = (
            structure.sections
            if structure is not None
            else analyze_structure(
                features,
                transients=timeline.transients,
                duration_s=timeline.audio_duration_seconds,
            )
        )
        return suggest_music_blocks_advanced(
            timeline,
            features,
            sections,
            target_duration_s=target_duration_s,
            selected_block_id=selected_block_id,
        )

    return suggest_music_blocks(
        timeline,
        envelope,
        chroma=load_chroma(temp_dir),
        target_duration_s=target_duration_s,
        selected_block_id=selected_block_id,
    )


def refresh_music_selection(
    config: JobConfig,
    temp_dir: Path,
    *,
    target_duration_s: float | None = None,
    selected_block_id: str | None = None,
    use_full_track: bool | None = None,
) -> tuple[JobConfig, MusicBlockPlan]:
    """Re-suggest blocks and sync ``JobConfig.music`` with the chosen window."""
    timeline = load_audio_timeline(temp_dir)
    envelope = load_onset_envelope(temp_dir)

    music = config.music.model_copy(deep=True)
    if target_duration_s is not None:
        music.target_duration_s = target_duration_s
    if use_full_track is not None:
        music.use_full_track = use_full_track
    if selected_block_id is not None:
        music.selected_block_id = selected_block_id

    target_changed = (
        target_duration_s is not None and target_duration_s != config.music.target_duration_s
    )
    full_track_changed = (
        use_full_track is not None and use_full_track != config.music.use_full_track
    )

    if target_changed or full_track_changed:
        # Prior block ids (e.g. block_c or block_full) may not exist in the new plan.
        music.selected_block_id = None
        plan = suggest_blocks_from_artifacts(
            temp_dir,
            timeline,
            envelope,
            target_duration_s=music.target_duration_s,
            selected_block_id=None,
        )
    else:
        try:
            plan = load_music_blocks(temp_dir)
        except FileNotFoundError:
            plan = suggest_blocks_from_artifacts(
                temp_dir,
                timeline,
                envelope,
                target_duration_s=music.target_duration_s,
                selected_block_id=music.selected_block_id,
            )

    if music.use_full_track or plan.use_full_track:
        music.use_full_track = True
        music.start_s = 0.0
        music.end_s = timeline.audio_duration_seconds
        music.selected_block_id = plan.selected_block_id
        plan = plan.model_copy(update={"use_full_track": True, "selected_block_id": music.selected_block_id})
    elif music.selected_block_id:
        if any(block.id == music.selected_block_id for block in plan.blocks):
            plan = apply_block_selection(plan, music.selected_block_id)
            block = selected_block(plan)
            if block is not None:
                music.start_s = block.start_s
                music.end_s = block.end_s
                music.selected_block_id = block.id
        else:
            music.selected_block_id = None
            block = selected_block(plan)
            if block is not None:
                music.start_s = block.start_s
                music.end_s = block.end_s
                music.selected_block_id = block.id
                plan = plan.model_copy(update={"selected_block_id": block.id})
    elif selected_block_id is None and not target_changed and not full_track_changed:
        block = selected_block(plan)
        if block is not None:
            music.start_s = block.start_s
            music.end_s = block.end_s
            music.selected_block_id = block.id
    else:
        block = selected_block(plan)
        if block is not None:
            music.start_s = block.start_s
            music.end_s = block.end_s
            music.selected_block_id = block.id
            plan = plan.model_copy(update={"selected_block_id": block.id})

    write_artifact(plan, "music_blocks", temp_dir)
    return config.model_copy(update={"music": music}), plan
