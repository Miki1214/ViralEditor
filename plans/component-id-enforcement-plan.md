# Component ID Enforcement Plan

## Scope

All 18 React components in `web/src/components/` requiring granular element-level `id` attributes per the Component ID Enforcement Rule.

## Summary Table

| # | Component | File | Root ID Status | Missing IDs Count | Priority |
|---|-----------|------|---------------|-------------------|----------|
| 1 | AudioScopePanel | AudioScopePanel.tsx | NONE | ~25 | HIGH |
| 2 | ClipCropTimeline | ClipCropTimeline.tsx | NONE | ~10 | HIGH |
| 3 | ConfirmDialog | ConfirmDialog.tsx | PARTIAL | ~6 | HIGH |
| 4 | DebugConsolePanel | DebugConsolePanel.tsx | NONE | ~12 | MEDIUM |
| 5 | HookOverlayPanel | HookOverlayPanel.tsx | NONE | ~12 | HIGH |
| 6 | JobForm | JobForm.tsx | PARTIAL | ~8 | HIGH |
| 7 | MusicBlockCard | MusicBlockCard.tsx | NONE | ~10 | HIGH |
| 8 | OutputPanel | OutputPanel.tsx | NONE | ~8 | MEDIUM |
| 9 | PhonePreview | PhonePreview.tsx | NONE | ~15 | HIGH |
| 10 | RetentionFxPanel | RetentionFxPanel.tsx | NONE | ~30 | HIGH |
| 11 | ScopeCanvas | ScopeCanvas.tsx | NONE | ~20 | MEDIUM |
| 12 | SpatialCropModal | SpatialCropModal.tsx | PARTIAL | ~25 | HIGH |
| 13 | SpeedCurveCanvas | SpeedCurveCanvas.tsx | NONE | ~15 | LOW |
| 14 | StageTelemetry | StageTelemetry.tsx | NONE | ~18 | MEDIUM |
| 15 | StoryboardBlockPlayer | StoryboardBlockPlayer.tsx | NONE | ~20 | HIGH |
| 16 | StoryboardPanel | StoryboardPanel.tsx | PARTIAL | ~30 | HIGH |
| 17 | StoryboardScopeCanvas | StoryboardScopeCanvas.tsx | NONE | ~25 | MEDIUM |
| 18 | StoryboardSegmentsPanel | StoryboardSegmentsPanel.tsx | NONE | ~12 | LOW |

---

## 1. AudioScopePanel (AudioScopePanel.tsx)

### Current State
- Root `<section>` has NO `id`
- No element-level IDs anywhere

### Required Additions

```
component-root:    id="audio-scope-panel"
h2:                id="audio-scope-panel-title"
p (BPM line):      id="audio-scope-panel-track-info"
button (preset):   id="audio-scope-panel-target-{preset.value}"
span (preset label): id="audio-scope-panel-target-label-{preset.value}"
span (loop pct):   id="audio-scope-panel-target-pct-{preset.value}"
button (full):     id="audio-scope-panel-full-btn"
span (full label): id="audio-scope-panel-full-label"
p (scroll hint):   id="audio-scope-panel-scroll-hint"
div (scope scroll):id="audio-scope-panel-scroll-container"
div (scope inner): id="audio-scope-panel-waveform-container"
section (legend):  id="audio-scope-panel-legend"
button (detail toggle): id="audio-scope-panel-detail-toggle"
div (detail scroll): id="audio-scope-panel-detail-scroll"
p (target mismatch): id="audio-scope-panel-mismatch-msg"
p (blocks label):  id="audio-scope-panel-blocks-label"
div (block list):  id="audio-scope-panel-block-list"
spinner:           id="audio-scope-panel-spinner"
```

---

## 2. ClipCropTimeline (ClipCropTimeline.tsx)

### Current State
- No IDs on any element

### Required Additions

```
div (track):       id="clip-crop-timeline-track"
div (shade left):  id="clip-crop-timeline-shade-left"
div (shade right): id="clip-crop-timeline-shade-right"
div (range):       id="clip-crop-timeline-range-slider"
button (handle in): id="clip-crop-timeline-handle-in"
button (handle out): id="clip-crop-timeline-handle-out"
p (time display):  id="clip-crop-timeline-time-display"
span (preview rate): id="clip-crop-timeline-preview-rate"
```

