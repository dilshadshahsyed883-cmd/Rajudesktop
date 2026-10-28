# AutoCapCut — Transitions Only (Independent Desktop App)

**Prototype v0.1 (28 October 2026)**. This is an independently implemented, standalone Windows tool. It is **not** an official TryAIToday build, not a modification of AutoCapCut v0.1.2, and not a Z Builder update. The original third-party EXE is untouched and is not bundled.

## Run

Python **3.10 or newer** on Windows. Unzip the package, double-click **`start.bat`**. Tkinter and all application dependencies use the Python standard library. No EXE build is included.

## Complete workflow

1. In CapCut, save a **duplicate** of the project you want to modify. Close CapCut completely.
2. Run `start.bat` and point **Change folder** to the parent folder of your CapCut project folders. The default is `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`.
3. Choose your project. **Refresh** scans saved CapCut project transition materials (`materials.transitions`) and lists them by `effect_id`. To make a missing transition available, use it once in CapCut, save that project, close CapCut, then refresh.
4. **Transitions** tab: select **Single** (one highlighted transition), **Random mix** (multiple selected), or **Edit file only** (leave all other cuts unchanged). Search transitions, star favorites, **Mix favorites**, and choose duration (0.2–1.5 seconds).
5. **Edit file** tab: load an AutoCapCut-compatible `version:1` JSON. Each `after` filename specifies the outgoing cut, `transition` is the exact transition name, optional `effect_id` disambiguates duplicate names, `duration` overrides the slider. This file overrides baseline selections. Extensionless/case-insensitive filenames are accepted. Unlike the original build, ambiguous filename matches are **skipped safely** instead of guessing; optionally supply `track_index` and `segment_index` (zero-based) to disambiguate.
6. **Validate / Preview** displays selected transitions plus `Will Apply`, `Missing`, `Skipped` warnings. Only directly adjacent clips **on the same video-type CapCut track** are eligible. Overlaps, gaps, missing resource identities, cross-track junctions and duplicate after-names without clarification are skipped.
7. **Apply transitions only** asks for confirmation, refuses to write while CapCut is open, and stores complete per-file backups. The engine replaces/attaches only the selected outgoing-cut native transition material references; it **never rebuilds the timeline**.
8. Reopen your duplicate project in CapCut and visually verify transitions, project integrity and exported video. Use **Open backups folder** to recover the original JSON files if a CapCut-version mismatch occurs.

## What is preserved

- **All existing image and video segments** on all tracks, exact sequence and layer order.
- **All source and target time ranges** (no trimming, shifting, duration changes).
- Audio tracks, voices, keyframes/motions, volume, canvas, fps and media paths.
- Any pre-existing transition on a cut **not targeted** by the new selection.
- Original media files (.mp4/.jpg/.png/.mp3) are never opened for editing or deleted.

The engine modifies only `materials.transitions` and selected outgoing `segments[].extra_material_refs`. It backs up, then synchronizes main and active nested CapCut timeline JSON where present and refreshes existing project metadata. Reapplying the same transition and duration is a no-op (idempotent). No CapCut binary is executed by the engine.

## Sample edit file

```json
{
  "version": 1,
  "transitions": [
    { "after": "0-00.png", "transition": "Flash Zoom", "duration": 0.6 },
    { "after": "1-41.mp4", "transition": "Blink", "effect_id": "REPLACE_WITH_REAL_EFFECT_ID" }
  ]
}
```

The names and IDs above are examples; only catalog entries found in your installed CapCut projects can be applied. The tool does **not** download effects. There is no promise of every CapCut version accepting the inserted native material. No render/export engine is included.

## Backups and undo

Before each actual change, original project JSONs + `draft_meta_info.json` and matching `root_meta_info.json` entry (if present) are backed up to:

`<Project Folder>\.transition_only_backups\<UTC Timestamp>\`

The backup directory contains `manifest.json` identifying each original path and backup. For manual restore, close CapCut, **first make a copy of the current project**, then copy each backed-up file to the exact original path listed in the manifest. Editing is blocked while CapCut is open; no unprompted automatic restore is performed. Atomic per-file writes are rolled back after a detected error.

## First owner-reported Windows/CapCut result — 2026-10-28

**Reported:** "transitions applied successfully" when testing the standalone AutoCapCut Transitions Only prototype on the owner's CapCut setup. This is a positive live application report beyond the synthetic unit tests.

**Follow-up owner confirmation:** Existing **video clips** and **timeline layers** were also preserved successfully after transitions were applied. Record these as **owner-reported live PASS** alongside successful transition application. These are observed results from the owner's test, not an independently inspected before/after draft or final MP4 export. Audio preservation, exact source/target timestamps, every multi-track junction and exported-render parity remain unverified.

**Change-control decision:** Freeze the presently working behavior. No changes to the original third-party AutoCapCut EXE, this application's engine, Z Builder, or the independent renderer are authorized by this success report. Continue testing new scenarios only on duplicate drafts.

## Testing

```sh
python -m unittest discover -s tests -v
```

16 synthetic unit tests passed in the supplied development environment. These tests cover mixed image/video preservation, editspec v1, missing transitions, duplicate names, same-track restrictions, idempotency, CapCut-open write block, backups, mirrored draft sync, stale preview and failed-write rollback. **Owner-reported live PASS (28 October 2026): transition application, existing video clips retained, and timeline layers retained**; timing, audio and final exported-render acceptance have not yet been independently verified. Test new cases only on a duplicate first.

## Privacy / ownership

No telemetry, API calls, downloads or credentials. No proprietary recovered source, original AutoCapCut executable, installed CapCut materials or user footage are included. The implementation is independently authored around publicly observable/native project JSON behavior. Z Builder, VPS_1 and the original AutoCapCut EXE remain unchanged.
