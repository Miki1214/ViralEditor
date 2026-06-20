"""Pipeline orchestrator — wired end-to-end in Phase 7."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from viral_editor.audio.beat_detector import (
    AudioAnalysisError,
    AudioDspConfig,
    analyze_audio_with_envelope,
    save_beat_features,
    save_chroma,
    save_onset_envelope,
    save_scope_lanes,
)
from viral_editor.audio.block_planner import selected_block, trim_timeline_to_window
from viral_editor.audio.loop_planner import suggest_music_blocks_advanced
from viral_editor.audio.structure import analyze_structure
from viral_editor.config import ConfigError, JobConfig
from viral_editor.ingest.loader import IngestError, validate_job
from viral_editor.models import MusicStructurePlan, write_artifact, write_artifact_list
from viral_editor.pipeline_events import PipelineEvent, StageAction
from viral_editor.utils.logging import get_logger, log_stage
from viral_editor.video.clip_reel import build_reel, hook_clip_for_teaser
from viral_editor.video.speed_ramp import (
    plan_speed_options,
    trim_beat_features_to_window,
    trim_envelope_to_window,
)
from viral_editor.video.spatial_fx import plan_spatial_fx
from viral_editor.video.teaser import build_teaser_spec, teaser_body_output_duration

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
    status: str = "completed"


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
                "Job loaded — clips=%d, audio=%s, output=%s",
                len(loaded.effective_clips()),
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
        scope_lanes_path = save_scope_lanes(
            analysis.scope_lanes,
            work_temp / "scope_lanes.npz",
        )
        artifacts.append(scope_lanes_path.name)

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

        is_draft = not loaded.effective_clips()
        if is_draft:
            from viral_editor.api.storyboard import persist_storyboard_for_job

            persist_storyboard_for_job(loaded, work_temp, sections=sections)
            for stage in PIPELINE_STAGES[3:]:
                _emit(
                    on_event,
                    stage,
                    "skip",
                    message="Awaiting slot clip assignment",
                )
            result = PipelineResult(
                config=loaded,
                output_duration_s=output_duration_s,
                artifacts=artifacts,
                output_path=None,
                status="draft",
            )
            _emit(on_event, "pipeline", "complete")
            return result

        if loaded.music.start_s is not None and loaded.music.end_s is not None:
            ramp_timeline = trim_timeline_to_window(
                analysis.timeline,
                start_s=loaded.music.start_s,
                end_s=loaded.music.end_s,
            )
            ramp_envelope = trim_envelope_to_window(
                analysis.onset_envelope,
                start_s=loaded.music.start_s,
                end_s=loaded.music.end_s,
            )
            ramp_features = (
                trim_beat_features_to_window(
                    analysis.beat_features,
                    start_s=loaded.music.start_s,
                    end_s=loaded.music.end_s,
                )
                if analysis.beat_features is not None
                else None
            )
            ramp_sections = [
                section.model_copy(
                    update={
                        "start_s": max(0.0, section.start_s - loaded.music.start_s),
                        "end_s": min(
                            output_duration_s,
                            section.end_s - loaded.music.start_s,
                        ),
                    }
                )
                for section in sections
                if section.end_s > loaded.music.start_s and section.start_s < loaded.music.end_s
            ]
            logger.info(
                "Music window %.2f–%.2fs (%.2fs output)",
                loaded.music.start_s,
                loaded.music.end_s,
                output_duration_s,
            )
        else:
            ramp_timeline = analysis.timeline
            ramp_envelope = analysis.onset_envelope
            ramp_features = analysis.beat_features
            ramp_sections = sections

        hook = hook_clip_for_teaser(loaded.clips) if loaded.clips else None
        teaser_spec = build_teaser_spec(
            ingest.video,
            loaded.teaser,
            hook_clip=hook,
            hook_media=ingest.clip_media.get(hook.id) if hook is not None else None,
        )
        body_output_duration_s = teaser_body_output_duration(
            output_duration_s,
            teaser_spec,
        )

        source_clips = loaded.clips if loaded.clips else loaded.effective_clips()
        clip_reel = build_reel(
            [clip for clip in source_clips if clip.included],
            ingest.clip_media,
            body_output_duration_s=body_output_duration_s,
            speed_config=loaded.speed_ramp,
        )
        reel_path = write_artifact(clip_reel, "clip_reel", work_temp)
        artifacts.append(reel_path.name)

        _emit(on_event, "speed_ramp", "start")
        speed_options = plan_speed_options(
            ramp_timeline,
            ramp_envelope,
            ingest.video,
            output_duration_s=body_output_duration_s,
            base_config=loaded.speed_ramp,
            features=ramp_features,
            sections=ramp_sections,
            hop_length=AudioDspConfig().hop_length,
            sr=analysis.timeline.sample_rate,
            output_fps=float(loaded.render.fps),
            reel=clip_reel,
        )
        options_path = write_artifact(speed_options, "speed_ramp_options", work_temp)
        artifacts.append(options_path.name)
        selected_plan = next(
            (
                option.plan
                for option in speed_options.options
                if option.style == speed_options.selected_style
            ),
            speed_options.options[0].plan if speed_options.options else None,
        )
        if selected_plan is None:
            raise RuntimeError("Speed ramp planner produced no options")
        speed_path = write_artifact(selected_plan, "speed_segments", work_temp)
        artifacts.append(speed_path.name)
        if selected_plan.requested_output_duration_s is not None:
            logger.warning(
                "Music window (%.2fs) exceeds source video (%.2fs); "
                "speed-ramp output capped to %.2fs.",
                selected_plan.requested_output_duration_s,
                selected_plan.src_duration_s,
                selected_plan.output_duration_s,
            )
        logger.info(
            "Speed ramp: %d options, style=%s, %d segments, %.2fs output -> %.2fs source (%s)",
            len(speed_options.options),
            speed_options.selected_style,
            len(selected_plan.segments),
            selected_plan.output_duration_s,
            selected_plan.segments[-1].src_end_s if selected_plan.segments else 0.0,
            selected_plan.budget_policy,
        )
        _emit(
            on_event,
            "speed_ramp",
            "complete",
            message=(
                f"options={len(speed_options.options)}, "
                f"style={speed_options.selected_style}, "
                f"segments={len(selected_plan.segments)}, "
                f"body={selected_plan.output_duration_s:.2f}s"
            ),
        )

        _emit(on_event, "teaser", "start")
        teaser_path = write_artifact(teaser_spec, "teaser_spec", work_temp)
        artifacts.append(teaser_path.name)
        fx_events = plan_spatial_fx(
            ramp_timeline,
            ingest.video,
            seed=loaded.seed,
            max_events_per_second=loaded.spatial_fx.max_events_per_second,
        ) if loaded.spatial_fx.enabled else []
        fx_path = write_artifact_list(fx_events, "fx_events", work_temp)
        artifacts.append(fx_path.name)
        logger.info(
            "Teaser: tail %.2f–%.2fs -> %.2fs (%s); %d FX events",
            teaser_spec.src_start_s,
            teaser_spec.src_end_s,
            teaser_spec.out_duration_s,
            teaser_spec.mask,
            len(fx_events),
        )
        _emit(
            on_event,
            "teaser",
            "complete",
            message=f"teaser={teaser_spec.out_duration_s:.2f}s, fx={len(fx_events)}",
        )

        total_output_duration_s = teaser_spec.out_duration_s + selected_plan.output_duration_s

        for stage in PIPELINE_STAGES[5:]:
            _emit(
                on_event,
                stage,
                "skip",
                message="Not yet implemented (Phases 4–6)",
            )

        logger.warning(
            "Stages after teaser are not yet implemented (Phases 5–6). "
            "Full wiring lands in Phase 7."
        )

        result = PipelineResult(
            config=loaded,
            output_duration_s=total_output_duration_s,
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
