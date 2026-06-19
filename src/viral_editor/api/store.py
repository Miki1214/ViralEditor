"""In-memory job store with SSE subscriber fan-out."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from viral_editor.api.schemas import JobStatus, JobSummary
from viral_editor.config import JobConfig
from viral_editor.pipeline_events import PipelineEvent

JOBS_ROOT = Path("temp/jobs")


@dataclass
class JobRecord:
    id: str
    status: JobStatus
    config: JobConfig
    workspace: Path
    stage: str | None = None
    error: str | None = None
    output_duration_s: float | None = None
    artifacts: list[str] = field(default_factory=list)
    events: list[PipelineEvent] = field(default_factory=list)
    subscribers: list[asyncio.Queue[PipelineEvent | None]] = field(default_factory=list)

    def to_summary(self) -> JobSummary:
        return JobSummary(
            id=self.id,
            status=self.status,
            stage=self.stage,
            hook_text=self.config.hook.text,
            error=self.error,
            output_duration_s=self.output_duration_s,
            artifacts=list(self.artifacts),
            has_output=self.config.output_path.is_file(),
        )


class JobStore:
    """Thread-safe job registry for the local Control Room API."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._loops: dict[str, asyncio.AbstractEventLoop] = {}

    def create(
        self,
        config: JobConfig,
        *,
        workspace: Path,
        job_id: str | None = None,
    ) -> JobRecord:
        resolved_id = job_id or uuid.uuid4().hex
        record = JobRecord(
            id=resolved_id,
            status="queued",
            config=config,
            workspace=workspace.resolve(),
        )
        with self._lock:
            self._jobs[resolved_id] = record
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobSummary]:
        with self._lock:
            records = sorted(
                self._jobs.values(),
                key=lambda job: job.events[0].timestamp if job.events else 0,
                reverse=True,
            )
        return [job.to_summary() for job in records]

    def register_loop(self, job_id: str, loop: asyncio.AbstractEventLoop) -> None:
        self._loops[job_id] = loop

    def subscribe(self, job_id: str) -> asyncio.Queue[PipelineEvent | None]:
        queue: asyncio.Queue[PipelineEvent | None] = asyncio.Queue()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            for past in job.events:
                queue.put_nowait(past)
            job.subscribers.append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[PipelineEvent | None]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if queue in job.subscribers:
                job.subscribers.remove(queue)

    def publish(self, job_id: str, event: PipelineEvent) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.events.append(event)
            if event.action in ("start", "complete", "skip", "error"):
                job.stage = event.stage
            subscribers = list(job.subscribers)

        loop = self._loops.get(job_id)
        for queue in subscribers:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(queue.put_nowait, event)
            else:
                try:
                    queue.put_nowait(event)
                except RuntimeError:
                    pass

    def set_status(self, job_id: str, status: JobStatus) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.status = status

    def set_error(self, job_id: str, message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.status = "failed"
                job.error = message

    def complete(
        self,
        job_id: str,
        *,
        output_duration_s: float | None,
        artifacts: list[str],
        config: JobConfig | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "completed"
            job.output_duration_s = output_duration_s
            job.artifacts = artifacts
            if config is not None:
                job.config = config

    def update_config(self, job_id: str, config: JobConfig) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            job.config = config
            if config.music.start_s is not None and config.music.end_s is not None:
                job.output_duration_s = config.music.end_s - config.music.start_s


def job_workspace(job_id: str) -> Path:
    return (JOBS_ROOT / job_id).resolve()


def save_upload(upload: bytes, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(upload)
    return destination


def write_job_config(config: JobConfig, workspace: Path) -> Path:
    config_path = workspace / "job.json"
    payload = json.loads(config.model_dump_json())
    for key in ("video_path", "audio_path", "output_path"):
        value = getattr(config, key)
        payload[key] = str(value) if value is not None else None
    for clip in payload.get("clips", []):
        clip["path"] = str(clip["path"])
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return config_path
