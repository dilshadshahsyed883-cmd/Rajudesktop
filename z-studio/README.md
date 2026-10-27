# Z Studio — independent desktop build

This **z-studio** branch stores the Z Studio source provided by the project owner. The complete modified source ZIP is stored as ten binary Git blobs to avoid GitHub connector single-request size limits.

## Run on Windows

1. Install Node.js LTS, with npm available in PATH.
2. From this repository checkout, double-click `z-studio\\start.bat`.
3. The batch launcher verifies all source chunks, unpacks the ZIP, and starts the Electron app. Electron installs via npm on first run.

Or run `python z-studio/assemble_source.py --extract` to unpack the complete source.

## Changes

- Removed vendor-specific license activation, device entitlement validation, Google license OAuth, updater entitlement, and remote Voice IPC from this local variant.
- Image and video workspace entry no longer requires a Z Studio license.
- Image generation still **requires your own authorized HTTPS Canvas URL**. A valid Canvas/API setup and Google sign-in are separate from Z Studio licensing, and image generation is not verified end-to-end.
- Remote vendor Voice cloning and credit-based TTS are **not reproduced**; a working Windows Speech (SAPI) WAV export entry point is provided instead, saving to Documents/Z Studio/Voice.
- The video editor implementation is retained, though some exports require FFmpeg available on PATH.
- No EXE or Electron runtime is included. `start.bat` runs source with npm.

The original developer is credited by the supplied package metadata. Retain all third-party notices when distributing a compiled runtime.

**Archive SHA-256:** `cf83034ae1c61f56aab84487d1f21ba6d9200e8e7a908c297385e09923f0b09f`
