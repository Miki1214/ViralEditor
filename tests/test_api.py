"""API tests for the Control Room."""

from __future__ import annotations

import io

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
