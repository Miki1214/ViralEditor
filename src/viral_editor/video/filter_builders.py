"""Pure FFmpeg filtergraph builders shared by preview and final render."""

from __future__ import annotations

from viral_editor.models import CaptionChunk, CaptionStyle, FxEvent, SpeedRampPlan, SpeedSegment, TeaserSpec
from viral_editor.utils.ffmpeg import escape_drawtext_text, resolve_drawtext_fontfile
from viral_editor.utils.fonts import resolve_font_for_ffmpeg
from viral_editor.video.spatial_fx import rotate_direction

DEFAULT_COMPOSITE_FPS = 30
CAPTION_MAX_LINES = 2
MIN_ROTATE_DECAY_S = 0.15
MIN_PAN_DECAY_S = 0.15
PAN_HEADROOM = 0.15
PAN_MAX_FRACTION = 0.95
DEFAULT_ROTATE_GAIN = 3.0
DEFAULT_PAN_GAIN = 1.5


def fx_decay_ramp(t0: float, dur: float) -> str:
    """Linear 1→0 ramp; commas unescaped — used inside quoted ffmpeg expressions."""
    return f"(1-(t-{t0:.6f})/{dur:.6f})"


def zoom_scale_factor(t0: float, dur: float, zoom: float) -> str:
    t1 = t0 + dur
    ramp = fx_decay_ramp(t0, dur)
    return f"if(between(t,{t0:.6f},{t1:.6f}),1+({zoom:.6f}-1)*{ramp},1)"


def pan_event_duration(event: FxEvent, fps: float) -> float:
    return max(
        event.decay_frames / max(fps, 1.0),
        MIN_PAN_DECAY_S,
        1.0 / fps,
    )


def combined_pan_x_expression(
    translate_events: list[FxEvent],
    *,
    fps: float,
    intensity: float,
    pan_gain: float = DEFAULT_PAN_GAIN,
) -> str:
    """Sum time-gated horizontal offsets; input is already headroom-scaled."""
    terms: list[str] = []
    for event in translate_events:
        t0 = event.timestamp_s
        dur = pan_event_duration(event, fps)
        t1 = t0 + dur
        sign = event.direction if event.direction != 0 else 1
        ramp = fx_decay_ramp(t0, dur)
        pan_strength = event.magnitude * intensity * PAN_MAX_FRACTION * pan_gain
        terms.append(
            f"if(between(t,{t0:.6f},{t1:.6f}),"
            f"{sign}*((iw-ow)/2)*{pan_strength:.6f}*{ramp},0)"
        )
    if not terms:
        return "(iw-ow)/2"
    return f"(iw-ow)/2+({'+' .join(terms)})"


def normalize_segment_timeline(
    parts: list[str],
    input_ref: str,
    label: str,
    *,
    fps: float = DEFAULT_COMPOSITE_FPS,
) -> str:
    """Force a common fps/timebase so xfade/concat inputs match."""
    parts.append(
        f"{input_ref}fps={fps},format=yuv420p,settb=1/{fps}[{label}]"
    )
    return f"[{label}]"


def source_trim_spans(
    src_start: float,
    src_end: float,
    src_duration: float,
    *,
    allow_wrap: bool,
) -> list[tuple[float, float]]:
    """Expand a possibly wrapped source range into in-bounds trim spans."""
    if src_end <= src_start + 1e-9:
        return []
    if src_duration <= 0:
        return [(src_start, src_end)]

    if not allow_wrap and src_end <= src_duration + 1e-6:
        return [(max(0.0, src_start), min(src_end, src_duration))]

    spans: list[tuple[float, float]] = []
    pos = src_start
    while pos < src_end - 1e-9:
        local = pos % src_duration
        remaining = src_end - pos
        to_cycle_end = src_duration - local if local > 1e-9 else src_duration
        chunk = min(remaining, to_cycle_end)
        if chunk <= 1e-9:
            chunk = min(remaining, src_duration)
        spans.append((local, local + chunk))
        pos += chunk
    return spans


