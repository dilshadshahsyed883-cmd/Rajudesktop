# Rajudesktop — Scene Desktop Studio for Windows

Independent, local-first **scene planning + indexed media library + multitrack video editor**. Windows application source and distributable are hosted ONLY in this repository. No existing VPS_1, Haseeb, Bilal, Scene Builder or SML deployments are modified.

## Editing capabilities

- Local media library: file/folder import (background indexing), searchable thumbnails, selected/video/image counts, tags, exact duplicates, candidate/approved/rejected review and approval.
- Scene Director: import TXT or paste script, split into editable timed scenes, match approved local media (local-first, alternate video/image, video-only or image-only), manual media selection and batch five-at-a-time approval.
- Optional **actual AI** scene proposal generation using an owner-installed **local Ollama** model. It runs only against 127.0.0.1:11434 when the operator clicks AI Scene Plan; no background model downloads and no hosted cloud upload. If no model is installed, the built-in deterministic planner works offline.
- Graphical six-track timeline for main video, video overlay, captions, narration, music and SFX. Drag positions, switch compatible tracks, edit source trims, split, duplicate, delete, undo/redo, lock/mute/hide tracks and scale timeline zoom.
- Inspector: zoom 50–300%, horizontal mirror, pan/reframe/slow-push/Ken Burns motion, 23 parameterized color looks (not .cube LUT files), look intensity, basic grain/noise styles, brightness, saturation, fade/dissolve and slide transitions, optional original-video audio, audio volume/fades and captions.
- SRT caption import/export, project save/open, backups, recover autosave, find/relink missing assets, read-only Windows resource panel.
- FFmpeg preview segment compositing from the same project model, preview continuation, 16:9/9:16 720p/1080p video export, original/voice/music/SFX audio mixing, output open/play, job cancellation and source-preserving non-overwrite.
- Hashed render-section reuse, guarded free-disk admission, app-owned cache trimming and preview expiry; original project media files NEVER removed.

## Important accuracy/limitations

The UI is **CapCut-inspired**, not full CapCut feature parity. Playback previews render short cached sections on a worker, so instant GPU-smooth scrubbing and frame-perfect arbitrary-layer preview on all hardware is NOT guaranteed. Transitions and presets cover an initial functional subset; third-party .cube LUTs, nonlinear motion keyframe authoring, AI word-level Whisper timing/karaoke, advanced face embeddings, integrated stock download, project collaboration, and full audio ducking are NOT implemented or independently verified.

The owner PC's CPU/RAM/GPU and media-heavy UAT are not yet measured. The initial app includes read-only PC Resources inspection. **Do not claim hardware/performance verification just because GitHub Windows runner tests passed.**

The optional local Ollama AI feature requires a separately installed, compatible local model; there is NO embedded large language model or automatic download. Local media and projects are never uploaded from CI or shared by default.

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
