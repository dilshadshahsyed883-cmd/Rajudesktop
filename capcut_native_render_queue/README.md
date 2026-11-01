# CapCut Native Render Queue — Windows 9.6 + 9.7 evidence build

**Purpose:** list all local CapCut drafts and render them sequentially from one **Start Render** control using CapCut's own native engine. **No FFmpeg, FFprobe, screen recording, mouse coordinate recording, keyboard macro, or user click calibration.**

## CapCut 9.7.0.4153 evidence and known blocker

The actual owner's [9.7 archive](https://drive.google.com/file/d/1D2T5DGd-Bcre1nhuvt7H5x4klnhoDkrR/view) was recovered from six split pieces. All part SHA-256 hashes, the full 929,429,692-byte ZIP SHA-256 and ZIP CRC validation passed. The ZIP contains 4,804 files and 1,257 directories. Its SHA-256 is a17790e03bf7ed2ffbaa2c32bab7a1ac96a5b8b75520904e7bd42e882bc9fff4.

New 9.7 DLL lyra_cli_client.dll is 12,953,000 bytes; SHA-256 8177f813b8c3ee1b58f36a2339c83691f0c7c53bac3d114cd4b66757e7f0879f (different from 9.6). The 9.7 installation still bundles bun.exe and lyraCliIpcClient.mjs; the native client still contains draft project list, draft export, RegisterProjectAdapter, and the literal error **host project adapter is unavailable**.

A real 9.6 test screenshot on the owner's PC shows that an IPC endpoint responded with **host project adapter is unavailable**. The error indicates a Native host registration/binding blocker, NOT a missing DLL or corrupted draft. We found static symbols, not a runnable public registration command, and switching to 9.7 does not establish a registered host adapter.

This existing app now recognizes installed/running 9.6 and 9.7 via their verified DLL fingerprints, prefers exactly one actively running supported instance, and clearly reports the adapter blocker. If ProjectAdapter is not registered, *render remains disabled*. Do not derive local:// refs from draft folder names and do not enable FFmpeg/mouse/keyboard fallbacks.

## Actual version-specific evidence

This is grounded in the owner's verified [CapCut 9.6.0.4097 archive](../capcut_960_evidence/README.md) (955,669,438-byte original, matching SHA-256 and 4,757 per-file hashes), not a screenshot-only export macro. The actual 9.6 `lyra_cli_client.dll` includes the `lyra-cli draft project list` and `lyra-cli draft export --ref local://example --output /tmp/out.mp4` command descriptions. The same installation bundles `bun.exe` and `Resources/common_agent/resources/lyra-cli-ipc/lyraCliIpcClient.mjs`, whose help advertises legacy command forwarding over the CapCut-native IPC endpoint.

The app launches **that bundled Bun + IPC client only**; it does not call `ffmpeg.exe` from the CapCut install or any independent renderer. Its exact native call is:

- Read-only project list: `bun.exe lyraCliIpcClient.mjs --product capcut --socket-timeout-seconds 45 -- draft project list`
- Render: `bun.exe lyraCliIpcClient.mjs --product capcut --socket-timeout-seconds 10920 -- draft export --ref local://<verified-native-ref> --output <unique-mp4-file> --timeout 180min`

Both calls are **runtime hypotheses based on real 9.6 embedded help**, not live-accepted Windows APIs. A running native CapCut IPC endpoint and authorization may be required. The project-list response must contain verified `local://` references; the app **never invents IDs from filenames**. A project shown by filesystem discovery but not uniquely matched is displayed as **Needs native match** and cannot render. If the IPC endpoint rejects these commands, the app fails closed rather than switching to FFmpeg or macros.

## User workflow

1. Download the portable Windows executable from the dedicated GitHub Actions artifact and open CapCut 9.6.0.4097 or 9.7.0.4153.
2. Launch `CapCut_Native_Render_Queue.exe`. The app automatically looks in the standard CapCut User Data/Projects locations and asks the actual native IPC for draft references. If the user keeps drafts elsewhere, **Browse** to their Projects folder once.
3. All discovered drafts appear in a table with their names, last-edited time, native binding, and render queue status. Every successfully matched native draft starts in **Queued**.
4. Pick an output folder (default Videos/CapCut Native Renders). Press **START RENDER** once. The app sends native export commands **serially**; no export settings are changed in the app. Each resulting filename is name + short stable ref hash, avoiding name collision.
5. Once the native command returns, the app checks stable file size, complete ISO BMFF top-level MP4 boxes, and a SHA-256 checksum **in pure Python**. It records Completed and advances to the next draft. A failed, ambiguous, changed-source or interrupted attempt enters Review and halts batch; no blind retry.
6. **Stop after current** ends the queue after the current render finishes. **Requeue selected** permits deliberate replay after checking that the prior output is resolved.

### Core safeguards

- CapCut.exe must come from verified version folder 9.6.0.4097 (DLL SHA-256 878df7053d8eb83bf2bf35621fbdc7652e80836680a658a786560689f788f9f7) or 9.7.0.4153 (DLL SHA-256 8177f813b8c3ee1b58f36a2339c83691f0c7c53bac3d114cd4b66757e7f0879f). No untested version fallback.
- No writes to CapCut drafts, user settings, media, resources, OAuth, installation, or existing MP4 files. Existing outputs are never overwritten. Draft content hashes are compared before and after when locally available.
- Crash-safe persistent queue journal in `%LOCALAPPDATA%\CapCutNativeRenderQueue\queue.json`. Interrupted Rendering becomes Review after restart, never automatically re-executed.
- Worker remains native-only; no standalone FFmpeg process is launched or included in the package.
- MP4 container checks do **not** prove correct visual effects, audio decoding, timeline fidelity or bit-perfect output. Real playback acceptance remains necessary.

## Acceptance status

- Static command discovery from **real** 9.6 and 9.7 files: verified.
- Queue discovery, binding, persistence, serial scheduling, safety tests: implemented.
- Windows portable EXE packaging: see workflow result.
- **Successful native 9.6 or 9.7 export on owner's Windows PC: NOT VERIFIED.** This is an experimental native-IPC adapter and may halt if the embedded CLI is not externally reachable. Do not call it a proven unattended batch exporter until at least one real draft exports and is visually verified.

## Build

Windows portable build workflow: [capcut-native-render-queue-windows.yml](../.github/workflows/capcut-native-render-queue-windows.yml). Package has a windowed single-file EXE and README; no Python is needed for the user. CI uses synthetic tests and frozen startup self-check, **not** an installed running CapCut.

Local source: `pip install -r capcut_native_render_queue/requirements.txt`, then `python -m capcut_native_render_queue.app`. Tests: `python -m unittest discover -s capcut_native_render_queue/tests -v`.

**Isolation:** independent Rajudesktop folder, no changes to Z Builder, existing CapCut export apps, user's drafts, VPS_1 or Auto Script. All CapCut binaries remain in original Google Drive and are not repackaged.
