# Phase 5 - Title / Hook Text Overlay Planner

**Goal:** Turn the hook text + style config into a precise `TitleSpec` (multiline layout, colors, emphasis, safe-zone placement, time window) for compositing over the teaser.

**Status:** Core. Depends on [Phase 1](phase-1-config-ingestion.md), [Phase 4](phase-4-teaser-spatial-fx.md).

---

## Objective

Compute the static hook overlay: wrap the headline into centered, high-readability multi-line text, apply duotone emphasis, keep everything inside a platform-safe bounding box, and place it over the teaser window. Pure planning here; FFmpeg rendering (drawtext or burned ASS) is in [Phase 6](phase-6-render.md).

## Contract

### Input
- `TitleConfig` (hook text, `emphasis_words`), `StyleConfig` (font, fill, emphasis color, box color, `safe_padding_pct`), `RenderConfig` (width/height/fps), `TeaserSpec` (window).

### Output: `TitleSpec`
```json
{
  "lines": ["I built this in", "30 DAYS"],
  "font": "Montserrat Black",
  "size_px": 96,
  "fill": "#FFFFFF",
  "emphasis": { "words": ["30", "days"], "color": "#FFD700" },
  "box": { "color": "rgba(0,0,0,0.85)", "padding_px": 24, "radius_px": 16 },
  "anchor": "center",
  "safe_rect": { "x": 108, "y": 192, "w": 864, "h": 1536 },
  "window_s": { "start": 0.0, "end": 2.5 }
}
```

## Detailed design

### 1. Safe zone
- `safe_rect` = viewport inset by `safe_padding_pct` (default 10%) on all sides: for `1080x1920`, that's `x=108, y=192, w=864, h=1536`. This clears TikTok/Reels native UI.

### 2. Text wrapping & sizing
- Greedy word-wrap into lines that fit `safe_rect.w` at the chosen font size; auto-shrink font size until all lines fit within `safe_rect` height (binary search between `min_px` and `max_px`).
- Requires text metrics. Two options:
  - **Pillow (`ImageFont`)** to measure glyph widths precisely for the actual font file (preferred for correctness). Adds `Pillow` as a dependency.
  - Heuristic average-glyph-width estimate (no extra dep, less accurate).
- Decision: use **Pillow** for measurement (accuracy matters for centered boxes) - add to `requirements.txt`.

### 3. Emphasis
- Match `emphasis_words` (case-insensitive) within lines; those tokens render in `emphasis_color`. Per-word coloring in FFmpeg `drawtext` is awkward, so prefer generating an **ASS subtitle** with inline color overrides for the emphasis spans (cleaner multi-color + pill box). Document drawtext as the simpler fallback (whole-line emphasis only).

### 4. Background pill / shadow
- A semi-transparent rounded box (`box.color`, `radius_px`) sized to the text block + `padding_px`, OR a drop shadow. ASS supports box backgrounds (`BorderStyle=3`) and shadow; record parameters here.

### 5. Placement & timing
- Center the block in `safe_rect`. `window_s` = teaser window (default `0.0..2.5`).

## Pure-function shape

```python
def plan_title(
    title_cfg: TitleConfig,
    style: StyleConfig,
    render: RenderConfig,
    teaser: TeaserSpec,
    font_path: Path,
) -> TitleSpec: ...
```

Pipeline writes `temp/title_spec.json` (and, if using ASS, Phase 6 generates `temp/title.ass`).

## Dependencies

- `Pillow` for text metrics (new dep, add in this phase).
- Font files: bundle/locate `Montserrat Black` / `Impact`; resolve a concrete `font_path` (document where fonts live, e.g., `assets/fonts/`).
- Teaser window from [Phase 4](phase-4-teaser-spatial-fx.md).

## Testing

- Wrapping: long headline wraps into >=2 lines that fit `safe_rect`; very long text shrinks font.
- Safe rect math for `1080x1920` and an alternate resolution.
- Emphasis matching is case-insensitive and token-accurate.
- Determinism (no randomness unless palette randomization is enabled via seed).

## Acceptance criteria

- Hook text produces a `TitleSpec` that fits the safe zone with correct emphasis tokens.
- Spec is sufficient for Phase 6 to render without further layout decisions.

## Risks & mitigations

- **Missing fonts on the system:** bundle the font file and pass an explicit `fontfile=`/ASS font dir rather than relying on system font names.
- **Per-word color complexity in drawtext:** use ASS for multi-color; keep drawtext as a documented fallback.
- **Emoji/Unicode in hook text:** note as out-of-scope for v1 (font dependent).
