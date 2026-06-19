"""Job API routes."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from viral_editor.api.runner import build_job_config, start_job
from viral_editor.api.schemas import (
    JobCreatedResponse,
    JobDetail,
    JobSummary,
    PipelineStagesResponse,
    StageInfo,
)
from viral_editor.api.store import JobStore, job_workspace, save_upload
from viral_editor.config import ConfigError
from viral_editor.pipeline import PIPELINE_STAGES

router = APIRouter(prefix="/jobs", tags=["jobs"])

STAGE_LABELS = {
    "pipeline": "Pipeline",
    "config": "Config",
    "ingest": "Ingest",
    "audio": "Audio DSP",
    "speed_ramp": "Speed ramp",
    "teaser": "Teaser",
    "title": "Title",
    "render": "Render",
    "job": "Job",
}


def _store(request: Request) -> JobStore:
    return request.app.state.job_store


@router.get("/stages", response_model=PipelineStagesResponse)
def list_stages() -> PipelineStagesResponse:
    stages = [
        StageInfo(id=stage, label=STAGE_LABELS.get(stage, stage.replace("_", " ").title()))
        for stage in ("pipeline", *PIPELINE_STAGES)
    ]
    return PipelineStagesResponse(stages=stages)


@router.get("", response_model=list[JobSummary])
def list_jobs(request: Request) -> list[JobSummary]:
    return _store(request).list_jobs()


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: str, request: Request) -> JobDetail:
    job = _store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    summary = job.to_summary()
    return JobDetail(**summary.model_dump(), config=job.config)


@router.post("", response_model=JobCreatedResponse, status_code=201)
async def create_job(
    request: Request,
    video: UploadFile = File(...),
    audio: UploadFile = File(...),
    hook_text: str = Form(...),
    emphasis_words: str = Form(""),
    fill_color: str = Form("#FFFFFF"),
    emphasis_color: str = Form("#FFD700"),
    font_family: str = Form("Montserrat Black"),
    safe_padding_pct: int = Form(10),
    seed: int = Form(42),
    verbose: bool = Form(False),
) -> JobCreatedResponse:
    store = _store(request)

    video_bytes = await video.read()
    audio_bytes = await audio.read()
    if not video_bytes:
        raise HTTPException(status_code=400, detail="Video file is empty")
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    video_name = Path(video.filename or "video.mp4").name
    audio_name = Path(audio.filename or "audio.mp3").name

    job_id = uuid.uuid4().hex
    workspace = job_workspace(job_id)
    workspace.mkdir(parents=True, exist_ok=True)

    save_upload(video_bytes, workspace / "input" / video_name)
    save_upload(audio_bytes, workspace / "input" / audio_name)

    try:
        config = build_job_config(
            workspace=workspace,
            hook_text=hook_text,
            emphasis_words=[w.strip() for w in emphasis_words.split(",") if w.strip()],
            video_filename=video_name,
            audio_filename=audio_name,
            fill_color=fill_color,
            emphasis_color=emphasis_color,
            font_family=font_family,
            safe_padding_pct=safe_padding_pct,
            seed=seed,
        )
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = store.create(config, workspace=workspace, job_id=job_id)
    start_job(store, job.id, verbose=verbose)
    return JobCreatedResponse(id=job.id, status=job.status)


@router.get("/{job_id}/events")
async def stream_job_events(job_id: str, request: Request) -> StreamingResponse:
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    loop = asyncio.get_running_loop()
    store.register_loop(job_id, loop)

    try:
        queue = store.subscribe(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                payload = json.dumps(event.model_dump(mode="json"))
                yield f"data: {payload}\n\n"
                if event.stage == "pipeline" and event.action in ("complete", "error"):
                    break
                job_ref = store.get(job_id)
                if job_ref is not None and job_ref.status in ("completed", "failed"):
                    if event.stage != "pipeline":
                        continue
        finally:
            store.unsubscribe(job_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/artifacts/{name}")
def get_artifact(job_id: str, name: str, request: Request) -> FileResponse:
    job = _store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not name.endswith(".json"):
        name = f"{name}.json"
    artifact_path = (job.workspace / "temp" / name).resolve()
    temp_root = (job.workspace / "temp").resolve()
    if not str(artifact_path).startswith(str(temp_root)):
        raise HTTPException(status_code=400, detail="Invalid artifact name")
    if not artifact_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(artifact_path, media_type="application/json")


@router.get("/{job_id}/output")
def get_output(job_id: str, request: Request) -> FileResponse:
    job = _store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    output_path = job.config.output_path
    if not output_path.is_file():
        raise HTTPException(status_code=404, detail="Output not ready")
    return FileResponse(output_path, media_type="video/mp4", filename="result.mp4")
