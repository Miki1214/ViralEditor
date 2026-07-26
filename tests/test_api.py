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


def test_create_job_rejects_empty_audio(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    response = client.post(
        "/api/jobs",
        data={"hook_text": "Hook"},
        files={
            "audio": ("track.mp3", io.BytesIO(b""), "audio/mpeg"),
        },
    )
    assert response.status_code == 400


def test_create_audio_only_draft_job(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)
    monkeypatch.setattr("viral_editor.api.routes.jobs.start_job", lambda *args, **kwargs: None)

    response = client.post(
        "/api/jobs",
        data={"hook_text": "Audio first"},
        files=[("audio", ("track.mp3", io.BytesIO(b"audio-bytes"), "audio/mpeg"))],
    )
    assert response.status_code == 201
    job_id = response.json()["id"]
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["config"]["clips"] == []


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


def test_patch_effects_updates_hook_split_durations(
    client: TestClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from viral_editor.api.store import job_workspace
    from viral_editor.api.storyboard import persist_storyboard, refresh_hook_inversion_layout
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.config import JobConfig
    from viral_editor.models import AudioTimeline, MusicBlock, MusicBlockPlan, write_artifact

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)
    monkeypatch.setattr("viral_editor.api.routes.jobs.start_job", lambda *args, **kwargs: None)

    response = client.post(
        "/api/jobs",
        data={"hook_text": "Hook split"},
        files={"audio": ("track.mp3", io.BytesIO(b"audio"), "audio/mpeg")},
    )
    assert response.status_code == 201
    job_id = response.json()["id"]
    temp_dir = job_workspace(job_id) / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    write_artifact(
        AudioTimeline(global_bpm=129.0, audio_duration_seconds=17.74, sample_rate=22050, transients=[]),
        "audio_timeline",
        temp_dir,
    )
    block = MusicBlock(
        id="block_a",
        start_s=0.0,
        end_s=17.74,
        duration_s=17.74,
        score=0.9,
        drop_count=1,
        transient_count=1,
        label="Intro",
        reason="test",
    )
    write_artifact(
        MusicBlockPlan(
            target_duration_s=17.74,
            track_duration_s=17.74,
            selected_block_id="block_a",
            blocks=[block],
        ),
        "music_blocks",
        temp_dir,
    )
    from viral_editor.audio.features import BeatFeaturesMeta, BeatSyncFeatures, save_features
    import numpy as np

    downbeats = np.array([0.0, 1.857, 3.714, 5.571, 17.74], dtype=np.float64)
    save_features(
        BeatSyncFeatures(
            beat_times_s=downbeats,
            downbeat_times_s=downbeats,
            chroma_sync=np.zeros((12, len(downbeats))),
            mfcc_sync=np.zeros((20, len(downbeats))),
            rms_sync=np.zeros((1, len(downbeats))),
            contrast_sync=np.zeros((7, len(downbeats))),
            tonnetz_sync=np.zeros((6, len(downbeats))),
            meta=BeatFeaturesMeta(
                engine="test",
                global_bpm=129.0,
                key="G#",
                n_beats=len(downbeats),
                n_downbeats=len(downbeats),
                hop_length=512,
                sample_rate=22050,
            ),
        ),
        temp_dir / "features.npz",
    )
    job = client.get(f"/api/jobs/{job_id}").json()
    config = JobConfig.model_validate(job["config"]).model_copy(
        update={
            "teaser": JobConfig.model_validate(job["config"]).teaser.model_copy(
                update={"enabled": True, "duration_s": 1.8, "tail_fraction": 0.17}
            )
        }
    )
    client.app.state.job_store.update_config(job_id, config)
    storyboard = refresh_hook_inversion_layout(plan_storyboard(block), config, temp_dir=temp_dir)
    persist_storyboard(temp_dir, storyboard)

    before = client.get(f"/api/jobs/{job_id}/storyboard").json()
    hook_start = next(slot for slot in before["slots"] if slot["role"] == "hook_start")
    hook_end = next(slot for slot in before["slots"] if slot["role"] == "hook_end")
    positions = before["teaser"]["payoff_downbeats_s"]
    assert len(positions) >= 1
    assert hook_start["target_duration_s"] in positions

    target = positions[-1] if len(positions) > 1 else positions[0]
    patched = client.patch(
        f"/api/jobs/{job_id}/effects",
        json={"teaser": {"duration_s": target + 0.4}},
    )
    assert patched.status_code == 200
    body = patched.json()
    hook_start = next(slot for slot in body["slots"] if slot["role"] == "hook_start")
    hook_end = next(slot for slot in body["slots"] if slot["role"] == "hook_end")
    assert hook_start["target_duration_s"] in body["teaser"]["payoff_downbeats_s"]
    assert hook_end["target_duration_s"] < hook_start["target_duration_s"]
    assert body["teaser"]["duration_s"] == pytest.approx(hook_start["target_duration_s"])


def test_start_render_requires_all_slots(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.models import MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_render"
    workspace.mkdir()
    config = build_job_config(
        workspace=workspace,
        hook_text="hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=0.0,
        end_s=10.0,
        duration_s=10.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    persist_storyboard(workspace / "temp", storyboard)

    response = client.post(f"/api/jobs/{job.id}/render")
    assert response.status_code == 400
    assert "all storyboard slots" in response.json()["detail"].lower()


def test_start_render_accepts_filled_storyboard(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    started: list[str] = []

    def fake_start(store, job_id: str) -> None:
        started.append(job_id)

    monkeypatch.setattr("viral_editor.api.routes.jobs.start_final_render", fake_start)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.models import MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_render_ok"
    workspace.mkdir()
    config = build_job_config(
        workspace=workspace,
        hook_text="hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=0.0,
        end_s=10.0,
        duration_s=10.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    filled = storyboard.model_copy(
        update={
            "slots": [
                slot.model_copy(update={"assigned_clip_id": f"clip_{index}"})
                for index, slot in enumerate(storyboard.slots)
            ]
        }
    )
    persist_storyboard(workspace / "temp", filled)

    response = client.post(f"/api/jobs/{job.id}/render")
    assert response.status_code == 202
    assert response.json()["status"] == "rendering"
    assert started == [job.id]


def test_get_and_patch_caption(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.models import MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_caption"
    workspace.mkdir()
    config = build_job_config(
        workspace=workspace,
        hook_text="My hook title",
        emphasis_words=["hook"],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=0.0,
        end_s=10.0,
        duration_s=10.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    persist_storyboard(workspace / "temp", storyboard)

    get_response = client.get(f"/api/jobs/{job.id}/caption")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["hook_text"] == "My hook title"
    assert body["words_per_second"] == 5.0
    assert len(body["wps_presets"]) >= 1
    assert len(body["slot_budgets"]) == len(storyboard.slots)

    # A plain script_text patch (e.g. on textarea blur) saves the raw text but
    # must NOT split it across slots implicitly.
    patch_response = client.patch(
        f"/api/jobs/{job.id}/caption",
        json={
            "script_text": "one two three four five six seven eight nine ten",
            "words_per_second": 5.0,
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["script_text"].startswith("one two three")
    assert patched["slot_overrides"] == {}

    # Explicit cleanup normalizes script whitespace.
    cleanup_response = client.patch(
        f"/api/jobs/{job.id}/caption",
        json={
            "script_text": "one two  three four five six seven eight nine ten ",
            "cleanup": True,
        },
    )
    assert cleanup_response.status_code == 200
    cleaned = cleanup_response.json()
    assert cleaned["script_text"] == "one two three four five six seven eight nine ten"
    assert cleaned["slot_overrides"]
    assert sum(len(text.split()) for text in cleaned["slot_overrides"].values()) == 10

    # Explicit auto_allocate splits by reading-speed budget (text only, no ASR timing).
    allocate_response = client.patch(
        f"/api/jobs/{job.id}/caption",
        json={
            "script_text": "one two three four five six seven eight nine ten",
            "auto_allocate": True,
        },
    )
    assert allocate_response.status_code == 200
    allocated = allocate_response.json()
    assert allocated["script_text"] == "one two three four five six seven eight nine ten"
    assert allocated["slot_budgets"][0]["actual_words"] > 0
    assert allocated["slot_overrides"]
    assert sum(len(text.split()) for text in allocated["slot_overrides"].values()) == 10


def test_transcribe_caption_persists_script_and_slot_overrides(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.models import CaptionWord, MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_transcribe"
    workspace.mkdir()
    (workspace / "input").mkdir()
    audio_path = workspace / "input" / "track.mp3"
    audio_path.write_bytes(b"fake")

    config = build_job_config(
        workspace=workspace,
        hook_text="My hook title",
        emphasis_words=["hook"],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=10.0,
        end_s=16.0,
        duration_s=6.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    persist_storyboard(workspace / "temp", storyboard)

    words = [
        CaptionWord(text="hello", start_s=10.5, end_s=10.8),
        CaptionWord(text="world", start_s=11.0, end_s=11.3),
        CaptionWord(text="again", start_s=13.2, end_s=13.5),
        CaptionWord(text="now", start_s=13.8, end_s=14.1),
    ]

    def fake_transcribe_audio(path, *, options=None):
        assert path == audio_path
        return "hello world again now", words

    monkeypatch.setattr(
        "viral_editor.audio.transcribe_sources.transcribe_audio",
        fake_transcribe_audio,
    )

    response = client.post(
        f"/api/jobs/{job.id}/caption/transcribe",
        data={"source": "audio_track"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["script_text"] == "hello world again now"
    assert body["source"] == "audio_track"
    assert body["slot_overrides"]
    assert sum(len(text.split()) for text in body["slot_overrides"].values()) == 4
    assert body["word_timing_overrides"]

    get_response = client.get(f"/api/jobs/{job.id}/caption")
    assert get_response.status_code == 200
    persisted = get_response.json()
    assert persisted["script_text"] == "hello world again now"
    assert persisted["slot_overrides"] == body["slot_overrides"]
    assert persisted["slot_budgets"][0]["actual_words"] > 0
    first_slot_words = persisted["slot_budgets"][0]["chunks"][0]["words"]
    assert first_slot_words[0]["start_s"] < 1.0


def test_audio_sync_restores_transcribed_word_timing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.models import CaptionWord, MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_audio_sync"
    workspace.mkdir()
    (workspace / "input").mkdir()
    audio_path = workspace / "input" / "track.mp3"
    audio_path.write_bytes(b"fake")

    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=10.0,
        end_s=16.0,
        duration_s=6.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    persist_storyboard(workspace / "temp", storyboard)

    words = [
        CaptionWord(text="hello", start_s=10.5, end_s=10.8),
        CaptionWord(text="world", start_s=11.0, end_s=11.3),
        CaptionWord(text="again", start_s=13.2, end_s=13.5),
        CaptionWord(text="now", start_s=13.8, end_s=14.1),
    ]

    monkeypatch.setattr(
        "viral_editor.audio.transcribe_sources.transcribe_audio",
        lambda path, *, options=None: ("hello world again now", words),
    )

    transcribe_response = client.post(
        f"/api/jobs/{job.id}/caption/transcribe",
        data={"source": "audio_track"},
    )
    assert transcribe_response.status_code == 200
    assert transcribe_response.json()["script_text"] == "hello world again now"

    get_after_transcribe = client.get(f"/api/jobs/{job.id}/caption")
    assert get_after_transcribe.status_code == 200
    assert get_after_transcribe.json()["audio_sync_available"] is True
    transcribed_first = get_after_transcribe.json()["slot_budgets"][0]["chunks"][0]["words"][0]
    assert transcribed_first["start_s"] < 1.0

    allocate_response = client.patch(
        f"/api/jobs/{job.id}/caption",
        json={
            "script_text": "hello world again now",
            "auto_allocate": True,
        },
    )
    assert allocate_response.status_code == 200

    sync_response = client.patch(
        f"/api/jobs/{job.id}/caption",
        json={"audio_sync": True},
    )
    assert sync_response.status_code == 200
    synced = sync_response.json()
    first_words = synced["slot_budgets"][0]["chunks"][0]["words"]
    assert first_words[0]["end_s"] > first_words[0]["start_s"]
    assert first_words[0]["start_s"] == transcribed_first["start_s"]


def test_patch_slot_override_preserves_asr_word_timing_on_typo(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.audio.captions import (
        assign_transcribed_words_to_slot_overrides,
        assign_transcribed_words_with_timing_to_slots,
        serialize_word_timing,
    )
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.audio.transcribe_sources import TranscribeSourceResult
    from viral_editor.models import CaptionWord, MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_typo_patch"
    workspace.mkdir()
    (workspace / "input").mkdir()
    audio_path = workspace / "input" / "track.mp3"
    audio_path.write_bytes(b"fake")

    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=10.0,
        end_s=16.0,
        duration_s=6.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    persist_storyboard(workspace / "temp", storyboard)

    words = [
        CaptionWord(text="hello", start_s=10.5, end_s=10.8),
        CaptionWord(text="world", start_s=11.0, end_s=11.3),
        CaptionWord(text="again", start_s=13.2, end_s=13.5),
        CaptionWord(text="now", start_s=13.8, end_s=14.1),
    ]

    def fake_transcribe_from_audio_track(config, storyboard, *, workspace=None, options=None):
        slot_overrides = assign_transcribed_words_to_slot_overrides(
            words,
            storyboard.slots,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
        )
        timed_by_slot = assign_transcribed_words_with_timing_to_slots(
            words,
            storyboard.slots,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
        )
        return TranscribeSourceResult(
            script_text="hello world again now",
            slot_overrides=slot_overrides,
            word_timing_overrides={
                slot_id: serialize_word_timing(slot_words)
                for slot_id, slot_words in timed_by_slot.items()
            },
            words=words,
        )

    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.transcribe_from_audio_track",
        fake_transcribe_from_audio_track,
    )

    transcribe_response = client.post(
        f"/api/jobs/{job.id}/caption/transcribe",
        data={"source": "audio_track"},
    )
    assert transcribe_response.status_code == 200
    transcribed = transcribe_response.json()
    first_slot_id = next(iter(transcribed["slot_overrides"]))
    original_override = transcribed["slot_overrides"][first_slot_id]
    original_first_start = transcribed["word_timing_overrides"][first_slot_id][0]["start_s"]
    typo_override = original_override.replace("hello", "helo", 1)

    patch_response = client.patch(
        f"/api/jobs/{job.id}/caption",
        json={
            "slot_overrides": {
                **transcribed["slot_overrides"],
                first_slot_id: typo_override,
            },
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    patched_words = patched["slot_budgets"][0]["chunks"][0]["words"]
    assert patched_words[0]["text"] == "helo"
    assert patched_words[0]["start_s"] == original_first_start
    assert patched["slot_budgets"][0]["has_asr_timing"] is True


def test_patch_word_timing_overrides_updates_single_word(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.audio.captions import (
        assign_transcribed_words_to_slot_overrides,
        assign_transcribed_words_with_timing_to_slots,
        serialize_word_timing,
    )
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.audio.transcribe_sources import TranscribeSourceResult
    from viral_editor.models import CaptionWord, MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_word_timing_patch"
    workspace.mkdir()
    (workspace / "input").mkdir()
    audio_path = workspace / "input" / "track.mp3"
    audio_path.write_bytes(b"fake")

    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=10.0,
        end_s=16.0,
        duration_s=6.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    persist_storyboard(workspace / "temp", storyboard)

    words = [
        CaptionWord(text="trust", start_s=10.5, end_s=10.8),
        CaptionWord(text="the", start_s=11.0, end_s=11.3),
        CaptionWord(text="Emperor", start_s=13.2, end_s=13.5),
    ]

    def fake_transcribe_from_audio_track(config, storyboard, *, workspace=None, options=None):
        slot_overrides = assign_transcribed_words_to_slot_overrides(
            words,
            storyboard.slots,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
        )
        timed_by_slot = assign_transcribed_words_with_timing_to_slots(
            words,
            storyboard.slots,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
        )
        return TranscribeSourceResult(
            script_text="trust the Emperor",
            slot_overrides=slot_overrides,
            word_timing_overrides={
                slot_id: serialize_word_timing(slot_words)
                for slot_id, slot_words in timed_by_slot.items()
            },
            words=words,
        )

    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.transcribe_from_audio_track",
        fake_transcribe_from_audio_track,
    )

    transcribe_response = client.post(
        f"/api/jobs/{job.id}/caption/transcribe",
        data={"source": "audio_track"},
    )
    assert transcribe_response.status_code == 200
    transcribed = transcribe_response.json()
    emperor_slot_id = next(
        slot_id
        for slot_id, timing in transcribed["word_timing_overrides"].items()
        if any(word["text"] == "Emperor" for word in timing)
    )
    updated_timing = [
        dict(word) for word in transcribed["word_timing_overrides"][emperor_slot_id]
    ]
    emperor_index = next(
        index
        for index, word in enumerate(updated_timing)
        if word["text"] == "Emperor"
    )
    updated_timing[emperor_index]["text"] = "Emperer"
    updated_override = " ".join(word["text"] for word in updated_timing)

    patch_response = client.patch(
        f"/api/jobs/{job.id}/caption",
        json={
            "slot_overrides": {
                **transcribed["slot_overrides"],
                emperor_slot_id: updated_override,
            },
            "word_timing_overrides": {
                emperor_slot_id: updated_timing,
            },
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    patched_words = [
        word
        for budget in patched["slot_budgets"]
        for chunk in budget["chunks"]
        for word in chunk["words"]
    ]
    emperor_word = next(word for word in patched_words if word["text"] == "Emperer")
    assert emperor_word["start_s"] == updated_timing[emperor_index]["start_s"]


def test_patch_word_timing_overrides_removing_last_word_clears_slot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.audio.captions import (
        assign_transcribed_words_to_slot_overrides,
        assign_transcribed_words_with_timing_to_slots,
        serialize_word_timing,
    )
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.audio.transcribe_sources import TranscribeSourceResult
    from viral_editor.models import CaptionWord, MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_word_remove_clear"
    workspace.mkdir()
    (workspace / "input").mkdir()
    audio_path = workspace / "input" / "track.mp3"
    audio_path.write_bytes(b"fake")

    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=10.0,
        end_s=16.0,
        duration_s=6.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    persist_storyboard(workspace / "temp", storyboard)

    words = [CaptionWord(text="only", start_s=10.5, end_s=10.8)]

    def fake_transcribe_from_audio_track(config, storyboard, *, workspace=None, options=None):
        slot_overrides = assign_transcribed_words_to_slot_overrides(
            words,
            storyboard.slots,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
        )
        timed_by_slot = assign_transcribed_words_with_timing_to_slots(
            words,
            storyboard.slots,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
        )
        return TranscribeSourceResult(
            script_text="only",
            slot_overrides=slot_overrides,
            word_timing_overrides={
                slot_id: serialize_word_timing(slot_words)
                for slot_id, slot_words in timed_by_slot.items()
            },
            words=words,
        )

    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.transcribe_from_audio_track",
        fake_transcribe_from_audio_track,
    )

    transcribe_response = client.post(
        f"/api/jobs/{job.id}/caption/transcribe",
        data={"source": "audio_track"},
    )
    assert transcribe_response.status_code == 200
    transcribed = transcribe_response.json()
    slot_id = next(iter(transcribed["word_timing_overrides"]))

    patch_response = client.patch(
        f"/api/jobs/{job.id}/caption",
        json={
            "word_timing_overrides": {slot_id: []},
            "slot_overrides": {
                **transcribed["slot_overrides"],
                slot_id: "",
            },
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["slot_overrides"].get(slot_id, "") == ""
    cleared_budget = next(
        budget for budget in patched["slot_budgets"] if budget["slot_id"] == slot_id
    )
    assert cleared_budget["has_asr_timing"] is False
    assert cleared_budget["actual_words"] == 0


def test_patch_word_timing_overrides_removing_single_word_updates_slot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.models import MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_word_remove_partial"
    workspace.mkdir()
    (workspace / "input").mkdir()
    audio_path = workspace / "input" / "track.mp3"
    audio_path.write_bytes(b"fake")

    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=10.0,
        end_s=16.0,
        duration_s=6.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    persist_storyboard(workspace / "temp", storyboard)
    slot_id = storyboard.slots[0].id
    timing = [
        {"text": "one", "start_s": 0.1, "end_s": 0.4},
        {"text": "two", "start_s": 0.5, "end_s": 0.8},
        {"text": "three", "start_s": 0.9, "end_s": 1.2},
    ]

    patch_response = client.patch(
        f"/api/jobs/{job.id}/caption",
        json={
            "word_timing_overrides": {slot_id: [timing[0], timing[2]]},
            "slot_overrides": {slot_id: "one three"},
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    slot_budget = next(
        budget for budget in patched["slot_budgets"] if budget["slot_id"] == slot_id
    )
    patched_words = [
        word for chunk in slot_budget["chunks"] for word in chunk["words"]
    ]
    assert [word["text"] for word in patched_words] == ["one", "three"]
    assert patched_words[0]["start_s"] == 0.1
    assert patched_words[1]["start_s"] == 0.9


def test_transcribe_caption_from_clips_builds_per_slot_overrides(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import assign_slot_clip, persist_storyboard
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.models import CaptionWord, MediaInfo, MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_transcribe_clips"
    workspace.mkdir()
    input_dir = workspace / "input"
    input_dir.mkdir()
    audio_path = input_dir / "track.mp3"
    audio_path.write_bytes(b"fake")
    clip_a = input_dir / "clip_a.mp4"
    clip_b = input_dir / "clip_b.mp4"
    clip_a.write_bytes(b"fake")
    clip_b.write_bytes(b"fake")

    from viral_editor.models import ClipInput

    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[
            ClipInput(id="clip_a", path=clip_a.resolve(), order=0),
            ClipInput(id="clip_b", path=clip_b.resolve(), order=1),
        ],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=0.0,
        end_s=10.0,
        duration_s=10.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    media_a = MediaInfo(path=clip_a, duration_s=5.0, has_video=True, has_audio=True)
    media_b = MediaInfo(path=clip_b, duration_s=5.0, has_video=True, has_audio=True)
    storyboard = assign_slot_clip(
        storyboard,
        storyboard.slots[0].id,
        clip_id="clip_a",
        filename="clip_a.mp4",
        crop_start_s=0.0,
        crop_end_s=5.0,
        media=media_a,
    )
    storyboard = assign_slot_clip(
        storyboard,
        storyboard.slots[1].id,
        clip_id="clip_b",
        filename="clip_b.mp4",
        crop_start_s=0.0,
        crop_end_s=5.0,
        media=media_b,
    )
    persist_storyboard(workspace / "temp", storyboard)

    calls: list[Path] = []

    def fake_transcribe_audio(path, *, options=None):
        calls.append(path)
        if "clip_a" in path.name or calls.index(path) == 0:
            return "first clip words", [
                CaptionWord(text="first", start_s=0.1, end_s=0.4),
                CaptionWord(text="clip", start_s=0.5, end_s=0.8),
            ]
        return "second clip words", [
            CaptionWord(text="second", start_s=0.2, end_s=0.5),
            CaptionWord(text="clip", start_s=0.6, end_s=0.9),
        ]

    def fake_extract_audio_track(source, dest, *, start_s=None, end_s=None):
        dest.write_bytes(b"wav")
        return dest

    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.clip_media_for_storyboard",
        lambda config, storyboard: {
            "clip_a": media_a,
            "clip_b": media_b,
        },
    )
    monkeypatch.setattr(
        "viral_editor.audio.transcribe_sources.transcribe_audio",
        fake_transcribe_audio,
    )
    monkeypatch.setattr(
        "viral_editor.audio.transcribe_sources.extract_audio_track",
        fake_extract_audio_track,
    )

    response = client.post(
        f"/api/jobs/{job.id}/caption/transcribe",
        data={"source": "clips"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "clips"
    assert len(body["slot_overrides"]) >= 2
    assert body["word_timing_overrides"]


def test_transcribe_caption_from_clips_skips_silent_clips(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import assign_slot_clip, persist_storyboard
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.models import CaptionWord, MediaInfo, MusicBlock, ClipInput

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_transcribe_silent"
    workspace.mkdir()
    input_dir = workspace / "input"
    input_dir.mkdir()
    (input_dir / "track.mp3").write_bytes(b"fake")
    silent_clip = input_dir / "silent.mp4"
    silent_clip.write_bytes(b"fake")

    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[ClipInput(id="silent", path=silent_clip.resolve(), order=0)],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=0.0,
        end_s=6.0,
        duration_s=6.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    storyboard = assign_slot_clip(
        storyboard,
        storyboard.slots[0].id,
        clip_id="silent",
        filename="silent.mp4",
        crop_start_s=0.0,
        crop_end_s=3.0,
        media=MediaInfo(path=silent_clip, duration_s=3.0, has_video=True, has_audio=False),
    )
    persist_storyboard(workspace / "temp", storyboard)

    silent_media = MediaInfo(path=silent_clip, duration_s=3.0, has_video=True, has_audio=False)
    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.clip_media_for_storyboard",
        lambda config, storyboard: {"silent": silent_media},
    )
    monkeypatch.setattr(
        "viral_editor.audio.transcribe_sources.extract_audio_track",
        lambda *args, **kwargs: args[1],
    )
    monkeypatch.setattr(
        "viral_editor.audio.transcribe_sources.transcribe_audio",
        lambda path, *, options=None: ("", []),
    )

    response = client.post(
        f"/api/jobs/{job.id}/caption/transcribe",
        data={"source": "clips"},
    )
    assert response.status_code == 200
    assert "silent" in response.json()["skipped_clip_ids"]


def test_transcribe_caption_custom_upload_distributes_by_reading_speed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.models import CaptionWord, MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_transcribe_custom"
    workspace.mkdir()
    (workspace / "input").mkdir()
    (workspace / "input" / "track.mp3").write_bytes(b"fake")

    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=0.0,
        end_s=10.0,
        duration_s=10.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    persist_storyboard(workspace / "temp", storyboard)

    words = [CaptionWord(text=f"word{i}", start_s=i * 0.4, end_s=i * 0.4 + 0.3) for i in range(10)]

    monkeypatch.setattr(
        "viral_editor.audio.transcribe_sources.probe_media",
        lambda path: type("M", (), {"has_audio": True})(),
    )
    monkeypatch.setattr(
        "viral_editor.audio.transcribe_sources.extract_audio_track",
        lambda source, dest, **kwargs: dest,
    )
    monkeypatch.setattr(
        "viral_editor.audio.transcribe_sources.transcribe_audio",
        lambda path, *, options=None: (" ".join(word.text for word in words), words),
    )

    response = client.post(
        f"/api/jobs/{job.id}/caption/transcribe",
        data={"source": "custom"},
        files={"media": ("voice.wav", b"fake-audio", "audio/wav")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "custom"
    assert body["slot_overrides"]
    assert body["word_timing_overrides"]
    assert sum(len(text.split()) for text in body["slot_overrides"].values()) == 10


def test_transcribe_caption_rejects_missing_custom_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_transcribe_missing"
    workspace.mkdir()
    (workspace / "input").mkdir()
    (workspace / "input" / "track.mp3").write_bytes(b"fake")
    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)

    response = client.post(
        f"/api/jobs/{job.id}/caption/transcribe",
        data={"source": "custom"},
    )
    assert response.status_code == 400


def test_transcribe_caption_accepts_language_and_translate(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.audio.transcribe import TranscribeOptions
    from viral_editor.models import CaptionWord, MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_transcribe_lang"
    workspace.mkdir()
    (workspace / "input").mkdir()
    audio_path = workspace / "input" / "track.mp3"
    audio_path.write_bytes(b"fake")

    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=0.0,
        end_s=10.0,
        duration_s=10.0,
        score=0.9,
        drop_count=1,
        transient_count=2,
        label="drop",
        reason="test",
    )
    persist_storyboard(workspace / "temp", plan_storyboard(block, features=None, transients=[]))

    captured: dict[str, TranscribeOptions | None] = {}

    def fake_transcribe_from_audio_track(config, storyboard, *, workspace=None, options=None):
        captured["options"] = options
        return type(
            "R",
            (),
            {
                "script_text": "cześć",
                "slot_overrides": {},
                "word_timing_overrides": {},
                "words": [CaptionWord(text="cześć", start_s=0.1, end_s=0.4)],
                "skipped_clip_ids": [],
            },
        )()

    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.transcribe_from_audio_track",
        fake_transcribe_from_audio_track,
    )

    response = client.post(
        f"/api/jobs/{job.id}/caption/transcribe",
        data={"source": "audio_track", "language": "pl", "translate": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "pl"
    assert body["translate"] is True
    assert captured["options"] == TranscribeOptions(language="pl", translate=True)


def test_transcribe_caption_rejects_unknown_language(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.routes.jobs.transcribe_available", lambda: True)

    from viral_editor.api.store import JobStore
    from viral_editor.api.runner import build_job_config

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_transcribe_bad_lang"
    workspace.mkdir()
    (workspace / "input").mkdir()
    (workspace / "input" / "track.mp3").write_bytes(b"fake")
    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)

    response = client.post(
        f"/api/jobs/{job.id}/caption/transcribe",
        data={"source": "audio_track", "language": "xx"},
    )
    assert response.status_code == 400


def _storyboard_job(client: TestClient, tmp_path) -> tuple[str, str]:
    from viral_editor.api.runner import build_job_config
    from viral_editor.api.storyboard import persist_storyboard
    from viral_editor.api.store import JobStore
    from viral_editor.audio.storyboard import plan_storyboard
    from viral_editor.models import MusicBlock

    store: JobStore = client.app.state.job_store
    workspace = tmp_path / "job_auto_rotate"
    workspace.mkdir()
    (workspace / "input").mkdir()
    (workspace / "input" / "track.mp3").write_bytes(b"fake")
    config = build_job_config(
        workspace=workspace,
        hook_text="Hook",
        emphasis_words=[],
        audio_filename="track.mp3",
        clips=[],
    )
    job = store.create(config, workspace=workspace)
    block = MusicBlock(
        id="block_a",
        start_s=0.0,
        end_s=6.0,
        duration_s=6.0,
        score=0.9,
        drop_count=1,
        transient_count=1,
        label="drop",
        reason="test",
    )
    storyboard = plan_storyboard(block, features=None, transients=[])
    persist_storyboard(workspace / "temp", storyboard)
    clip_slot = next(slot for slot in storyboard.slots if slot.role == "clip")
    return job.id, clip_slot.id


def test_assign_slot_video_auto_rotation_when_form_omits_rotation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    job_id, slot_id = _storyboard_job(client, tmp_path)

    from viral_editor.models import MediaInfo

    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.probe_media",
        lambda _path: MediaInfo(
            path=_path,
            duration_s=4.0,
            has_video=True,
            width=1920,
            height=1080,
        ),
    )
    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.run_auto_rotation",
        lambda *_args, **_kwargs: 90,
    )

    response = client.put(
        f"/api/jobs/{job_id}/slots/{slot_id}/clip",
        data={"crop_start_s": "0", "crop_end_s": "4"},
        files={"video": ("landscape.mp4", io.BytesIO(b"video-bytes"), "video/mp4")},
    )
    assert response.status_code == 200
    slot = next(item for item in response.json()["slots"] if item["id"] == slot_id)
    assert slot["rotation_deg"] == 90


def test_assign_slot_video_explicit_rotation_overrides_auto_detection(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    job_id, slot_id = _storyboard_job(client, tmp_path)

    from viral_editor.models import MediaInfo

    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.probe_media",
        lambda _path: MediaInfo(
            path=_path,
            duration_s=4.0,
            has_video=True,
            width=1920,
            height=1080,
        ),
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("run_auto_rotation should not run when rotation_deg is explicit")

    monkeypatch.setattr("viral_editor.api.routes.jobs.run_auto_rotation", fail_if_called)

    response = client.put(
        f"/api/jobs/{job_id}/slots/{slot_id}/clip",
        data={"crop_start_s": "0", "crop_end_s": "4", "rotation_deg": "180"},
        files={"video": ("landscape.mp4", io.BytesIO(b"video-bytes"), "video/mp4")},
    )
    assert response.status_code == 200
    slot = next(item for item in response.json()["slots"] if item["id"] == slot_id)
    assert slot["rotation_deg"] == 180


def test_create_job_sets_clip_rotation_from_auto_detection(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viral_editor.api.runner.ensure_ffmpeg", lambda: None)
    monkeypatch.setattr("viral_editor.api.routes.jobs.start_job", lambda *args, **kwargs: None)

    from viral_editor.models import MediaInfo

    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.probe_media",
        lambda _path: MediaInfo(
            path=_path,
            duration_s=4.0,
            has_video=True,
            width=1920,
            height=1080,
        ),
    )
    monkeypatch.setattr(
        "viral_editor.api.routes.jobs.run_auto_rotation",
        lambda *_args, **_kwargs: 90,
    )

    response = client.post(
        "/api/jobs",
        data={
            "hook_text": "Auto rotate",
            "clips": json.dumps([{"id": "clip_0", "order": 0, "role": "clip"}]),
        },
        files=[
            ("video", ("clip.mp4", io.BytesIO(b"video-bytes"), "video/mp4")),
            ("audio", ("track.mp3", io.BytesIO(b"audio-bytes"), "audio/mpeg")),
        ],
    )
    assert response.status_code == 201
    job_id = response.json()["id"]
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["config"]["clips"][0]["rotation_deg"] == 90


