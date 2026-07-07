"""Caption API helpers."""

from __future__ import annotations

import json
import time

from viral_editor.audio.captions import (
    WPS_PRESETS,
    build_caption_chunks_for_slots,
    suggested_word_count,
)
from viral_editor.audio.transcribe import transcribe_available
from viral_editor.api.schemas import (
    CaptionChunkResponse,
    CaptionResponse,
    CaptionStyleResponse,
    CaptionWordResponse,
    SlotCaptionBudgetResponse,
    WpsPresetResponse,
)
from viral_editor.config import JobConfig
from viral_editor.models import CaptionStyle, Storyboard


def _style_response(style: CaptionStyle) -> CaptionStyleResponse:
    return CaptionStyleResponse(
        font_family=style.font_family,
        fill_color=style.fill_color,
        emphasis_color=style.emphasis_color,
        outline_color=style.outline_color,
        outline_enabled=style.outline_enabled,
        box_enabled=style.box_enabled,
        box_color=style.box_color,
        position=style.position,
        size_scale=style.size_scale,
        safe_padding_pct=style.safe_padding_pct,
        karaoke_enabled=style.karaoke_enabled,
    )


def build_caption_response(config: JobConfig, storyboard: Storyboard | None) -> CaptionResponse:
    slots = sorted(storyboard.slots, key=lambda slot: slot.order) if storyboard else []
    chunks_by_slot = (
        build_caption_chunks_for_slots(
            config.caption,
            slots,
            emphasis_words=config.hook.emphasis_words,
        )
        if slots
        else {}
    )

    slot_budgets: list[SlotCaptionBudgetResponse] = []
    for slot in slots:
        chunks = chunks_by_slot.get(slot.id, [])
        actual_words = sum(len(chunk.words) for chunk in chunks)
        slot_budgets.append(
            SlotCaptionBudgetResponse(
                slot_id=slot.id,
                label=slot.label,
                duration_s=slot.target_duration_s,
                suggested_words=suggested_word_count(
                    slot.target_duration_s,
                    config.caption.words_per_second,
                ),
                actual_words=actual_words,
                chunks=[
                    CaptionChunkResponse(
                        words=[
                            CaptionWordResponse(
                                text=word.text,
                                start_s=word.start_s,
                                end_s=word.end_s,
                                emphasis=word.emphasis,
                            )
                            for word in chunk.words
                        ],
                        start_s=chunk.start_s,
                        end_s=chunk.end_s,
                    )
                    for chunk in chunks
                ],
            )
        )

    stored_overrides = dict(config.caption.slot_overrides)
    effective_overrides = dict(stored_overrides)
    for slot in slots:
        if effective_overrides.get(slot.id, "").strip():
            continue
        chunks = chunks_by_slot.get(slot.id, [])
        words = [word.text for chunk in chunks for word in chunk.words]
        if words:
            effective_overrides[slot.id] = " ".join(words)

    # #region agent log
    try:
        with open("debug-5521a3.log", "a", encoding="utf-8") as _dbg:
            for _slot in slots:
                _chunks = chunks_by_slot.get(_slot.id, [])
                _chunk_words = sum(len(c.words) for c in _chunks)
                _stored = stored_overrides.get(_slot.id, "")
                _effective = effective_overrides.get(_slot.id, "")
                _dbg.write(
                    json.dumps(
                        {
                            "sessionId": "5521a3",
                            "runId": "post-fix",
                            "hypothesisId": "H1-H2",
                            "location": "caption.py:build_caption_response",
                            "message": "slot override vs chunks",
                            "data": {
                                "slot_id": _slot.id,
                                "stored_override_len": len(_stored.strip()),
                                "effective_override_len": len(_effective.strip()),
                                "chunk_word_count": _chunk_words,
                                "has_stored": bool(_stored.strip()),
                                "chunks_only": not _stored.strip() and _chunk_words > 0,
                            },
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
    except OSError:
        pass
    # #endregion

    return CaptionResponse(
        script_text=config.caption.script_text,
        words_per_second=config.caption.words_per_second,
        hook_text=config.hook.text,
        emphasis_words=list(config.hook.emphasis_words),
        hook_style=_style_response(config.hook_style),
        caption_style=_style_response(config.caption.style),
        slot_overrides=effective_overrides,
        slot_budgets=slot_budgets,
        wps_presets=[
            WpsPresetResponse(words_per_second=preset.words_per_second, label=preset.label)
            for preset in WPS_PRESETS
        ],
        transcribe_available=transcribe_available(),
        audio_sync_available=bool(config.caption.asr_words),
    )


def apply_caption_style_patch(
    style: CaptionStyle,
    patch,
) -> CaptionStyle:
    updates = patch.model_dump(exclude_unset=True)
    return style.model_copy(update=updates)
