"""Job API routes."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from viral_editor.api.music import (
    load_audio_timeline,
    load_beat_features,
    load_music_blocks,
    load_music_structure,
    load_onset_envelope,
    refresh_music_selection,
    suggest_blocks_from_artifacts,
)
from viral_editor.api.runner import build_job_config, start_job
from viral_editor.api.schemas import (
    JobCreatedResponse,
    JobDetail,
    JobSummary,
    MusicSelectionUpdate,
    PipelineStagesResponse,
    SpeedSelectionUpdate,
    StageInfo,
)
from viral_editor.api.speed import (
    compute_speed_options,
    load_speed_ramp_options,
    refresh_speed_selection,
    speed_proxy_cache_key,
)
from viral_editor.api.store import JobStore, job_workspace, save_upload, write_job_config
from viral_editor.audio.preview import ensure_audio_preview
from viral_editor.audio.waveform import build_waveform_payload
from viral_editor.config import ConfigError
from viral_editor.models import SpeedRampOptionSet, WaveformPayload
from viral_editor.pipeline import PIPELINE_STAGES
from viral_editor.utils.ffmpeg import FFmpegError
from viral_editor.video.proxy_render import render_speed_proxy

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
    target_duration_s: float = Form(30.0),
    use_full_track: bool = Form(False),
    selected_block_id: str | None = Form(None),
    music_start_s: float | None = Form(None),
    music_end_s: float | None = Form(None),
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
            target_duration_s=target_duration_s,
            use_full_track=use_full_track,
            selected_block_id=selected_block_id,
            music_start_s=music_start_s,
            music_end_s=music_end_s,
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


@router.get("/{job_id}/audio/waveform", response_model=WaveformPayload)
def get_waveform(job_id: str, request: Request) -> WaveformPayload:
    job = _store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    temp_dir = job.workspace / "temp"
    try:
        timeline = load_audio_timeline(temp_dir)
        envelope = load_onset_envelope(temp_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        block_plan = load_music_blocks(temp_dir)
    except FileNotFoundError:
        block_plan = suggest_blocks_from_artifacts(
            temp_dir,
            timeline,
            envelope,
            target_duration_s=job.config.music.target_duration_s,
            selected_block_id=job.config.music.selected_block_id,
        )

    return build_waveform_payload(
        timeline,
        envelope,
        block_plan,
        structure=load_music_structure(temp_dir),
        features=load_beat_features(temp_dir),
    )


@router.get("/{job_id}/audio/preview")
def get_audio_preview(
    job_id: str,
    request: Request,
    start_s: float = Query(..., ge=0),
    end_s: float = Query(..., gt=0),
    loop_only: bool = Query(False, description="Preview only the loop seam crossfade"),
) -> FileResponse:
    job = _store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if end_s <= start_s:
        raise HTTPException(status_code=400, detail="end_s must be greater than start_s")
    try:
        preview_path = ensure_audio_preview(
            job.config.audio_path,
            start_s=start_s,
            end_s=end_s,
            temp_dir=job.workspace / "temp",
            loop_only=loop_only,
        )
    except (ValueError, FFmpegError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(preview_path, media_type="audio/wav", filename=preview_path.name)


@router.patch("/{job_id}/music-selection", response_model=JobDetail)
def update_music_selection(
    job_id: str,
    payload: MusicSelectionUpdate,
    request: Request,
) -> JobDetail:
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_dir = job.workspace / "temp"
    try:
        updated_config, _plan = refresh_music_selection(
            job.config,
            temp_dir,
            target_duration_s=payload.target_duration_s,
            selected_block_id=payload.selected_block_id,
            use_full_track=payload.use_full_track,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store.update_config(job_id, updated_config)
    write_job_config(updated_config, job.workspace)
    job = store.get(job_id)
    assert job is not None
    return JobDetail(**job.to_summary().model_dump(), config=job.config)


@router.get("/{job_id}/speed-ramp", response_model=SpeedRampOptionSet)
def get_speed_ramp(job_id: str, request: Request) -> SpeedRampOptionSet:
    job = _store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    temp_dir = job.workspace / "temp"
    try:
        return compute_speed_options(job.config, temp_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{job_id}/speed-selection", response_model=SpeedRampOptionSet)
def update_speed_selection(
    job_id: str,
    payload: SpeedSelectionUpdate,
    request: Request,
) -> SpeedRampOptionSet:
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_dir = job.workspace / "temp"
    overrides = payload.model_dump(exclude_none=True, exclude={"style"})
    try:
        updated_config, option_set = refresh_speed_selection(
            job.config,
            temp_dir,
            style=payload.style,
            overrides=overrides or None,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store.update_config(job_id, updated_config)
    write_job_config(updated_config, job.workspace)
    return option_set


@router.get("/{job_id}/speed-ramp/preview")
def get_speed_ramp_preview(
    job_id: str,
    request: Request,
    style: str | None = Query(default=None),
) -> FileResponse:
    job = _store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_dir = job.workspace / "temp"
    try:
        option_set = load_speed_ramp_options(temp_dir) or compute_speed_options(job.config, temp_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    selected_style = style or option_set.selected_style
    option = next((item for item in option_set.options if item.style == selected_style), None)
    if option is None:
        raise HTTPException(status_code=404, detail=f"Speed style {selected_style!r} not found")

    preview_dir = temp_dir / "previews"
    cache_key = speed_proxy_cache_key(
        style=selected_style,
        plan=option.plan,
        video_path=job.config.video_path,
        music_start_s=job.config.music.start_s,
        music_end_s=job.config.music.end_s,
    )
    preview_path = preview_dir / f"{cache_key}.mp4"
    force = request.query_params.get("force") == "1"
    if force and preview_path.is_file():
        preview_path.unlink(missing_ok=True)
    if not preview_path.is_file():
        try:
            render_speed_proxy(
                job.config.video_path,
                job.config.audio_path,
                option.plan,
                music_start_s=job.config.music.start_s,
                music_end_s=job.config.music.end_s,
                out_path=preview_path,
            )
        except (RuntimeError, FFmpegError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileResponse(preview_path, media_type="video/mp4", filename=preview_path.name)
