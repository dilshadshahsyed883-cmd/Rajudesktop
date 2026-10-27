# Z CapCut — CapCut Research & Z Builder Integration Record

**Recorded:** 2026-10-27  
**Target application:** CapCut for Windows **9.6.0.4097** (native drafts report app version 9.6.0)  
**Related desktop app:** Z Builder (in Rajudesktop, independent of VPS_1)  
**Status:** Static inventory/configuration research and TWO native-draft comparisons completed. **Generated-draft round-trip in CapCut not yet tested.**

This folder is a persistent engineering record named **Z CapCut**. It is **not** a claim that CapCut automation, project generation, or all premium effects have been implemented.

## Evidence and contents

| Evidence | Status / observation | Document |
|---|---|---|
| CapCut installation inventory CSV | 4,741 file entries; ~1.780 GiB; structure and sizes | [01 — Installation inventory](01_INSTALLATION_INVENTORY.md) |
| Safe resource collector ZIP | 249 selected resource files + manifest; 209 parseable JSON documents | [02 — Deep resource research](02_DEEP_RESOURCE_RESEARCH.md) |
| CapCut native draft A | 1 track; 3 sequential items; animation and transition | [03 — Draft schema and experiments](03_NATIVE_DRAFTS.md) |
| CapCut native draft B | 2 tracks; lower-index photos and higher-index video; two 0.2 s gaps | [03 — Draft schema and experiments](03_NATIVE_DRAFTS.md) |
| Z Builder implementation mapping | Proposed requirements, status labels, safety and test matrix | [04 — Z Builder integration](04_ZBUILDER_INTEGRATION.md) |
| CapCut root-binary ZIP | 177 root-level native/runtime files; sensitive crash dumps excluded from public repo | [05 — Binary ZIP inspection](05_ROOT_BINARY_ZIP.md) |
| Machine-readable public findings | Sanitized resource IDs, version and verified field names | [capability_manifest.json](capability_manifest.json) |

| Official installer retrieval and next native sample priorities | Overlapping-layer, fill/trim, audio, effects samples; master doc linked; installer fetch attempted but failed | [06 — Next evidence](06_NEXT_EVIDENCE_AND_OFFICIAL_INSTALLER.md) |

## Most useful verified facts

- Timeline positions and clip lengths are in **microseconds** using segment `target_timerange`; trims are in `source_timerange`.
- Media linkage: `tracks[].segments[].material_id` resolves against `materials.videos[].id`. In the two supplied drafts **both images and video** are represented in `materials.videos`, with material `type` = `photo` or `video`.
- Sample A: one track, three consecutive items, **14 seconds** at **30 fps**; video 0–4 s, photo 4–9 s, photo 9–14 s.
- Sample B: **two tracks**, **14.4 seconds** at **30 fps**; photos on `tracks[0]` / `render_index=0`, video on `tracks[1]` / `render_index=1`. Photos: 0–5 and 9.4–14.4 s; video: 5.2–9.2 s. Two visible timeline-content gaps of 0.2 s each if no background fills them.
- Both samples have **1920 × 1362** canvas at ratio `original`, **not 16:9**.
- Sample A links photo animation **Pendulum 1** (resource `6811007755785081357`, 5s) and transition **Halo Shift** (resource `7683535350479817991`, 2s, overlap=true). Sample B retains Pendulum 1 but has **no transition**.
- Zero audio tracks/materials in both samples shows **audio-free drafts exist**, not how audio insertion works.
- 39 DefaultAdjustBundle subgroups, 10 mix-mode IDs, 9 aspect-ratio presets and named animation publishing routes were found in installed resource files.
- Common Agent documents a session-dependent timeline draft CLI. **Not evidence of a public, universally callable CapCut API.**

## Verification definitions

- **Observed**: present directly in user-provided filesystem inventory, extracted resource text/configuration, or native JSON draft.
- **Documented internally**: usage described by CapCut/Common Agent bundled text, but not executed as an external integration.
- **Hypothesis / pending**: plausible but not verified in a live CapCut editing session.
- **Requested behavior**: a Z Builder product requirement, not evidence CapCut already supports it.

## Safety and reproducibility

The original inventory, draft JSON and inspection archive are **not** committed: they include computer-specific paths, machine/account identifiers, and may reference proprietary installation assets. This folder contains only sanitized summaries and public-form resource metadata. No CapCut binary was executed or modified during the investigation. Avoid editing an original draft: generate copies in isolated folders and reopen in the installed CapCut version for visual validation.

## Next validation

Create a throwaway overlapping example with a photo lower and video upper *at the same moment* to prove visual compositing order; then audio, source-trim, keyframe, canvas fill, and effect persistence comparisons. See [04 — Integration](04_ZBUILDER_INTEGRATION.md) for the test matrix.
