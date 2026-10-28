# Smart Media Manager (Rajudesktop)

One Windows desktop program with four separate native tabs. Uses the existing tested processing engines, without changing or removing any of the original standalone apps.

**Tab 1 — Batch Video Clip Cutter (V2):** Add multiple PC videos in one batch and/or paste multiple YouTube URLs (one per line) into the same persistent FIFO queue. Each YouTube video downloads automatically then proceeds immediately to numbered MP4 clips; PC files go directly to cutting. Select adjustable length (default 4 seconds), optional keyword prefix, output root (Documents/ProcessedClips by default), quick presets, progress and per-job statuses. Every source has a separate output directory; no originals or existing clips are overwritten. Cancel preserves already completed clips; pending queue stays saved across app restarts; failed/cancelled jobs can be retried in new output directories without destroying previous partial output. YouTube downloads can fail if YouTube requires sign-in or blocks automated retrieval.

**Tab 2 — Image Renamer:** Choose a folder, include subfolders or add individual images. Keyword and start numbering, filename preview, copies by default to preserve input images, optional confirmed in-place rename with Undo, and remembered output location.

**Tab 3 — Smart Clip Renamer:** Select a folder of curated clips, choose keyword and output root; preview order that separates original consecutively numbered clips where possible. Output clips are copied byte-for-byte to a unique folder. Originals are preserved.

**Tab 4 — YouTube Downloader:** Full video, video-only and audio-only modes; multiple URLs, selectable quality/format, progress and saved retryable queue. A Snapshots subtab now accepts either one YouTube URL **or a video selected directly from the PC** using "Choose Video from PC" (local files are processed without a network download). It saves JPG/PNG frames on an adjustable interval, with optional time range, quality, resolution, cache/restart support and pause/resume. Local video snapshots go into a video-named subfolder to avoid collisions. Clear the PC selection to switch back to the YouTube URL. Requires access to the video and compliance with platform rules. YouTube anti-bot challenges may prevent downloads.

## Windows download and run

From GitHub Releases download **SmartMediaManager.exe** directly from the latest **V3 Single Portable EXE** release. Save it anywhere (for example D:\\Apps\\SmartMediaManager.exe), then double-click. There is **no ZIP to extract and no adjacent support folder**. The single EXE embeds Python runtime, FFmpeg, FFprobe, yt-dlp and all four tool modules. The PyInstaller one-file bootloader automatically extracts temporary internal components at runtime; user data and output clips are saved to the selected output folder and persistent settings/queue live under LOCALAPPDATA. The EXE is not an installer; it does not modify other apps. First launch may be slower because the EXE unpacks its embedded files.

Source run: `python launch_smart_media_manager.py`

Unit tests: `python -m unittest discover -s tests -p test_smart_media_manager.py -v`, `python -m unittest discover -s tests -p test_cutter_queue.py -v`, `python -m unittest discover -s tests -p test_snapshots_local.py -v`

All processing is local. Existing files are never overwritten automatically. Default image mode and Smart Clip mode leave all originals intact. Existing Edge Voice, SML and desktop editor applications are independent and unchanged.


## October 28, 2026 — V2 batch cutter + local snapshot upgrade

- Smart Media Manager is the only integrated app changed. Independent standalone clip cutter, legacy Image Renamer and Smart Clip Renamer remain intact.
- New modules: `smart_media_manager/cutter_queue.py` and `smart_media_manager/cutter_queue_ui.py`.
- Queue records persist under `%LOCALAPPDATA%\\SmartMediaManager\\cutter_queue.json`. YouTube cutter source cache is kept at `%LOCALAPPDATA%\\SmartMediaManager\\cutter_sources`; it is not auto-purged.
- **V3 single-file release:** GitHub Actions builds `--onefile --windowed` and publishes a directly downloadable `SmartMediaManager.exe` plus `SmartMediaManager.exe.sha256` as independent release assets. Do not ZIP the EXE or distribute a sidecar `_internal` directory. The EXE bundles the Python runtime, FFmpeg, FFprobe and yt-dlp. The canonical source of truth is Rajudesktop `main`; release assets are built and tested on a Windows GitHub runner.

## V3 distribution rule — 28 October 2026

- **Deliver exactly one user-runnable file:** `SmartMediaManager.exe`, linked directly from GitHub Release assets, similar to Z Studio. A separate optional SHA-256 verification text file is published but is not needed for running the app.
- No ZIP extraction, no copied program directories, no Python/FFmpeg installation. One-file PyInstaller does require a temporary unpack directory during startup (managed and cleaned by the bootloader); this is not an installer or permanent app folder.
- Future Smart Media Manager Windows builds should keep one-file packaging and direct EXE release delivery unless the owner explicitly changes this rule.
