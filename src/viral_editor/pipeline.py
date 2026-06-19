"""Pipeline orchestrator — wired end-to-end in Phase 7."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from viral_editor.audio.beat_detector import (
    AudioAnalysisError,
    analyze_audio_with_envelope,
    save_beat_features,
    save_chroma,
    save_onset_envelope,
)
from viral_editor.audio.block_planner import selected_block, trim_timeline_to_window
from viral_editor.audio.loop_planner import suggest_music_blocks_advanced
from viral_editor.audio.structure import analyze_structure
from viral_editor.config import ConfigError, JobConfig
from viral_editor.ingest.loader import IngestError, validate_job
from viral_editor.models import MusicStructurePlan, write_artifact
from viral_editor.pipeline_events import PipelineEvent, StageAction
from viral_editor.utils.logging import get_logger, log_stage

logger = get_logger(__name__)

TEMP_DIR = Path("temp")

PIPELINE_STAGES = (
    "config",
    "ingest",
    "audio",
    "speed_ramp",
    "teaser",
    "title",
    "render",
)


@dataclass
class PipelineResult:
    """Outcome of a pipeline run."""

    config: JobConfig
    output_duration_s: float | None = None
    artifacts: list[str] = field(default_factory=list)
    output_path: Path | None = None


def _emit(
    on_event: Callable[[PipelineEvent], None] | None,
    stage: str,
    action: StageAction,
    *,
    message: str | None = None,
) -> None:
    if action in ("start", "complete", "skip"):
        log_stage(stage, action=action)  # type: ignore[arg-type]
    if on_event is not None:
        on_event(PipelineEvent.now(stage, action, message=message))


def run_pipeline(
    config_path: Path | None = None,
    *,
    cfg: JobConfig | None = None,
    temp_dir: Path | None = None,
    verbose: bool = False,
    keep_temp: bool = False,
    on_event: Callable[[PipelineEvent], None] | None = None,
) -> PipelineResult:
    """Execute the retention video pipeline.

    Provide either ``config_path`` or a pre-validated ``cfg``. Optional
    ``on_event`` receives stage boundaries for API/SSE consumers.
    """
    del verbose, keep_temp  # honored once later stages write temp artifacts

    if (config_path is None) == (cfg is None):
        raise ValueError("Provide exactly one of config_path or cfg")

    work_temp = (temp_dir or TEMP_DIR).resolve()
    artifacts: list[str] = []

    _emit(on_event, "pipeline", "start")

    try:
        _emit(on_event, "config", "start")
        if cfg is None:
            assert config_path is not None
            logger.info("Config file: %s", config_path.resolve())
            loaded = JobConfig.load(config_path)
        else:
            loaded = cfg
            logger.info(
                "Job loaded — video=%s, audio=%s, output=%s",
                loaded.video_path,
                loaded.audio_path,
                loaded.output_path,
            )
        _emit(on_event, "config", "complete")

        _emit(on_event, "ingest", "start")
        ingest = validate_job(loaded)
        artifact_path = write_artifact(ingest, "media_info", work_temp)
        artifacts.append(artifact_path.name)
        logger.info("Wrote %s", artifact_path.resolve())
        logger.info("Output duration: %.2fs (music track)", ingest.output_duration_s)
        _emit(
            on_event,
            "ingest",
            "complete",
            message=f"output_duration_s={ingest.output_duration_s:.2f}",
        )

        _emit(on_event, "audio", "start")
        analysis = analyze_audio_with_envelope(
            loaded.audio_path,
            expected_duration_s=ingest.audio.duration_s,
        )
        timeline_path = write_artifact(analysis.timeline, "audio_timeline", work_temp)
        artifacts.append(timeline_path.name)
        envelope_path = save_onset_envelope(
            analysis.onset_envelope,
            work_temp / "onset_envelope.npy",
        )
        artifacts.append(envelope_path.name)
        chroma_path = save_chroma(
            analysis.chroma,
            work_temp / "chroma.npy",
        )
        artifacts.append(chroma_path.name)
        features_path = save_beat_features(
            analysis.beat_features,
            work_temp / "features.npz",
        )
        artifacts.append(features_path.name)

        sections = analyze_structure(
            analysis.beat_features,
            transients=analysis.timeline.transients,
            duration_s=analysis.timeline.audio_duration_seconds,
        )
        structure_plan = MusicStructurePlan(
            sections=sections,
            key=analysis.beat_features.meta.key,
            beat_engine=analysis.beat_features.meta.engine,
        )
        structure_path = write_artifact(structure_plan, "music_structure", work_temp)
        artifacts.append(structure_path.name)

        logger.info("Wrote %s", timeline_path.resolve())
        drop_count = sum(1 for t in analysis.timeline.transients if t.type == "drop")

        block_plan = suggest_music_blocks_advanced(
            analysis.timeline,
            analysis.beat_features,
            sections,
            target_duration_s=loaded.music.target_duration_s,
            selected_block_id=loaded.music.selected_block_id,
        )

        if loaded.music.start_s is not None and loaded.music.end_s is not None:
            output_duration_s = loaded.music.end_s - loaded.music.start_s
            if loaded.music.selected_block_id:
                block_plan = block_plan.model_copy(
                    update={"selected_block_id": loaded.music.selected_block_id}
                )
        elif block_plan.use_full_track:
            loaded.music.use_full_track = True
            loaded.music.start_s = 0.0
            loaded.music.end_s = analysis.timeline.audio_duration_seconds
            loaded.music.selected_block_id = block_plan.selected_block_id
            output_duration_s = analysis.timeline.audio_duration_seconds
        else:
            block = selected_block(block_plan)
            if block is not None:
                loaded.music.start_s = block.start_s
                loaded.music.end_s = block.end_s
                loaded.music.selected_block_id = block.id
                block_plan = block_plan.model_copy(update={"selected_block_id": block.id})
            output_duration_s = (
                (loaded.music.end_s - loaded.music.start_s)
                if loaded.music.start_s is not None and loaded.music.end_s is not None
                else ingest.output_duration_s
            )

        blocks_path = write_artifact(block_plan, "music_blocks", work_temp)
        artifacts.append(blocks_path.name)
        logger.info("Wrote %s", blocks_path.resolve())

        _emit(
            on_event,
            "audio",
            "complete",
            message=(
                f"bpm={analysis.timeline.global_bpm:.1f}, "
                f"engine={analysis.beat_features.meta.engine}, "
                f"key={analysis.beat_features.meta.key}, "
                f"transients={len(analysis.timeline.transients)}, drops={drop_count}, "
                f"blocks={len(block_plan.blocks)}"
            ),
        )

        if loaded.music.start_s is not None and loaded.music.end_s is not None:
            windowed = trim_timeline_to_window(
                analysis.timeline,
                start_s=loaded.music.start_s,
                end_s=loaded.music.end_s,
            )
            logger.info(
                "Music window %.2f–%.2fs (%.2fs output)",
                loaded.music.start_s,
                loaded.music.end_s,
                output_duration_s,
            )
            del windowed  # used by later phases once speed ramp lands

        for stage in PIPELINE_STAGES[3:]:
            _emit(
                on_event,
                stage,
                "skip",
                message="Not yet implemented (Phases 3–6)",
            )

        logger.warning(
            "Stages after audio are not yet implemented (Phases 3–6). "
            "Full wiring lands in Phase 7."
        )

        result = PipelineResult(
            config=loaded,
            output_duration_s=output_duration_s,
            artifacts=artifacts,
            output_path=loaded.output_path if loaded.output_path.exists() else None,
        )
        _emit(on_event, "pipeline", "complete")
        return result

    except (ConfigError, IngestError, AudioAnalysisError) as exc:
        _emit(on_event, "pipeline", "error", message=str(exc))
        raise
    except Exception as exc:
        _emit(on_event, "pipeline", "error", message=str(exc))
        raise
