# Z Studio — independent Windows desktop source

This branch contains the independent Z Studio source and a **one-click launcher**.
The original app's archive is stored as ten verified Git blobs; current launcher
files are maintained in `z-studio/launcher/` and applied automatically during
source reassembly.

## Windows start

1. Clone/download the **z-studio** branch.
2. Double-click **`z-studio/start.bat`**. Extracting the GitHub ZIP first is required.
3. The assembler checks the source archive SHA-256 and extracts it.
4. The inner launcher checks for working Node.js and npm. If missing, it uses
   Python 3 to download a portable Node 24 LTS ZIP from official `nodejs.org`,
   verifies the official SHA-256 checksum, and installs it under
   `Z-Studio-Local/.runtime/node` (no admin rights, global PATH edits, or manual install).
5. npm installs the Electron dependency on the first launch; repeat launches
   reuse it. Internet access is required for first-time downloads.

Alternatively, run `python z-studio/assemble_source.py --extract`, then launch
`z-studio/Z-Studio-Local/start.bat`.

## Important behavior

- Vendor license activation/device entitlement and vendor updater are removed
  from the local variant; its Image/Video/Voice workspaces open without activation.
- The remote AI Canvas engine is **not bundled**. Image generation still needs
  a separately authorized Canvas HTTPS URL and working sign-in.
- Vendor voice-cloning/credits were not reproduced; Windows SAPI WAV export
  replaces the vendor speech endpoint.
- Video rendering/export may need FFmpeg on PATH.
- No custom EXE was created. This is editable Electron source; a verified
  official portable Node runtime and Electron are acquired on first run.
- Original author attribution and all third-party notices must be preserved.

## Verification

The GitHub Actions workflow reassembles the ZIP, verifies the overlay, checks
all JavaScript syntax, and runs unit tests for Node bootstrapping and checksum
verification. This does **not** substitute for a real Windows GUI/export test.

Base archive SHA-256: `cf83034ae1c61f56aab84487d1f21ba6d9200e8e7a908c297385e09923f0b09f`.
