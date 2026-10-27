# 04 — Z Builder / Z CapCut implementation notes and validation gates

**Scope:** Requirements from the user plus **separately labeled** conclusions from analyzed CapCut 9.6.0 data. This folder is research documentation; no app code or CapCut installation has been changed by this documentation update.

## Intended desktop workflow (user requirements)

1. Edge TTS generates a voice MP3 and a synchronized ~3–4-second SRT (handled outside Z Builder).
2. ChatGPT uses SRT + Master Prompt + media summary to produce a full Scene Plan.
3. Z Builder accepts Scene Plan and voice as input; voice import may be optional for the CapCut handoff.
4. Next opens existing local media library and selects images/videos, building scene-aligned timing from the Scene Plan.
5. Open in CapCut makes **5–7-minute parts**, not one entire long draft. Split at scene boundaries where possible; maintain continuous scene/voice offsets and avoid missing or duplicated content.
6. Intended layer order: **images on lower video track, videos on upper video track**, not a locked one-layer layout.
7. Optionally omit audio from generated CapCut parts; final voice/audio may be added manually in CapCut.
8. No globally hardcoded 2.5-second segment. Video clips may originate as 4s sources and should be trimmed to exact scene durations, never naively extended beyond source content.
9. Canvas fill/fit rules, effects, bulk image animation and transitions must be controlled explicitly and must not silently override Scene Plan timings.

These are target behaviors, **not** all demonstrated as working external CapCut APIs.

## Capability matrix

| Area | Evidence level | Z Builder mapping / safety rule |
|---|---|---|
| Local Windows CapCut installation | Observed inventory | Version-pin behavior to tested 9.6.0; preserve isolation |
| Audio-free video drafts | Observed twice | No \`materials.audios\` or audio tracks needed for the two examples |
| Exact timeline positions | Observed twice | Use integer microseconds; round to chosen 30-fps frame policy consistently |
| Separate lower-index photo and upper-index video tracks | Observed in draft B | Two \`tracks[]\` and distinct \`render_index\`; actual z-order requires overlap test |
| Timeline gaps | Observed in draft B | Preflight check visual coverage (5.0–5.2 and 9.2–9.4 s in example) |
| Clip source trim vs timeline duration | Observed schema fields | Distinguish \`source_timerange\` and \`target_timerange\`; test real edit |
| Image/photo storage | Observed twice | \`materials.videos[].type = photo\` |
| Pendulum 1 / Halo Shift | Observed in draft A | Refer by valid material IDs and check local cache; names alone not enough |
| 39 adjustments, 10 blend IDs | Observed in resource files | No guarantee applying config by ID into a draft succeeds |
| Canvas width/height | Observed twice | Examples are 1920×1362 original; need explicit 16:9 test draft |
| 5–7 minute split output | User requirement only | Split by scene boundaries and independently validate each generated part |
| Optional audio import/export | User requirement + audio-free draft evidence | Native audio serialization still unverified |
| One-click bulk animations | User requirement | Need per-image draft reference test; unknown if safe at scale |
| Direct native timeline command | Internally documented | Depends on active session/permissions; do not rely on unsupported API |
| Converter/OTIO | Binary dependencies observed | Execute only isolated and review help/licenses; actual compatibility unknown |
| Editable true keyframes / layer compositing | Not verified | Dedicated controlled draft comparisons and visual round trip |

## Proposed safe processing algorithm (not implemented)

- Parse Scene Plan with exact timestamps and source media references.
- Validate each planned scene interval: no unintended missing time, conflicts, duplicate IDs or source outruns.
- Map scene timeline into integer microseconds; when 30-fps frame alignment is needed, use one deterministic rounding strategy and record adjustments. Avoid cumulative floating-point drift.
- Allocate tracks by media type: photos on a lower-index track; videos on a separate higher-index track. **Do not claim correct rendered z-order until a true overlapping test passes.**
- For videos, set source trim independent of target slot; video 4s source intended to last 2.5s must reference a validated 2.5s source interval, not simply set a 2.5s display duration without checking editor interpretation.
- For image fill, compute transform/scale from real source dimension versus explicit canvas size, and validate in CapCut preview (not yet tested).
- Partition scene list into independent ~5–7 minute parts at stable scene boundaries, reset each part's local origin, preserve global offsets in a manifest.
- If audio import off: generate audio-free drafts. If on: block until tested audio schema is available.
- Resolve effects only when resource reference is valid and present; otherwise show an explicit warning rather than silently pretending applied.
- Write new files into a separate output folder, never overwrite an original CapCut project. Preserve a rollback-safe backup copy.

## Validation gates before shipping a generated CapCut draft

1. JSON parser passes; unique IDs exist and every \`material_id\` / \`extra_material_refs\` reference resolves.
2. All target time ranges are nonnegative, match declared duration, have intentional overlap semantics and no accidental gaps.
3. All source trims are within available media duration (unless deliberately using an explicit image semantics rule); no missing paths.
4. Photo and video tracks exist and are presented in the intended order; verify with actual simultaneous overlap.
5. Image animation/transition survives save/reopen and resource availability checks; no unannounced substitutions.
6. Optional audio works in both modes; no accidental media duplicates or misplaced offsets at 5–7 minute boundaries.
7. CapCut 9.6.0 opens each **copy**, timeline timings look correct, UI preview renders, and the project remains editable.
8. Regression tests pass for an unchanged current Z Builder, with no VPS_1 or other Rajudesktop app modifications.

## Future minimum samples

- One photo covering 0–5s on lower track and an overlapping video e.g. 1–3s upper track, with both visible; save JSON plus a non-private preview screenshot.
- One audio clip MP3 with and without audio, same otherwise-identical timeline.
- 2.5s trimmed clip, 16:9 Canvas Fill, one animation/keyframe, one adjustment and one blend mode added separately so each change can be diffed.
- Isolated, explicit project reopen from generated copy, not writing to a user original.

## Privacy

Do not commit full draft originals, CapCut cache/effect binaries, personal media, full \`path\` values, device IDs, MAC/hardware IDs, login/auth resources, or crash dumps. Repository visibility is **public** at the time of this research. This documentation is intentionally sanitized.
