# CapCut Native Export Controller (Windows) — v0.2.0

**Separate from Z Builder.** This app drives CapCut's real Windows export UI and then verifies that the generated MP4 container is complete. It never edits CapCut drafts, effects, captions, or timelines. Developed from the Windows CapCut 9.6.0.4097 audit of 2026-10-28; no claim of live Windows success until a real test is returned.

## v0.2 recovery from "Expected exactly one visible CapCut editor window; found 0"

The uploaded CapCutNativeExport.log confirms discovery failure. The native
CapCut editor may be present even when Qt window detection fails. v0.2
accepts the process name CapCut.exe if executable path inspection is blocked,
and recognizes smaller/dynamically titled native Qt editor windows.

If Detect still fails, manually click Export in CapCut. Keep the native
Export-1028 dialog open. Return to this app, use Detect CapCut,
then Preview export click. Check the red click marker, verify CapCut output
name and folder, then start guarded native Export. It requires one real
CapCut.exe native export dialog for the exact project. A second dialog,
wrong name or cross-PID mismatch still blocks the export.

If detection fails, the app saves diagnostic_windows.json next to native_export.log
under the user's LOCALAPPDATA/CapCutNativeExport folder.

## Run

1. Open the intended project in **CapCut desktop** and keep CapCut in the foreground. Use a normal unlocked Windows session with a monitor on. Windows scale/layout changes may require recalibration.
2. Unzip this folder, then double-click `start.bat`. Python 3.10+ is needed; the launcher uses a local `.venv`.
3. Type the **exact project name**. For audit project `1028`, enter `1028`.
4. Select the expected MP4 folder. **CapCut's native Export dialog must independently be set to the same folder, and its Name field to the same name.** The app does not read or modify these QML text boxes in v0.1.
5. Press **Detect CapCut** → **Open native Export** → **Preview export click**. The preview shows a red circle on the button that will be clicked. If the red dot misses the turquoise Export button, **do not start**.
6. In CapCut's Export dialog confirm audio/video settings, export name, and export location. Tick the confirmation checkbox in this app, then choose **START NATIVE EXPORT**.
7. Keep the Windows session unlocked and the display on. The app waits for a new `<name>.mp4`, checks stable size/timestamps, and verifies MP4 top-level `ftyp`/`mdat`/`moov` boxes. If monitoring stops or times out, the CapCut render may still run.

## Safety and limitations

- Only one visible CapCut **editor window** is supported; ambiguous windows block execution.
- The native export dialog title must match `Export-<name>` and must belong to the same CapCut process as the editor.
- No overwrite: the app blocks if `<name>.mp4` already exists in the selected folder.
- No computer vision, OCR or fragile UI Automation child controls are required. It uses screenshot-calibrated proportional button coordinates after verifying CapCut native window identity and geometry.
- Screen DPI/theme/layout changes may make button positions wrong. Inspect the marked preview each time layout changes.
- Export settings are **not changed programmatically**. The controller cannot prove effects, transitions, fonts, or audio parity from MP4 container metadata; visual review is still needed.
- This release handles **one already-open project**. It does **not** claim fully unattended, multi-project overnight queue functionality yet. Queuing requires verified safe project switching and end-to-end native export proof.
- UI screenshots and logs are stored locally in `%LOCALAPPDATA%\CapCutNativeExport\` and are never auto-uploaded.
- Anti-lock-screen automation is not implemented. Windows UI control cannot run during a locked/sleeping desktop.

## Evidence-specific coordinates

Based on attached `CapCut_Native_Audit_20261028_113919_116.zip`:

| Control | Evidence | Relative click position |
| --- | --- | --- |
| CapCut editor Export | `Editor_132706.png`, class `MainWindow_QMLTYPE_544` | x=0.920, y=0.023 |
| Native dialog Export | `Export_198506.png`, title `Export-1028`, class `ExportWindow_QMLTYPE_1594` | x=0.817, y=0.959 |

The raw audit's `native_attempt.json` says `blocked_project_identity_not_visible`, even though the `Export-1028` window is identifiable. This app resolves identity via window title + class + process association, not inaccessible QML descendants.

## Tests

`python -m unittest discover -s tests -v`

## Repo placement

Source of truth: `Rajudesktop/main/capcut_native_export_app/` (separate from `z_builder/` and `Z_CapCut/`).