def spatial_crop_filter(
    crop_x: float,
    crop_y: float,
    crop_w: float,
    crop_h: float,
) -> str:
    """Crop/pad chain for normalized spatial crop; may letterbox when extending outside the frame."""
    eps = 1e-6
    within = (
        crop_x >= -eps
        and crop_y >= -eps
        and crop_x + crop_w <= 1.0 + eps
        and crop_y + crop_h <= 1.0 + eps
    )
    if within:
        return (
            f"crop=iw*{crop_w:.6f}:ih*{crop_h:.6f}:"
            f"iw*{crop_x:.6f}:ih*{crop_y:.6f}"
        )

    pad_left = max(0.0, -crop_x)
    pad_top = max(0.0, -crop_y)
    pad_right = max(0.0, crop_x + crop_w - 1.0)
    pad_bottom = max(0.0, crop_y + crop_h - 1.0)
    denom_w = 1.0 + pad_left + pad_right
    denom_h = 1.0 + pad_top + pad_bottom

    pad_filter = (
        f"pad="
        f"w=iw+max(0\\,-trunc(iw*{crop_x:.6f}))+max(0\\,trunc(iw*{crop_x:.6f}+iw*{crop_w:.6f})-iw):"
        f"h=ih+max(0\\,-trunc(ih*{crop_y:.6f}))+max(0\\,trunc(ih*{crop_y:.6f}+ih*{crop_h:.6f})-ih):"
        f"x=max(0\\,-trunc(iw*{crop_x:.6f})):"
        f"y=max(0\\,-trunc(ih*{crop_y:.6f})):color=black"
    )
    crop_filter = (
        f"crop="
        f"w=trunc(iw*{crop_w:.6f}/{denom_w:.6f}):"
        f"h=trunc(ih*{crop_h:.6f}/{denom_h:.6f}):"
        f"x=trunc(max(0\\,-trunc(iw*{crop_x:.6f}/{denom_w:.6f}))+trunc(iw*{crop_x:.6f}/{denom_w:.6f})):"
        f"y=trunc(max(0\\,-trunc(ih*{crop_y:.6f}/{denom_h:.6f}))+trunc(ih*{crop_y:.6f}/{denom_h:.6f}))"
    )
    return f"{pad_filter},{crop_filter}"


