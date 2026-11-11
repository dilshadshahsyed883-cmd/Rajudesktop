# CapCut Native Export Trigger — 2nd Audit (2026-10-28)

## Scope
**NO independent renderer.** Examine how the installed *CapCut application itself* can be asked to export a draft using its native export engine. No edits to Z Builder or production, and no real CapCut export executed in this audit.

## Findings and evidence
1. **Documented third-party experimental native adapter:** [leileqiTHU/reverse-cli-anything](https://github.com/leileqiTHU/reverse-cli-anything/tree/main/capcut-cli) reports a Windows x64 native export tested against **CapCut 9.5.0.4050** with a real media workflow and recorded evidence. The demonstration's evidence belongs to its authors; it is not an independent local reproduction in our environment.
2. **Execution method:** A Python command in `capcut_agent.py` validates project and active timeline, starts an isolated worker, then `capcut_editor_worker.py` verifies pinned DLL SHA-256 hashes and uses Frida to attach to a **running CapCut process**. A loaded native bridge invokes existing Qt frontend methods on the application's thread.
3. **The actual native trigger** in `capcut_export_frontend_agent.js` is:
   - `MainWindowStyleTitleBarViewModel.openExportWindow` — opens the native export pane.
   - `ExportFileSelectorPanelViewModel` and `ExportVideoOptionsPanelViewModel` — set path, title, resolution, H.264, MP4, FPS and read back the settings.
   - `ExportHomeBottomViewModel.compileClick` — fires native export from within CapCut (no mouse click emulation).
   - `ExportClient::exportStart` observer / completion callback and export UI `FINISH` — verify that CapCut's real render ran. Output passes an independent media verification before publishing.
4. A separate official public headless render/CLI API was **not found**. Finding `ffmpeg.exe` inside CapCut does **not** prove that invoking FFmpeg standalone preserves CapCut effects or the rendering pipeline.
5. **Version limitation:** Our earlier signed and hash-verified installer audit extracted **CapCut 9.3.0.3970** (4,043 files) and found `videoeditor.dll`, `ffmpeg.exe`, etc. The 9.5.0.4050 Frida adapter's native addresses/hashes cannot safely be assumed to work on 9.3.0.3970 or whichever build the user currently runs.
6. **Runtime limitations:** Native bridge needs an *active* CapCut session with project and timeline open. It is **not headless**, may crash the CapCut process, and the adapter limits its command timeout to **300 s**. Overnight 5–7 minute parts might need longer; increasing the limit requires new acceptance tests, not just a flag change.
7. **Terms caveat:** CapCut Terms of Service as published on 2026-04-15 prohibit reverse engineering and automated scripts interacting with the Services. Native reverse-engineered injection/automation may violate those terms, so review this before using a third-party bridge. Source: https://www.capcut.com/clause/terms-of-service

## Exact upstream command surface (only on a verified supported build)
```powershell
cd D:\\ChatGPT\\reverse-cli\\capcut-cli
# CapCut must already be running with the target project and timeline active.
# Do not guess PID, project ID or timeline UUID. Inspect live state.
.\\capcut-agent.ps1 capabilities
.\\capcut-agent.ps1 version
Get-Process CapCut | Select-Object Id,MainWindowTitle
.\\capcut-agent.ps1 editor inspect --pid <PID> --project '<PROJECT_DIR>' --timeline '<TIMELINE_UUID>'
# Render the entire active timeline, via *CapCut itself*. NEW.mp4 must not exist.
.\\capcut-agent.ps1 --timeout 300 editor export --pid <PID> --project '<PROJECT_DIR>' --timeline '<TIMELINE_UUID>' --output 'D:\\Exports\\NEW.mp4' --width 1920 --height 1080 --fps 30
```

The CLI and its dependencies must come from the audited upstream repository; do not copy version-specific DLL offsets into our code blindly. Its own SHA-256 checks should reject version mismatches. The above command is a documented route, **not** a claim of a successful local export.

## Recommended architecture — native render only

Z Builder (existing draft generation unchanged) → Launch/Open saved project in CapCut → verify active editor + timeline → trigger native CapCut export with guarded version-specific bridge → await CapCut native task + UI completion → independently verify MP4 duration/streams → mark job completed; advance queue.

Control-plane alternatives:
- **Route A (research pilot):** Native adapter `openExportWindow → compileClick → ExportClient`, supported build only and subject to terms/reliability limits. No separate renderer.
- **Route B (fallback):** Human-equivalent keyboard/UI automation using CapCut's standard export controls (`Ctrl+E` etc.). Same CapCut renderer. Version UI changes and remote/locked desktop sessions are fragile.
- **Route C:** Official command line/headless API — no verified public interface currently.

## Acceptance gate
1. Verify actual installed CapCut version, exe signer, target DLL hashes, adapter license and legitimacy.
2. Clone a disposable short project (10–20 seconds), never test on originals. Native inspect checks right project/timeline.
3. Trigger one native CapCut export, prove provenance using native `ExportClient` completion and output duration. Confirm effects/text/captions visually survive.
4. Reopen/reexport using explicit fresh output names. Export must refuse output overwrite and simultaneous jobs.
5. Test 5–7 minute real draft, long rendering timeout behavior and stuck/cancel/recovery, without changing source timeline.
6. Only then support serial night queue, one active CapCut session at a time, no unattended replay when result unknown.

## Source index
- https://github.com/leileqiTHU/reverse-cli-anything/blob/main/capcut-cli/capcut_export.py
- https://github.com/leileqiTHU/reverse-cli-anything/blob/main/capcut-cli/capcut_export_frontend_agent.js
- https://github.com/leileqiTHU/reverse-cli-anything/blob/main/capcut-cli/capcut_export_observer_agent.js
- https://github.com/leileqiTHU/reverse-cli-anything/blob/main/capcut-cli/capcut_editor_worker.py
- https://github.com/leileqiTHU/reverse-cli-anything/blob/main/capcut-cli/docs/implementation.md
- https://github.com/yousefomar724/capcut-desktop-editing (native CapCut GUI export fallback; 9.4.0.4015)

## Follow-up binary fingerprint result — Windows CI PASS
- CI run: https://github.com/dilshadshahsyed883-cmd/Rajudesktop/actions/runs/40746599446
- Evidence artifact: https://github.com/dilshadshahsyed883-cmd/Rajudesktop/actions/runs/40746599446/artifacts/12842215931
- Target signed installer: **CapCut 9.3.0.3970**; native adapter pin reference: **CapCut 9.5.0.4050**.
- `lyra_cli_client.dll`: present but SHA-256 **does not match** reference.
- `videoeditor.dll`: present but SHA-256 **does not match** reference.
- `VECreator.dll`: present but SHA-256 **does not match** reference.
- `Qt6Core.dll`: present but SHA-256 **does not match** reference.
- **Determination:** Native adapter's fail-closed hash gate must reject audited CapCut 9.3. The underlying native API exists in some form, but direct 9.5 bridge compatibility is **not established**. Do not disable pin checks or reuse hardcoded 9.5 offsets.
- Test was read-only: no CapCut process launched, no Frida injected, no MP4 exported.
