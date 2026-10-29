# CapCut Controls Studio

Independent Windows app extracted from the verified Z Builder V6.1 source at [`dfb39f8ab3e0457d54317de31cc2a6e80e16023e`](https://github.com/dilshadshahsyed883-cmd/Rajudesktop/commit/dfb39f8ab3e0457d54317de31cc2a6e80e16023e). Z Builder's source, engines, release and runtime remain unchanged.

## Workflow

1. Select the CapCut projects folder once. The app detects projects and remembers the selected project.
2. Use the shared project selector above **Transitions / Animations / Scale**. One Refresh loads external changes; automatic background scanning keeps the same project synchronized without resetting valid previews or reopening popups.
3. Choose controls and click Preview. Click Apply to edit only that selected project, with automatic backup, guarded writes, validation and rollback. Close CapCut before Apply.

The dark, compact window defaults to 980 × 820 and can be resized. Native controls, favorites, random mixes, transition Edit File JSON, image selection, blur levels and deterministic Scale seed are retained. Scanning, native resource validation, previews and saves run in a background thread. One per-project write lock also serializes this standalone app's editors across processes. Status, errors and progress stay inline; Apply is the explicit write action.

**Scale defaults:** Strong Level 3 canvas blur; video scale 150–170%, Y -250 to -190 px, X 0; image scale 105–110%, Y -50 to 0 px, existing X preserved; seed 28; invert Y off. Existing transform keyframes are skipped according to the original reference engine, while animation references remain intact.

Only native resources referenced by the selected project's saved draft are listed. Missing animation cache assets are marked and blocked before application. Combo animation duration is fitted to each image's duration; In/Out/compound animation retiming remains unsupported. Existing mixed image/video tracks, clip order, durations, source trims, media files and audio are preserved. This app edits existing drafts; it does not generate or rebuild a timeline.

**Effects and filters are excluded:** no detection UI, controls, extension module or editing operation. Existing effect/filter data is preserved in native drafts.

## Run and build

```powershell
python -m pip install -r capcut_controls_studio/requirements.txt
python -m capcut_controls_studio
```

End users download **CapCut_Controls_Studio.exe** from the GitHub Release. It is a one-file PyInstaller build with a bundled Python runtime; no Python installation, BAT launcher, ZIP extraction or external internal folder is required. PyInstaller's temporary runtime extraction is automatic.

```powershell
python -m unittest discover -s capcut_controls_studio/tests -v
python -m capcut_controls_studio.launch --self-test-report smoke/Windows-Smoke.json
```

The Windows Actions workflow runs native safety/UI tests, checks protected Z Builder paths have no changes, builds the one-file EXE, and **actually launches that frozen executable**. Its isolated smoke workflow detects disposable projects and applies transitions, animations and Scale, verifying backups, same-track preservation, untouched media/peer projects/audio/timing and screenshots of all three tabs. It never edits user projects to test the app.

Native CapCut visual playback on the user's installed version is a separate acceptance check. JSON fixture success does not establish every downloaded asset's playback behavior.

## UI references and provenance

See [REFERENCE_AUDIT.md](REFERENCE_AUDIT.md) for the exact AutoCapCut revisions and architecture review. UI patterns are implemented in this app; backend logic is extracted from the user's Rajudesktop repository. No third-party AutoCapCut source, assets, timeline generator, UI automation, rendering pipeline or packaging code is bundled. The screenshot supplied by the owner is the primary visual direction.

[EXTRACTION.json](EXTRACTION.json) records source paths and hashes. Extracted transition and animation engines remain byte-for-byte copies of V6.1. The visual engine preserves its Scale/Position/Blur logic; only the excluded filter/effect import, option fields and extension block were removed.
