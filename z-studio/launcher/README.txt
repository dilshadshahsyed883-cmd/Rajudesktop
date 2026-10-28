Z Studio Local - Windows source edition

FIRST RUN
  1. Extract the full ZIP into a folder (do NOT run start.bat inside the ZIP preview).
  2. Double-click start.bat. Keep an internet connection on first launch.
  3. If Node.js/npm is absent, Python 3 automatically downloads the official portable
     Node 24 LTS release from https://nodejs.org (no admin access needed).
     It verifies the official SHA-256 checksum and keeps Node inside .runtime/node.
  4. npm installs Electron into app/node_modules on the first launch.
     Later launches reuse the existing dependencies and runtime.

You do not need to install Node.js manually. A Python 3 interpreter on PATH
is needed only if Node.js/npm is not already present.

Image, Video, Voice workspaces open without the vendor license activation.
Image generation requires a separately authorized Canvas HTTPS URL, which is
not bundled with this app; generation has not been tested on an active Canvas.
Voice export uses built-in Windows SAPI WAV at Documents/Z Studio/Voice;
original remote voice cloning and credit service are not included.
FFmpeg on PATH may be required for some video rendering/export operations.

No custom .exe has been built. The Electron runtime installs via npm on first run.
Retain copyright and third-party legal notices when redistributing this app.

If the runtime install fails, verify your internet connection and retry.
Manual fallback: install Node.js LTS from https://nodejs.org/en/download.
