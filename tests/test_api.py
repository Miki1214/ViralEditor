"""API tests for the Control Room."""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from viral_editor.api.main import create_app
from viral_editor.pipeline import PipelineResult


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "ffmpeg_available" in body


def test_list_stages(client: TestClient) -> None:
    response = client.get("/api/jobs/stages")
    assert response.status_code == 200
    stages = response.json()["stages"]
    assert any(stage["id"] == "ingest" for stage in stages)


def test_create_job_runs_pipeline(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)

    def fake_run_pipeline(**kwargs):
        on_event = kwargs.get("on_event")
        if on_event:
            from viral_editor.pipeline_events import PipelineEvent

            on_event(PipelineEvent.now("pipeline", "start"))
            on_event(PipelineEvent.now("config", "start"))
            on_event(PipelineEvent.now("config", "complete"))
            on_event(PipelineEvent.now("ingest", "start"))
            on_event(PipelineEvent.now("ingest", "complete", message="output_duration_s=10.00"))
            on_event(PipelineEvent.now("pipeline", "complete"))
        return PipelineResult(
            config=kwargs["cfg"],
            output_duration_s=10.0,
            artifacts=["media_info.json"],
        )

    monkeypatch.setattr("viral_editor.api.runner.run_pipeline", fake_run_pipeline)

    def immediate_start(store, job_id, *, verbose=False):
        del verbose

        def _run():
            from viral_editor.api.runner import _on_event_factory
            from viral_editor.pipeline_events import PipelineEvent

            store.set_status(job_id, "running")
            job = store.get(job_id)
            assert job is not None
            on_event = _on_event_factory(store, job_id)
            on_event(PipelineEvent.now("pipeline", "start"))
            on_event(PipelineEvent.now("config", "complete"))
            on_event(PipelineEvent.now("ingest", "complete", message="output_duration_s=10.00"))
            on_event(PipelineEvent.now("pipeline", "complete"))
            store.complete(job_id, output_duration_s=10.0, artifacts=["media_info.json"])

        _run()

    monkeypatch.setattr("viral_editor.api.routes.jobs.start_job", immediate_start)

    response = client.post(
        "/api/jobs",
        data={
            "hook_text": "Test hook",
            "emphasis_words": "Test",
            "fill_color": "#FFFFFF",
            "emphasis_color": "#FFD700",
        },
        files={
            "video": ("clip.mp4", io.BytesIO(b"video-bytes"), "video/mp4"),
            "audio": ("track.mp3", io.BytesIO(b"audio-bytes"), "audio/mpeg"),
        },
    )
    assert response.status_code == 201
    job_id = response.json()["id"]

    detail = client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["hook_text"] == "Test hook"
    assert detail.json()["status"] == "completed"
    assert detail.json()["output_duration_s"] == 10.0


