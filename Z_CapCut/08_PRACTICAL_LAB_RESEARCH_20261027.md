# Z CapCut — deeper practical JSON research, 27 Oct 2026

Scope: **research only** for already-working Z Builder → CapCut handoff. Existing Z Builder code, GitHub `main`, original native CapCut drafts, Windows installation and private media remain unchanged.

## Sources / confidence labels

- **Owner evidence (O):** two user-provided native CapCut 9.6.0 `draft_content.json` samples, inspected *read-only* and audited locally with this kit. User-specific IDs/paths are excluded from this report and kit.
- **Community code/fixtures (C):** [capcut-cli](https://github.com/renezander030/capcut-cli) schema docs and source, [pyCapCut](https://github.com/GuanYixuan/pyCapCut) documentation, plus anonymized real-schema fixtures from [capcut-cli-david](https://github.com/Davidb-2107/capcut-cli-david/tree/master/test-fixtures/fixtures). Neither community project is an official CapCut API.
- **Offline demonstration (L):** this tool's static JSON edits and 9 Python unit tests. The demo files use fictitious media paths and synthetic IDs. Passing means *internal consistency*, not CapCut acceptance or rendered output.

## Audited native user drafts (O+L)

| Measurement | Owner draft A | Owner draft B |
|---|---:|---:|
| JSON schema version | 360000 | 360000 |
| Frame rate | 30 | 30 |
| Timeline duration | 14 s | 14.4 s |
| Tracks | 1 | 2 |
| Segments: video / photo | 1 / 2 | 1 / 2 |
| Broken referenced materials | 0 | 0 |
| Missing global visual coverage | none | 5.0–5.2 s; 9.2–9.4 s |
| Active animation entries | 1 | 1 |
| Transition entries | 1 (Halo Shift) | 0 |
| Audio tracks | 0 | 0 |

Both have `canvas_config` 1920×1362 and `ratio=original` (not 16:9). Photo materials are in `materials.videos` with `type: photo`; target/source timeranges are microseconds.

## Most valuable new discovery: real resource-ID match (O+C)

Owner sample's image combo **Pendulum 1** uses `resource_id=6811007755785081357`. This exact ID appears in public `capcut-cli/src/enums.json` as `capcut.image_combos` `slug=pendulum-1`. This is a **positive resource identity cross-check**, stronger than name-only matching. The owner's transition **Halo Shift**, ID `7683535350479817991`, was not found in that public catalog. Therefore the catalog is **not comprehensive** for this installation/account.

The community catalog currently describes **951 entries** under the CapCut section:

| Category | Listed entries |
|---|---:|
| transitions | 116 |
| masks | 9 |
| image intros | 43 |
| image outros | 23 |
| image combo animations | 108 |
| text intros | 76 |
| text outros | 68 |
| text loop animations | 53 |
| scene effects | 345 |
| character effects | 95 |
| audio effects | 15 |
| **Total** | **951** |

Do **not** interpret that list as installed/downloaded/licensed/free effects. Catalog has duplicate displayed names and different IDs; disambiguate by *category + resource ID + schema version*, not title. The `is_vip` flag in the third-party catalogue is not evidence of the owner's license or local cache state. `image_combos` may have titles in `title`, not `name`.

## Practical JSON experiment: original owners untouched (O+L)

The Python `z_capcut_lab.py experiment` command was run against a **memory copy** of owner draft B and briefly wrote a new copy in an isolated temporary location:

- Took an existing `sticker_animation` carrying the **Pendulum 1** preset; copied its nested `animations` metadata into the second photo's **already-linked empty animation slot**.
- Added two `common_keyframes` property lists on the second photo: `KFTypeScaleX` and `KFTypeScaleY`, each with a starting scale 1.00 and last visible frame scale 1.06. Offsets are relative to clip start, in microseconds, with a 30-fps last-visible-frame adjustment.
- Preserved every segment's `source_timerange`, `target_timerange`, material ID, `render_index`, number of tracks and project duration.
- Rebuilt material-ID lookup after modification; all references resolved. Source file SHA-256 was unchanged. The temporary modified owner draft was deleted after the offline test.
- No CapCut process was opened, no effect renderer run, and no companion `Timelines/` mirrors were updated. **Editor acceptance remains untested.**

## Bulk scalability experiment (L only)

- Synthetic draft populated with **300 photos** (plus an existing video) and valid, artificial image-to-material references.
- Copied existing animation metadata to **299 unanimated photo segments**; created **299 independent animation material slots** when none existed.
- Verified all material references remained valid, segment timing unchanged, project duration unchanged.
- **9/9 Python automated tests PASS** including both native-sample-shape audits, gap detection, owner-pattern animation copy, copy-protection SHA, missing reference rejection, unsupported schema rejection, existing keyframe refusal, 300-photo bulk test, and image-count safety guard.
- This is proof that metadata copying/validation scales on synthetic JSON, **not** proof of 300 rendered CapCut effects or editing throughput.

## Schema traps confirmed from external code/fixtures (C)

- Custom motion keyframes are under `segments[].common_keyframes` with `property_type` identifiers; preset intro/outro/combo effects are `materials.material_animations` references through `extra_material_refs`. An independent real fixture shows keyframed scale X/Y and `FreeCurveInOut` handles.
- `capcut-cli/src/decorators.ts` maps uniform zoom to `UNIFORM_SCALE`, **not** `KFTypeUniformScale`. Our conservative demo uses separate `KFTypeScaleX`/`KFTypeScaleY` until directly validated on owner's version.
- Public real fixture `masks-filters-draft.json`: filter material under `materials.effects` on a `filter` track. Another `effects-draft.json`: VFX under `materials.video_effects` with an `effect` track. Do not assume a single material array or apply-to-one-clip scope. `apply_target_type=2` is global composite in the documented VFX schema.
- `capcut-cli` reports that alpha-opacity keyframe fades may fail in final render even if preview shows them; this is a **third-party reported limitation**, not validated in the owner's installed CapCut.
- Some CapCut 8.x/9.x builds prioritize active nested timeline JSON or mirror data over project-root JSON. A root JSON patch alone may be ignored. Any practical generator must detect/sync companions on independent copies only.
- pyCapCut reports several capabilities through 9.5.0.4050, **not** a guarantee for owner's 9.6.0.4097. Current pyCapCut API warns about potential future track-order changes; pin versions if later integrating.

## Proposed Z Builder *experimental only* acceptance gates

1. **Do not rework the already-working timeline, clip trim, 5–7-minute splitting or layering.** Advanced editing is an optional post-processing operation, OFF by default.
2. Save a new complete CapCut project-folder copy, never edit user original or live CapCut project while it is open.
3. Map resource IDs to user PC cache availability, not merely community catalog names.
4. Explicitly select `image-only` versus `global`, independent of shared effect track defaults.
5. A/B check 1 image then 10 images, then 300 images, with CapCut reopen, *actual export*, cache presence and editor editability verification. Abort/revert when a feature doesn't render or persists incorrectly.
6. Validate active timeline/mirror authority before attempting any external writer operation; no undocumented internal IPC hooking.
7. Keep research on `docs/z-capcut-findings-20261027`; store private source media and native drafts on the private Drive archive.

## Final testing status

**Completed:** read-only owner draft analysis; 9/9 local schema tests; safe animation metadata clone and keyframe sample; public catalog ID cross-check; 300-image synthetic batch.

**Not completed:** native CapCut opening of any generated draft, visual effects rendering, actual 300-photo performance inside CapCut, Windows 9.6 version compatibility proof, effect cache availability, mirror/Timeline import handling in the owner's editor, real advanced-editing deployment.