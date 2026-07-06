"""Tests for all_blocks catalog exposure on waveform payload."""

from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from viral_editor.api.main import create_app
from viral_editor.api.store import job_workspace
from viral_editor.models import (
    AudioTimeline,
    MusicBlock,
    MusicBlockCatalog,
    MusicBlockPlan,
    MusicSection,
    MusicStructurePlan,
    Transient,
    WaveformPayload,
    write_artifact,
)
from tests.test_audio_scope_api import _seed_analysis_artifacts


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _seed_music_block_catalog(job_id: str) -> None:
    temp_dir = job_workspace(job_id) / "temp"
    plan_10 = MusicBlockPlan(
        target_duration_s=10.0,
        track_duration_s=45.0,
        blocks=[
            MusicBlock(
                id="block_10_a",
                start_s=0.0,
                end_s=10.0,
                duration_s=10.0,
                score=0.9,
                drop_count=1,
                transient_count=2,
                label="Ten second loop",
                reason="Phrase at 10s",
                expected_slot_count=2,
            ),
        ],
    )
    plan_15 = MusicBlockPlan(
        target_duration_s=15.0,
        track_duration_s=45.0,
        blocks=[
            MusicBlock(
                id="block_15_a",
                start_s=5.0,
                end_s=20.0,
                duration_s=15.0,
                score=0.85,
                drop_count=1,
                transient_count=3,
                label="Fifteen second loop",
                reason="Phrase at 15s",
                expected_slot_count=4,
            ),
        ],
    )
    catalog = MusicBlockCatalog(plans={"10": plan_10, "15": plan_15})
    write_artifact(catalog, "music_block_catalog", temp_dir)


def _create_job_with_catalog(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> str:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)
    create = client.post(
        "/api/jobs",
        data={"hook_text": "All blocks test"},
        files={
            "video": ("clip.mp4", io.BytesIO(b"video"), "video/mp4"),
            "audio": ("track.mp3", io.BytesIO(b"audio"), "audio/mpeg"),
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]
    _seed_analysis_artifacts(job_id)
    _seed_music_block_catalog(job_id)
    return job_id


def test_music_block_has_preset_target_duration_s_field() -> None:
    block = MusicBlock(
        id="block_a",
        start_s=0.0,
        end_s=10.0,
        duration_s=10.0,
        score=0.8,
        drop_count=1,
        transient_count=2,
        label="Test",
        reason="Test block",
    )
    assert hasattr(block, "preset_target_duration_s")
    assert block.preset_target_duration_s is None


def test_waveform_payload_has_all_blocks_field() -> None:
    payload = WaveformPayload(duration_s=45.0, global_bpm=128.0)
    assert hasattr(payload, "all_blocks")
    assert payload.all_blocks == []


def test_get_waveform_all_blocks_includes_blocks_from_all_catalog_plans(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    job_id = _create_job_with_catalog(client, monkeypatch, tmp_path)
    response = client.get(f"/api/jobs/{job_id}/audio/waveform")
    assert response.status_code == 200
    data = response.json()
    assert "all_blocks" in data
    presets = {
        block["preset_target_duration_s"]
        for block in data["all_blocks"]
        if block.get("preset_target_duration_s") is not None
    }
    assert len(presets) > 1


def test_get_waveform_all_blocks_blocks_have_expected_slot_count(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    job_id = _create_job_with_catalog(client, monkeypatch, tmp_path)
    response = client.get(f"/api/jobs/{job_id}/audio/waveform")
    assert response.status_code == 200
    for block in response.json()["all_blocks"]:
        assert block["expected_slot_count"] is not None
