# Song Audio Downloader (Windows)

New standalone executable \`SongAudioDownloader.exe\` reuses the working Smart Media Manager YouTube Downloader tab, preserving Audio Only, Full Video, Video Only, Snapshots, and Queue.

- **Naming (VPS Audio Downloader rule)**: audio \`sQ74S7cZ3Kg.mp3\` or \`.m4a\`/\`.wav\`; optional matching thumbnail \`sQ74S7cZ3Kg.jpg\`. The stem is always the 11-character YouTube Video ID, not the video title.
- **Thumbnail**: default enabled, can toggle in Download tab. If image fails, existing audio is kept; retry can fetch thumbnail alone without re-downloading audio.
- **Independent**: original Smart Media Manager, its data, workers, queues, and settings remain unchanged. New settings and queue live in \`%LOCALAPPDATA%\SongAudioDownloader\`.
- **Output folder**: default \`Documents\Song Audio Downloads\`, changeable.
- **No external Python or FFmpeg install**: single portable EXE bundles runtime, yt-dlp, FFmpeg, and FFprobe. YouTube access restrictions may still prevent some downloads. Download only content you have rights to use.
- **No Google Drive upload**, and no cookie/auth bypass.

CI: \`.github/workflows/song-audio-downloader-windows.yml\` tests, builds and uploads the Windows EXE as artifact. On main it publishes a direct EXE GitHub Release asset.
