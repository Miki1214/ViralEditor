"""Transcription source handlers for caption auto-fill."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from viral_editor.audio.captions import (
    assign_transcribed_words_to_slot_overrides,
    assign_transcribed_words_with_timing_to_slots,
    distribute_script_to_slot_overrides,
    distribute_words_with_timing_to_slots,
    rebase_clip_words_to_slot_local,
    serialize_word_timing,
    transcribed_script_in_window,
)
from viral_editor.audio.storyboard import storyboard_to_segments
from viral_editor.audio.transcribe import TranscribeOptions, extract_audio_track, transcribe_audio
from viral_editor.config import JobConfig
from viral_editor.ingest.loader import probe_media
from viral_editor.models import CaptionWord, MediaInfo, Storyboard


@dataclass
class TranscribeSourceResult:
    script_text: str
    slot_overrides: dict[str, str] = field(default_factory=dict)
    word_timing_overrides: dict[str, list[dict[str, float | str]]] = field(
        default_factory=dict
    )
    words: list[CaptionWord] = field(default_factory=list)
    skipped_clip_ids: list[str] = field(default_factory=list)


def _scratch_dir(workspace: Path) -> Path:
    return workspace / "temp" / "transcribe_scratch"


def _cleanup_scratch(scratch: Path) -> None:
    if scratch.is_dir():
        shutil.rmtree(scratch, ignore_errors=True)


def transcribe_from_audio_track(
    config: JobConfig,
    storyboard: Storyboard | None,
    *,
    options: TranscribeOptions | None = None,
) -> TranscribeSourceResult:
    script_text, words = transcribe_audio(config.audio_path, options=options)
    slot_overrides: dict[str, str] = {}
    word_timing_overrides: dict[str, list[dict[str, float | str]]] = {}

    if storyboard and storyboard.slots:
        script_text = transcribed_script_in_window(
            words,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
        )
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
        word_timing_overrides = {
            slot_id: serialize_word_timing(slot_words)
            for slot_id, slot_words in timed_by_slot.items()
        }
        if not slot_overrides and script_text.strip():
            slot_overrides = distribute_script_to_slot_overrides(
                script_text,
                storyboard.slots,
                words_per_second=config.caption.words_per_second,
            )
            word_timing_overrides = {}

    return TranscribeSourceResult(
        script_text=script_text,
        slot_overrides=slot_overrides,
        word_timing_overrides=word_timing_overrides,
        words=words,
    )


def transcribe_from_clips(
    config: JobConfig,
    storyboard: Storyboard,
    clip_media: dict[str, MediaInfo],
    *,
    workspace: Path,
    options: TranscribeOptions | None = None,
) -> TranscribeSourceResult:
    scratch = _scratch_dir(workspace)
    scratch.mkdir(parents=True, exist_ok=True)
    skipped_clip_ids: list[str] = []
    slot_overrides: dict[str, str] = {}
    word_timing_overrides: dict[str, list[dict[str, float | str]]] = {}
    all_words: list[CaptionWord] = []
    script_parts: list[str] = []

    segments, _roles, slot_ids = storyboard_to_segments(storyboard, clip_media)
    clips_by_id = {clip.id: clip for clip in config.clips}
    slots_by_id = {slot.id: slot for slot in storyboard.slots}

    try:
        for segment, slot_id in zip(segments, slot_ids, strict=True):
            slot = slots_by_id[slot_id]
            clip = clips_by_id.get(segment.source_id or "")
            if clip is None or not clip.path.is_file():
                if segment.source_id:
                    skipped_clip_ids.append(segment.source_id)
                continue

            media = clip_media.get(segment.source_id or "")
            if media is None or not media.has_audio:
                if segment.source_id:
                    skipped_clip_ids.append(segment.source_id)
                continue

            segment_path = scratch / f"{slot_id}.wav"
            extract_audio_track(
                clip.path,
                segment_path,
                start_s=segment.src_start_s,
                end_s=segment.src_end_s,
            )
            segment_text, segment_words = transcribe_audio(segment_path, options=options)
            if not segment_text.strip():
                continue

            rebased_words = rebase_clip_words_to_slot_local(
                segment_words,
                slot=slot,
                speed_factor=segment.speed_factor,
            )
            slot_overrides[slot_id] = segment_text.strip()
            word_timing_overrides[slot_id] = serialize_word_timing(rebased_words)
            script_parts.append(segment_text.strip())
            all_words.extend(rebased_words)
    finally:
        _cleanup_scratch(scratch)

    return TranscribeSourceResult(
        script_text=" ".join(script_parts),
        slot_overrides=slot_overrides,
        word_timing_overrides=word_timing_overrides,
        words=all_words,
        skipped_clip_ids=skipped_clip_ids,
    )


def transcribe_from_custom_upload(
    config: JobConfig,
    storyboard: Storyboard | None,
    media_path: Path,
    *,
    workspace: Path,
    options: TranscribeOptions | None = None,
) -> TranscribeSourceResult:
    scratch = _scratch_dir(workspace)
    scratch.mkdir(parents=True, exist_ok=True)
    wav_path = scratch / "custom.wav"

    try:
        probed = probe_media(media_path)
        if probed.has_audio:
            extract_audio_track(media_path, wav_path)
        else:
            raise ValueError("Uploaded media has no audio track")

        script_text, words = transcribe_audio(wav_path, options=options)
        slot_overrides: dict[str, str] = {}
        word_timing_overrides: dict[str, list[dict[str, float | str]]] = {}

        if storyboard and storyboard.slots and words:
            slot_overrides, word_timing_overrides = distribute_words_with_timing_to_slots(
                words,
                storyboard.slots,
                words_per_second=config.caption.words_per_second,
            )

        return TranscribeSourceResult(
            script_text=script_text,
            slot_overrides=slot_overrides,
            word_timing_overrides=word_timing_overrides,
            words=words,
        )
    finally:
        _cleanup_scratch(scratch)
