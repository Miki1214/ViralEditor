# Graph Report - ViralAutomation  (2026-06-20)

## Corpus Check
- 156 files · ~102,724 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2096 nodes · 6748 edges · 89 communities (82 shown, 7 thin omitted)
- Extraction: 61% EXTRACTED · 39% INFERRED · 0% AMBIGUOUS · INFERRED: 2619 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `de28ada5`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 81|Community 81]]

## God Nodes (most connected - your core abstractions)
1. `MediaInfo` - 109 edges
2. `Transient` - 104 edges
3. `JobConfig` - 103 edges
4. `AudioTimeline` - 97 edges
5. `ClipInput` - 91 edges
6. `BeatSyncFeatures` - 88 edges
7. `DomainModel` - 75 edges
8. `SpeedSegment` - 64 edges
9. `MusicSection` - 63 edges
10. `SpeedRampConfig` - 61 edges

## Surprising Connections (you probably didn't know these)
- `AudioDspConfig` --uses--> `AudioDspConfig`  [INFERRED]
  tests/conftest.py → src/viral_editor/audio/beat_detector.py
- `MonkeyPatch` --uses--> `AudioDspConfig`  [INFERRED]
  tests/conftest.py → src/viral_editor/audio/beat_detector.py
- `Path` --uses--> `AudioDspConfig`  [INFERRED]
  tests/conftest.py → src/viral_editor/audio/beat_detector.py
- `Path` --uses--> `FFmpegError`  [INFERRED]
  tests/test_ffmpeg_env.py → src/viral_editor/utils/ffmpeg.py
- `Path` --uses--> `JobConfig`  [INFERRED]
  scripts/debug_hook_split.py → src/viral_editor/config.py

## Import Cycles
- 1-file cycle: `src/viral_editor/api/main.py -> src/viral_editor/api/main.py`