---

## 3. ConfirmDialog (ConfirmDialog.tsx)

### Current State
- `id="confirm-dialog-title"` and `id="confirm-dialog-message"` exist on headings/paragraphs
- Missing IDs on buttons, overlay, dialog container

### Required Additions

```
div (overlay):     id="confirm-dialog-overlay"
button (close):    id="confirm-dialog-close-btn"
div (dialog):      id="confirm-dialog-container"
button (cancel):   id="confirm-dialog-cancel-btn"
button (confirm):  id="confirm-dialog-confirm-btn"
```

---

## 4. DebugConsolePanel (DebugConsolePanel.tsx)

### Current State
- No IDs on any element

### Required Additions

```
button (show):     id="debug-console-show-btn"
p (log count):     id="debug-console-log-count"
div (panel):       id="debug-console-panel"
p (title):         id="debug-console-title"
button (clear):    id="debug-console-clear-btn"
button (hide):     id="debug-console-hide-btn"
div (log list):    id="debug-console-log-list"
p (no entries):    id="debug-console-no-entries"
div (log entry):   id="debug-console-entry-{entry.id}"
p (entry level):   id="debug-console-entry-msg-{entry.id}"
span (entry time): id="debug-console-entry-time-{entry.id}"
span (entry detail): id="debug-console-entry-detail-{entry.id}"
```

---

## 5. HookOverlayPanel (HookOverlayPanel.tsx)

### Current State
- No IDs on any element

### Required Additions

```
div (panel):       id="hook-overlay-panel"
h2:                id="hook-overlay-title"
p (description):   id="hook-overlay-desc"
label (hook text): id="hook-overlay-hook-text-label"
input (hook text): id="hook-overlay-hook-text-input"
label (emphasis):  id="hook-overlay-emphasis-label"
input (emphasis):  id="hook-overlay-emphasis-input"
label (font):      id="hook-overlay-font-label"
select (font):     id="hook-overlay-font-select"
option:            id="hook-overlay-font-option-{font.value}"
label (fill):      id="hook-overlay-fill-label"
input (fill color): id="hook-overlay-fill-color-input"
label (emphasis color): id="hook-overlay-emphasis-color-label"
input (emphasis color): id="hook-overlay-emphasis-color-input"
label (padding):   id="hook-overlay-padding-label"
input (padding):   id="hook-overlay-padding-input"
```

---

## 6. JobForm (JobForm.tsx)

### Current State
- `id={projectNameId}` and `id={audioInputId}` exist on inputs
- Missing IDs on labels, form, file drop zone, project name label

### Required Additions

```
form:              id="job-form"
section:           id="job-form-section"
label (project):   id="job-form-project-label"
input (project):   id="job-form-project-input" (already has ID via useId)
h2 (music):        id="job-form-music-title"
p (music desc):    id="job-form-music-desc"
label (audio):     id="job-form-audio-label"
div (drop zone):   id="job-form-drop-zone"
input (audio):     id="job-form-audio-input" (already has ID via useId)
span (drop text):  id="job-form-drop-text"
span (analyzing):  id="job-form-analyzing-text"
p (disabled):      id="job-form-disabled-msg"
```

---

## 7. MusicBlockCard (MusicBlockCard.tsx)

### Current State
- No IDs on any element

### Required Additions

```
div (card):        id="music-block-card-{block.id}"
button (select):   id="music-block-card-select-{block.id}"
p (label/time):    id="music-block-card-label-{block.id}"
p (drops info):    id="music-block-card-info-{block.id}"
span (loop label): id="music-block-card-loop-label-{block.id}"
div (loop bar):    id="music-block-card-loop-bar-{block.id}"
div (loop fill):   id="music-block-card-loop-fill-{block.id}"
span (loop pct):   id="music-block-card-loop-pct-{block.id}"
p (reason):        id="music-block-card-reason-{block.id}"
div (play buttons): id="music-block-card-play-btns-{block.id}"
button (audition): id="music-block-card-audition-{block.id}"
button (loop):     id="music-block-card-loop-preview-{block.id}"
```

---

## 8. OutputPanel (OutputPanel.tsx)

### Current State
- No IDs on any element

### Required Additions

