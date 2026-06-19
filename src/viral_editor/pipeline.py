"""Pipeline orchestrator — wired end-to-end in Phase 7."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from viral_editor.config import ConfigError, JobConfig
from viral_editor.ingest.loader import IngestError, validate_job
from viral_editor.models import write_artifact
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

        for stage in PIPELINE_STAGES[2:]:
            _emit(
                on_event,
                stage,
                "skip",
                message="Not yet implemented (Phases 2–6)",
            )

        logger.warning(
            "Stages after ingest are not yet implemented (Phases 2–6). "
            "Full wiring lands in Phase 7."
        )

        result = PipelineResult(
            config=loaded,
            output_duration_s=ingest.output_duration_s,
            artifacts=artifacts,
            output_path=loaded.output_path if loaded.output_path.exists() else None,
        )
        _emit(on_event, "pipeline", "complete")
        return result

    except (ConfigError, IngestError) as exc:
        _emit(on_event, "pipeline", "error", message=str(exc))
        raise
    except Exception as exc:
        _emit(on_event, "pipeline", "error", message=str(exc))
        raise
