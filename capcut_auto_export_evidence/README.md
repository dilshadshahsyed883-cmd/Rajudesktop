# CapCut 9.6 Ready-Draft Auto Export — evidence-based Windows proof of concept

**Status: CODE + synthetic verification, NOT real CapCut Windows acceptance.** Independent from Z Builder and every VPS app.

## Exact evidence used

- [Verified owner's 9.6.0.4097 archive inventory and DLL research](../capcut_960_evidence/README.md) — six original Drive parts verified to SHA-256; 4,757 files, each hashed. Native DLL lyra_cli_client.dll SHA-256 878df7053d8eb83bf2bf35621fbdc7652e80836680a658a786560689f788f9f7.
- In the real DLL, literal lyra-cli draft export, exportStart, ExportService, ExportDraft and other native symbols exist. Wrapper lyra-cli-ipc.cmd and lyraCliIpcClient.mjs also exist in the owner's 9.6 package, but **that does not prove this release exposes a working public CLI endpoint or one-click native export**.
- Existing [CapCut Native Export Controller](../capcut_native_export_app/README.md) includes a Windows 9.6 audit of actual Qt/QML editor and dialog identities: MainWindow_QMLTYPE_* with editor title CapCut, native dialog Export-<exact project name>, same process ID. Export-button ratios from that audit: editor (0.920, 0.023), dialog (0.817, 0.959). They **must be visually checked** on owner's actual screen.

### Why guarded GUI export?

The goal is native CapCut-rendered MP4, not an FFmpeg approximation. This demo avoids assuming undocumented native CLI works in 9.6. It **does not** inject DLLs, change CapCut preferences, switch resolution/FPS, create drafts, download assets, click cloud, upload video, or edit JSON.

It opens one prepared draft from a recorded CapCut Home card (or an already-open editor); recognizes installed 9.6 by exact DLL SHA-256 and CapCut process/window identity; opens native Export and matches Export-<name>; clicks native Export using calibrated audit ratios; waits for a new <name>.mp4; checks stable MP4 container and ffprobe streams/duration/dimensions/SHA-256.

## Windows usage

1. Download the Windows ZIP from a successful dedicated GitHub Actions run, extract and launch CapCut_Auto_Export_Evidence_Demo.exe.
2. In CapCut **9.6.0.4097**, finish editing/export settings **before** the demo. Set native Name to exact project name and Export to to chosen folder. Switch cloud sync OFF yourself. Return to Home for the ready draft or leave correct editor open.
3. Enter project name, MP4 output folder and ffprobe.exe path (autodetect if FFprobe is on PATH).
4. Open CapCut native Export dialog to inspect Name/Export-to/settings; click **Preview existing Export button**. Check red marker lands on real Export button. Close Export dialog without rendering and return Home.
5. Click **Record Home draft card**; within five seconds hover over the center of the intended draft thumbnail. Do not click. For already-open editor, choose checkbox instead.
6. Tick preflight acknowledgment and click **START SINGLE DRAFT EXPORT**. Keep Windows **unlocked, awake, and CapCut foreground available**. Don't touch mouse/keyboard while automation clicks.
7. After render, demo monitors <project>.mp4 and validates MP4 atoms and FFprobe streams, duration, resolution and checksum. Results/logs are local under %LOCALAPPDATA%\CapCutAutoExportEvidence\.

## Safety

- Single project only. No unattended multi-project queue until real 9.6 Windows rendering and project-switching tests pass.
- Multiple windows, title mismatch, changed geometry, wrong DLL fingerprint or existing output cause a **HALT**, no blind retry.
- State is journaled before final Export click. After crash/uncertain result, manually check CapCut and reconcile output before acknowledging a new attempt. Stop monitoring **does not cancel CapCut rendering**.
- No scheduler, anti-sleep bypass, cloud access, background service or locked-desktop support.
- FFprobe verification only validates **media metadata**, not visual effects, lip sync, subtitles, cloud status or timeline parity. Manually play first real MP4.
- An existing CapCut export path/name must be confirmed by the operator. QML field values are not read from the app, and settings are never overwritten.

## CI, build and tests

Dedicated workflow: [.github/workflows/capcut-evidence-auto-export-windows.yml](../.github/workflows/capcut-evidence-auto-export-windows.yml). On PR, tests pure functions, creates portable Windows EXE, runs frozen self-check without CapCut, creates SHA-256 and uploads ZIP artifact. GitHub Actions runner has no running CapCut: **packaging PASS is not export PASS**.

Local: Python 3.12+, install requirements.txt and run python -m capcut_auto_export_evidence.app. Tests: python -m unittest discover -s capcut_auto_export_evidence/tests -v.

## Production isolation and pending acceptance

Nothing modified in Z Builder, existing CapCut tools, the real CapCut installation, original drafts, PC services, other Rajudesktop apps or VPS_1. Original binary ZIP retained on owner's Google Drive; code and evidence only in GitHub.

Pending: live 9.6 window + DLL fingerprint, disposable ready-draft export, MP4 full decode/playback, screenshot-confirmed buttons, then safe serial multi-draft queue and recovery only after successful acceptance.