def visual_filters(
    width: int,
    height: int,
    *,
    rotation_deg: int = 0,
    fit_mode: str = "contain",
    spatial_crop: tuple[float, float, float, float] | None = None,
) -> str:
    """Rotate, optionally spatial-crop, then scale/pad to the output frame."""
    parts: list[str] = []
    rot = rotation_deg % 360
    if rot == 90:
        parts.append("transpose=1")
    elif rot == 180:
        parts.append("hflip,vflip")
    elif rot == 270:
        parts.append("transpose=2")
    if spatial_crop is not None:
        crop_x, crop_y, crop_w, crop_h = spatial_crop
        parts.append(spatial_crop_filter(crop_x, crop_y, crop_w, crop_h))
        parts.append(f"scale={width}:{height},setsar=1")
    elif fit_mode == "cover":
        parts.append(
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1"
        )
    else:
        parts.append(
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
    return ",".join(parts)


def segment_filter_chains(
    segment: SpeedSegment,
    *,
    input_label: str,
    src_duration: float,
    width: int,
    height: int,
    label_prefix: str,
    allow_wrap: bool,
    rotation_deg: int = 0,
    fit_mode: str = "contain",
    spatial_crop: tuple[float, float, float, float] | None = None,
) -> tuple[list[str], str]:
    """Build filter chains for one output segment, including source loops."""
    out_len = max(segment.out_end_s - segment.out_start_s, 1e-6)
    speed = max(segment.speed_factor, 1e-6)
    spans = source_trim_spans(
        segment.src_start_s,
        segment.src_end_s,
        src_duration,
        allow_wrap=allow_wrap,
    )

    if not spans:
        spans = [(0.0, min(out_len * speed, max(src_duration, 1e-6)))]

    visual = visual_filters(
        width,
        height,
        rotation_deg=rotation_deg,
        fit_mode=fit_mode,
        spatial_crop=spatial_crop,
    )

    if len(spans) == 1:
        start, end = spans[0]
        label = label_prefix
        chain = (
            f"[{input_label}]trim=start={start:.6f}:end={end:.6f},"
            f"setpts=PTS-STARTPTS,"
            f"setpts=PTS/{speed:.6f},"
            f"{visual},"
            f"trim=duration={out_len:.6f},setpts=PTS-STARTPTS[{label}]"
        )
        return [chain], f"[{label}]"

    parts: list[str] = []
    span_labels: list[str] = []
    total_src = max(segment.src_end_s - segment.src_start_s, 1e-6)

    for index, (start, end) in enumerate(spans):
        span_src = max(end - start, 1e-6)
        span_out = out_len * (span_src / total_src)
        span_labels.append(f"{label_prefix}s{index}")
        parts.append(
            f"[{input_label}]trim=start={start:.6f}:end={end:.6f},"
            f"setpts=PTS-STARTPTS,"
            f"setpts=PTS/{speed:.6f},"
            f"{visual},"
            f"trim=duration={span_out:.6f},setpts=PTS-STARTPTS[{span_labels[-1]}]"
        )

    joined = "".join(f"[{name}]" for name in span_labels)
    merged = f"{label_prefix}merged"
    parts.append(f"{joined}concat=n={len(span_labels)}:v=1:a=0[{merged}]")
    parts.append(
        f"[{merged}]trim=duration={out_len:.6f},setpts=PTS-STARTPTS[{label_prefix}]"
    )
    return parts, f"[{label_prefix}]"


def _enable_between_expr(start_s: float, end_s: float) -> str:
    """Return an enable= expression with commas escaped for filter_complex."""
    return f"between(t\\,{start_s:.6f}\\,{end_s:.6f})"


def _enable_union_expr(windows: list[tuple[float, float]]) -> str | None:
    if not windows:
        return None
    parts = [_enable_between_expr(start_s, end_s) for start_s, end_s in windows]
    return parts[0] if len(parts) == 1 else "+".join(parts)


def _hook_title_windows(
    segments: list[SpeedSegment],
    segment_roles: list[str] | None,
) -> list[tuple[float, float]]:
    windows: list[tuple[float, float]] = []
    for index, segment in enumerate(segments):
        role = segment_roles[index] if segment_roles and index < len(segment_roles) else None
        if role in ("hook", "hook_start") or (role is None and index == 0):
            windows.append((segment.out_start_s, segment.out_end_s))
    return windows


def _ffmpeg_fontcolor(color: str) -> str:
    if color.startswith("#") and len(color) in (4, 7):
        hex_body = color[1:]
        if len(hex_body) == 3:
            hex_body = "".join(ch * 2 for ch in hex_body)
        return f"0x{hex_body.upper()}"
    return color


def _ffmpeg_boxcolor(color: str) -> str:
    if color.startswith("rgba(") and color.endswith(")"):
        inner = color[5:-1]
        parts = [part.strip() for part in inner.split(",")]
        if len(parts) == 4:
            alpha = parts[3]
            return f"black@{alpha}"
    return _ffmpeg_fontcolor(color)


def _caption_y_expression(style: CaptionStyle) -> str:
    padding = style.safe_padding_pct / 100.0
    if style.position == "top":
        return f"h*{padding:.4f}"
    if style.position == "center":
        return f"(h-text_h)/2"
    return f"h*(1-{padding:.4f})-text_h"


def _max_caption_width_px(width: int, style: CaptionStyle) -> float:
    padding = style.safe_padding_pct / 100.0
    return width * max(0.5, 1.0 - (2.0 * padding))


def _caption_line_spacing_px(fontsize: int) -> int:
    return max(fontsize + 4, int(fontsize * 1.25))


def _caption_block_y_base_px(
    style: CaptionStyle,
    *,
    height: int,
    fontsize: int,
    num_lines: int,
    line_spacing: int,
) -> float:
    """Return y for the first line in a fixed-height caption block."""
    block_h = fontsize + max(0, num_lines - 1) * line_spacing
    padding = style.safe_padding_pct / 100.0
    if style.position == "top":
        return height * padding
    if style.position == "center":
        return (height - block_h) / 2.0
    return height * (1.0 - padding) - block_h


def _base_font_size(style: CaptionStyle, height: int) -> int:
    return max(12, int(height * 0.045 * style.size_scale))


def styled_drawtext(
    parts: list[str],
    input_ref: str,
    text: str,
    style: CaptionStyle,
    label: str,
    *,
    width: int,
    height: int,
    enable_expr: str | None = None,
    font_path: str | None = None,
    x_expr: str | None = None,
    y_expr: str | None = None,
    fontcolor_override: str | None = None,
    fontsize_override: int | None = None,
    fix_bounds: bool = True,
) -> str:
    """Append a styled drawtext filter and return the output label ref."""
    resolved_font = font_path or resolve_font_for_ffmpeg(style.font_family)
    if not resolved_font or not text.strip():
        return input_ref

    escaped = escape_drawtext_text(text)
    fontsize = fontsize_override or _base_font_size(style, height)
    fontcolor = _ffmpeg_fontcolor(fontcolor_override or style.fill_color)
    y = y_expr or _caption_y_expression(style)
    x = x_expr or "(w-text_w)/2"
    enable = f":enable='{enable_expr}'" if enable_expr else ""
    bounds = ":fix_bounds=1" if fix_bounds else ""

    border = ""
    if style.outline_enabled:
        border = (
            f":borderw={max(2, fontsize // 14)}"
            f":bordercolor={_ffmpeg_fontcolor(style.outline_color)}"
        )

    box = ""
    if style.box_enabled:
        box = (
            f":box=1:boxcolor={_ffmpeg_boxcolor(style.box_color)}"
            f":boxborderw={max(4, fontsize // 6)}"
        )

    parts.append(
        f"{input_ref}drawtext=text='{escaped}':fontfile='{resolved_font}'"
        f":fontsize={fontsize}:fontcolor={fontcolor}:x={x}:y={y}{border}{box}{bounds}"
        f":expansion=none{enable}[{label}]"
    )
    return f"[{label}]"


def drawtext_hook_overlay(
    parts: list[str],
    input_ref: str,
    hook_text: str,
    label: str,
    *,
    style: CaptionStyle | None = None,
    width: int = 360,
    height: int = 640,
    enable_expr: str | None = None,
) -> str:
    caption_style = style or CaptionStyle(position="top")
    return styled_drawtext(
        parts,
        input_ref,
        hook_text,
        caption_style,
        label,
        width=width,
        height=height,
        enable_expr=enable_expr,
    )


def build_hook_title_overlay(
    parts: list[str],
    input_ref: str,
    hook_text: str,
    *,
    style: CaptionStyle | None = None,
    segments: list[SpeedSegment],
    segment_roles: list[str] | None = None,
    width: int,
    height: int,
    label: str = "hooktitle",
) -> str:
    """Overlay hook title on a motion-stabilized frame with slot-timed visibility."""
    windows = _hook_title_windows(segments, segment_roles)
    if not hook_text or not hook_text.strip() or not windows:
        return input_ref
    return drawtext_hook_overlay(
        parts,
        input_ref,
        hook_text,
        label,
        style=style,
        width=width,
        height=height,
        enable_expr=_enable_union_expr(windows),
    )


def build_caption_filter_chain(
    parts: list[str],
    input_ref: str,
    *,
    chunks_by_slot: dict[str, list[CaptionChunk]],
    segments: list[SpeedSegment],
    slot_ids: list[str],
    style: CaptionStyle,
    label_prefix: str,
    width: int,
    height: int,
    slot_offsets: dict[str, float] | None = None,
) -> str:
    """Overlay timed phrase captions on a composed segment reference."""
    from viral_editor.utils.fonts import resolve_font_path
    from viral_editor.utils.text_metrics import layout_caption_chunk

    current = input_ref
    chunk_index = 0
    max_width_px = _max_caption_width_px(width, style)
    ffmpeg_font = resolve_font_for_ffmpeg(style.font_family)
    font_path = resolve_font_path(style.font_family)

    for segment_index, segment in enumerate(segments):
        slot_id = slot_ids[segment_index] if segment_index < len(slot_ids) else f"slot{segment_index}"
        # Captions follow the muxed audio / storyboard timeline, not the packed
        # composited video cursor (which can diverge when slots are unassigned).
        slot_offset = (
            slot_offsets[slot_id]
            if slot_offsets is not None and slot_id in slot_offsets
            else segment.out_start_s
        )
        for chunk in chunks_by_slot.get(slot_id, []):
            abs_start = slot_offset + chunk.start_s
            abs_end = slot_offset + chunk.end_s
            enable_expr = _enable_between_expr(abs_start, abs_end)
            words = [word.text for word in chunk.words]

            layouts: list = []
            fontsize = _base_font_size(style, height)
            if font_path is not None and words:
                layouts, fontsize = layout_caption_chunk(
                    words,
                    font_path=font_path,
                    base_font_size=fontsize,
                    max_width_px=max_width_px,
                    max_lines=CAPTION_MAX_LINES,
                )

            line_spacing = _caption_line_spacing_px(fontsize)
            block_y = _caption_block_y_base_px(
                style,
                height=height,
                fontsize=fontsize,
                num_lines=CAPTION_MAX_LINES,
                line_spacing=line_spacing,
            )

            if layouts:
                for line_index, layout in enumerate(layouts):
                    phrase = " ".join(layout.words)
                    label = f"{label_prefix}{chunk_index}l{line_index}"
                    y_px = block_y + line_index * line_spacing
                    current = styled_drawtext(
                        parts,
                        current,
                        phrase,
                        style,
                        label,
                        width=width,
                        height=height,
                        enable_expr=enable_expr,
                        font_path=ffmpeg_font,
                        y_expr=f"{y_px:.2f}",
                        fontsize_override=fontsize,
                    )
            else:
                phrase = " ".join(words)
                label = f"{label_prefix}{chunk_index}"
                current = styled_drawtext(
                    parts,
                    current,
                    phrase,
                    style,
                    label,
                    width=width,
                    height=height,
                    enable_expr=enable_expr,
                    font_path=ffmpeg_font,
                    fontsize_override=fontsize,
                )

            if style.karaoke_enabled and layouts:
                word_cursor = 0
                for line_index, layout in enumerate(layouts):
                    y_px = block_y + line_index * line_spacing
                    for offset in layout.word_offsets:
                        if word_cursor >= len(chunk.words):
                            break
                        word = chunk.words[word_cursor]
                        word_cursor += 1
                        x_expr = f"(w-{layout.line_width_px:.2f})/2+{offset.x_px:.2f}"
                        word_start = slot_offset + word.start_s
                        word_end = slot_offset + word.end_s
                        karaoke_label = (
                            f"{label_prefix}k{chunk_index}l{line_index}w{word_cursor - 1}"
                        )
                        current = styled_drawtext(
                            parts,
                            current,
                            word.text,
                            style,
                            karaoke_label,
                            width=width,
                            height=height,
                            enable_expr=_enable_between_expr(word_start, word_end),
                            font_path=ffmpeg_font,
                            x_expr=x_expr,
                            y_expr=f"{y_px:.2f}",
                            fontcolor_override=style.emphasis_color,
                            fontsize_override=fontsize,
                        )

            chunk_index += 1

    return current


def teaser_mask_filter(mask: str) -> str:
    if mask == "dir_blur":
        return "gblur=sigma=12"
    return "vignette=angle=PI/5"


def build_teaser_filter_chain(
    teaser: TeaserSpec,
    *,
    input_label: str,
    src_duration: float,
    width: int,
    height: int,
    rotation_deg: int = 0,
    fit_mode: str = "contain",
    spatial_crop: tuple[float, float, float, float] | None = None,
    hook_text: str | None = None,
    fps: float = DEFAULT_COMPOSITE_FPS,
) -> tuple[list[str], str]:
    """Extract and time-fit the teaser tail into a prepended clip."""
    parts: list[str] = []
    src_len = max(teaser.src_end_s - teaser.src_start_s, 1e-6)
    out_len = teaser.out_duration_s
    speed = src_len / out_len
    visual = visual_filters(
        width,
        height,
        rotation_deg=rotation_deg,
        fit_mode=fit_mode,
        spatial_crop=spatial_crop,
    )
    label = "teaser"
    chain = (
        f"[{input_label}]trim=start={teaser.src_start_s:.6f}:end={teaser.src_end_s:.6f},"
        f"setpts=PTS-STARTPTS,"
        f"setpts=PTS/{speed:.6f},"
        f"{visual},"
        f"trim=duration={out_len:.6f},setpts=PTS-STARTPTS,"
        f"{teaser_mask_filter(teaser.mask)}[{label}]"
    )
    parts.append(chain)
    current = f"[{label}]"
    if hook_text:
        current = drawtext_hook_overlay(
            parts,
            current,
            hook_text,
            f"{label}titled",
            width=width,
            height=height,
        )
    norm = normalize_segment_timeline(parts, current, "teasernorm", fps=fps)
    return parts, norm


def apply_spatial_fx_chain(
    parts: list[str],
    input_ref: str,
    fx_events: list[FxEvent],
    *,
    width: int,
    height: int,
    fps: float,
    seed: int,
    intensity: float,
    max_events: int = 24,
    rotate_gain: float = DEFAULT_ROTATE_GAIN,
    pan_gain: float = DEFAULT_PAN_GAIN,
    output_label: str = "outv",
) -> str:
    """Apply beat-synced zoom/rotate/pan impulses."""
    if not fx_events or intensity <= 0:
        parts.append(f"{input_ref}copy[{output_label}]")
        return f"[{output_label}]"

    current = input_ref.lstrip("[").rstrip("]")
    if current.startswith("["):
        current = input_ref.strip("[]")

    capped = fx_events[:max_events]
    translate_events = [event for event in capped if event.kind == "translate"]
    fx_index = 0

    for event in capped:
        if event.kind == "translate":
            continue
        t0 = event.timestamp_s
        if event.kind == "rotate":
            dur = max(
                event.decay_frames / max(fps, 1.0),
                MIN_ROTATE_DECAY_S,
                1.0 / fps,
            )
        else:
            dur = max(event.decay_frames / max(fps, 1.0), 1.0 / fps)
        t1 = t0 + dur
        out_label = f"fx{fx_index}"
        fx_index += 1
        if event.kind == "zoom":
            zoom = 1.0 + (event.magnitude - 1.0) * intensity
            factor = zoom_scale_factor(t0, dur, zoom)
            parts.append(
                f"[{current}]scale=w='trunc(iw*({factor}))':h='trunc(ih*({factor}))':eval=frame,"
                f"crop={width}:{height}:(iw-ow)/2:(ih-oh)/2[{out_label}]"
            )
        else:
            sign = rotate_direction(event, seed=seed)
            radians = (
                event.magnitude
                * sign
                * intensity
                * rotate_gain
                * 3.14159265
                / 180.0
            )
            ramp = fx_decay_ramp(t0, dur)
            parts.append(
                f"[{current}]rotate=enable='between(t,{t0:.6f},{t1:.6f})':"
                f"a='{radians:.8f}*{ramp}':c=none:ow={width}:oh={height}[{out_label}]"
            )
        current = out_label

    if translate_events:
        headroom = 1.0 + PAN_HEADROOM
        x_expr = combined_pan_x_expression(
            translate_events,
            fps=fps,
            intensity=intensity,
            pan_gain=pan_gain,
        )
        out_label = f"fx{fx_index}"
        parts.append(
            f"[{current}]scale=w='trunc(iw*{headroom:.6f})':h='trunc(ih*{headroom:.6f})',"
            f"crop={width}:{height}:x='{x_expr}':y='(ih-oh)/2'[{out_label}]"
        )
        current = out_label

    parts.append(f"[{current}]copy[{output_label}]")
    return f"[{output_label}]"


def build_proxy_filtergraph(
    plan: SpeedRampPlan,
    *,
    scale: tuple[int, int] = (360, 640),
    clip_input_index: dict[str, int] | None = None,
    clip_durations: dict[str, float] | None = None,
) -> str:
    """Build an ffmpeg filtergraph for segment-wise speed preview."""
    if not plan.segments:
        return f"nullsrc=s={scale[0]}x{scale[1]}:d=0.1,format=yuv420p"

    width, height = scale
    parts: list[str] = []
    concat_inputs: list[str] = []

    for index, segment in enumerate(plan.segments):
        label = f"v{index}"
        input_idx = 0
        src_dur = plan.src_duration_s
        allow_wrap = segment.source_id is None
        if segment.source_id and clip_input_index is not None:
            input_idx = clip_input_index.get(segment.source_id, 0)
        if segment.source_id and clip_durations is not None:
            src_dur = clip_durations.get(segment.source_id, plan.src_duration_s)
            allow_wrap = False
        chains, concat_ref = segment_filter_chains(
            segment,
            input_label=f"{input_idx}:v",
            src_duration=src_dur,
            width=width,
            height=height,
            label_prefix=label,
            allow_wrap=allow_wrap,
        )
        parts.extend(chains)
        concat_inputs.append(concat_ref)

    parts.append(f"{''.join(concat_inputs)}concat=n={len(plan.segments)}:v=1:a=0[outv]")
    return ";".join(parts)


def build_composite_filtergraph(
    segments: list[SpeedSegment],
    transitions: list[str],
    *,
    scale: tuple[int, int] = (360, 640),
    clip_input_index: dict[str, int] | None = None,
    clip_durations: dict[str, float] | None = None,
    clip_transforms: dict[str, tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    segment_transforms: list[tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    hook_text: str | None = None,
    hook_style: CaptionStyle | None = None,
    caption_chunks_by_slot: dict[str, list[CaptionChunk]] | None = None,
    caption_style: CaptionStyle | None = None,
    slot_ids: list[str] | None = None,
    slot_offsets: dict[str, float] | None = None,
    xfade_s: float = 0.25,
    segment_roles: list[str] | None = None,
    hook_start_mask: str | None = None,
    fx_events: list[FxEvent] | None = None,
    fx_seed: int = 42,
    fx_intensity: float = 1.0,
    fps: float = DEFAULT_COMPOSITE_FPS,
    rotate_gain: float = DEFAULT_ROTATE_GAIN,
    pan_gain: float = DEFAULT_PAN_GAIN,
) -> str:
    """Build ffmpeg filtergraph for storyboard slots with optional xfade + hook title."""
    if not segments:
        return f"nullsrc=s={scale[0]}x{scale[1]}:d=0.1,format=yuv420p"

    width, height = scale
    parts: list[str] = []
    segment_labels: list[str] = []

    for index, segment in enumerate(segments):
        label = f"slot{index}"
        input_idx = 0
        src_dur = segment.src_end_s - segment.src_start_s
        clip_id = segment.source_id
        if clip_id and clip_input_index is not None:
            if clip_id not in clip_input_index:
                raise ValueError(f"Composite preview missing ffmpeg input for clip {clip_id!r}")
            input_idx = clip_input_index[clip_id]
        if clip_id and clip_durations is not None:
            src_dur = clip_durations.get(clip_id, src_dur)
        rotation_deg = 0
        fit_mode = "contain"
        spatial_crop = None
        if segment_transforms is not None and index < len(segment_transforms):
            rotation_deg, fit_mode, spatial_crop = segment_transforms[index]
        elif clip_id and clip_transforms is not None:
            rotation_deg, fit_mode, spatial_crop = clip_transforms.get(
                clip_id,
                (0, "contain", None),
            )
        chains, concat_ref = segment_filter_chains(
            segment,
            input_label=f"{input_idx}:v",
            src_duration=max(src_dur, 1e-6),
            width=width,
            height=height,
            label_prefix=label,
            allow_wrap=False,
            rotation_deg=rotation_deg,
            fit_mode=fit_mode,
            spatial_crop=spatial_crop,
        )
        parts.extend(chains)
        role = segment_roles[index] if segment_roles and index < len(segment_roles) else None
        if role == "hook_start" and hook_start_mask:
            masked = f"{label}masked"
            parts.append(f"{concat_ref}{teaser_mask_filter(hook_start_mask)}[{masked}]")
            concat_ref = f"[{masked}]"
        segment_labels.append(concat_ref)

    if segment_labels:
        normalized_labels: list[str] = []
        for index, ref in enumerate(segment_labels):
            norm = f"slot{index}norm"
            normalized_labels.append(
                normalize_segment_timeline(parts, ref, norm, fps=fps)
            )
        segment_labels = normalized_labels

        if len(segment_labels) == 1:
            parts.append(f"{segment_labels[0]}copy[bodyv]")
        else:
            current = segment_labels[0]
            elapsed = segments[0].out_end_s - segments[0].out_start_s
            for index in range(1, len(segment_labels)):
                transition = transitions[index] if index < len(transitions) else "cut"
                nxt = segment_labels[index]
                seg_len = segments[index].out_end_s - segments[index].out_start_s
                if transition == "xfade" and xfade_s > 1e-6:
                    merged = f"xf{index}"
                    offset = max(elapsed - xfade_s, 0.0)
                    parts.append(
                        f"{current}{nxt}xfade=transition=fade:duration={xfade_s:.6f}:"
                        f"offset={offset:.6f}[{merged}]"
                    )
                    current = f"[{merged}]"
                    elapsed = offset + seg_len
                else:
                    merged = f"cat{index}"
                    parts.append(f"{current}{nxt}concat=n=2:v=1:a=0[{merged}]")
                    current = f"[{merged}]"
                    elapsed += seg_len
            parts.append(f"{current}copy[bodyv]")
        composed_ref = "[bodyv]"
    else:
        parts.append(f"nullsrc=s={width}x{height}:d=0.1,format=yuv420p[bodyv]")
        composed_ref = "[bodyv]"

    hook_windows = _hook_title_windows(segments, segment_roles) if hook_text else []
    has_hook_title = bool(hook_text and hook_text.strip() and hook_windows)
    has_captions = bool(
        caption_chunks_by_slot and caption_style and any(caption_chunks_by_slot.values())
    )
    has_steady_overlays = has_hook_title or has_captions
    motion_label = "motionv" if has_steady_overlays else "outv"
    composed_ref = apply_spatial_fx_chain(
        parts,
        composed_ref,
        fx_events or [],
        width=width,
        height=height,
        fps=fps,
        seed=fx_seed,
        intensity=fx_intensity,
        rotate_gain=rotate_gain,
        pan_gain=pan_gain,
        output_label=motion_label,
    )

    storyboard_dur = storyboard_mux_duration_s(segments)
    compressed_dur = composite_output_duration_s(
        segments,
        transitions=transitions,
        xfade_s=xfade_s,
    )
    pad_s = max(0.0, storyboard_dur - compressed_dur)
    if pad_s > 1e-6:
        pad_label = "storyboardpad"
        parts.append(
            f"{composed_ref}tpad=stop_mode=clone:stop_duration={pad_s:.6f}[{pad_label}]"
        )
        composed_ref = f"[{pad_label}]"

    if has_hook_title:
        composed_ref = build_hook_title_overlay(
            parts,
            composed_ref,
            hook_text,
            style=hook_style,
            segments=segments,
            segment_roles=segment_roles,
            width=width,
            height=height,
        )

    if has_captions:
        ids = slot_ids or [f"slot{index}" for index in range(len(segments))]
        composed_ref = build_caption_filter_chain(
            parts,
            composed_ref,
            chunks_by_slot=caption_chunks_by_slot,
            segments=segments,
            slot_ids=ids,
            style=caption_style,
            label_prefix="cap",
            width=width,
            height=height,
            slot_offsets=slot_offsets,
        )

    if has_steady_overlays:
        parts.append(f"{composed_ref}copy[outv]")
    return ";".join(parts)


def storyboard_mux_duration_s(segments: list[SpeedSegment]) -> float:
    """Packed segment timeline length — matches storyboard/audio caption clock."""
    return max(segments[-1].out_end_s if segments else 0.0, 0.1)


def composite_output_duration_s(
    segments: list[SpeedSegment],
    *,
    xfade_s: float = 0.25,
    transitions: list[str] | None = None,
) -> float:
    """Estimate xfade-compressed composited video body length before storyboard pad."""
    body = segments[-1].out_end_s if segments else 0.0
    if segments and transitions:
        for index in range(1, len(segments)):
            if index < len(transitions) and transitions[index] == "xfade":
                body -= xfade_s
    return max(body, 0.1)