```
div (panel):       id="output-panel"
h2:                id="output-panel-title"
p (failed):        id="output-panel-failed-msg"
video (output):    id="output-panel-video"
a (download):      id="output-panel-download-btn"
p (analysis done): id="output-panel-analysis-msg"
p (pipeline):      id="output-panel-pipeline-msg"
div (artifacts):   id="output-panel-artifacts"
p (artifact title): id="output-panel-artifacts-title"
li (artifact):     id="output-panel-artifact-{name}"
```

---

## 9. PhonePreview (PhonePreview.tsx)

### Current State
- No IDs on any element

### Required Additions

```
div (outer):       id="phone-preview-container"
div (phone frame): id="phone-preview-frame"
video (preview):   id="phone-preview-video"
div (error overlay): id="phone-preview-error-overlay"
p (error text):    id="phone-preview-error-msg"
div (safe zone):   id="phone-preview-safe-zone"
span (safe label): id="phone-preview-safe-label"
div (hook text):   id="phone-preview-hook-text"
div (safe border): id="phone-preview-safe-border"
span (safe tag):   id="phone-preview-safe-tag"
div (top gradient): id="phone-preview-top-gradient"
p (preview info):  id="phone-preview-info"
```

---

## 10. RetentionFxPanel (RetentionFxPanel.tsx)

### Current State
- No IDs on any element

### Required Additions

```
div (panel):       id="retention-fx-panel"
h3:                id="retention-fx-title"
p (description):   id="retention-fx-desc"
p (score):         id="retention-fx-score"
p (preview label): id="retention-fx-preview-label"
section (teaser):  id="retention-fx-teaser-section"
label (toggle hook inversion): id="retention-fx-hook-inversion-toggle"
span (hook label): id="retention-fx-hook-inversion-label"
span (hook hint):  id="retention-fx-hook-inversion-hint"
button (toggle switch): id="retention-fx-hook-inversion-switch"
fieldset:          id="retention-fx-hook-split-fieldset"
legend:            id="retention-fx-hook-split-legend"
p (no downbeat):   id="retention-fx-no-downbeat-msg"
div (radio group): id="retention-fx-payoff-radios"
label (radio):     id="retention-fx-payoff-{payoff}-label"
input (radio):     id="retention-fx-payoff-{payoff}-radio"
span (payoff time): id="retention-fx-payoff-time-{payoff}"
span (buildup time): id="retention-fx-buildup-time-{payoff}"
span (only label): id="retention-fx-only-downbeat"
p (payoff share):  id="retention-fx-payoff-share-msg"
label (mask):      id="retention-fx-mask-label"
select (mask):     id="retention-fx-mask-select"
option (vignette): id="retention-fx-mask-vignette"
option (dir blur): id="retention-fx-mask-dir-blur"
section (spatial): id="retention-fx-spatial-section"
label (toggle spatial): id="retention-fx-spatial-toggle"
span (spatial label): id="retention-fx-spatial-label"
span (spatial hint): id="retention-fx-spatial-hint"
button (spatial switch): id="retention-fx-spatial-switch"
label (intensity): id="retention-fx-intensity-label"
input (intensity range): id="retention-fx-intensity-range"
span (intensity pct): id="retention-fx-intensity-pct"
label (density):   id="retention-fx-density-label"
input (density range): id="retention-fx-density-range"
span (density value): id="retention-fx-density-value"
div (pan section): id="retention-fx-pan-section"
label (toggle pan): id="retention-fx-pan-toggle"
span (pan label):  id="retention-fx-pan-label"
span (pan hint):   id="retention-fx-pan-hint"
button (pan switch): id="retention-fx-pan-switch"
label (pan cadence): id="retention-fx-pan-cadence-label"
select (pan cadence): id="retention-fx-pan-cadence-select"
option (auto):     id="retention-fx-pan-cadence-auto"
option (beats):    id="retention-fx-pan-cadence-beats"
option (downbeats): id="retention-fx-pan-cadence-downbeats"
label (pan hold):  id="retention-fx-pan-hold-label"
input (pan hold range): id="retention-fx-pan-hold-range"
span (pan hold ms): id="retention-fx-pan-hold-ms"
label (energy gate): id="retention-fx-energy-gate-label"
input (energy range): id="retention-fx-energy-range"
span (energy pct): id="retention-fx-energy-pct"
label (first pan toggle): id="retention-fx-first-pan-toggle"
span (first pan label): id="retention-fx-first-pan-label"
span (first pan hint): id="retention-fx-first-pan-hint"
button (first pan switch): id="retention-fx-first-pan-switch"
label (first pan by): id="retention-fx-first-pan-by-label"
input (first pan range): id="retention-fx-first-pan-range"
span (first pan value): id="retention-fx-first-pan-value"
p (fx counts):     id="retention-fx-fx-counts"
p (rotate info):   id="retention-fx-rotate-info"
```

