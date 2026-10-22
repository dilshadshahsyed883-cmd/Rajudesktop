# Desktop Self Media Library — offline full-workspace port

The desktop port incorporates the existing VPS_1 SML v2 UI and backend as an
independent copy in the Rajudesktop repository. The production VPS_1 files,
database, login credentials and jobs are never modified or synchronized.

## Desktop navigation and feature scope

Open **Self Media Library (Offline)** as a full-width top-level workspace in
Rajudesktop. The embedded localhost page reproduces the source SML controls:

- **Dashboard:** local library and sources counters, queue, AI status
- **Input:** Videos, Images and Folder, local uploads, file/asset status, and
  existing online/import controls visibly labeled disabled in offline mode
- **Process:** source processing, shot detection, clip creation, review pairs,
  batch decisions and progress
- **Library & Preview:** clip/image library, selection, approval, tags, search,
  trash and restore, image preview, AI metadata/review/search
- **AI:** CPU CLIP scene descriptions/embeddings, OCR and optional Whisper
  speech analysis only when corresponding model files/tools are already
  installed locally; queue, history, collections, corrections and duplicates
- **Settings:** clip length, scene sensitivity, quality and AI controls
- **Trash:** deleted items and the existing restore controls
- **Scene Editor integration:** an explicit Send Approved SML Media to Scene
  Editor command links verified approved local images/clips into the separate
  Studio SQLite catalog. This never deletes or moves SML originals.

The imported UI is a desktop adaptation of the VPS source at
apps/self-media-library/part01/ (from vps1-deploy-control as of 2026-10-22).
The source UI may mention old VPS-specific language; a Desktop Offline banner
makes the actual local data/behavior explicit.

## Network and privacy

The SML backend binds 127.0.0.1 only. A restricted Qt WebEngine embedded
browser allows resources/navigation only from its own loopback port. The local
web server checks Host, Origin and localhost peer; online YouTube, Drive and
Proxy management/import endpoints return 409, rather than making network
requests. There is no API token, VPS deployment, external login or cloud sync
required.

All data is local to Rajudesktop's app data directory, inside offline-sml/:
SQLite library.db, sources/, clips/, images/, thumbs/, ai_models/,
speech_models/, ai_previews/, temp and workspace metadata.
Models are NOT fetched automatically; supply verified local weights when
choosing to use optional AI functions.

Qt WebEngine, FastAPI/uvicorn, Pillow and inference libraries are runtime
source dependencies. On Windows, the app adapts FFmpeg availability and uses
a PyAV technical probing fallback when ffprobe is absent. A dedicated
cross-platform file lock protects AI worker processes; Linux /proc data
is optional. The original production SML code remains untouched.

## Release policy

The user has explicitly stopped automatic EXE builds. The existing packaging
workflow is workflow_dispatch only. Normal feature commits may run source
tests but NEVER PyInstaller, create a ZIP, change VPS_1 or deploy to the PC.

**Verification:** source copy and tests do not prove every GUI control works on
the owner's CPU-only Windows PC. Source-only Windows tests cover FastAPI routes,
the offline guard, Qt UI construction and approved media library linking.
Optional offline model inference, codecs, local file/folder UI workflows and
physical-PC UAT remain acceptance gates. No release-ready claim without them.
