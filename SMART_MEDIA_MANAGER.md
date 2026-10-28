# Smart Media Manager (Rajudesktop)

One Windows desktop program with four separate native tabs. Uses the existing tested processing engines, without changing or removing any of the original standalone apps.

**Tab 1 — Batch Video Clip Cutter (V2):** Add multiple PC videos in one batch and/or paste multiple YouTube URLs (one per line) into the same persistent FIFO queue. Each YouTube video downloads automatically then proceeds immediately to numbered MP4 clips; PC files go directly to cutting. Select adjustable length (default 4 seconds), optional keyword prefix, output root (Documents/ProcessedClips by default), quick presets, progress and per-job statuses. Every source has a separate output directory; no originals or existing clips are overwritten. Cancel preserves already completed clips; pending queue stays saved across app restarts; failed/cancelled jobs can be retried in new output directories without destroying previous partial output. YouTube downloads can fail if YouTube requires sign-in or blocks automated retrieval.

**Tab 2 — Image Renamer:** Choose a folder, include subfolders or add individual images. Keyword and start numbering, filename preview, copies by default to preserve input images, optional confirmed in-place rename with Undo, and remembered output location.

**Tab 3 — Smart Clip Renamer:** Select a folder of curated clips, choose keyword and output root; preview order that separates original consecutively numbered clips where possible. Output clips are copied byte-for-byte to a unique folder. Originals are preserved.

**Tab 4 — YouTube Downloader:** Full video, video-only and audio-only modes; multiple URLs, selectable quality/format, progress and saved retryable queue. A Snapshots subtab now accepts either one YouTube URL **or a video selected directly from the PC** using "Choose Video from PC" (local files are processed without a network download). It saves JPG/PNG frames on an adjustable interval, with optional time range, quality, resolution, cache/restart support and pause/resume. Local video snapshots go into a video-named subfolder to avoid collisions. Clear the PC selection to switch back to the YouTube URL. Requires access to the video and compliance with platform rules. YouTube anti-bot challenges may prevent downloads.

## Windows download and run

From GitHub Releases download the latest **SmartMediaManager-Windows.zip** (V2 or newer) after the Windows build succeeds on main. Extract everything into a folder such as **D:\Apps\SmartMediaManager**. Double-click **SmartMediaManager.exe**. No Python or system FFmpeg installation is needed for the GitHub Windows release; FFmpeg and yt-dlp are bundled.

Source run: `python launch_smart_media_manager.py`

Unit tests: `python -m unittest discover -s tests -p test_smart_media_manager.py -v`, `python -m unittest discover -s tests -p test_cutter_queue.py -v`, `python -m unittest discover -s tests -p test_snapshots_local.py -v`

All processing is local. Existing files are never overwritten automatically. Default image mode and Smart Clip mode leave all originals intact. Existing Edge Voice, SML and desktop editor applications are independent and unchanged.


## October 28, 2026 — V2 batch cutter + local snapshot upgrade

- Smart Media Manager is the only integrated app changed. Independent standalone clip cutter, legacy Image Renamer and Smart Clip Renamer remain intact.
- New modules: `smart_media_manager/cutter_queue.py` and `smart_media_manager/cutter_queue_ui.py`.
- Queue records persist under `%LOCALAPPDATA%\\SmartMediaManager\\cutter_queue.json`. YouTube cutter source cache is kept at `%LOCALAPPDATA%\\SmartMediaManager\\cutter_sources`; it is not auto-purged.
- On Windows releases the runnable `SmartMediaManager.exe` resides inside `SmartMediaManager-Windows.zip` alongside bundled libraries, FFmpeg, and FFprobe. Extract the entire ZIP before running. The canonical source of truth is Rajudesktop `main`; Windows builds and SHA256 files are published as release assets by GitHub Actions.
