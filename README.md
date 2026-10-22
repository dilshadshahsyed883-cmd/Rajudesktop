# Scene Desktop Studio — Rajudesktop

A standalone Windows video production studio combining local Media Library workflows, script-to-scene planning and a CapCut-inspired editable timeline. Independent of existing VPS_1 Scene Builder, SML, Haseeb and Bilal projects.

Development policy: one consolidated feature branch until unified acceptance. GitHub builds and tests automatically. NO automatic installation or remote desktop deployment; Windows app installation is exclusively via an owner-approved manual Tailscale/PowerShell action.

## Functional unified-build scope

- Persistent indexed local library (SQLite): folder/file imports, tagging, search, status filters, video/image/selected counts, explicit approval, SHA-256 exact duplicate grouping, crisp image/video thumbnails. Source files are read-only.
- Script TXT import/paste, offline timed scene planning, keyword/media matching against approved local assets, source preference modes, manual media replacements, five-scene batch review and bulk approval/locking. Auto-approval optional and off by default.
- Native six-track graphical timeline (main video, overlay, captions, narration, music, SFX): drag, reposition/change compatible track, trim, split, replace, delete, undo/redo and properties inspector.
- Supported clip options include zoom, mirror, brightness/contrast/saturation, basic grain, alpha fade transitions, audio volume and fades, timed captions, SRT import/export.
- Short composited audiovisual FFmpeg proxy preview (cached), full H.264/AAC video export, compatible-section caching, background rendering and cancellation. Existing exports are never overwritten.
- Atomic editable project saves (.sds2) with backups, local autosave recovery and missing-file relinking. Read-only PC resource/codec report available in app.
- Windows GitHub Actions PyInstaller build, versioned downloadable ZIP, SHA-256 and tests with real generated audio/video and Qt UI smoke.

## Honest current limitations (not full CapCut parity)

- Script planning uses offline keyword/timing estimation: it is NOT yet a generative AI model, Whisper word-aligned captions or fully accurate voice timing.
- GPU hardware acceleration, 4K and actual owner's Windows PC performance are not verified. Preview renders short cached segments, not instantaneous full-timeline GPU compositing.
- Advanced animated keyframes, full named transition/LUT libraries, noise modes, face clustering and automatic AI inference remain future milestones. Nothing silently claims to implement these.
- Local original media must remain accessible; portable project import of actual VPS-only Scene Builder/SML assets and external Drive/Pexels connectors are NOT wired.
- Video visuals do not automatically mix their source audio; manually place the file on an audio track when needed. Sophisticated music ducking is not implemented yet.
- Source lives exclusively in Rajudesktop; does not edit or migrate production apps, jobs, OAuth credentials or the user's videos.

## Developer workflow

For developers with Python 3.11+:
1. python -m pip install -r requirements.txt
2. python -m unittest discover -s tests -v
3. python launch.py

Windows CI generates SceneDesktopStudio-windows-x64.zip and SceneDesktopStudio-windows-x64.zip.sha256 via PyInstaller, with artifact retention. This is a CI build, not a validation of the executable on the owner's actual PC.

Only later, upon explicit owner authorization, an operator may perform a manual Tailscale-connected PowerShell deployment. Confirm target identity, installation directory, artifact/checksum, GUI session, app-only backup/rollback and smoke tests. No GitHub-to-PC auto-deploy is configured.

The living decisions and development register belong to the separate Scene Desktop Studio Master Google Doc; previous Master Docs are untouched.
