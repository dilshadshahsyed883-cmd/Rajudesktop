# Scene Desktop Studio — Rajudesktop

A **new, independent Windows desktop video editor** combining an indexed-media-library direction with Scene Builder-inspired planning and CapCut-like editing. The **initial MVP** is intentionally focused on a functional cut timeline, rather than presenting unfinished advanced controls.

## Milestone 1 capabilities (source)

- Import local images and videos directly into an editable V1 cut timeline.
- Native Windows UI, Qt video playback and still-image preview, global seek/play controls.
- Drag to reorder clips; trim source in/out; split at playhead; remove timeline items.
- Editable JSON `.sdsproj` projects with atomic Save/Open and local autosave recovery.
- Choose one narration track (WAV/MP3/M4A/AAC); preview via separate audio player.
- CPU-safe FFmpeg export to 720p or 1080p, landscape or portrait; optional narration mixed into final H.264/AAC MP4.
- Real FFmpeg smoke test checks export without touching original source files.
- Portable Windows build from GitHub Actions with checksums; **no automatic deployment**.

### Explicit MVP limits

This is **not yet a full CapCut editor**. Advanced layered timeline, LUTs, transitions, keyframes, asset tagging, AI script-to-scene generation, audio-video mixing parity and preview cache proxies remain future milestones. Export renders cut visuals, **does not preserve source-video audio**, and optionally adds one narration track. Project files keep absolute local media references (missing-media relinking is still pending). Playback is on the active clip, with cut-to-cut progression; complex visual compositing is not live-previewed yet.

## Windows development launch (developer use only)

1. Python 3.11+ (for developers): `python -m pip install -r requirements.txt`
2. Run: `python launch.py`
3. Import media, reorder/trim/split, Save as `.sdsproj`, Export MP4.

**Owners do not need to install Python for a future packaged Windows release.** Download the verified Windows ZIP artifact from a successful GitHub Actions run. The packaged executable uses a bundled imageio-ffmpeg executable; source inputs, exports and project files are not embedded in the application.

## Planned build and delivery

CI: GitHub Actions Windows runner → model + FFmpeg smoke tests → PyInstaller portable Windows build → SHA-256 checksum → downloadable artifact.

Installation: **manual operator-triggered Tailscale command only**, after Windows device, OpenSSH availability, target install path, checksum, backup and idle-editor state are validated. No auto-deploy, GitHub runner shell access to the PC, installer execution, VPS access, or existing app migration is wired into this repository.

Repository is currently public: **do not commit user videos, private keys, OAuth tokens or downloaded media**. Existing VPS_1/Haseeb/Bilal applications remain untouched.

## Tests

`python -m unittest discover -s tests -v`

Master plan and progress are maintained only in the separate **Scene Desktop Studio Master Google Doc** (not the VPS_1 Master Doc).
