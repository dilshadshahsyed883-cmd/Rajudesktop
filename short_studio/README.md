# Short Studio — standalone Windows EXE

An independent **native Windows** Short Maker + Short Uploader. It does **not** call the VPS engine, modify live production or enable Auto Script.

## Workflow

1. In **Short Maker**, create/select a persisted output folder, select a PC image folder and optional music files, configure duration/fit/motion/batch and start rendering.
2. Output is vertical 1080×1920 MP4, with names such as `Aina Asif 001_abcdef.mp4`; numbering remains monotonic even after upload/deletion.
3. **Channels & Groups**: connect each intended YouTube channel via the official desktop OAuth flow. Select channels (Ctrl-click), then create a group.
4. **Auto Engine**: save one *group* profile with a Short Studio folder, locally saved title/description/category, per-channel daily limit, PKT schedule and deletion preference.
5. Queue the selected profile's folder videos. SHA-256 per channel prevents duplicate uploads of the same MP4 even when renamed. Click **Start Upload Queue** to submit. Upload records retain YouTube IDs.
6. For public profiles, YouTube receives a private upload with a future `publishAt` time. Private/unlisted profiles do not schedule publication. Cleanup affects only studio-managed MP4s after known queued channel uploads succeed.

## Build and run

- Source: `start_short_studio.bat` (Python 3.12 and FFmpeg on PATH required).
- Windows single-file: GitHub Actions [short-studio-windows.yml](../.github/workflows/short-studio-windows.yml) builds `ShortStudio.exe`, bundles FFmpeg, performs offline tests and a frozen startup smoke check, and attaches a direct EXE to a new release **after merging to main**.
- To connect YouTube: create an OAuth **Desktop app** client in your Google Cloud project with **YouTube Data API v3** enabled. Choose its downloaded `client_secret.json` from the app. Never paste keys into GitHub. Account/token authorization and YouTube quota must be valid. The connected Google account must have access to the channel.
- Local data: `%LOCALAPPDATA%\\ShortStudio\\` (SQLite, videos, credentials); it is intentionally outside the EXE/repository.

## Safety and scope notes

- The desktop app is **not** an exact clone of the VPS web service: VPS multi-user authentication, Google Drive rclone imports/uploads, backend scheduling/arm controls, Sheets Sync, token migrations and existing VPS queues are **not** ported.
- This first desktop version uses **manual local metadata** and native YouTube OAuth. Videos are not uploaded unless the user explicitly starts an upload run. Google's API may require verification, consent-screen configuration and quota.
- If a network/API error occurs after an upload starts, the result is **uncertain**; no automatic retry occurs, since YouTube might already have received it. Check in YouTube Studio manually.
- Source inputs are never deleted. Video cleanup (if selected) removes only eligible completed MP4 outputs in the chosen managed Short Studio folder.
- No actual Google OAuth or real YouTube upload is exercised by offline CI; user acceptance of live credentials/quota is required.
