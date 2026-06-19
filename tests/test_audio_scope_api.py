"""Tests for waveform and music-selection API endpoints."""

from __future__ import annotations

import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from viral_editor.api.main import create_app
from viral_editor.api.store import job_workspace
from viral_editor.models import AudioTimeline, MusicBlock, MusicBlockPlan, MusicSection, MusicStructurePlan, Transient, write_artifact


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _seed_analysis_artifacts(job_id: str) -> None:
    workspace = job_workspace(job_id)
    temp_dir = workspace / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    timeline = AudioTimeline(
        global_bpm=128.0,
        audio_duration_seconds=45.0,
        sample_rate=22050,
        transients=[
            Transient(timestamp_ms=5000, amplitude_normalized=0.9, type="drop"),
        ],
    )
    write_artifact(timeline, "audio_timeline", temp_dir)
    np.save(temp_dir / "onset_envelope.npy", np.linspace(0.1, 1.0, 500))
    plan = MusicBlockPlan(
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
    )
    write_artifact(plan, "music_blocks", temp_dir)
    structure = MusicStructurePlan(
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
    )
    write_artifact(structure, "music_structure", temp_dir)


def test_waveform_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)

    create = client.post(
        "/api/jobs",
        data={"hook_text": "Scope test"},
        files={
            "video": ("clip.mp4", io.BytesIO(b"video"), "video/mp4"),
            "audio": ("track.mp3", io.BytesIO(b"audio"), "audio/mpeg"),
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]
    _seed_analysis_artifacts(job_id)

    response = client.get(f"/api/jobs/{job_id}/audio/waveform")
    assert response.status_code == 200
    body = response.json()
    assert body["global_bpm"] == 128.0
    assert len(body["points"]) > 0
    assert body["blocks"][0]["id"] == "block_a"
    assert body["key"] == "C"
    assert body["beat_engine"] == "librosa"
    assert len(body["sections"]) == 1


def test_music_selection_patch(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)

    create = client.post(
        "/api/jobs",
        data={"hook_text": "Patch test", "target_duration_s": "30"},
        files={
            "video": ("clip.mp4", io.BytesIO(b"video"), "video/mp4"),
            "audio": ("track.mp3", io.BytesIO(b"audio"), "audio/mpeg"),
        },
    )
    job_id = create.json()["id"]
    _seed_analysis_artifacts(job_id)

    response = client.patch(
        f"/api/jobs/{job_id}/music-selection",
        json={"selected_block_id": "block_a"},
    )
    assert response.status_code == 200
    config = response.json()["config"]["music"]
    assert config["selected_block_id"] == "block_a"
    assert config["start_s"] == 4.0
    assert config["end_s"] == 19.0

    blocks = json.loads((job_workspace(job_id) / "temp" / "music_blocks.json").read_text())
    assert blocks["selected_block_id"] == "block_a"


def _fake_video_probe(path):
    from pathlib import Path

    from viral_editor.models import MediaInfo

    return MediaInfo(
        path=Path(path),
        duration_s=30.0,
        has_video=True,
        fps=30.0,
        width=1920,
        height=1080,
    )


def _noop_start_job(store, job_id, *, verbose=False):
    del store, job_id, verbose


def test_speed_ramp_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)
    monkeypatch.setattr("viral_editor.api.routes.jobs.start_job", _noop_start_job)
    monkeypatch.setattr(
        "viral_editor.api.speed.probe_clip_media",
        lambda config: {"clip_primary": _fake_video_probe("clip.mp4")},
    )

    create = client.post(
        "/api/jobs",
        data={"hook_text": "Speed ramp test"},
        files={
            "video": ("clip.mp4", io.BytesIO(b"video"), "video/mp4"),
            "audio": ("track.mp3", io.BytesIO(b"audio"), "audio/mpeg"),
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]
    _seed_analysis_artifacts(job_id)

    response = client.get(f"/api/jobs/{job_id}/speed-ramp")
    assert response.status_code == 200
    body = response.json()
    assert body["selected_style"] == "drop_sync"
    assert len(body["options"]) == 4
    assert body["options"][0]["plan"]["speed_curve"]


def test_speed_selection_patch(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)
    monkeypatch.setattr("viral_editor.api.routes.jobs.start_job", _noop_start_job)
    monkeypatch.setattr(
        "viral_editor.api.speed.probe_clip_media",
        lambda config: {"clip_primary": _fake_video_probe("clip.mp4")},
    )

    create = client.post(
        "/api/jobs",
        data={"hook_text": "Speed selection test"},
        files={
            "video": ("clip.mp4", io.BytesIO(b"video"), "video/mp4"),
            "audio": ("track.mp3", io.BytesIO(b"audio"), "audio/mpeg"),
        },
    )
    job_id = create.json()["id"]
    _seed_analysis_artifacts(job_id)

    response = client.patch(
        f"/api/jobs/{job_id}/speed-selection",
        json={"style": "steady_flow", "alpha": 6.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["selected_style"] == "steady_flow"

    segments_path = job_workspace(job_id) / "temp" / "speed_segments.json"
    assert segments_path.is_file()
    segments = json.loads(segments_path.read_text())
    assert segments["style"] == "steady_flow"
