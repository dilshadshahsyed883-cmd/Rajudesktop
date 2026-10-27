# Smart Media Manager (Rajudesktop)

One Windows desktop program with four separate native tabs. Uses the existing tested processing engines, without changing or removing any of the original standalone apps.

**Tab 1 — Video Clip Cutter:** Choose a local video, keyword and adjustable clip length (default 4 seconds). Outputs numbered MP4 clips, retains audio, remembers the output directory (Documents/ProcessedClips by default), supports cancellation and opening the output folder.

**Tab 2 — Image Renamer:** Choose a folder, include subfolders or add individual images. Keyword and start numbering, filename preview, copies by default to preserve input images, optional confirmed in-place rename with Undo, and remembered output location.

**Tab 3 — Smart Clip Renamer:** Select a folder of curated clips, choose keyword and output root; preview order that separates original consecutively numbered clips where possible. Output clips are copied byte-for-byte to a unique folder. Originals are preserved.

**Tab 4 — YouTube Downloader:** Full video, video-only and audio-only modes; multiple URLs, selectable quality/format, progress and saved retryable queue. A Snapshots subtab saves JPG/PNG frames on an adjustable interval, with optional time range, quality, resolution, cache/restart support and pause/resume. Requires access to the video and compliance with platform rules. YouTube anti-bot challenges may prevent downloads.

## Windows download and run

From GitHub Releases download the latest **SmartMediaManager-Windows.zip** after the Windows build succeeds on main. Extract everything into a folder such as **D:\Apps\SmartMediaManager**. Double-click **SmartMediaManager.exe**. No Python or system FFmpeg installation is needed for the GitHub Windows release; FFmpeg and yt-dlp are bundled.

Source run: `python launch_smart_media_manager.py`

Unit tests: `python -m unittest discover -s tests -p test_smart_media_manager.py -v`

All processing is local. Existing files are never overwritten automatically. Default image mode and Smart Clip mode leave all originals intact. Existing Edge Voice, SML and desktop editor applications are independent and unchanged.
