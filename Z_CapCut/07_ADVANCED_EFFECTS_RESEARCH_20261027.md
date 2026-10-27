# Z CapCut — Advanced Effects & Editable Draft Research

**Date:** 2026-10-27  
**Repository:** `dilshadshahsyed883-cmd/Rajudesktop`  
**Research branch only:** `docs/z-capcut-findings-20261027` (never merge into `main` by default)  
**Target app:** CapCut Windows `9.6.0.4097` / native projects report version `9.6.0`  
**Purpose:** Extend *already-working* Z Builder timeline handoff with advanced native editable animations, VFX, filters, color and keyframe effects. **Do not rewrite or reimplement existing Z Builder video/scene plan/5–7-minute parts functionality.**

## Evidence classes

- **A — Owner-draft observed:** exact fields visible in the two provided CapCut 9.6 native JSON drafts; *not proof of new externally generated project success*.
- **B — Third-party sanitized real fixture:** anonymized real CapCut draft, schema version 360000, from independently published fixture set; *not a Z Builder or Windows 9.6 live test*.
- **C — Community library claim / schema documentation:** describes how open-source tools implement a feature; *compatibility not guaranteed on installed CapCut 9.6*.
- **D — Pending validation:** no project-file live round trip, visual proof, or feature availability confirmation.

## A. Important discoveries

### 1. Two separate image motion systems [A+B+C]

- **Custom editable motion keyframes**: `tracks[].segments[].common_keyframes[]`. Independent property lists (`property_type`, `keyframe_list`, `time_offset`, `values`, optional interpolation controls). `time_offset` is **relative to the segment start** in microseconds, not global timeline position.
- **CapCut preset animations**: `materials.material_animations[]`, typically an item with `type: "sticker_animation"` even when attached to a video/image segment, and referenced using the segment's `extra_material_refs[]`.
- Owner's first JSON proves **Pendulum 1** preset metadata and reference exist on an image. Both user drafts contain **empty keyframe data**, so keyframe behavior on the owner's CapCut build remains to be validated.
- External, sanitized real fixtures independently show `common_keyframes` for Ken Burns `KFTypeScaleX`/`KFTypeScaleY` with `curveType: "FreeCurveInOut"`, and an animation material with both `Fade In` and `Fade Out` entries.

**Practical consequence:** implement an independent future `motion_keyframes` path for Pan/Ken Burns, separate from `capcut_preset_animation` for prebuilt effects. Keep both explicit in Scene Plan and preflight; do not translate one into the other silently.

### 2. Uniform-scale identifier trap [C; source code checked]

Community `capcut-cli` source `src/decorators.ts` maps:

| Semantic property | Serialized `property_type` |
|---|---|
| `position_x` | `KFTypePositionX` |
| `position_y` | `KFTypePositionY` |
| `rotation` | `KFTypeRotation` |
| `scale_x` | `KFTypeScaleX` |
| `scale_y` | `KFTypeScaleY` |
| **`uniform_scale`** | **`UNIFORM_SCALE`** |
| `alpha` | `KFTypeAlpha` |
| `brightness` | `KFTypeBrightness` |
| `contrast` | `KFTypeContrast` |
| `saturation` | `KFTypeSaturation` |

Community docs explicitly warn that `KFTypeUniformScale` can be silently ignored; that behavior was reported and fixed in the CLI (`#80`). This is third-party evidence, **not** owner-machine 9.6 validation. If supporting scale keyframes, verify against a native 9.6 UI-generated copy first. For ease curves the fixtures show `FreeCurveInOut` and `left_control`/`right_control` handles.

### 3. Fade/opacity keyframes may not render [C; needs 9.6 test]

Community schema notes distinguish a preview vs exported-video pitfall: `KFTypeAlpha` keyframes on video/text can appear in preview yet fail in final output. Their workaround uses **intro/outro preset fade animations** in `materials.material_animations`, not standalone alpha-only keyframes. This is a **reported limitation of third-party testing**, not a verified blanket fact for every CapCut version. For robust Z Builder fade behavior, require an actual export test before enabling alpha-keyframe fades.

### 4. Effects and filters are not just decorations attached to image segments [B+C]

