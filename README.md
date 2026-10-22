# Rajudesktop — Scene Desktop Studio for Windows

Independent, local-first **scene planning + indexed media library + multitrack video editor**. Windows application source and distributable are hosted ONLY in this repository. No existing VPS_1, Haseeb, Bilal, Scene Builder or SML deployments are modified.

## Editing capabilities

- Local media library: file/folder import (background indexing), searchable thumbnails, selected/video/image counts, tags, exact duplicates, candidate/approved/rejected review and approval.
- Scene Director: import TXT or paste script, split into editable timed scenes, match approved local media (local-first, alternate video/image, video-only or image-only), manual media selection and batch five-at-a-time approval.
- Optional **actual AI** scene proposal generation using an owner-installed **local Ollama** model. It runs only against 127.0.0.1:11434 when the operator clicks AI Scene Plan; no background model downloads and no hosted cloud upload. If no model is installed, the built-in deterministic planner works offline.
- Graphical six-track timeline for main video, video overlay, captions, narration, music and SFX with clip thumbnails and audio waveforms. Drag positions, switch compatible tracks, edit source trims, split, duplicate, delete, undo/redo, lock/mute/hide tracks and timeline zoom.
- Inspector: zoom 50–300%, horizontal mirror, pan/reframe/slow-push/Ken Burns motion, 23 color looks plus optional user-supplied .cube LUTs, timeline keyframes for zoom/brightness/saturation, look intensity, noise/grain styles, fade/dissolve/slide transitions, optional original-video audio, audio volume/fades and captions.
- SRT caption import/export, Whisper-compatible word JSON import, timed ASS karaoke highlighting, user-initiated local CPU faster-whisper transcription (tiny/base/small model weights downloaded only with express approval), project save/open, backups, recover autosave, missing-asset relinking and read-only Windows resource panel.
- FFmpeg preview segment compositing from the same project model, preview continuation, 16:9/9:16 720p/1080p video export, original/voice/music/SFX audio mixing, output open/play, job cancellation and source-preserving non-overwrite.
- Hashed render-section reuse, guarded free-disk admission, app-owned cache trimming and preview expiry; original project media files NEVER removed.

## Important accuracy/limitations

The UI is **CapCut-inspired**, not full CapCut feature parity. Playback previews render short cached sections on a worker, so instant GPU-smooth scrubbing and frame-perfect arbitrary-layer preview on all hardware is NOT guaranteed. Transitions and presets cover a functional subset; arbitrary transform keyframes beyond zoom/brightness/saturation, editable spline easing, advanced face embeddings, stock downloads, project collaboration, full audio ducking and long-running Whisper inference on the owner's hardware remain UNVERIFIED/NOT IMPLEMENTED. Whisper word captions and .cube LUTs do have Windows render test coverage, but a real local Whisper model inference quality test is not performed on the owner's machine.

The owner PC's CPU/RAM/GPU and media-heavy UAT are not yet measured. The initial app includes read-only PC Resources inspection. **Do not claim hardware/performance verification just because GitHub Windows runner tests passed.**

The optional local Ollama director requires a separately installed model. Faster-whisper inference libraries are bundled in the Windows build, but the audio model weights are NOT included: the operator explicitly authorizes a tiny/base/small model download or uses an already-cached model. This is not a promise of offline first-run transcription without a model. Local media and projects are never uploaded from CI or shared by default.

## Build and automated validation

Windows workflow: source lint/compile and model/unit tests → real FFmpeg generated-media rendering and 1080p landscape/portrait smoke → Qt headless smoke → PyInstaller Windows EXE → executable headless launch → artifact SHA-256/manifest + manual installer PowerShell syntax validation.

Developer commands (not needed for packaged app):

    python -m pip install -r requirements.txt
    python -m unittest discover -s tests -v
    python launch.py

## Manual-only Windows delivery

1. Open the successful GitHub Actions Windows build and download its artifact bundle. It contains the portable application ZIP, checksum file and standalone manual installer script.
2. Copy the three files to an authorized Windows machine (locally or over Tailscale). Do not execute inside GitHub Actions.
3. Verify Tailscale device identity, installed release, idle editor, disk room and backup destination.
4. Run from a PowerShell terminal opened in that folder:

    .\Install-SceneDesktop.ps1 -ArtifactZip .\SceneDesktopStudio-windows-x64.zip -ChecksumFile .\SceneDesktopStudio-windows-x64.zip.sha256

For remote noninteractive sessions over Windows OpenSSH Server and Tailscale, invoke the same script with -SkipLaunchSmoke, then log into the actual interactive Windows desktop session for GUI playback/UAT. Tailscale's Linux built-in SSH server is not the Windows OpenSSH server.

The script verifies ZIP and EXE hashes, refuses installation when the GUI is running, retains the previous app version for rollback, and does not touch project data. **No automatic deployment, auto-updater, cloud credentials, remote runner shell or other project mutations exist.**

See docs/THIRD_PARTY_NOTICES.txt before redistribution or commercialization. Detailed decisions and results are maintained in the independent Desktop Studio Master Google Doc, not the VPS_1 Master Doc.

## Resource and verification distinctions

Windows GitHub Actions can verify a native GUI launch, FFmpeg frame tests, bundled Whisper library imports, Windows installer checksum/rollback and 720p/1080p output. Those checks do NOT certify smooth 4K instant compositing, user-device GPU acceleration, real-model transcription accuracy, or multi-hour source-library performance. Validate actual hardware through the local PC Resources panel and owner-side editing tests before any final production/UAT claim.
