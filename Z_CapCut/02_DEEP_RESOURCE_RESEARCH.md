# 02 — Deep inspection: configuration, resources, CLI and effects

**Source:** read-only `CapCut_Deep_Inspection.zip` collected from CapCut 9.6.0.4097. The archive has 257 entries including directory records; collector reports 249 selected resource files plus manifest, 250 nonempty file entries including manifest, and **209 valid JSON documents with 0 JSON parse failures**. This is static file analysis, not execution or live feature verification.

## A. Timeline-draft CLI: bundled documentation

`Resources/common_agent/skills/timeline-draft-cli/SKILL.md` documents a `lyra-cli-ipc timeline add-draft` command to insert a draft Asset into an already running native timeline.

- Representations: `nested` (preserve child tracks) or `expanded` (expand top-level tracks).
- Placement: `append`, or `at --position-us … --collision ripple`, or `at --position-us … --collision overwrite`.
- Guardrails mentioned: `--dry-run`, expected asset/timeline revision values, request ID, session capabilities and existing current project.
- **Warning**: `overwrite` is destructive. Session-bound agent commands are NOT evidence of a supported public API or working external Z Builder integration.

`Resources/common_agent/skills/canvas-node-cli/SKILL.md` describes a separate Canvas node API. Canvas and native timeline IDs must not be conflated.

## B. Default adjustment resources (39 groups)

The 39 immediate configuration groups observed under `Resources/DefaultAdjustBundle` are:

`FC`, `black_white`, `brightness`, `brightness_v1`, `brightness_v2`, `clear`, `color_match_select_target`, `combine_adjust`, `contrast`, `contrast_v1`, `contrast_v2`, `contrast_v3`, `fade`, `highlight`, `highlight_v1`, `hsl`, `hsl_v1`, `light_sensation`, `merge_all_adjust_color`, `particle`, `particle_v1`, `particle_v2`, `saturation`, `saturation_v1`, `shadow`, `shadow_highlight_v2_gles2`, `shadow_highlight_v2_gles3`, `shadow_highlight_v3_gles3`, `shadow_v1`, `sharpen`, `sharpen_v1`, `temperature`, `temperature_tone_v2`, `temperature_tone_v3`, `tone`, `tone_v1`, `vignetting`, `vignetting_v1`, `yunfu_npu`.

Examples suggest brightness, contrast, HSL, highlights/shadows, saturation, sharpen, temperature, fade, vignette, combined color pipeline and particle/grain-related internals. **These are package resource names, not a validated control-to-draft schema, complete catalog, or assurance a given editor preset is available.**

## C. Mix-mode lookup

Found in `Resources/MixMode/MixMode.json`:

| Internal nameId | effectId |
|---|---:|
| color_filter | 871339 |
| dark_en | 871342 |
| bright_en | 871341 |
| over_lay | 871340 |
| glare_pc | 871338 |
| soft_light | 871337 |
| linear_deepening | 871336 |
| darken_color | 871335 |
| color_dodge | 871334 |
| multiply_blend_mode | 871333 |

Observed resource identifiers; not tested for successful injection into native project JSON. The exact user-facing English names and rendering behaviors are not fully established by these labels alone.

## D. Aspect-ratio resource presets

`Resources/video_template_ratio.json` exposes **9** ratio choices:
`9:16`, `16:9`, `1:1`, `4:3`, `2:1`, `5.8"`, `2.35:1`, `3:4`, `1.85:1`.

These are UI/resource presets, not proof of a specified exported resolution. The actual supplied drafts use 1920×1362 at `original`.

## E. Material-publishing routes

**8** publishing-route keys observed:
`publish-effects`, `publish-audio-effect`, `publish-filter-single`, `publish-caption-animation`, `publish-video`, `publish-caption-template`, `publish-filter-collection`, `publish-text-animation`.

Names establish that page resources exist, **not** the complete installable animation or transition library.

## F. Other relevant resources

- `Resources/matting_config/config.json` lists matting/video model references.
- `Resources/figure/beauty_head/face_recognition/config.json` references face model assets.
- `Resources/Chroma` and `Chroma2` contain keying configurations.
- `Tools/draft-converter` bundles OpenTimelineIO modules and AAF/FCP XML adapters. **No converter execution, supported-format claim, or CapCut import success was tested.**
- No complete animation/effect catalog was obtained. Cloud caches, paid templates and runtime assets may differ per account, PC and version.

## G. Verification matrix

| Capability | Evidence level | Remaining work |
|---|---|---|
| Resource files and adjustment group names | Observed | Map to actual editor controls via controlled test |
| Mix-mode identifiers | Observed | Compare generated editor drafts with and without mode |
| Aspect-ratio choices | Observed | Test actual canvas/resolution serialization |
| Material publishing route names | Observed | Enumerate available templates separately |
| Native draft insertion CLI arguments | Documented internally | Authorised live-session behavior, not standalone assumed |
| Converter executable and dependency names | Observed | Run isolated, permission-safe `--help` / documented flags if appropriate |
| True effect availability / offline persistence | Not verified | Native editor reopen/render test |
| Native audio serialization | Not verified | Audio-containing throwaway draft required |

All statements above describe observed resources or internal docs. They do not grant licensing or special access to CapCut services.