- Effects may be represented on dedicated `type: "effect"` tracks; filters may use dedicated `type: "filter"` tracks with their own timed segments.
- The external **real** `effects-draft.json` has 49 video segments and 1 separate effect track, with a material called `VHS Horror` at `materials.video_effects[]`, `apply_target_type: 2`.
- The external **real** `masks-filters-draft.json` has a separate filter track containing a `Vintage` filter at **`materials.effects[]`** with `apply_target_type: 0`, not `materials.video_effects[]`. This is significant: **different real drafts and community explanations use more than one material-array location**. An importer must recognize both, with a version/schema-specific decision; never assume one fixed `materials.video_effects[]` shape is universal.
- `apply_target_type` is documented by `capcut-cli` as `0=one segment`, `1=track type`, `2=global composite`. This is a *community interpretation* and needs a controlled 9.6 test for reliable per-image-only effects.

**Practical consequence:** applying an effect to images only is not equivalent to adding one global VFX filter to the whole project. Global effect tracks may affect videos underneath or elsewhere. Create effects only on intended image intervals and verify scope in CapCut; when unsure, refuse a supposedly image-only effect rather than silently affect videos.

### 5. Transition material is attached to outgoing segment [A+B+C]

- Owner's native draft A has **Halo Shift** in `materials.transitions[]`, bound to the preceding photo by its `extra_material_refs[]`, `duration=2_000_000`, `is_overlap=true`.
- Real external fixture shows **Dissolve**, `duration=466_666`, `is_overlap=false`, stored in the first of two adjacent clips' extra refs.
- A documented transition joins neighboring segments on **the same track**. Cross-track photo/video compositing and automatic transitions across independent tracks are **not proven**, so default to safe contiguous same-track pairs or explicit crossfade/render-compatible alternatives only after tests.

### 6. Modern CapCut projects can have active-timeline mirrors [C]

Community `capcut-cli` compatibility docs and reports show on several modern builds that root `draft_content.json` edits may be shadowed by `Timelines/<id>/...`, `template-2.tmp`, `draft_meta_info.json`, or other registration metadata. One reported Windows 8.7 and macOS 9.2+ mode chooses the *active* timeline document. Their **9.x row is only expected-compatible, not fully desktop-validated**. A separate report describes a successful 9.3 app-created-template round trip. This is why *safely generated drafts should use a CapCut-created project template* and preserve/synchronize the authoritative timeline/mirror format rather than modifying only one root JSON blindly.

**Existing Z Builder 5–7-minute parts already work per owner. Do not disrupt them.** For any *new effects-writing layer*, inspect the output bundle and compare CapCut's save/reopen behavior on a copy; only add mirror support if a demonstrated bug requires it.

## B. Open-source interoperability options (research, no dependency added)

