# CapCut 9.6.0.4097 — verified source-archive inspection (2026-11-01)

## Ground truth (bytes actually inspected)
- Google Drive original: [capcut 9.6.0.4097.zip](https://drive.google.com/file/d/1IsgH2HbuelpJsicsAuPjNMi_BBuSk-OT/view)
- Google Drive split parts: [capcut_9.6.0.4097_parts](https://drive.google.com/drive/folders/1NpHE7-vAVWsamd0ypPItnt38sCCEKrX2)
- Original length: **955,669,438 bytes**. Original SHA-256: `389c0ad94cc7f6e967b8be374e78f4640496194e12671567ad19d752e5e84cbd`.
- **6/6 parts SHA-256 and sizes match the Drive manifest**. Reassembled archive SHA-256 matches, and Python zipfile CRC check (all entries) passed.
- Archive contains **4,757 files**, **1,263 directory entries**, **1,921,605,941 bytes total uncompressed file content**.
- Per-file SHA-256, CRC32, compressed/uncompressed sizes, and original ZIP path for *all* 6,020 entries: [inventory/part_01.csv](inventory/part_01.csv) through [inventory/part_07.csv](inventory/part_07.csv). CSV parts are consecutive rows, each starts with the same field header. Parts 01-06 cover 1,000 ZIP entries each; part 07 covers 20. No files were extracted into the repo.
- These are original file integrity checks. They do **not** prove signature authenticity or runtime/renderer correctness. All actual executable files remain in Google Drive, not GitHub.

## Static native export evidence found in this exact 9.6 archive

| Archive path | Bytes | SHA-256 |
| --- | ---: | --- |
| `9.6.0.4097/CapCut.exe` | 90,536 | `1bf33b74a2638ad665ae77c44d7df4cc1b0082d8c305c5d4292321a467d30873` |
| `9.6.0.4097/lyra_cli_client.dll` | 10,809,256 | `878df7053d8eb83bf2bf35621fbdc7652e80836680a658a786560689f788f9f7` |
| `9.6.0.4097/ffmpeg.exe` | 473,512 | `e20b3fd63c6fe82297734ca5a30f4d3e17154428010c1eb08d9b5ed8f3a5af26` |
| `9.6.0.4097/Resources/common_agent/bin/lyra-cli-ipc.cmd` | 236 | `5ab0c011380f0e547afeeefcfffcdc692a814a9382d7f7675f8dcab7ac10bafc` |
| `9.6.0.4097/Resources/common_agent/resources/lyra-cli-ipc/lyraCliIpcClient.mjs` | 36,337 | `ae36164102672efe36cbb40a5d63724e9e34034a7b49e977d1987e1736dbb762` |

The actual DLL contains literal readable strings for `lyra-cli draft export --ref local://example --output /tmp/out.mp4`, `exportStart`, `ExportService`, `ExportDraft`, `exportAudioStart`, `prepareExportCover`, codec/quality choices, and many other draft operations. This is stronger evidence than the 9.5-only third-party bridge: it is **direct static evidence inside the supplied 9.6 release**. It is *not* proof the documented command can be invoked successfully on the owner's Windows session.

The actual `lyra-cli-ipc.cmd` launches a bundled Bun script; `lyraCliIpcClient.mjs` documents forwarding other `lyra-cli` commands to a Native product endpoint using IPC. The package also contains `9.6.0.4097/bun.exe`.

## What to test next (on an unlocked Windows CapCut 9.6 session)
1. Read-only detection: installed version, process and CLI help; no edits, no settings changes, no external network.
2. Read-only draft listing and inspection on a disposable draft; check command routing, IPC endpoint availability and project identity.
3. One native export of a **disposable copy** to a never-before-used output filename; require explicit permission, no overwrite or cloud actions; verify with ffprobe and full decode, compare duration/audio/codec/visual spot check.
4. Only after reliable step 3, add a serial queue with persisted job state, verified project switching, timeout recovery, and pauses between projects.
5. Preserve existing export settings; do not call unverified setting mutators such as `saveExportPath`. Investigate any side effect before unattended runs.

### Known limits
- No Windows runtime was available here. **Actual native 9.6 export and unattended batch remain NOT TESTED**.
- Merely finding static CLI strings does not certify headless export, effect parity, or safe output-path persistence.
- The earlier fixed-coordinate one-draft prototype is **not** accepted as a verified exporter.
- Do not bundle proprietary CapCut binaries in source control. Original 912 MiB ZIP and its 160 MiB segments exceed GitHub's normal 100 MiB per-file maximum; available connected GitHub operations are text-file based. This repo stores comprehensive provenance, hashes, inventory and original Drive references instead.
- Rajudesktop existing apps / Z Builder / VPS_1 unchanged. No automatic deployment and no Auto Script.

## Reproducing
Use the included `verify_capcut_960.py` with the manifest and six local pieces. It creates a new combined archive outside the parts folder, checks SHA-256, and writes a complete per-entry inventory without extracting or executing app binaries.
