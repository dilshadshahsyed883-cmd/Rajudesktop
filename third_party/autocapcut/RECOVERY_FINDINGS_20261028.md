# AutoCapCut v0.1.2 — Verified Read-Only Source Recovery

**Date:** 2026-10-28  
**Scope:** third-party Windows executable provided by user; **private source inspection only**, no copied proprietary files in this public repo.  
**Binary SHA-256:** `ea0590f1a18d723792746d55260b83313b6e2feada04260effb6b31b04a99157`

## Recovery result

The installer contains a valid 7z archive at executable file offset **93,546**, inside an NSIS self-extracting executable. Read-only extraction and parsing yielded:

- `resources/app.asar`, **582,630 bytes**, containing **25 application files**.
- `package.json` identifies `tryaitoday-autocapcut`, version `0.1.2`, Electron JavaScript (`type: module`), author `TryAIToday`. Its `private: true` setting is not a reuse/redistribution license.
- Extracted file types: JS/CJS modules, JSON CapCut templates, HTML/CSS UI, PNG/ICO assets.
- Embedded ASAR file integrity checks passed.
- **17 JS/CJS files** passed `node --check` under Node.js 22. This verifies parser syntax, not runtime functionality, product safety, compatibility, or rights to reuse.
- Electron runtime and installer assets were not executed, and no CapCut projects were modified.
- **Do not upload recovered third-party source, source ZIP, or the EXE into this public repository** without an appropriate license. A private user-specific extraction was supplied separately.

## Technical architecture observed (high-level, not copied code)

1. **Transition discovery** (`lib/transitions.js`): scans local CapCut project directories and examines `materials.transitions[]`; collects reusable templates indexed by `effect_id`, accounting for duplicate names with distinct IDs. It appears to use already-existing local CapCut project materials, not a public effect-search API.
2. **Transition linking**: constructs per-cut transition choices, clones the selected material with a unique ID, appends to `materials.transitions`, then references that material from the outgoing video segment's `extra_material_refs`.
3. **Image zoom** (`lib/zoom.js`): generates `KFTypeScaleX` and `KFTypeScaleY` keyframes using offsets **relative to a segment**, with in/out/alternate modes. Duration values follow microsecond conventions.
4. **Timeline creation** (`lib/builder.js`): aligns images via timestamps parsed from file names when enough are present, or evenly over the project's audio duration. This is more limited than Z Builder's Scene Plan authority and image/video sequencing.
5. **Persistent native draft updates** (`lib/write.js`): backs up top-level draft, writes nested `Timelines/<active id>/draft_content.json` mirrors when present, and updates project and root metadata timestamps/durations. It refuses to write when CapCut is running unless explicitly forced. This offers an independently testable compatibility hypothesis, not evidence that every CapCut version behaves identically.
6. **Edit spec** (`lib/editspec.js`): supports per-cut transition selection and validation; reports missing/ambiguous transition names/IDs and clips that cannot be matched.
7. **UI/IPC** (`electron/`, `renderer/`): native Electron desktop interface; actual GUI and export behavior were not executed in this analysis.

## Z Builder implications

| Candidate | Priority | Approach / evidence required |
| --- | --- | --- |
| Local transition catalog by actual ID | High | Independently implement inventory of allowed local CapCut draft transition metadata; A/B compare against genuine CapCut samples |
| Safe mirrored draft + root metadata handling | High | Use copies/temporary drafts; verify root index and nested timeline remain in sync after CapCut reopen |
| Native zoom via X/Y scale keyframes | High | Independently construct/test still-image keyframes and confirm CapCut preview + exported frame output |
| Transition rule validation | Medium | Surface missing, ambiguous and unavailable effects before generating Scene Plan drafts |
| Filename timestamp alignment | Low | Existing Z Builder uses authoritative Scene Plan timestamps; do **not** replace it |
| Full CapCut effects parity / export | Not demonstrated | The recovered JS does **not** establish full native effect coverage or direct final rendering |

### Follow-up acceptance tests

- Make two **disposable** native CapCut draft fixtures: transition-free baseline and otherwise identical transition-applied sample; compare `materials.transitions`, `extra_material_refs`, timeline copies and metadata.
- Verify selected transition with original downloaded resource, missing resource fallback, altered CapCut version, and reopen/edit/export. No modifying original projects.
- Test image zoom on second clip and later (relative vs absolute offset).
- Add independent tests under `Z_CapCut/lab` before proposing changes to `z_builder/`.
- Preserve Z Builder's unused-media priority, video non-reuse, video/image sequencing, fixed layering, optional audio and 5–7-minute splits. No unauthorized code merging or deployment.

## Trust and licensing boundary

The exact JavaScript was recoverable as unminified Electron application files, **but it is third-party code**, not thereby open-source or permission-granted. This public record intentionally contains only original technical analysis and factual interface/schema descriptions. The private recovered archive is not a project dependency and is not required for builds.
