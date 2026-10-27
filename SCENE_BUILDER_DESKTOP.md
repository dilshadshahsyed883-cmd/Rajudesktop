# Scene Builder Desktop — independent Windows edition

This is a separate, local Windows Python application in the Rajudesktop repository. It does **not** modify or deploy the VPS_1 Scene Builder application and does not connect to the VPS server.

## Run on Windows

1. Download the repository or the **Scene Builder Desktop Python ZIP** artifact from the Scene Builder Desktop CI workflow; extract it to a folder.
2. Double-click **start_scene_builder_desktop.bat**. Python 3.11+ must be installed. The launcher installs PySide6/imageio-ffmpeg when missing; it does not compile or install an EXE.
3. Import images and videos into **Media Library**, open **Director V25** to paste/load a scene-plan TXT, or use **Timeline & Export** to manually build, save, preview and render videos.
4. Media is stored in **Documents/SceneBuilderDesktop/MediaLibrary**; original source files are never edited. Project manifests are saved as .sdsproj through the editor. Exports are saved to user-selected MP4 paths and do not overwrite existing files.

## Current working feature boundaries

- Native Qt app shell, folder/files import with background operation notification, image/video counts, automatic approval, exact filename and hashed-ID catalog, SHA-256 deduplication, downloadable inventory TXT and confirmed deletion/clean.
- Existing Rajudesktop scene_desktop editor provides still/video previews, playback/seek, timeline reorder, trim and split, project save/reopen/autosave and 720p/1080p H.264 MP4 export with optional narration.
- Source-pinned Scene Builder V25 strict parser, preflight and compiler: local filenames must resolve to approved IDs. Pexels fallback is accepted for plan validation when selected, but is not a desktop asset downloader.
- **Create Editable Rough Cut** can turn compatible local-only plans into a maximum 3-second-per-shot cut timeline for manual review. This is not speech alignment or full Director rendering.
- Advanced V25 motion, animated transitions, effects, caption rendering, LUTs, intro composition, music tracks and voice-volume changes **block rough-cut creation**. They are never silently ignored.
- Does not yet replicate the entire VPS_1 FastAPI backend, online queue, Whisper, TTS engines, Pexels fetching or Google Drive delivery.

## Technical components

- Entrypoint: launch_scene_builder_desktop.py / scene_builder_desktop.app.
- Core edit/render reuse: scene_desktop/ in this repository.
- Source-pinned Director V25 and scene media core: vps1-deploy-control/apps/scene-builder/part01/ as of October 27, 2026. Desktop adapters live in desktop_catalog.py and director_bridge.py.
- Local library: SQLite and managed media inside Documents/SceneBuilderDesktop/MediaLibrary.
- Tests: python -m unittest discover -s tests -p test_scene_builder_desktop.py -v.
- GitHub Actions packages a **Python source ZIP**, not an EXE. No production deployment, token storage or auto-script startup.

## Next integration stage: Z Studio

Separately audit Z Studio components for licensing and dependencies. Integrate through explicit modules after local verification, without silently replacing Scene Builder V25 rules or touching VPS production.