## Communities (89 total, 7 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.10
Nodes (120): AbstractEventLoop, build_job_config(), _on_event_factory(), Background pipeline execution for API jobs., Run a queued job on a background thread., start_job(), ClipInfoResponse, ClipReelResponse (+112 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (106): save_upload(), write_job_config(), apply_storyboard_patch(), assign_slot_clip(), clear_slot_clip(), clip_media_for_storyboard(), _copy_slot_assignment(), hook_clip_id_for_slot() (+98 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (86): apply_hook_inversion_layout(), assigned_storyboard_slots(), _composite_video_start_for_assigned_index(), _compute_boundaries(), _downbeats_in_window(), _drop_counts_by_slot(), effective_output_duration(), _full_hook_crop() (+78 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (83): _beat_index(), build_block_catalog(), _build_phrase_candidate(), _Candidate, _classify_candidate(), _correlation(), _duration_in_target_window(), _enumerate_all_phrase_candidates() (+75 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (70): _catalog_key(), ensure_music_block_catalog(), load_audio_timeline(), load_beat_features(), load_chroma(), load_music_block_catalog(), load_music_blocks(), load_music_structure() (+62 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (64): apply_clip_updates(), build_reel_for_config(), clip_durations_map(), clip_info_payload(), load_clip_reel(), persist_clip_reel(), primary_video_media(), probe_clip_media() (+56 more)

### Community 6 - "Community 6"
Cohesion: 0.10
Nodes (65): apply_effects_patch(), assigned_slot_boundary_times_abs(), effective_window_end_s(), hook_teaser_for_storyboard(), Retention FX helpers for composited preview., Merge partial teaser / spatial FX / retention settings from an API patch., Build teaser spec from the hook slot when enabled., Absolute audio times where assigned slots begin or end. (+57 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (61): _audio_content_sha256(), _calibrate_vocal_activity(), compute_vocal_activity(), _configure_torch_threads_for_demucs(), _default_demucs_workers(), demucs_device_label(), demucs_progress_label(), _global_vocal_stem_cache_dir() (+53 more)

### Community 8 - "Community 8"
Cohesion: 0.11
Nodes (61): BudgetPolicy, SpeedCurvePoint, SpeedPreset, JobConfig, AudioTimeline, BeatSyncFeatures, ClipReel, MediaInfo (+53 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (59): apply_block_selection(), _bar_period(), _beat_period(), _Candidate, _chroma_slice(), _classify_window(), _correlation_score(), _envelope_slice() (+51 more)

### Community 10 - "Community 10"
Cohesion: 0.07
Nodes (42): assignSlotClip(), clearSlotClip(), compositePreviewUrl(), createDraftJob(), CreateDraftJobInput, fetchCompositePreview(), fetchHealth(), fetchJobs() (+34 more)

### Community 11 - "Community 11"
Cohesion: 0.09
Nodes (44): countFxCandidates(), EffectsPatchPayload, nearestPayoffIndex(), panPlanFromSpatialFx(), RetentionFxPanel(), sliderReleaseHandlers(), useDebouncedPatch(), useSliderDraft() (+36 more)

### Community 12 - "Community 12"
Cohesion: 0.07
Nodes (43): Export retention policy symbols., IngestResult, Probed media metadata for both input streams., RetentionPlanScore, Transient, JobConfig, TeaserSpec, Path (+35 more)

### Community 13 - "Community 13"
Cohesion: 0.10
Nodes (40): ReelEntry, ClipInput, ClipReel, MediaInfo, Path, SpeedRampConfig, SpeedSegment, SpeedRampPlan (+32 more)

### Community 14 - "Community 14"
Cohesion: 0.12
Nodes (40): RetentionConfig, SpatialFxConfig, AudioTimeline, FxEvent, MediaInfo, ndarray, Transient, AudioTimeline (+32 more)

### Community 15 - "Community 15"
Cohesion: 0.12
Nodes (40): classify_accents(), _ensure_hook_pan(), _ensure_slot_boundary_pans(), _ensure_tail_beat_pans(), find_energy_peaks(), find_flux_peaks(), _frame_to_time(), _lane_amplitude_at() (+32 more)

### Community 16 - "Community 16"
Cohesion: 0.12
Nodes (29): MusicBlockCardProps, blockPixelRange(), ScopeCanvas(), ScopeCanvasProps, ChromaHeatmap(), ChromaHeatmapProps, MusicDetailRack, MusicDetailRackChartProps (+21 more)

### Community 17 - "Community 17"
Cohesion: 0.07
Nodes (32): AudioScopePanelProps, RetentionFxPanelProps, SpatialCropModalProps, SpeedCurveCanvasProps, SlotTransformDraft, StoryboardPanelProps, StoryboardScopeCanvasProps, AudioTimeline (+24 more)

### Community 18 - "Community 18"
Cohesion: 0.17
Nodes (33): SpeedRampConfig, Tests for speed-ramp preset profiles., test_all_preset_ids_resolve(), test_config_alpha_overrides_preset_default(), test_overrides_merge_on_top_of_preset(), test_unknown_style_raises(), _assert_tiles_output(), _flat_envelope() (+25 more)

### Community 19 - "Community 19"
Cohesion: 0.12
Nodes (31): _duration_from_probe(), _ensure_output_writable(), _log_vfr_warning(), _parse_duration(), parse_frame_rate(), _pick_stream(), probe_media(), Media validation and ffprobe-based ingestion. (+23 more)

### Community 20 - "Community 20"
Cohesion: 0.14
Nodes (31): analyze_audio_with_envelope(), _compute_surge_lane(), Windowed low→high RMS rise — peaks at steep surges that land loud., Analyze audio and return the timeline plus the onset strength envelope., _is_downbeat_time(), place_interrupts(), place_translations(), Beat-synced horizontal pan impulses with energy gating and hook boost. (+23 more)

### Community 21 - "Community 21"
Cohesion: 0.14
Nodes (24): StoryboardScopeCanvas, buildTimeTicks(), formatScopeTime(), LANE_COLORS, SECTION_FILLS, TICK_INTERVALS_S, timeTickInterval(), cropTimesToWindow() (+16 more)

### Community 22 - "Community 22"
Cohesion: 0.12
Nodes (29): ClipInput, MediaInfo, TeaserSpec, TeaserConfig, MediaInfo, Tests for the frame-0 teaser planner., test_body_output_duration_after_teaser(), test_split_hook_crop_by_duration_head_and_tail() (+21 more)

### Community 23 - "Community 23"
Cohesion: 0.12
Nodes (28): BeatTrackResult, _bpm_from_beats(), _estimate_downbeats_librosa(), _fold_bpm(), infer_beats(), _infer_beats_beat_this(), _infer_beats_librosa(), Beat and downbeat inference — beat-this neural tracker with librosa fallback. (+20 more)

### Community 24 - "Community 24"
Cohesion: 0.17
Nodes (17): slotClipLabel(), StoryboardPanel(), StoryboardSegmentsPanel(), StoryboardSegmentsPanelProps, StoryboardPayload, StoryboardSegmentsDebugPayload, StorySlot, shouldCommitCrop() (+9 more)

### Community 25 - "Community 25"
Cohesion: 0.13
Nodes (27): AudioDspConfig, _classify_transients(), _compute_pacing_density(), _compute_scope_lanes(), _dedupe_onsets(), _estimate_tempo(), load_scope_lanes(), _low_band_energy_ratio() (+19 more)

### Community 26 - "Community 26"
Cohesion: 0.10
Nodes (17): loopSeamPreviewUrl(), AudioScopePanel(), fallbackFullTrackBlock(), formatRange(), loopQualityLabel(), MusicBlockCard(), PreviewMode, TARGET_DURATION_PRESET_VALUES (+9 more)

### Community 27 - "Community 27"
Cohesion: 0.12
Nodes (25): FxEvent, _apply_spatial_fx_chain(), build_proxy_filtergraph(), _build_teaser_filter_chain(), _combined_pan_x_expression(), _fx_decay_ramp(), _normalize_segment_timeline(), _pan_event_duration() (+17 more)

### Community 28 - "Community 28"
Cohesion: 0.13
Nodes (21): previewAudioUrl(), PhonePreview(), PhonePreviewProps, PreviewTransportRestore, renderHookLine(), applyPlayheadDom(), BlockPlayheadChangeHandler, formatTime() (+13 more)

### Community 29 - "Community 29"
Cohesion: 0.14
Nodes (19): DragMode, SpatialCropModal(), clampCropBoxFree(), clampCropBoxNw(), clampCropBoxNwFree(), clampCropBoxSe(), clampCropBoxSeFree(), defaultPortraitCrop() (+11 more)

### Community 30 - "Community 30"
Cohesion: 0.21
Nodes (22): Path, _minimal_job_payload(), MonkeyPatch, Path, Tests for job configuration loading and validation., test_absolute_paths_in_job(), test_bad_color_rejected(), test_bad_teaser_mask_rejected() (+14 more)

### Community 31 - "Community 31"
Cohesion: 0.08
Nodes (23): dependencies, @fontsource/jetbrains-mono, react, react-dom, devDependencies, autoprefixer, postcss, tailwindcss (+15 more)

### Community 32 - "Community 32"
Cohesion: 0.12
Nodes (17): build_loop_audition_filter(), build_loop_seam_only_filter(), Render-grade seamless loop seam helpers., Extract a loop audition clip with crossfade at the wrap point., Snap a cut time to the nearest zero crossing within a small window., FFmpeg filter graph: segment + equal-power crossfade loop audition., FFmpeg filter: ~4s tail→crossfade→head, then silence before the next cycle., Extract ~4s around the loop wrap plus a short gap before each repeat. (+9 more)

### Community 33 - "Community 33"
Cohesion: 0.13
Nodes (17): Logger, StageAction, configure_logging(), get_logger(), log_stage(), Structured logging helpers., Configure root logging once per process., Return a module logger (call ``configure_logging`` from the CLI first). (+9 more)

### Community 34 - "Community 34"
Cohesion: 0.15
Nodes (19): Path, test_ensure_ffmpeg_succeeds_when_binaries_on_path(), _binary_version(), ensure_ffmpeg(), escape_filter_path(), ffmpeg_available(), FFmpeg / ffprobe subprocess wrappers., Return True when both ffmpeg and ffprobe can be resolved. (+11 more)

### Community 35 - "Community 35"
Cohesion: 0.10
Nodes (19): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleDetection, moduleResolution (+11 more)

### Community 36 - "Community 36"
Cohesion: 0.27
Nodes (18): analyze_audio(), fold_tempo(), Fold half/double-tempo estimates into a musical BPM band., Analyze a music track and return beat/transient metadata., _click_track(), ndarray, Path, Tests for audio beat/transient detection. (+10 more)

### Community 37 - "Community 37"
Cohesion: 0.15
Nodes (14): DebugConsolePanel(), App(), clearDebugLogs(), DebugLevel, DebugLogEntry, entries, getDebugLogs(), installDebugConsoleCapture() (+6 more)

### Community 38 - "Community 38"
Cohesion: 0.12
Nodes (16): Acceptance criteria, `cli.py`, Deliverables, Dependencies, Files & responsibilities, `.gitignore`, `models.py`, Objective (+8 more)

### Community 39 - "Community 39"
Cohesion: 0.12
Nodes (16): 1. Build the speed function R(t), 2. Discretize into segments, 3. Fit source footage to the music (the budget problem), 4. Frame alignment, Acceptance criteria, Contract, Dependencies, Detailed design (+8 more)

### Community 40 - "Community 40"
Cohesion: 0.12
Nodes (16): 1. Safe zone, 2. Text wrapping & sizing, 3. Emphasis, 4. Background pill / shadow, 5. Placement & timing, Acceptance criteria, Contract, Dependencies (+8 more)

### Community 41 - "Community 41"
Cohesion: 0.12
Nodes (15): API ([src/viral_editor/api/routes/jobs.py](src/viral_editor/api/routes/jobs.py), [src/viral_editor/api/music.py](src/viral_editor/api/music.py)), Architecture, Backend, Data utilization (current vs target), Design direction, Files, Frontend, Goal (+7 more)

### Community 42 - "Community 42"
Cohesion: 0.14
Nodes (13): Architecture, Automated Retention Video Editor - Local Core Loop Breakdown, Best-practice notes, Deferred phases (wanted eventually, sensibly sequenced after the core loop works), Phase 0 - Scaffolding and environment, Phase 1 - Config and ingestion, Phase 2 - Audio DSP (BeatViz core), Phase 3 - Speed-ramp planner (hardest module, isolated) (+5 more)

### Community 43 - "Community 43"
Cohesion: 0.14
Nodes (13): Back-compat, Decisions locked, Flow, Multi-Clip Reel Composer, Phase 1 - Domain models ([src/viral_editor/models.py](src/viral_editor/models.py)), Phase 2 - Config ([src/viral_editor/config.py](src/viral_editor/config.py)), Phase 3 - Ingest ([src/viral_editor/ingest/loader.py](src/viral_editor/ingest/loader.py)), Phase 4 - Reel builder (new [src/viral_editor/video/clip_reel.py](src/viral_editor/video/clip_reel.py)) (+5 more)

### Community 44 - "Community 44"
Cohesion: 0.14
Nodes (14): Acceptance criteria, `config.py`, Contracts, Deliverables, Dependencies, Detailed design notes, Files & responsibilities, `ingest/loader.py` (+6 more)

### Community 45 - "Community 45"
Cohesion: 0.14
Nodes (14): Acceptance criteria, Contract, Contract, Dependencies, Design, Design, Determinism, Objective (+6 more)

### Community 46 - "Community 46"
Cohesion: 0.32
Nodes (13): add_bass_thump(), add_impulse(), analyzed_transients(), build_bass(), build_clicks(), build_drop(), build_mixed(), click_track() (+5 more)

### Community 47 - "Community 47"
Cohesion: 0.24
Nodes (12): invalidate_speed_previews(), load_speed_ramp_options(), load_speed_segments(), Load speed-ramp artifacts and refresh style selection., Apply style/overrides, recompute options, and persist selected segments., refresh_speed_selection(), speed_proxy_cache_key(), _trim_sections() (+4 more)

### Community 48 - "Community 48"
Cohesion: 0.15
Nodes (13): Acceptance criteria, Configuration knobs (with defaults), Contract, Deliverables, Dependencies, Detailed design, Objective, Output: `AudioTimeline` (+5 more)

### Community 49 - "Community 49"
Cohesion: 0.15
Nodes (13): 9.1 API layer, 9.2 Asynchronous orchestration, 9.3 Storage & I/O abstraction, 9.4 Scalable rendering, 9.5 Delivery & ops, Acceptance criteria, Objective, Phase 9 - Cloud / Web Migration (Deferred) (+5 more)

### Community 50 - "Community 50"
Cohesion: 0.15
Nodes (12): Phase A - Beat-synchronous analysis foundation, Phase B - Structural segmentation, Phase C - Loop & window planner rewrite, Phase D - Render-grade seamless loop, Phase E - Scope UI, Phase F - Full containerization (API + analysis + ffmpeg), Principles applied, Rollout / risk (+4 more)

### Community 51 - "Community 51"
Cohesion: 0.15
Nodes (12): Control Room UI (Option A), Development, Development (two terminals), Docker (recommended for beat-this neural tracking), Phased implementation, Production-style (single server), Project layout, Requirements (+4 more)

### Community 52 - "Community 52"
Cohesion: 0.24
Nodes (12): Tests for speed-ramp proxy filtergraph builder., _sample_plan(), test_build_composite_filtergraph_hook_start_mask_and_spatial_fx(), test_build_composite_filtergraph_rotation_and_cover(), test_build_composite_filtergraph_spatial_crop(), test_build_composite_filtergraph_spatial_crop_letterbox(), test_build_composite_filtergraph_translate_pan(), test_build_composite_filtergraph_translate_pan_many_beats() (+4 more)

### Community 53 - "Community 53"
Cohesion: 0.24
Nodes (10): ensure_audio_preview(), ensure_loop_seam_audio(), preview_cache_path(), Generate trimmed audio preview clips via FFmpeg., Render-grade seamless loop WAV — equal-power crossfade at the wrap.      Shared, Extract a preview clip — full loop audition or seam-only crossfade., Path, Tests for render-grade loop seam helpers. (+2 more)

### Community 55 - "Community 55"
Cohesion: 0.17
Nodes (12): Acceptance criteria, Dependencies, Encode settings (locked), FFmpeg technique notes, Files & responsibilities, Objective, Phase 6 - FFmpeg Graph Builder & Renderer, `render/ffmpeg_builder.py` (+4 more)

### Community 56 - "Community 56"
Cohesion: 0.24
Nodes (11): CompletedProcess, Path, test_render_composite_uses_looped_seam_audio(), Run ``ffmpeg`` with logging and structured error reporting., run_ffmpeg(), _append_looped_music_input(), Render a storyboard composite preview with trimmed music mux., Render a cached low-res proxy clip with trimmed music mux. (+3 more)

### Community 57 - "Community 57"
Cohesion: 0.36
Nodes (8): ClipCropTimeline(), ClipCropTimelineProps, DragMode, SlotRole, formatSlotSpeedLabel(), slotPreviewPlaybackRate(), slotRenderSpeedFactor(), slotTimestretch()

### Community 58 - "Community 58"
Cohesion: 0.18
Nodes (11): Acceptance criteria, `cli.py`, Definition of done for the local core loop, Dependencies, Design notes, Files & responsibilities, Objective, Phase 7 - CLI & End-to-End Pipeline Orchestration (+3 more)

### Community 59 - "Community 59"
Cohesion: 0.18
Nodes (10): disable_demucs_vocal_separation(), AudioDspConfig, MonkeyPatch, Path, Shared pytest fixtures., Isolated directory for model artifact round-trip tests., AudioDspConfig with Demucs disabled for fast unit tests., Skip Demucs during analysis in the default test suite. (+2 more)

### Community 60 - "Community 60"
Cohesion: 0.20
Nodes (10): 1. System Architecture Overview, 2.1. Hook & Pattern Interrupt Module (Trend Watchers Core), 2.2. Audio DSP & Temporal Synchronization Module (BeatViz Core), 2.3. Dynamic Frame-Ramping & Video Composition Engine, 2.4. Retention Optimization & Kinetic Captions Engine, 2. Core Modules & Engineering Specifications, 3. Technology Stack & Deployment Specs, 4. Operational Pipeline Flow Execution (+2 more)

### Community 61 - "Community 61"
Cohesion: 0.20
Nodes (10): 8.1 Kinetic captions (Whisper ASR), 8.2 Progress indicator, 8.3 Infinite loop wrap, Acceptance criteria, Objective, Phase 8 - Retention Engine (Deferred), Risks & mitigations, Sequencing (+2 more)

### Community 62 - "Community 62"
Cohesion: 0.20
Nodes (9): Architecture: one policy, every stage, Notes / decisions, Phase 1 - New high-value signals (moderate effort, reuse-friendly), Phase 2 - Central RetentionPolicy module, Phase 3 - Retarget each stage to the policy, Phase 4 - Rationale + config surface, Phase 5 - Tests + validation, Viral Editing Decision Engine (+1 more)

### Community 63 - "Community 63"
Cohesion: 0.31
Nodes (9): _load_job_config(), main(), _print_table(), JobConfig, Path, _render_and_probe(), test_composite_output_duration_uses_segment_timeline(), composite_output_duration_s() (+1 more)

### Community 64 - "Community 64"
Cohesion: 0.36
Nodes (7): MonkeyPatch, Path, Tests for FFmpeg environment checks., test_ensure_ffmpeg_raises_with_install_hint_when_missing(), test_resolve_ffmpeg_binary_falls_back_to_winget_path(), test_run_ffmpeg_raises_on_nonzero_exit(), test_run_ffprobe_json_parses_output()

### Community 65 - "Community 65"
Cohesion: 0.33
Nodes (5): Audio validation fixtures, Automated check, Files, Regenerate, Use in the app

### Community 66 - "Community 66"
Cohesion: 0.33
Nodes (6): Automated Retention Video Editor - Phased Implementation Plans, Guiding architectural principles, Locked decisions, Phase index, Pipeline overview, Shared domain models (the contract between phases)

### Community 67 - "Community 67"
Cohesion: 0.47
Nodes (5): _load_manifest(), _matches_expected(), Verify committed audio fixtures match manifest ground truth., test_fixture_matches_manifest(), test_fixture_onset_grid_for_clicks()

### Community 68 - "Community 68"
Cohesion: 0.50
Nodes (4): load_features(), Beat-synchronous feature extraction and persistence., save_features(), Path

### Community 69 - "Community 69"
Cohesion: 0.50
Nodes (3): notes, samples, schema

### Community 70 - "Community 70"
Cohesion: 0.50
Nodes (4): Return 0 when loop boundaries sit in vocal gaps, 1 when both cut mid-phrase., vocal_boundary_penalty(), test_vocal_boundary_penalty_is_zero_without_lane(), test_vocal_boundary_penalty_prefers_gaps()

## Knowledge Gaps
- **286 isolated node(s):** `schema`, `notes`, `samples`, `viral-editor`, `CompletedProcess` (+281 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `DomainModel` connect `Community 12` to `Community 0`, `Community 32`, `Community 68`, `Community 5`, `Community 6`, `Community 4`, `Community 8`, `Community 13`, `Community 14`, `Community 15`, `Community 18`, `Community 19`, `Community 20`, `Community 22`, `Community 23`, `Community 25`, `Community 30`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `analyze_audio_with_envelope()` connect `Community 20` to `Community 0`, `Community 2`, `Community 36`, `Community 4`, `Community 6`, `Community 7`, `Community 15`, `Community 23`, `Community 25`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Why does `Transient` connect `Community 6` to `Community 0`, `Community 2`, `Community 3`, `Community 5`, `Community 8`, `Community 9`, `Community 12`, `Community 14`, `Community 15`, `Community 18`, `Community 20`, `Community 25`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Are the 94 inferred relationships involving `MediaInfo` (e.g. with `BudgetPolicy` and `IngestError`) actually correct?**
  _`MediaInfo` has 94 INFERRED edges - model-reasoned connections that need verification._
- **Are the 94 inferred relationships involving `Transient` (e.g. with `AudioAnalysisError` and `AudioAnalysisResult`) actually correct?**
  _`Transient` has 94 INFERRED edges - model-reasoned connections that need verification._
- **Are the 97 inferred relationships involving `JobConfig` (e.g. with `AbstractEventLoop` and `ClipInfoResponse`) actually correct?**
  _`JobConfig` has 97 INFERRED edges - model-reasoned connections that need verification._
- **Are the 91 inferred relationships involving `AudioTimeline` (e.g. with `AudioAnalysisError` and `AudioAnalysisResult`) actually correct?**
  _`AudioTimeline` has 91 INFERRED edges - model-reasoned connections that need verification._