| Project | Language | What documentation/source shows | Limitation / integration risk |
|---|---|---|---|
| [pyCapCut](https://github.com/GuanYixuan/pyCapCut) | Python; published `0.0.4` | Images/video, animations, effects, filters, transitions, keyframes, blend, masks; several feature rows validated on CapCut 9.5.0.4050 | Preview/migration project; README warns forthcoming API/track order break at 0.1.0. Existing repository root did **not** expose a LICENSE file in reviewed root; verify legal terms before copying code. No 9.6 live test here. |
| [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft) | Python | Underlying related draft-editing work and examples | Chinese JianYing IDs/names and CapCut international schema may diverge. Repository includes Apache-2.0 LICENSE; still verify package/version and comply with notices. |
| [capcut-cli](https://github.com/renezander030/capcut-cli) | Node >=18 CLI + Python wrapper | MIT licensed, draft JSON operations, editing/keyframes, transitions, effects, version detection, timeline mirrors, `lint`, `diagnose`; supports compiled specs and app-created project imports | Version matrix labels CapCut 9.x expected-compatible/unverified; desktop round trip for owner 9.6 not proven. Older CLI <=0.17.x documented security issues—do not introduce an outdated dependency. `caption --cloud` uploads audio only when explicitly opted in; avoid cloud route for offline-first Z Builder. |
| [capcut-cli-david fixtures](https://github.com/Davidb-2107/capcut-cli-david/tree/master/test-fixtures/fixtures) | Sanitized JSON fixtures | Actual 360000 schema sample names: `animations-draft.json`, `effects-draft.json`, `ken-burns-draft.json`, `masks-filters-draft.json`, `transitions-draft.json` | Fixtures are NOT editable output tested against owner's exact 9.6 Windows app. Read-only reference useful without asking user to reupload samples. |

**Recommendation:** no new dependency immediately. If advanced effects implementation is approved later, first prototype a **read-only validator** or isolated writer on a disposable generated project, compare direct JSON serialization against these examples, and enforce a Windows CapCut 9.6 saved/reopened/rendered acceptance gate. Do not replace existing working Z Builder generation.

## C. Exact observed sample fixture findings (public, anonymized)

| Sample fixture | Schema `version` | Observed features |
|---|---|---|
| `animations-draft.json` | 360000 | 1 video and 1 text track, `material_animations[0]` holds intro `Fade In` 0.5s and outro `Fade Out` 0.5s; material referenced by text segment. |
| `ken-burns-draft.json` | 360000 | 5 video segments, 2 audio tracks, 10 common-keyframe property groups reported in fixture; scale keyframes show `FreeCurveInOut` controls. |
| `masks-filters-draft.json` | 360000 | 1 video track + 1 filter track, `materials.effects[0]` contains `Vintage` filter, `value=0.5`, `apply_target_type=0`; one `common_mask` entry. |
| `effects-draft.json` | 360000 | 49 video segments, one effect track, `materials.video_effects[0]` = `VHS Horror`, `apply_target_type=2` (global). |
| `transitions-draft.json` | 360000 | 2 consecutive clips on one video track, outgoing clip references one `Dissolve` transition of 466666µs and `is_overlap=false`. |

All above are community-provided *fixtures*: no hidden claim of executed binary, verified licence availability or actual rendering on user's PC.

## D. Recommended acceptance test for advanced editing only

1. **No change to existing Z Builder** baseline; duplicate a working 5–7-minute part to an isolated disposable project and save hashes/manifests first.
2. Add **one** new feature at a time in a copy: Ken Burns 2-point `common_keyframes`, then a `material_animations` intro animation, then same-track transition, then a non-global image-only filter.
3. Validate JSON pointer references, unique IDs, timeline microseconds, effect-cache presence, frame-grid alignment and intended scopes.
4. Open in **CapCut 9.6**; check visibility in effect/animation UI, preview playback, export result, save/close/reopen, and editability. Preview alone is insufficient—particularly for alpha fading.
5. Test same feature on a 5–7-minute part with 300+ media segments only AFTER the single-feature specimen passes; avoid global VFX bleeding into video tracks.
6. If a feature is unverified, keep it OFF or mark it unsupported, not “applied”.

## E. Security and record policy

- Original user ZIPs, draft JSONs and reports: [private Z CapCut Drive archive](https://drive.google.com/drive/folders/1XmOgG1jY7_GI_UuXOC37zCLJsYbsdwdt).
- Sanitized findings: [Rajudesktop separate research branch `Z_CapCut`](https://github.com/dilshadshahsyed883-cmd/Rajudesktop/tree/docs/z-capcut-findings-20261027/Z_CapCut); **main unchanged**, no PR or merging.
- No proprietary CapCut binaries, cache assets, crash dumps, user personal files, account/device IDs or original project JSON will be committed to public GitHub.
- Do not execute bundled native agent IPC/DLLs or install tools as part of static research.
- Community dependency caution: version-pin, read LICENSE and changelogs, isolate test copy, avoid unreviewed cloud commands; CapCut app/pro asset licensing remains independent from an open-source code license.

## Sources verified in research

- Owner's two saved draft JSONs from private Drive / conversation; provided by owner (not reproduced publicly).
- Installed CapCut 9.6.0.4097 inventory and sanitized deep inspection; original archive remains private.
- https://github.com/renezander030/capcut-cli/blob/master/docs/draft-schema/03-keyframes-and-animations.md
- https://github.com/renezander030/capcut-cli/blob/master/docs/draft-schema/04-effects-filters-stickers.md
- https://github.com/renezander030/capcut-cli/blob/master/docs/version-support.md
- https://github.com/renezander030/capcut-cli/blob/master/src/decorators.ts
- https://github.com/GuanYixuan/pyCapCut/blob/main/pypi_readme.md
- https://github.com/GuanYixuan/pyJianYingDraft/blob/main/LICENSE
- https://github.com/Davidb-2107/capcut-cli-david/tree/master/test-fixtures/fixtures

**Status: additional external research + read-only fixture inspection complete. No Z Builder source code changed; no user CapCut draft changed or rendered.**