---

## 11. ScopeCanvas (ScopeCanvas.tsx)

### Current State
- No IDs on any element (SVG-based component)

### Required Additions

```
svg:               id="scope-canvas-svg"
rect (section ribbon): id="scope-canvas-section-ribbon"
rect (block bg):   id="scope-canvas-block-{block.id}"
rect (block hit):  id="scope-canvas-block-hit-{block.id}"
path (waveform):   id="scope-canvas-waveform-path"
rect (ruler bg):   id="scope-canvas-ruler-bg"
line (ruler top):  id="scope-canvas-ruler-line"
g (tick group):    id="scope-canvas-tick-{timeS}"
line (tick mark):  id="scope-canvas-tick-mark-{timeS}"
text (tick label): id="scope-canvas-tick-label-{timeS}"
```

---

## 12. SpatialCropModal (SpatialCropModal.tsx)

### Current State
- `id="spatial-crop-title"` exists on h2
- Missing IDs on overlay, dialog, video, crop box, zoom controls

### Required Additions

```
div (overlay):     id="spatial-crop-overlay"
button (close):    id="spatial-crop-close-btn"
div (dialog):      id="spatial-crop-dialog"
p (description):   id="spatial-crop-desc"
button (cancel):   id="spatial-crop-cancel-btn"
div (viewport):    id="spatial-crop-viewport"
div (stage):       id="spatial-crop-stage"
video:             id="spatial-crop-video"
div (shade top):   id="spatial-crop-shade-top"
div (shade bottom): id="spatial-crop-shade-bottom"
div (shade left):  id="spatial-crop-shade-left"
div (shade right): id="spatial-crop-shade-right"
div (letterbox):   id="spatial-crop-letterbox-{index}"
div (crop box):    id="spatial-crop-box"
span (9:16 label): id="spatial-crop-label-916"
button (resize nw): id="spatial-crop-resize-nw"
button (resize se): id="spatial-crop-resize-se"
button (reset):    id="spatial-crop-reset-btn"
button (fit):      id="spatial-crop-fit-btn"
div (zoom group):  id="spatial-crop-zoom-group"
button (zoom out): id="spatial-crop-zoom-out"
button (zoom reset): id="spatial-crop-zoom-reset"
span (zoom pct):   id="spatial-crop-zoom-pct"
button (zoom in):  id="spatial-crop-zoom-in"
button (clear):    id="spatial-crop-clear-btn"
button (apply):    id="spatial-crop-apply-btn"
```

---

## 13. SpeedCurveCanvas (SpeedCurveCanvas.tsx)

### Current State
- No IDs on any element (SVG-based component)

### Required Additions

```
svg:               id="speed-curve-svg"
rect (section):    id="speed-curve-section-{section.id}"
rect (slow band):  id="speed-curve-slow-{index}"
line (downbeat):   id="speed-curve-db-{time}"
circle (bass):     id="speed-curve-bass-{t}"
path (curve):      id="speed-curve-path"
text (max label):  id="speed-curve-max-label"
text (min label):  id="speed-curve-min-label"
```

---

## 14. StageTelemetry (StageTelemetry.tsx)

### Current State
- No IDs on any element

### Required Additions

