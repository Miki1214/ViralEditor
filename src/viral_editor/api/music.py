"""Load analysis artifacts and refresh music block selection."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from viral_editor.audio.block_planner import apply_block_selection, selected_block, suggest_music_blocks
from viral_editor.audio.features import BeatSyncFeatures, load_features
from viral_editor.audio.loop_planner import (
    build_block_catalog,
    is_phrase_aligned_plan,
    list_target_loop_qualities,
    loop_qualities_from_plans,
    suggest_music_blocks_advanced,
)
from viral_editor.audio.structure import analyze_structure
from viral_editor.config import JobConfig
from viral_editor.models import (
    AudioTimeline,
    MusicBlock,
    MusicBlockCatalog,
    MusicBlockPlan,
    MusicStructurePlan,
    TargetLoopQuality,
    read_artifact,
    write_artifact,
)


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


def load_scope_lanes(temp_dir: Path) -> dict[str, np.ndarray] | None:
    from viral_editor.audio.beat_detector import load_scope_lanes as _load_scope_lanes

    return _load_scope_lanes(temp_dir / "scope_lanes.npz")


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


def load_music_block_catalog(temp_dir: Path) -> MusicBlockCatalog | None:
    path = temp_dir / "music_block_catalog.json"
    if not path.is_file():
        return None
    return read_artifact(MusicBlockCatalog, path)


def collect_all_blocks_from_catalog(
    catalog: MusicBlockCatalog | None,
) -> list[MusicBlock]:
    """Flatten phrase-aligned catalog plans into tagged blocks for client-side filtering."""
    if catalog is None:
        return []

    from viral_editor.audio.storyboard import _recommended_slot_count

    all_blocks: list[MusicBlock] = []
    for key, plan in catalog.plans.items():
        if plan.use_full_track or plan.target_match_failed:
            continue
        preset_s = float(key)
        for block in plan.blocks:
            slot_count = (
                block.expected_slot_count
                if block.expected_slot_count is not None
                else _recommended_slot_count(block.duration_s)
            )
            all_blocks.append(
                block.model_copy(
                    update={
                        "preset_target_duration_s": preset_s,
                        "expected_slot_count": slot_count,
                    }
                )
            )
    all_blocks.sort(key=lambda block: (block.preset_target_duration_s or 0, -block.loop_quality))
    return all_blocks


def _catalog_key(target_duration_s: float) -> str:
    return str(int(round(target_duration_s)))


def _sections_for_planner(
    temp_dir: Path,
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
) -> list:
    structure = load_music_structure(temp_dir)
    if structure is not None:
        return structure.sections
    return analyze_structure(
        features,
        transients=timeline.transients,
        duration_s=timeline.audio_duration_seconds,
    )


def persist_music_block_catalog(
    temp_dir: Path,
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list,
    *,
    scope_lanes: dict[str, np.ndarray] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> MusicBlockCatalog:
    """Build and persist precomputed plans for all preset target lengths."""
    catalog = build_block_catalog(
        timeline,
        features,
        sections,
        scope_lanes=scope_lanes,
        on_progress=on_progress,
    )
    write_artifact(catalog, "music_block_catalog", temp_dir)
    return catalog


def ensure_music_block_catalog(
    temp_dir: Path,
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list,
    *,
    scope_lanes: dict[str, np.ndarray] | None = None,
) -> MusicBlockCatalog:
    catalog = load_music_block_catalog(temp_dir)
    if catalog is not None:
        return catalog
    return persist_music_block_catalog(
        temp_dir,
        timeline,
        features,
        sections,
        scope_lanes=scope_lanes,
    )


def plan_from_catalog(
    catalog: MusicBlockCatalog,
    target_duration_s: float,
) -> MusicBlockPlan | None:
    return catalog.plans.get(_catalog_key(target_duration_s))


def target_loop_qualities_from_artifacts(
    temp_dir: Path,
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
) -> list[TargetLoopQuality]:
    """Phrase-loop quality scores for preset chips (independent of cached catalog)."""
    sections = _sections_for_planner(temp_dir, timeline, features)
    return list_target_loop_qualities(
        timeline,
        features,
        sections,
        scope_lanes=load_scope_lanes(temp_dir),
    )


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
        sections = _sections_for_planner(temp_dir, timeline, features)
        return suggest_music_blocks_advanced(
            timeline,
            features,
            sections,
            target_duration_s=target_duration_s,
            selected_block_id=selected_block_id,
            scope_lanes=load_scope_lanes(temp_dir),
        )

    return suggest_music_blocks(
        timeline,
        envelope,
        chroma=load_chroma(temp_dir),
        target_duration_s=target_duration_s,
        selected_block_id=selected_block_id,
        scope_lanes=load_scope_lanes(temp_dir),
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
    features = load_beat_features(temp_dir)
    scope_lanes = load_scope_lanes(temp_dir)

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
        music.selected_block_id = None
        plan: MusicBlockPlan | None = None
        catalog: MusicBlockCatalog | None = None
        if features is not None and not music.use_full_track:
            catalog = load_music_block_catalog(temp_dir)
            if catalog is None:
                sections = _sections_for_planner(temp_dir, timeline, features)
                catalog = persist_music_block_catalog(
                    temp_dir,
                    timeline,
                    features,
                    sections,
                    scope_lanes=scope_lanes,
                )
            plan = plan_from_catalog(catalog, music.target_duration_s)
            track_longer_than_target = timeline.audio_duration_seconds > music.target_duration_s
            if track_longer_than_target and (
                plan is None or not is_phrase_aligned_plan(plan)
            ):
                fresh = suggest_blocks_from_artifacts(
                    temp_dir,
                    timeline,
                    envelope,
                    target_duration_s=music.target_duration_s,
                    selected_block_id=None,
                )
                if is_phrase_aligned_plan(fresh):
                    plan = fresh
                    updated_plans = dict(catalog.plans)
                    updated_plans[_catalog_key(music.target_duration_s)] = fresh
                    catalog = catalog.model_copy(
                        update={
                            "plans": updated_plans,
                            "loop_qualities": loop_qualities_from_plans(updated_plans),
                        },
                    )
                    write_artifact(catalog, "music_block_catalog", temp_dir)
                elif plan is None:
                    plan = fresh
        if plan is None:
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