def test_create_job_rejects_empty_video(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    response = client.post(
        "/api/jobs",
        data={"hook_text": "Hook"},
        files={
            "video": ("clip.mp4", io.BytesIO(b""), "video/mp4"),
            "audio": ("track.mp3", io.BytesIO(b"audio"), "audio/mpeg"),
        },
    )
    assert response.status_code == 400


def test_create_job_accepts_multiple_videos(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)
    monkeypatch.setattr("viral_editor.api.routes.jobs.start_job", lambda *args, **kwargs: None)

    response = client.post(
        "/api/jobs",
        data={
            "hook_text": "Multi clip",
            "clips": json.dumps(
                [
                    {"id": "clip_0", "order": 0, "role": "hook"},
                    {"id": "clip_1", "order": 1, "role": "clip"},
                ]
            ),
        },
        files=[
            ("video", ("a.mp4", io.BytesIO(b"video-a"), "video/mp4")),
            ("video", ("b.mp4", io.BytesIO(b"video-b"), "video/mp4")),
            ("audio", ("track.mp3", io.BytesIO(b"audio"), "audio/mpeg")),
        ],
    )
    assert response.status_code == 201
    job_id = response.json()["id"]
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert len(detail["config"]["clips"]) == 2
    assert detail["config"]["clips"][0]["role"] == "hook"


def test_create_job_matches_clip_metadata_by_upload_order(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    """Metadata at clips JSON index N must apply to the Nth uploaded video."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)
    monkeypatch.setattr("viral_editor.api.routes.jobs.start_job", lambda *args, **kwargs: None)

    response = client.post(
        "/api/jobs",
        data={
            "hook_text": "Reordered meta",
            "clips": json.dumps(
                [
                    {
                        "id": "clip_2",
                        "order": 0,
                        "role": "hook",
                        "crop_start_s": 1.0,
                        "crop_end_s": 5.0,
                    },
                    {
                        "id": "clip_0",
                        "order": 1,
                        "role": "clip",
                        "crop_start_s": 0.0,
                        "crop_end_s": 3.0,
                    },
                ]
            ),
        },
        files=[
            ("video", ("second-clip.mp4", io.BytesIO(b"video-2"), "video/mp4")),
            ("video", ("first-clip.mp4", io.BytesIO(b"video-0"), "video/mp4")),
            ("audio", ("track.mp3", io.BytesIO(b"audio"), "audio/mpeg")),
        ],
    )
    assert response.status_code == 201
    job_id = response.json()["id"]
    detail = client.get(f"/api/jobs/{job_id}").json()
    clips = {clip["id"]: clip for clip in detail["config"]["clips"]}
    assert clips["clip_2"]["role"] == "hook"
    assert clips["clip_2"]["crop_start_s"] == pytest.approx(1.0)
    assert clips["clip_0"]["crop_start_s"] == pytest.approx(0.0)


def test_patch_clips_recomputes_reel(
    client: TestClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from viral_editor.api.store import job_workspace
    from viral_editor.models import (
        AudioTimeline,
        MediaInfo,
        MusicBlock,
        MusicBlockPlan,
        MusicSection,
        MusicStructurePlan,
        write_artifact,
    )
    import numpy as np

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)
    monkeypatch.setattr("viral_editor.api.routes.jobs.start_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "viral_editor.api.speed.probe_clip_media",
        lambda config: {
            clip.id: MediaInfo(
                path=clip.path,
                duration_s=30.0,
                has_video=True,
                fps=30.0,
            )
            for clip in config.clips
        },
    )
    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.probe_clip_media",
        lambda config: {
            clip.id: MediaInfo(
                path=clip.path,
                duration_s=30.0,
                has_video=True,
                fps=30.0,
            )
            for clip in config.clips
        },
    )

    response = client.post(
        "/api/jobs",
        data={
            "hook_text": "Patch clips",
            "clips": json.dumps(
                [
                    {"id": "clip_0", "order": 0, "role": "clip"},
                    {"id": "clip_1", "order": 1, "role": "hook"},
                ]
            ),
        },
        files=[
            ("video", ("a.mp4", io.BytesIO(b"video-a"), "video/mp4")),
            ("video", ("b.mp4", io.BytesIO(b"video-b"), "video/mp4")),
            ("audio", ("track.mp3", io.BytesIO(b"audio"), "audio/mpeg")),
        ],
    )
    assert response.status_code == 201
    job_id = response.json()["id"]
    temp_dir = job_workspace(job_id) / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    write_artifact(
        AudioTimeline(global_bpm=128.0, audio_duration_seconds=45.0, sample_rate=22050, transients=[]),
        "audio_timeline",
        temp_dir,
    )
    np.save(temp_dir / "onset_envelope.npy", np.linspace(0.1, 1.0, 500))
    write_artifact(
        MusicBlockPlan(
            target_duration_s=15.0,
            track_duration_s=45.0,
            selected_block_id="block_a",
            blocks=[
                MusicBlock(
                    id="block_a",
                    start_s=4.0,
                    end_s=19.0,
                    duration_s=15.0,
                    score=0.8,
                    drop_count=1,
                    transient_count=3,
                    label="Drop opener",
                    reason="Starts near a drop",
                )
            ],
        ),
        "music_blocks",
        temp_dir,
    )
    write_artifact(
        MusicStructurePlan(
            sections=[
                MusicSection(
                    id="section_a",
                    start_s=0.0,
                    end_s=20.0,
                    start_beat=0,
                    end_beat=40,
                    label="Hook 1",
                    repetition_count=2,
                    energy=0.7,
                    is_repeated=True,
                )
            ],
            key="C",
            beat_engine="librosa",
        ),
        "music_structure",
        temp_dir,
    )

    from viral_editor.config import JobConfig

    job = client.get(f"/api/jobs/{job_id}").json()
    updated = JobConfig.model_validate(job["config"]).model_copy(
        update={
            "music": JobConfig.model_validate(job["config"]).music.model_copy(
                update={"start_s": 4.0, "end_s": 19.0}
            )
        }
    )
    client.app.state.job_store.update_config(job_id, updated)

    patch = client.patch(
        f"/api/jobs/{job_id}/clips",
        json={
            "clips": [
                {
                    "id": "clip_0",
                    "order": 0,
                    "included": True,
                    "role": "clip",
                    "crop_start_s": 0.0,
                    "crop_end_s": 5.0,
                },
                {
                    "id": "clip_1",
                    "order": 1,
                    "included": True,
                    "role": "hook",
                    "crop_start_s": 0.0,
                    "crop_end_s": None,
                },
            ]
        },
    )
    assert patch.status_code == 200
    body = patch.json()
    assert len(body["clips"]) == 2
    assert (temp_dir / "clip_reel.json").is_file()
    assert (temp_dir / "speed_segments.json").is_file()