```
div (container):   id="stage-telemetry-container"
h2:                id="stage-telemetry-title"
span (status):     id="stage-telemetry-status"
div (stages bar):  id="stage-telemetry-stages"
div (stage item):  id="stage-telemetry-stage-{stage.id}"
span (state label): id="stage-telemetry-state-{stage.id}"
span (active step): id="stage-telemetry-active-{stage.id}"
button (log toggle): id="stage-telemetry-log-toggle"
span (log count):  id="stage-telemetry-log-count"
span (chevron):    id="stage-telemetry-chevron"
div (log panel):   id="stage-telemetry-log-panel"
p (log entry):     id="stage-telemetry-log-{index}"
span (offset):     id="stage-telemetry-offset-{index}"
span (stage name): id="stage-telemetry-stage-name-{index}"
span (action):     id="stage-telemetry-action-{index}"
span (duration):   id="stage-telemetry-duration-{index}"
span (message):    id="stage-telemetry-message-{index}"
```

---

## 15. StoryboardBlockPlayer (StoryboardBlockPlayer.tsx)

### Current State
- No IDs on any element

### Required Additions

```
div (container):   id="storyboard-block-player"
audio:             id="storyboard-block-player-audio"
div (waveform bar): id="storyboard-block-player-waveform-bar"
div (highlight bg): id="storyboard-block-player-highlight-bg"
div (slot highlight): id="storyboard-block-player-slot-{slot.id}"
div (playhead):    id="storyboard-block-player-playhead"
input (scrubber):  id="storyboard-block-player-scrubber"
button (play track): id="storyboard-block-player-play-track-btn"
button (play slot): id="storyboard-block-player-play-slot-btn"
p (info text):     id="storyboard-block-player-info"
span (time display): id="storyboard-block-player-time-display"
span (active slot): id="storyboard-block-player-active-slot"
span (looping label): id="storyboard-block-player-looping-label"
```

---

## 16. StoryboardPanel (StoryboardPanel.tsx)

### Current State
- `id={inputId}` exists on file input
- Missing IDs on panel root, sections, slots, controls, transforms

### Required Additions

```
div (panel):       id="storyboard-panel"
h2:                id="storyboard-panel-title"
p (description):   id="storyboard-panel-desc"
dl (timeline):    id="storyboard-panel-timeline"
dt:                id="storyboard-panel-timeline-label"
dd:                id="storyboard-panel-timeline-value"
div (scope canvas): id="storyboard-panel-scope"
div (detail rack): id="storyboard-panel-detail-rack"
div (block player): id="storyboard-panel-block-player"
div (slots bar):   id="storyboard-panel-slots-bar"
div (slot item):   id="storyboard-panel-slot-{slot.id}"
button (transition): id="storyboard-panel-transition-{slot.id}"
button (slot select): id="storyboard-panel-slot-btn-{slot.id}"
span (slot color): id="storyboard-panel-slot-color-{slot.id}"
p (slot label):    id="storyboard-panel-slot-label-{slot.id}"
p (slot duration): id="storyboard-panel-slot-duration-{slot.id}"
p (slot clip):     id="storyboard-panel-slot-clip-{slot.id}"
div (loop to hook): id="storyboard-panel-loop-hint"
div (active panel): id="storyboard-panel-active-{active.id}"
input (file):      id="storyboard-panel-file-input"
p (active label):  id="storyboard-panel-active-label"
button (rotate left): id="storyboard-panel-rotate-left-btn"
button (rotate right): id="storyboard-panel-rotate-right-btn"
button (frame crop): id="storyboard-panel-frame-crop-btn"
button (clear clip): id="storyboard-panel-clear-clip-btn"
label (drop zone): id="storyboard-panel-drop-zone-{active.id}"
span (drop text):  id="storyboard-panel-drop-text-{active.id}"
div (crop timeline): id="storyboard-panel-crop-timeline-{active.id}"
div (segments):    id="storyboard-panel-segments"
div (spatial modal): id="storyboard-panel-spatial-modal"
p (saving):        id="storyboard-panel-saving-msg"
```

---

## 17. StoryboardScopeCanvas (StoryboardScopeCanvas.tsx)

### Current State
- No IDs on any element (SVG-based component)

### Required Additions

