"""Background pipeline execution for API jobs."""

from __future__ import annotations

import threading
from pathlib import Path

from viral_editor.api.store import JobStore, write_job_config
from viral_editor.audio.beat_detector import AudioAnalysisError
from viral_editor.config import ConfigError, JobConfig, MusicSelectionConfig, StyleConfig, TitleConfig
from viral_editor.ingest.loader import IngestError
from viral_editor.models import ClipInput
from viral_editor.pipeline import run_pipeline
from viral_editor.pipeline_events import PipelineEvent
from viral_editor.utils.ffmpeg import ensure_ffmpeg
from viral_editor.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


def _on_event_factory(store: JobStore, job_id: str):
    def on_event(event: PipelineEvent) -> None:
        store.publish(job_id, event)

    return on_event


def start_job(
    store: JobStore,
    job_id: str,
    *,
    verbose: bool = False,
) -> None:
    """Run a queued job on a background thread."""

    def _run() -> None:
        configure_logging(verbose=verbose)
        job = store.get(job_id)
        if job is None:
            return

        store.set_status(job_id, "running")
        store.publish(job_id, PipelineEvent.now("job", "start", message=job_id))

        try:
            ensure_ffmpeg()
            write_job_config(job.config, job.workspace)
            result = run_pipeline(
                cfg=job.config,
                temp_dir=job.workspace / "temp",
                verbose=verbose,
                keep_temp=True,
                on_event=_on_event_factory(store, job_id),
            )
            store.complete(
                job_id,
                output_duration_s=result.output_duration_s,
                artifacts=result.artifacts,
                config=result.config,
            )
        except (ConfigError, IngestError, AudioAnalysisError) as exc:
            logger.error("Job %s failed: %s", job_id, exc)
            store.set_error(job_id, str(exc))
            store.publish(job_id, PipelineEvent.now("pipeline", "error", message=str(exc)))
        except EnvironmentError as exc:
            logger.error("Job %s environment error: %s", job_id, exc)
            store.set_error(job_id, str(exc))
            store.publish(job_id, PipelineEvent.now("pipeline", "error", message=str(exc)))
        except Exception as exc:
            logger.exception("Job %s failed unexpectedly", job_id)
            store.set_error(job_id, str(exc))
            store.publish(job_id, PipelineEvent.now("pipeline", "error", message=str(exc)))

    thread = threading.Thread(target=_run, name=f"job-{job_id[:8]}", daemon=True)
    thread.start()


def build_job_config(
    *,
    workspace: Path,
    hook_text: str,
    emphasis_words: list[str],
    audio_filename: str,
    fill_color: str = "#FFFFFF",
    emphasis_color: str = "#FFD700",
    font_family: str = "Montserrat Black",
    safe_padding_pct: int = 10,
    seed: int = 42,
    target_duration_s: float = 30.0,
    use_full_track: bool = False,
    selected_block_id: str | None = None,
    music_start_s: float | None = None,
    music_end_s: float | None = None,
    video_filename: str | None = None,
    clips: list[ClipInput] | None = None,
) -> JobConfig:
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    common = dict(
        audio_path=(input_dir / audio_filename).resolve(),
        output_path=(output_dir / "result.mp4").resolve(),
        seed=seed,
        hook=TitleConfig(text=hook_text, emphasis_words=emphasis_words),
        style=StyleConfig(
            font_family=font_family,
            fill_color=fill_color,
            emphasis_color=emphasis_color,
            safe_padding_pct=safe_padding_pct,
        ),
        music=MusicSelectionConfig(
            target_duration_s=target_duration_s,
            use_full_track=use_full_track,
            selected_block_id=selected_block_id,
            start_s=music_start_s,
            end_s=music_end_s,
        ),
    )
    if clips:
        return JobConfig(clips=clips, **common)
    if video_filename is None:
        raise ValueError("Provide video_filename or clips")
    return JobConfig(
        video_path=(input_dir / video_filename).resolve(),
        **common,
    )
