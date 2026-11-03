# VideoFlow Original Desktop Test — Windows portable EXE

This app packages the **official upstream @videoflow/react-video-editor** as an
independent Electron desktop window. It is NOT a redesigned VideoFlow, not a
CapCut replacement and not an official VideoFlow desktop release.

Upstream: https://github.com/ybouane/videoflow-react-video-editor
Live example: https://videoflow.dev/playground?step=video-editor
Editor licensing: https://videoflow.dev/license

## What is included

- Original VideoFlow editor: multi-track timeline, media panel, preview,
  inspector, text/keyframe animation, transitions, effects and built-in MP4 export.
- Electron and Chromium; React, VideoFlow core, DOM and browser renderers.
- Native Windows Save dialogs for VideoJSON project and rendered MP4.
- Imported media streamed in 4 MiB chunks into the app's private local media
  directory; secure vf:// local media protocol with byte-range responses.
- Automatically restored local draft; Save exports JSON and stores last project.
- No VPS, SaladCloud, third-party asset server, cloud account or runtime npm.

The original editor's drop/import control is unchanged. It supports multiple
video clips and tracks; one-click bulk picker selection is NOT guaranteed by
the official component.

## Getting the EXE

A separate GitHub Actions workflow builds the unsigned portable Windows EXE:
.github/workflows/videoflow-original-windows.yml

After a successful branch/PR build, download the Actions artifact
VideoFlow-Original-Windows-Portable. Following a successful main-branch build,
the workflow also publishes a GitHub Release with direct EXE and SHA256 file.

Windows SmartScreen may warn about an unsigned test build. The portable launcher
unpacks Electron to a temporary directory. No Node.js or FFmpeg installation is
required on the user's PC to launch this evaluation build.

## Manual Windows build (Node.js 22)

~~~powershell
cd videoflow_desktop
npm install --no-audit --no-fund
npm test
npm run package:win
~~~

Output: release/VideoFlow-Original-Portable.exe

## 30-second test on PC

1. Run the EXE; the original VideoFlow interface should open.
2. Drop/import 2–3 MP4 files via the editor's own controls and place them on
   different timeline tracks or sequentially.
3. Set a 30-second timeline, apply transition/effect/keyframe text animation.
4. Export with the original VideoFlow export dialog, then select a local MP4
   destination in the Windows Save dialog.
5. Verify MP4 duration, sound sync, transitions, effects and real render time.

A successful GitHub build DOES NOT certify runtime speed, WebGL/WebCodecs,
render completion or specific Dell E5570 GPU/drivers. A real local acceptance
test is mandatory. Some unsupported media codecs may fail.

## Storage, portability, and limitations

- The latest draft and imported media are saved under Electron's userData
  location on this PC. Do not delete the media folder if you need those clips.
- A saved VideoJSON project references local vf:// media URLs, not a portable
  media bundle. Copying JSON alone to another computer will not copy MP4s.
- Original MP4 files selected by the user are not deleted or modified.
- The editor component uses a separate two-tier license from Apache-2.0 core.
  Free licensing covers individuals and specified small/nonprofit/evaluation
  use cases. Some commercial organizations require a company license.
- This isolated test does not modify any other Rajudesktop application.
- The frozen Cloud rendere Editly + FFmpeg plan and VPS_1 remain unchanged.

For third-party notices read THIRD_PARTY_LICENSES.md.