```
div (container):   id="storyboard-scope-container"
p (block label):   id="storyboard-scope-label"
p (window size):   id="storyboard-scope-window-size"
div (fx legend):   id="storyboard-scope-fx-legend"
span (zoom legend): id="storyboard-scope-fx-zoom"
span (rotate legend): id="storyboard-scope-fx-rotate"
span (pan legend): id="storyboard-scope-fx-pan"
svg:               id="storyboard-scope-svg"
div (section ribbon): id="storyboard-scope-section-ribbon"
rect (ruler bg):   id="storyboard-scope-ruler-bg"
line (ruler line): id="storyboard-scope-ruler-line"
g (slot group):    id="storyboard-scope-slot-{slot.id}"
rect (slot rect):  id="storyboard-scope-slot-rect-{slot.id}"
text (slot label): id="storyboard-scope-slot-text-{slot.id}"
path (waveform):   id="storyboard-scope-waveform"
g (highlight):     id="storyboard-scope-highlight-{slot.id}"
clipPath:          id="storyboard-scope-clip-{slot.id}"
path (highlight path): id="storyboard-scope-highlight-path-{slot.id}"
div (marker strip): id="storyboard-scope-marker-strip"
line (boundary):   id="storyboard-scope-boundary-{slot.id}"
line (playhead):   id="storyboard-scope-playhead"
g (tick group):    id="storyboard-scope-tick-{timeS}"
line (tick mark):  id="storyboard-scope-tick-mark-{timeS}"
text (tick label): id="storyboard-scope-tick-label-{timeS}"
```

---

## 18. StoryboardSegmentsPanel (StoryboardSegmentsPanel.tsx)

### Current State
- No IDs on any element

### Required Additions

```
div (container):   id="segments-panel"
button (toggle):   id="segments-panel-toggle-btn"
span (title):      id="segments-panel-title"
span (count):      id="segments-panel-count"
span (expand label): id="segments-panel-expand-label"
p (loading):       id="segments-panel-loading"
p (error):         id="segments-panel-error"
div (table):       id="segments-panel-table"
thead:             id="segments-panel-thead"
th (role):         id="segments-panel-th-role"
th (src):          id="segments-panel-th-src"
th (target):       id="segments-panel-th-target"
th (speed):        id="segments-panel-th-speed"
tr (row):          id="segments-panel-row-{row.id}"
td (role):         id="segments-panel-td-role-{row.id}"
td (src time):     id="segments-panel-td-src-{row.id}"
span (src span):   id="segments-panel-td-src-span-{row.id}"
td (target):       id="segments-panel-td-target-{row.id}"
td (speed):        id="segments-panel-td-speed-{row.id}"
p (hook summary):  id="segments-panel-hook-summary"
```

---

## Implementation Order (Dependency Graph)

```
Phase 1 - Simple Panels (no cross-component deps):
  ConfirmDialog -> DebugConsolePanel -> OutputPanel -> SpeedCurveCanvas

Phase 2 - Form & Overlay Components:
  JobForm -> HookOverlayPanel -> MusicBlockCard

Phase 3 - Timeline & Canvas Components:
  ClipCropTimeline -> ScopeCanvas -> SpeedCurveCanvas (update)

Phase 4 - Complex Panels:
  AudioScopePanel -> StoryboardPanel -> RetentionFxPanel

Phase 5 - Modal & Preview Components:
  SpatialCropModal -> PhonePreview

Phase 6 - Telemetry & Player:
  StageTelemetry -> StoryboardBlockPlayer

Phase 7 - Scope Canvases:
  StoryboardScopeCanvas (update)
```

## Total ID Count by Category

| Category | Count |
|----------|-------|
| Component root IDs | 18 |
| Section/region IDs | 25 |
| Button IDs | 40 |
| Input/select IDs | 20 |
| Label IDs | 18 |
| List/item IDs (dynamic) | 35 |
| SVG element IDs | 60 |
| Media element IDs | 8 |
| Text/label IDs | 30 |
| **Total** | **~254** |

## Naming Convention Applied

All IDs follow kebab-case pattern: `component-name-element-description`

For dynamic/repeated elements: `component-name-element-{variable}`

## Checklist for Implementation

- [ ] Each component root has `id="component-name"`
- [ ] Every section/region has descriptive ID
- [ ] Every button has action-descriptive ID
- [ ] Every input/select/textarea has field-descriptive ID
- [ ] Every mapped item has dynamic ID with unique key
- [ ] Every SVG shape/line/text has an ID
- [ ] Every media element (video/audio) has an ID
- [ ] No duplicate IDs within any component
- [ ] All IDs follow kebab-case convention
- [ ] All IDs are descriptive enough to identify purpose without context
