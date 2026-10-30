# Song Studio Desktop — Windows standalone

One Windows executable: `SongStudio.exe`. Source: `song_studio/`, launcher `launch_song_studio.py`.

## Native workflow

**Audio Downloader:** Paste multiple YouTube links, choose/create a named local folder, download matching `VideoID.mp3` and unmodified `VideoID.jpg` through the established Rajudesktop downloader engine. Download queue runs sequentially in a background thread; optional auto-render after each pair.

**Song Maker:** Discover exact matching audio/photo stems in that folder. Render selected or all unrendered pairs to `<folder>/renders/VideoID.mp4`, using FFmpeg (H.264/AAC), adjustable 1080p / 720p / 9:16, Fit/Blur canvas and quality preset. Existing MP4 is never overwritten; original MP3 and JPEG remain untouched.

**Song Uploader:** Connect each YouTube channel through its own Google Installed App OAuth flow, assign channels to a group, save a group-level uploader profile (source folder, title template, description, category, privacy), then explicitly confirm one upload batch. One profile can target many channels. An original matching JPEG is applied as thumbnail without alteration. Each (channel, source Video ID) pair has a durable SQLite receipt; failed ambiguous uploads are **not auto retried**, preventing accidental duplicate videos. YouTube auth and API quotas remain subject to Google's rules.

## Privacy, migration and boundaries

- App data: `%LOCALAPPDATA%\\SongStudio` (SQLite, settings, tokens); media: `Documents\\Song Studio` by default.
- Google OAuth client JSON is picked **on the user's PC** and not bundled, hardcoded or uploaded to GitHub. Tokens are stored locally; do not share the token folder.
- Output source files and videos are retained after uploading, until manually deleted.
- This is an **independent local application**, not the web Song Studio frontend or its VPS session. It does not read VPS users, queues, Google Drive folders, cloud profiles or existing OAuth tokens automatically.
- Current desktop v1 has manual profile metadata and explicit upload batches. Google Sheets Sync, timed auto scheduling, import of old VPS account tokens, full VPS job/Drive integration and auto cleanup are **not** replicated; they require separate authenticated desktop integrations. Do not describe it as exact VPS parity.
- Download only audio and imagery you are authorized to use. Windows Defender/SmartScreen may show an unsigned EXE warning.

## Build

The workflow `.github/workflows/song-studio-desktop-windows.yml` runs offline unit tests, builds `SongStudio.exe` with Python, yt-dlp, Google API dependencies and bundled FFmpeg/FFprobe on a Windows runner, verifies frozen imports and GUI startup, then uploads an Action artifact. On a merge to `main`, a GitHub Release publishes **direct EXE** and SHA256.

Locally for development: `pip install yt-dlp google-api-python-client google-auth-oauthlib`, install FFmpeg, then `python launch_song_studio.py`. No Google credentials are needed to test the offline workflow.
