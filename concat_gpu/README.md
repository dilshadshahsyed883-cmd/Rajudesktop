# Concat Windows editor — Send to GPU (Stage 1)

**Product:** the genuine upstream [Concat v0.2.8](https://github.com/jub0t/Concat) Rust/Slint editor, compiled from pinned upstream commit `79116bd0f9a103c633d888603ad27890e929dbdc` with a minimal new **File > Send to GPU (CUDA)...** action.

This is NOT a separate editor or a modified copy of the official upstream release binary. The pre-existing `concat_original/` official Windows installer and all other Rajudesktop apps remain unchanged.

## Workflow

1. In Concat, open/create a native `concat.json` project with one single, gapless **1080p30** cut timeline (JPEG/MP4/HEVC, single narration). Save project and verify it locally.
2. File > **Send to GPU (CUDA)...** saves the original project using upstream's own atomic save semantics, then launches an embedded PowerShell upload helper. The editor stays open.
3. First use only: supply your **existing** Salad Gateway HTTPS origin, existing `Salad-Api-Key`, and existing `RENDERER_API_TOKEN`. The helper protects secrets using Windows DPAPI in the **current user's** `%LOCALAPPDATA%\Concat\GPU\connection.json`. Never supply a VPS or Google Drive token here. Further exports reuse saved credentials. To change them, delete that locally encrypted connection file and run the action again.
4. The helper packages the **native Concat** `concat.json` and its actual referenced source files in the existing checksum-verified `project_bundle` ZIP format. No source files are modified.
5. The helper uses the existing Salad HTTPS gateway and authenticated **resumable 8 MiB chunks**, explicitly selecting `render_mode=cuda-stage1`. It polls the existing worker job states.
6. The updated **existing Salad GPU image** maps the native Concat cuts to CUDA/NVENC and sends the verified MP4 to the **existing VPS Cloud Render receiver**. No VPS website/config/proxy/deployment change.
7. On confirmed `delivered` state, delete only the temporary ZIP snapshot; always retain original PC media. If interrupted or failed, keep it locally for recovery.

### Supported Stage 1 edit subset

Single visual track with sequential gapless stills or 30-fps H.264/HEVC clips, one basic narration clip, 1080p30 SDR. No transitions, fades, effects, captions, overlays, animations, speed changes or non-neutral transforms. If a video contains embedded audio, its clip must be explicitly muted: only the narration is supported in Stage 1. Unsupported edits are **rejected with an exact worker error** rather than silently dropped or CPU-video-rendered.

### Scope and prerequisites

- Windows PowerShell 5.1 (built into supported Windows versions); the EXE embeds its helper. No separate Python installation on the user's PC.
- The **new GPU worker image** containing the opt-in native Concat adapter must be running in your existing Salad instance. An old image responds with an explicit incompatibility error. Only the matching version works; image build/smoke and a real Windows-native project GPU render are separate acceptance gates.
- Your original Salad connection URL and render API token must be valid. The VPS Cloud Render receiver is already operational and remains unchanged.
- The existing Salad worker ZIP limit is 4 GiB. This pilot is particularly important on slow mobile hotspot; test with a small project first. Chunk retries and a retained local upload snapshot avoid silent data loss.
- For transparency: credentials cannot be reused automatically from VPS GPU Config because that page does **not** expose tokens back to a PC client. The first-use local prompts avoid modifying VPS or adding an API to leak saved keys.
- Shipping this modified Concat distribution is governed by the upstream **AGPL-3.0-or-later** license. Retain upstream license/notices and publish corresponding modified source and patches.

## Build

The `concat-gpu-editor-windows.yml` GitHub Actions workflow fetches the exact upstream source SHA, asserts its identity, applies `patch_editor.py`, checks PowerShell syntax and native ZIP packing, compiles `concat` from source on a Windows 2022 runner using the upstream pinned FFmpeg/ONNX/Sherpa dependencies, and publishes a **portable EXE + DLLs + notices** as a GitHub Actions artifact.

This is a custom from-source build, unlike `concat_original/` which only packages the unmodified official release.

**Acceptance pending:** native Windows build, actual editor File menu interaction, real project submission with CUDA rendering, audio sync, and VPS delivery. Do not call Stage 1 fully working from offline tests alone.

## Sources

- Upstream Concat: `jub0t/Concat`, revision `79116bd0f9a103c633d888603ad27890e929dbdc`.
- GPU feature implementation: `dilshadshahsyed883-cmd/vps1-deploy-control` PR #707 (`cloud_render/concat/gpu/`).
- Existing VPS receiver: `apps/scene-builder/part01/cloud_render.py` (unchanged).
