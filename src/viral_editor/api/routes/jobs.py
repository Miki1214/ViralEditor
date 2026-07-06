"""Job API routes."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from viral_editor.api.music import (
    collect_all_blocks_from_catalog,
    load_audio_timeline,
    load_beat_features,
    target_loop_qualities_from_artifacts,
    load_music_block_catalog,
    load_music_blocks,
    load_music_structure,
    load_onset_envelope,
    load_scope_lanes,
    refresh_music_selection,
    suggest_blocks_from_artifacts,
)
from viral_editor.api.clips import (
    clip_durations_map,
    clip_info_payload,
    load_clip_reel,
    probe_clip_media,
    refresh_clips_selection,
    speed_planning_context,
)
from viral_editor.video.clip_reel import clip_paths_by_id
from viral_editor.api.runner import build_job_config, start_job
from viral_editor.api.render_job import start_final_render
from viral_editor.api.storyboard import (
    apply_storyboard_patch,
    assign_slot_clip,
    clear_slot_clip,
    clip_media_for_storyboard,
    hook_clip_id_for_slot,
    hook_family_assigned_clip_id,
    load_storyboard,
    persist_storyboard,
    refresh_hook_inversion_layout,
    refresh_storyboard_after_music,
    sync_config_clips_from_storyboard,
    sync_teaser_duration_from_layout,
    sync_storyboard_hook_layout,
    teaser_settings_response,
    update_slot_crop,
    update_slot_transform,
    storyboard_segments_debug_payload,
)
from viral_editor.api.schemas import (
    ClipReelResponse,
    ClipsPatchRequest,
    JobCreatedResponse,
    JobDetail,
    EffectsPatchRequest,
    JobSummary,
    MusicSelectionUpdate,
    PipelineStagesResponse,
    SpeedSelectionUpdate,
    SlotCropPatchRequest,
    SlotTransformPatchRequest,
    SpatialCropInput,
    RetentionPlanScoreResponse,
    RetentionSettingsResponse,
    SpatialFxSettingsResponse,
    StageInfo,
    StoryboardPatchRequest,
    StoryboardResponse,
    StoryboardSegmentsDebugResponse,
    StoryboardSegmentsSummary,
    StoryboardSegmentDebugRow,
    StorySlotResponse,
    TeaserSettingsResponse,
)
from viral_editor.api.effects import (
    apply_effects_patch,
    spatial_fx_for_preview,
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
from viral_editor.models import ClipInput, SpeedRampOptionSet, StorySlot, WaveformPayload
from viral_editor.audio.storyboard import (
    assigned_storyboard_slots,
    remap_fx_events_for_composite,
    storyboard_filled_enough,
    storyboard_slots_complete,
    storyboard_to_segments,
)
from viral_editor.pipeline import PIPELINE_STAGES
from viral_editor.utils.ffmpeg import FFmpegError
from viral_editor.video.proxy_render import render_composite, render_speed_proxy

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
    audio: UploadFile = File(...),
    project_name: str = Form(""),
    hook_text: str = Form(...),
    emphasis_words: str = Form(""),
    fill_color: str = Form("#FFFFFF"),
    emphasis_color: str = Form("#FFD700"),
    font_family: str = Form("Montserrat Black"),
    safe_padding_pct: int = Form(10),
    seed: int = Form(42),
    target_duration_s: float = Form(10.0),
    use_full_track: bool = Form(False),
    selected_block_id: str | None = Form(None),
    music_start_s: float | None = Form(None),
    music_end_s: float | None = Form(None),
    clips: str | None = Form(None),
    verbose: bool = Form(False),
    video: list[UploadFile] = File(default=[]),
) -> JobCreatedResponse:
    store = _store(request)

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    parsed_clips: list[dict] = []
    if clips:
        try:
            parsed = json.loads(clips)
            if isinstance(parsed, list):
                parsed_clips = [item for item in parsed if isinstance(item, dict)]
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid clips JSON: {exc}") from exc

    audio_name = Path(audio.filename or "audio.mp3").name
    resolved_project_name = project_name.strip() or Path(audio_name).stem

    job_id = uuid.uuid4().hex
    workspace = job_workspace(job_id)
    workspace.mkdir(parents=True, exist_ok=True)
    input_dir = workspace / "input"

    clip_inputs: list[ClipInput] = []
    for index, upload in enumerate(video or []):
        video_bytes = await upload.read()
        if not video_bytes:
            raise HTTPException(status_code=400, detail=f"Video file {index} is empty")
        default_id = f"clip_{index}"
        meta = parsed_clips[index] if index < len(parsed_clips) else {}
        clip_id = str(meta.get("id", default_id))
        video_name = Path(upload.filename or f"{clip_id}.mp4").name
        save_upload(video_bytes, input_dir / video_name)
        clip_inputs.append(
            ClipInput(
                id=clip_id,
                path=(input_dir / video_name).resolve(),
                order=int(meta.get("order", index)),
                included=bool(meta.get("included", True)),
                role=meta.get("role", "clip"),
                crop_start_s=meta.get("crop_start_s"),
                crop_end_s=meta.get("crop_end_s"),
            )
        )

    save_upload(audio_bytes, input_dir / audio_name)

    try:
        if len(clip_inputs) == 1 and not clips:
            config = build_job_config(
                workspace=workspace,
                project_name=resolved_project_name,
                hook_text=hook_text,
                emphasis_words=[w.strip() for w in emphasis_words.split(",") if w.strip()],
                video_filename=clip_inputs[0].path.name,
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
        elif clip_inputs:
            config = build_job_config(
                workspace=workspace,
                project_name=resolved_project_name,
                hook_text=hook_text,
                emphasis_words=[w.strip() for w in emphasis_words.split(",") if w.strip()],
                audio_filename=audio_name,
                clips=clip_inputs,
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
        else:
            config = build_job_config(
                workspace=workspace,
                project_name=resolved_project_name,
                hook_text=hook_text,
                emphasis_words=[w.strip() for w in emphasis_words.split(",") if w.strip()],
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
    except (ConfigError, ValueError) as exc:
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


@router.post("/{job_id}/render", status_code=202)
def start_job_render(job_id: str, request: Request) -> dict[str, str]:
    """Encode the final 1080p MP4 when all storyboard slots have clips assigned."""
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "running":
        raise HTTPException(status_code=409, detail="Job is already running")

    temp_dir = job.workspace / "temp"
    storyboard = load_storyboard(temp_dir)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not found")
    if not storyboard_slots_complete(storyboard):
        raise HTTPException(
            status_code=400,
            detail="Assign clips to all storyboard slots before rendering",
        )

    start_final_render(store, job_id)
    return {"status": "rendering"}


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

    # Normalize expected_slot_count on any blocks that are missing it.
    # This handles cached music_blocks.json / catalog entries written before this field existed.
    from viral_editor.audio.storyboard import _recommended_slot_count

    if block_plan.blocks:
        updated_blocks = [
            block.model_copy(
                update={
                    "expected_slot_count": (
                        block.expected_slot_count
                        if block.expected_slot_count is not None
                        else _recommended_slot_count(block.duration_s)
                    )
                }
            )
            for block in block_plan.blocks
        ]
        block_plan = block_plan.model_copy(update={"blocks": updated_blocks})

    features = load_beat_features(temp_dir)
    loop_qualities = (
        target_loop_qualities_from_artifacts(temp_dir, timeline, features)
        if features is not None
        else None
    )

    catalog = load_music_block_catalog(temp_dir)
    all_blocks = collect_all_blocks_from_catalog(catalog)

    payload = build_waveform_payload(
        timeline,
        envelope,
        block_plan,
        structure=load_music_structure(temp_dir),
        features=features,
        scope_lanes=load_scope_lanes(temp_dir),
        loop_qualities=loop_qualities,
    )
    return payload.model_copy(update={"all_blocks": all_blocks})


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
    refresh_storyboard_after_music(updated_config, temp_dir)
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


@router.get("/{job_id}/clips", response_model=ClipReelResponse)
def get_clips(job_id: str, request: Request) -> ClipReelResponse:
    job = _store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_dir = job.workspace / "temp"
    clip_media = probe_clip_media(job.config)
    reel = load_clip_reel(temp_dir)

    music_window_s: float | None = None
    target_body_s: float | None = None
    if job.config.music.start_s is not None and job.config.music.end_s is not None:
        music_window_s = job.config.music.end_s - job.config.music.start_s
    elif temp_dir.joinpath("audio_timeline.json").is_file():
        try:
            timeline = load_audio_timeline(temp_dir)
            music_window_s = timeline.audio_duration_seconds
        except FileNotFoundError:
            music_window_s = None

    if music_window_s is not None:
        _, _, target_body_s, _ = speed_planning_context(
            job.config,
            clip_media,
            music_window_s,
        )

    return ClipReelResponse(
        clips=clip_info_payload(job.config, clip_media, reel),
        reel_duration_s=reel.reel_duration_s if reel is not None else 0.0,
        target_body_duration_s=target_body_s,
        entries=[entry.model_dump(mode="json") for entry in reel.entries] if reel else [],
    )


@router.get("/{job_id}/clips/{clip_id}/source")
def get_clip_source(job_id: str, clip_id: str, request: Request) -> FileResponse:
    job = _store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    clip = next((item for item in job.config.clips if item.id == clip_id), None)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    if not clip.path.is_file():
        raise HTTPException(status_code=404, detail="Clip file missing")
    return FileResponse(clip.path, media_type="video/mp4", filename=clip.path.name)


@router.patch("/{job_id}/clips", response_model=ClipReelResponse)
def update_clips(
    job_id: str,
    payload: ClipsPatchRequest,
    request: Request,
) -> ClipReelResponse:
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.config.clips:
        raise HTTPException(status_code=400, detail="Job has no multi-clip reel to update")

    temp_dir = job.workspace / "temp"
    updates = []
    for item in payload.clips:
        existing = next((clip for clip in job.config.clips if clip.id == item.id), None)
        if existing is None:
            raise HTTPException(status_code=400, detail=f"Unknown clip id: {item.id}")
        updates.append(
            ClipInput(
                id=item.id,
                path=existing.path,
                order=item.order,
                included=item.included,
                role=item.role,
                crop_start_s=item.crop_start_s,
                crop_end_s=item.crop_end_s,
            )
        )
    try:
        updated_config, reel, _option_set = refresh_clips_selection(
            job.config,
            temp_dir,
            updates,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store.update_config(job_id, updated_config)
    write_job_config(updated_config, job.workspace)
    clip_media = probe_clip_media(updated_config)
    target_body_s: float | None = None
    if updated_config.music.start_s is not None and updated_config.music.end_s is not None:
        music_window_s = updated_config.music.end_s - updated_config.music.start_s
        _, _, target_body_s, _ = speed_planning_context(
            updated_config,
            clip_media,
            music_window_s,
        )
    return ClipReelResponse(
        clips=clip_info_payload(updated_config, clip_media, reel),
        reel_duration_s=reel.reel_duration_s,
        target_body_duration_s=target_body_s,
        entries=[entry.model_dump(mode="json") for entry in reel.entries],
    )


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
    clip_media = probe_clip_media(job.config)
    clip_paths = clip_paths_by_id(job.config.effective_clips())
    source_ids = {segment.source_id for segment in option.plan.segments}
    if source_ids - {None}:
        clip_paths = {
            clip_id: path
            for clip_id, path in clip_paths.items()
            if clip_id in source_ids
        }
    cache_key = speed_proxy_cache_key(
        style=selected_style,
        plan=option.plan,
        video_path=job.config.video_path,
        clip_paths=clip_paths if job.config.clips else None,
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
                job.config.audio_path,
                option.plan,
                video_path=job.config.video_path,
                clip_paths=clip_paths if job.config.clips else None,
                clip_durations=clip_durations_map(clip_media) if job.config.clips else None,
                music_start_s=job.config.music.start_s,
                music_end_s=job.config.music.end_s,
                out_path=preview_path,
                temp_dir=temp_dir,
            )
        except (RuntimeError, FFmpegError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileResponse(preview_path, media_type="video/mp4", filename=preview_path.name)


def _safe_unlink(path: Path) -> bool:
    """Delete a file if possible. Returns False when the file is locked (common on Windows)."""
    try:
        path.unlink(missing_ok=True)
        return not path.is_file()
    except PermissionError:
        return False


def _invalidate_composite_previews(temp_dir: Path) -> None:
    preview_dir = temp_dir / "previews"
    if not preview_dir.is_dir():
        return
    for path in preview_dir.glob("composite_*.mp4"):
        _safe_unlink(path)


def _spatial_crop_response(crop) -> SpatialCropInput | None:
    if crop is None:
        return None
    return SpatialCropInput(x=crop.x, y=crop.y, w=crop.w, h=crop.h)


def _storyboard_response(
    job_id: str,
    storyboard,
    *,
    preview_ready: bool,
    config,
    temp_dir=None,
) -> StoryboardResponse:
    return StoryboardResponse(
        music_block_id=storyboard.music_block_id,
        music_start_s=storyboard.music_start_s,
        music_end_s=storyboard.music_end_s,
        total_duration_s=storyboard.total_duration_s,
        loop_to_hook=storyboard.loop_to_hook,
        preview_ready=preview_ready,
        render_ready=storyboard_slots_complete(storyboard),
        teaser=TeaserSettingsResponse(
            **teaser_settings_response(config, storyboard, temp_dir),
        ),
        spatial_fx=SpatialFxSettingsResponse(
            enabled=config.spatial_fx.enabled,
            intensity=config.spatial_fx.intensity,
            max_events_per_second=config.spatial_fx.max_events_per_second,
            translate_enabled=config.spatial_fx.translate_enabled,
            pan_beat_mode=config.spatial_fx.pan_beat_mode,
            pan_min_decay_s=config.spatial_fx.pan_min_decay_s,
            pan_energy_threshold=config.spatial_fx.pan_energy_threshold,
            pan_energy_floor=config.spatial_fx.pan_energy_floor,
            pan_hook_enabled=config.spatial_fx.pan_hook_enabled,
            pan_hook_by_s=config.spatial_fx.pan_hook_by_s,
        ),
        retention=RetentionSettingsResponse(
            interrupt_min_gap_s=config.retention.interrupt_min_gap_s,
            interrupt_max_gap_s=config.retention.interrupt_max_gap_s,
            hook_window_s=config.retention.hook_window_s,
            early_hook_fx_by_s=config.retention.early_hook_fx_by_s,
            peak_snap_tolerance_s=config.retention.peak_snap_tolerance_s,
        ),
        retention_score=(
            RetentionPlanScoreResponse(
                overall=storyboard.retention_score.overall,
                hook_strength=storyboard.retention_score.hook_strength,
                cadence_adherence=storyboard.retention_score.cadence_adherence,
                beat_sync=storyboard.retention_score.beat_sync,
                energy_coverage=storyboard.retention_score.energy_coverage,
            )
            if storyboard.retention_score is not None
            else None
        ),
        slots=[
            StorySlotResponse(
                id=slot.id,
                order=slot.order,
                label=slot.label,
                role=slot.role,
                out_start_s=slot.out_start_s,
                out_end_s=slot.out_end_s,
                target_duration_s=slot.target_duration_s,
                transition_in=slot.transition_in,
                assigned_clip_id=slot.assigned_clip_id,
                crop_start_s=slot.crop_start_s,
                crop_end_s=slot.crop_end_s,
                clip_filename=slot.clip_filename,
                rotation_deg=slot.rotation_deg,
                fit_mode=slot.fit_mode,
                spatial_crop=_spatial_crop_response(slot.spatial_crop),
                rationale=slot.rationale,
                clip_source_url=(
                    f"/api/jobs/{job_id}/clips/{slot.assigned_clip_id}/source"
                    if slot.assigned_clip_id
                    else None
                ),
            )
            for slot in sorted(storyboard.slots, key=lambda item: item.order)
        ],
    )


@router.get("/{job_id}/storyboard/segments", response_model=StoryboardSegmentsDebugResponse)
def get_storyboard_segments(job_id: str, request: Request) -> StoryboardSegmentsDebugResponse:
    """Return per-slot source spans and speed factors for crop/composite debugging."""
    job = _store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    temp_dir = job.workspace / "temp"
    storyboard = load_storyboard(temp_dir)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not found")
    clip_media = clip_media_for_storyboard(job.config, storyboard)
    payload = storyboard_segments_debug_payload(storyboard, clip_media)
    return StoryboardSegmentsDebugResponse(
        slots=[StoryboardSegmentDebugRow.model_validate(row) for row in payload["slots"]],
        summary=StoryboardSegmentsSummary.model_validate(payload["summary"]),
    )


@router.get("/{job_id}/storyboard", response_model=StoryboardResponse)
def get_storyboard(job_id: str, request: Request) -> StoryboardResponse:
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    temp_dir = job.workspace / "temp"
    storyboard = load_storyboard(temp_dir)
    if storyboard is None:
        storyboard = refresh_storyboard_after_music(job.config, temp_dir)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not ready — select a music block")
    synced = sync_storyboard_hook_layout(storyboard, job.config, temp_dir=temp_dir)
    config = job.config
    if synced.model_dump() != storyboard.model_dump():
        persist_storyboard(temp_dir, synced)
        storyboard = synced
        config = sync_teaser_duration_from_layout(config, storyboard)
        if config is not job.config:
            store.update_config(job_id, config)
            write_job_config(config, job.workspace)
    return _storyboard_response(
        job_id,
        storyboard,
        preview_ready=storyboard_filled_enough(storyboard),
        config=config,
        temp_dir=temp_dir,
    )


@router.patch("/{job_id}/effects", response_model=StoryboardResponse)
def patch_effects(
    job_id: str,
    payload: EffectsPatchRequest,
    request: Request,
) -> StoryboardResponse:
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not payload.teaser and not payload.spatial_fx and not payload.retention:
        raise HTTPException(status_code=400, detail="No effect fields provided")

    temp_dir = job.workspace / "temp"
    storyboard = load_storyboard(temp_dir)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not found")

    updated_config = apply_effects_patch(job.config, payload)
    updated_storyboard = refresh_hook_inversion_layout(
        storyboard,
        updated_config,
        temp_dir=temp_dir,
        reshape_crops=payload.teaser is not None,
    )
    updated_config = sync_teaser_duration_from_layout(updated_config, updated_storyboard)
    updated_config = sync_config_clips_from_storyboard(updated_config, updated_storyboard)
    store.update_config(job_id, updated_config)
    write_job_config(updated_config, job.workspace)
    persist_storyboard(temp_dir, updated_storyboard)
    _invalidate_composite_previews(temp_dir)
    return _storyboard_response(
        job_id,
        updated_storyboard,
        preview_ready=storyboard_filled_enough(updated_storyboard),
        config=updated_config,
        temp_dir=temp_dir,
    )


@router.patch("/{job_id}/storyboard", response_model=StoryboardResponse)
def patch_storyboard(
    job_id: str,
    payload: StoryboardPatchRequest,
    request: Request,
) -> StoryboardResponse:
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    temp_dir = job.workspace / "temp"
    storyboard = load_storyboard(temp_dir)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not found")

    slot_updates: list[StorySlot] | None = None
    if payload.slots is not None:
        by_id = {slot.id: slot for slot in storyboard.slots}
        slot_updates = []
        for item in payload.slots:
            existing = by_id.get(item.id)
            if existing is None:
                raise HTTPException(status_code=400, detail=f"Unknown slot id: {item.id}")
            slot_updates.append(
                existing.model_copy(
                    update={
                        k: v
                        for k, v in {
                            "order": item.order,
                            "label": item.label,
                            "role": item.role,
                            "out_start_s": item.out_start_s,
                            "out_end_s": item.out_end_s,
                            "target_duration_s": item.target_duration_s,
                            "transition_in": item.transition_in,
                        }.items()
                        if v is not None
                    }
                )
            )

    updated = apply_storyboard_patch(
        storyboard,
        slots=slot_updates,
        loop_to_hook=payload.loop_to_hook,
    )
    persist_storyboard(temp_dir, updated)
    _invalidate_composite_previews(temp_dir)
    return _storyboard_response(
        job_id,
        updated,
        preview_ready=storyboard_filled_enough(updated),
        config=job.config,
        temp_dir=temp_dir,
    )


@router.put("/{job_id}/slots/{slot_id}/clip", response_model=StoryboardResponse)
async def assign_slot_video(
    job_id: str,
    slot_id: str,
    request: Request,
    video: UploadFile = File(...),
    crop_start_s: float | None = Form(None),
    crop_end_s: float | None = Form(None),
    rotation_deg: int | None = Form(None),
    spatial_crop_json: str | None = Form(None),
) -> StoryboardResponse:
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_dir = job.workspace / "temp"
    storyboard = load_storyboard(temp_dir)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not found")
    if not any(slot.id == slot_id for slot in storyboard.slots):
        raise HTTPException(status_code=404, detail="Slot not found")

    target_slot = next(slot for slot in storyboard.slots if slot.id == slot_id)
    clip_id = hook_clip_id_for_slot(slot_id, target_slot.role)

    video_bytes = await video.read()
    if not video_bytes:
        raise HTTPException(status_code=400, detail="Video file is empty")

    video_name = Path(video.filename or f"{clip_id}.mp4").name
    input_dir = job.workspace / "input"
    save_upload(video_bytes, input_dir / video_name)
    clip_path = (input_dir / video_name).resolve()
    from viral_editor.ingest.loader import probe_media

    media = probe_media(clip_path)

    spatial_crop = None
    if spatial_crop_json:
        from viral_editor.models import SpatialCrop

        try:
            spatial_crop = SpatialCrop.model_validate(json.loads(spatial_crop_json))
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid spatial_crop_json") from exc

    updated_storyboard = assign_slot_clip(
        storyboard,
        slot_id,
        clip_id=clip_id,
        filename=video_name,
        crop_start_s=crop_start_s,
        crop_end_s=crop_end_s,
        media=media,
        rotation_deg=rotation_deg or 0,
        spatial_crop=spatial_crop,
    )
    updated_storyboard = refresh_hook_inversion_layout(
        updated_storyboard,
        job.config,
        temp_dir=temp_dir,
        reshape_crops=True,
    )
    updated_config = sync_teaser_duration_from_layout(job.config, updated_storyboard)

    existing = {clip.id: clip for clip in updated_config.clips}
    existing[clip_id] = ClipInput(
        id=clip_id,
        path=clip_path,
        order=len(existing),
        included=True,
        role="clip",
        crop_start_s=updated_storyboard.slots[
            next(i for i, s in enumerate(updated_storyboard.slots) if s.id == slot_id)
        ].crop_start_s,
        crop_end_s=updated_storyboard.slots[
            next(i for i, s in enumerate(updated_storyboard.slots) if s.id == slot_id)
        ].crop_end_s,
    )
    updated_config = updated_config.model_copy(update={"clips": list(existing.values())})
    updated_config = sync_config_clips_from_storyboard(updated_config, updated_storyboard)

    persist_storyboard(temp_dir, updated_storyboard)
    _invalidate_composite_previews(temp_dir)
    store.update_config(job_id, updated_config)
    write_job_config(updated_config, job.workspace)
    return _storyboard_response(
        job_id,
        updated_storyboard,
        preview_ready=storyboard_filled_enough(updated_storyboard),
        config=updated_config,
        temp_dir=temp_dir,
    )


@router.patch("/{job_id}/slots/{slot_id}/crop", response_model=StoryboardResponse)
def patch_slot_crop(
    job_id: str,
    slot_id: str,
    payload: SlotCropPatchRequest,
    request: Request,
) -> StoryboardResponse:
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_dir = job.workspace / "temp"
    storyboard = load_storyboard(temp_dir)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not found")
    slot = next((item for item in storyboard.slots if item.id == slot_id), None)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot not found")
    clip_id = hook_family_assigned_clip_id(storyboard, slot)
    if clip_id is None:
        raise HTTPException(status_code=400, detail="Slot has no assigned clip")

    clip_media = clip_media_for_storyboard(job.config, storyboard)
    media = clip_media.get(clip_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Assigned clip media not found")

    try:
        updated_storyboard = update_slot_crop(
            storyboard,
            slot_id,
            crop_start_s=payload.crop_start_s,
            crop_end_s=payload.crop_end_s,
            media=media,
            payoff_duration_s=(
                job.config.teaser.duration_s if job.config.teaser.enabled else None
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated_config = sync_config_clips_from_storyboard(job.config, updated_storyboard)
    persist_storyboard(temp_dir, updated_storyboard)
    _invalidate_composite_previews(temp_dir)
    store.update_config(job_id, updated_config)
    write_job_config(updated_config, job.workspace)
    return _storyboard_response(
        job_id,
        updated_storyboard,
        preview_ready=storyboard_filled_enough(updated_storyboard),
        config=updated_config,
        temp_dir=temp_dir,
    )


@router.patch("/{job_id}/slots/{slot_id}/transform", response_model=StoryboardResponse)
def patch_slot_transform(
    job_id: str,
    slot_id: str,
    payload: SlotTransformPatchRequest,
    request: Request,
) -> StoryboardResponse:
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_dir = job.workspace / "temp"
    storyboard = load_storyboard(temp_dir)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not found")
    slot = next((item for item in storyboard.slots if item.id == slot_id), None)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot.assigned_clip_id is None:
        raise HTTPException(status_code=400, detail="Slot has no assigned clip")

    patch_fields = payload.model_dump(exclude_unset=True)
    if not patch_fields:
        raise HTTPException(status_code=400, detail="No transform fields provided")

    spatial_crop = None
    update_spatial_crop = False
    if "spatial_crop" in patch_fields:
        update_spatial_crop = True
        raw = patch_fields["spatial_crop"]
        if raw is not None:
            from viral_editor.models import SpatialCrop

            spatial_crop = SpatialCrop.model_validate(raw)

    try:
        updated_storyboard = update_slot_transform(
            storyboard,
            slot_id,
            rotation_deg=payload.rotation_deg,
            fit_mode=payload.fit_mode,
            spatial_crop=spatial_crop,
            update_spatial_crop=update_spatial_crop,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated_config = sync_config_clips_from_storyboard(job.config, updated_storyboard)
    persist_storyboard(temp_dir, updated_storyboard)
    _invalidate_composite_previews(temp_dir)
    store.update_config(job_id, updated_config)
    write_job_config(updated_config, job.workspace)
    return _storyboard_response(
        job_id,
        updated_storyboard,
        preview_ready=storyboard_filled_enough(updated_storyboard),
        config=updated_config,
        temp_dir=temp_dir,
    )


@router.delete("/{job_id}/slots/{slot_id}/clip", response_model=StoryboardResponse)
def clear_slot_video(job_id: str, slot_id: str, request: Request) -> StoryboardResponse:
    store = _store(request)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_dir = job.workspace / "temp"
    storyboard = load_storyboard(temp_dir)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not found")

    target = next((slot for slot in storyboard.slots if slot.id == slot_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Slot not found")

    clip_id = hook_clip_id_for_slot(slot_id, target.role)
    updated_storyboard = clear_slot_clip(storyboard, slot_id)
    remaining_clips = list(job.config.clips)
    if not any(slot.assigned_clip_id == clip_id for slot in updated_storyboard.slots):
        remaining_clips = [clip for clip in job.config.clips if clip.id != clip_id]
    updated_config = job.config.model_copy(update={"clips": remaining_clips})

    persist_storyboard(temp_dir, updated_storyboard)
    _invalidate_composite_previews(temp_dir)
    store.update_config(job_id, updated_config)
    write_job_config(updated_config, job.workspace)
    return _storyboard_response(
        job_id,
        updated_storyboard,
        preview_ready=storyboard_filled_enough(updated_storyboard),
        config=updated_config,
        temp_dir=temp_dir,
    )


def _segment_transform_for_slot(slot: StorySlot) -> tuple[int, str, tuple[float, float, float, float] | None]:
    spatial = None
    if slot.spatial_crop is not None:
        spatial = (
            slot.spatial_crop.x,
            slot.spatial_crop.y,
            slot.spatial_crop.w,
            slot.spatial_crop.h,
        )
    return (slot.rotation_deg, slot.fit_mode, spatial)


@router.get("/{job_id}/preview")
def get_composite_preview(
    job_id: str,
    request: Request,
    force: bool = Query(default=False),
) -> FileResponse:
    job = _store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_dir = job.workspace / "temp"
    storyboard = load_storyboard(temp_dir)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not found")
    if not storyboard_filled_enough(storyboard):
        raise HTTPException(status_code=400, detail="Assign a clip to the hook slot first")

    clip_media = clip_media_for_storyboard(job.config, storyboard)
    segments, segment_roles, segment_slot_ids = storyboard_to_segments(storyboard, clip_media)
    if not segments:
        raise HTTPException(status_code=400, detail="No assigned clips to preview")

    slots_by_id = {slot.id: slot for slot in storyboard.slots}
    ordered_slots = [slots_by_id[slot_id] for slot_id in segment_slot_ids]

    needed_clip_ids = {segment.source_id for segment in segments if segment.source_id}
    clips_by_id = {clip.id: clip for clip in job.config.clips}
    clip_paths = {
        clip_id: clips_by_id[clip_id].path
        for clip_id in needed_clip_ids
        if clip_id in clips_by_id and clips_by_id[clip_id].path.is_file()
    }
    missing = needed_clip_ids - set(clip_paths)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing clip files for preview: {', '.join(sorted(missing))}",
        )

    clip_durations = {clip_id: info.duration_s for clip_id, info in clip_media.items()}
    transitions = [slot.transition_in for slot in ordered_slots]
    segment_transforms = [_segment_transform_for_slot(slot) for slot in ordered_slots]

    primary_media = next(iter(clip_media.values()), None)
    fx_events = (
        spatial_fx_for_preview(
            job.config,
            temp_dir,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
            media=primary_media,
            storyboard=storyboard,
        )
        if primary_media is not None
        else []
    )
    fx_events = remap_fx_events_for_composite(fx_events, storyboard)

    import hashlib
    import json

    cache_payload = {
        "storyboard": storyboard.model_dump(mode="json"),
        "hook": job.config.hook.text,
        "teaser": job.config.teaser.model_dump(mode="json"),
        "spatial_fx": job.config.spatial_fx.model_dump(mode="json"),
        "seed": job.config.seed,
    }
    digest = hashlib.sha256(json.dumps(cache_payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    preview_path = temp_dir / "previews" / f"composite_{digest}.mp4"
    if force and preview_path.is_file():
        if not _safe_unlink(preview_path) and preview_path.is_file():
            preview_path = temp_dir / "previews" / f"composite_{digest}_{uuid.uuid4().hex[:8]}.mp4"
    if not preview_path.is_file() or force:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            render_composite(
                job.config.audio_path,
                segments,
                transitions,
                clip_paths=clip_paths,
                clip_durations=clip_durations,
                segment_transforms=segment_transforms,
                music_start_s=job.config.music.start_s,
                music_end_s=job.config.music.end_s,
                out_path=preview_path,
                hook_text=job.config.hook.text,
                temp_dir=temp_dir,
                segment_roles=segment_roles,
                hook_start_mask=(
                    job.config.teaser.mask if job.config.teaser.enabled else None
                ),
                fx_events=fx_events,
                fx_seed=job.config.seed,
                fx_intensity=job.config.spatial_fx.intensity,
            )
        except (RuntimeError, FFmpegError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileResponse(preview_path, media_type="video/mp4", filename="preview.mp4")
