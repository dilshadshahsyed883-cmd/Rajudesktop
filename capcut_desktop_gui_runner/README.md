# CapCut Desktop GUI Export — portable agent-assisted package

**This is an actual portable Windows toolkit, not a fully standalone automatic exporter.**
The reused upstream is an agent skill: `cc.py` provides input/observations, while a visual
Codex/Claude agent (or human operator) interprets screenshots and decides the next command.
No agent/model/API credentials are bundled. A chat-only agent without permission and tools to
control your Windows session cannot execute it. No unattended overnight success is claimed.

Download `CapCut_Desktop_GUI_Export.zip` from the dedicated workflow artifact or release.
Extract to a writable folder and open `START.bat`. Python 3.12.10 and the upstream dependencies
are bundled; no Python installation or first-run dependency download is needed. CapCut itself
and its bundled `ffmpeg.exe` must already be installed. No renderer or CapCut binary is shipped.
Windows x64; an active unlocked foreground desktop is required. Do not share keyboard/mouse
with the agent while it operates. Screen lock, disconnection, layout/DPI and UI changes can break it.

## Export only

1. `START.bat detect` — original installed/running CapCut detection. No input or export.
2. `START.bat inspect list` — original read-only project list.
3. `START.bat prepare --project "D:\Projects\ReadyProject" --folder "D:\Exports"`
   reserves a unique empty job folder and records JSON hashes, duration and canvas.
   It prints `output` and **does not open the project or start export**.
4. Follow **AGENT_EXPORT.md**. Select the exact project in CapCut Home using a fresh screenshot,
   open Ctrl+E, inspect settings and the cloud checkbox, select the reserved folder and name
   `export`. Every screenshot-only control needs visual review; no replayed universal coordinates.
5. Only after actual completion is visible:
   `START.bat verify --folder "D:\Exports" --ffmpeg "D:\CapCut\Apps\9.4.0.4015\ffmpeg.exe" --completion-seen`
6. `START.bat status --folder "D:\Exports"` shows current project, status and result.
   Prepare the next project only after VERIFIED. One reserved job globally per Windows user; the persisted global reservation blocks
   other batch folders until verification. Other Windows users/manual CapCut exports cannot
   be locked by this toolkit: the agent must ensure none is active.

Verification requires a stable MP4, matching H.264 codec/duration/canvas, an audio stream,
full video/audio decode, and unchanged source JSON hashes. Audio presence/decode is checked;
listening, lip sync, loudness and visual timeline parity still require human review.
Silent projects and non-H.264 output are deliberately rejected by this acceptance profile.
Each success records checksum, stream information and output size in `job.json`.
The `--completion-seen` flag is a visual attestation, not machine detection of the completion UI.

Use `START.bat cc ...` for the original upstream primitives (version/windows/tree/find/focus/
key/click/type/act/scroll/screenshot/wait/wait-for); consult original command help via
`runtime\python.exe upstream\scripts\cc.py --help`. The export launcher excludes edit-specific
scripts. Generic input can still edit if misused; use only the documented export route.
Original scripts remain unmodified and are not an editing UI in this application.

## Version and safety

Upstream author demonstrated 9.4.0.4015. The owner's previously recorded **9.6.0.4097 is NOT
ACCEPTED**. Input including screenshot-induced focus is blocked on another running version;
read-only version/tree inspection remains available. No override switch is shipped. See
ACCEPTANCE.md for the fresh acceptance requirements before a developer changes that gate.
Even 9.4 requires per-session visual review: baseline version alone does not validate coordinates.

Never modify original JSON, timeline, media, account or settings. Do not click cloud, Share,
sign-in, purchases or Pro activation. Export dialog cloud sync may be ON by default. If already
OFF, leave it OFF. If ON, **stop**: the owner must resolve this beforehand; this package does not
change account/settings. Fresh screenshots must show it OFF before Export. Also stop on
unexpected windows, missing media, Pro prompts or unsupported controls. CapCut may remember
last export path itself; the runner does not edit settings or promise to prevent CapCut's own
normal persistence. Do not auto-save, restore, delete or rewrite originals if hashes change.

No-overwrite: unique job directory, fixed fresh `export.mp4`, inspect empty destination before
Export; never accept an overwrite prompt. Verification does not encode or rewrite output.
Unresolved/failed verification blocks the next job. Leave partial files/logs for diagnosis.
Do not auto-close a running export, retry a click, or start another project after ambiguity.
There is no automatic recovery/skip or unattended queue in this source; inventing these would
require new screenshot interpretation logic beyond the demonstrated scripts.

## Build and evidence

`build_windows.ps1` builds the portable runtime and checks dependencies, launcher, original
command help/version/windows, and read-only inspector. Tests use disposable fixtures and real
FFmpeg media on CI. GitHub-hosted Windows has no interactive CapCut: actual selection,
cloud-off review, export completion and unattended batch remain **NOT TESTED**.
See TEST_REPORT.md and the artifact's WINDOWS_SMOKE.json. Packaging PASS is not export PASS.

Only this folder, its dedicated workflow and APP_INDEX.md are changed. Z Builder and other
applications are untouched. Upstream MIT license and exact source hashes: PROVENANCE.json.
