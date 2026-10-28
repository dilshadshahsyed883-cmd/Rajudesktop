# Rajudesktop — App Directory (main)

**Canonical branch:** [main](https://github.com/dilshadshahsyed883-cmd/Rajudesktop/tree/main)  
**Consolidation date:** 2026-10-28  
**Scope:** Source code, project records, launch instructions, tests, and checked-in release archives where supplied. This consolidation does not deploy or install applications.

For each application, use the **main-branch path below** instead of searching old feature branches. Apps remain independent; Z Builder is not Z Studio, and Scene Builder Desktop is not Scene Desktop Studio.

| App / record | Canonical location in `main` | Start / source instructions | Notes |
| --- | --- | --- | --- |
| **Z Builder** | [`z_builder/`](z_builder/) | [`start_z_builder.bat`](start_z_builder.bat), [`Z_BUILDER.md`](Z_BUILDER.md) | CapCut draft generation, multi-part/full project and media-use counts; PRs #8, #11–14, #16–17 |
| **Scene Builder Desktop** | [`scene_builder_desktop/`](scene_builder_desktop/) | [`start_scene_builder_desktop.bat`](start_scene_builder_desktop.bat), [guide](SCENE_BUILDER_DESKTOP.md) | Separate Python desktop app; PR #7 |
| **Edge Voice Studio** | [`edge_voice_studio/`](edge_voice_studio/) | [`launch_edge_voice.py`](launch_edge_voice.py), [guide](EDGE_VOICE_STUDIO.md) | English TTS desktop code; check current main for the actual SRT behavior before packaging |
| **Voice → SRT Studio (batch)** | [`voice_to_srt_batch/`](voice_to_srt_batch/) | [`start.bat`](voice_to_srt_batch/start.bat), [guide](voice_to_srt_batch/VOICE_TO_SRT_STUDIO.md) | Batch voice transcription/SRT and Windows EXE workflow; PR #15 |
| **Smart Media Manager** | [`smart_media_manager/`](smart_media_manager/) | [`launch_smart_media_manager.py`](launch_smart_media_manager.py), [guide](SMART_MEDIA_MANAGER.md) | Combined editor utilities, including the downloader module |
| **Video Clip Cutter** | [`video_clip_cutter/`](video_clip_cutter/) | [`launch_video_clip_cutter.py`](launch_video_clip_cutter.py) | Independent source also accessible through the manager |
| **Image Renamer** | [`image_renamer/`](image_renamer/) | [`launch_image_renamer.py`](launch_image_renamer.py), [guide](IMAGE_RENAMER.md) | Independent utility; PR #4 |
| **Smart Clip Renamer** | [`smart_clip_renamer/`](smart_clip_renamer/) | [`launch_smart_clip_renamer.py`](launch_smart_clip_renamer.py), [guide](SMART_CLIP_RENAMER.md) | Independent utility; PR #5 |
| **SML Desktop** | [`sml_desktop/`](sml_desktop/) | [setup/launch instructions](sml_desktop/README.md) | Separate desktop media library; PR #3 |
| **Scene Desktop Studio** | [`scene_desktop/`](scene_desktop/) | [`launch.py`](launch.py), [root README](README.md) | Original editing MVP; different from Scene Builder Desktop and Z Builder |
| **Project Image Downloader (Chrome)** | [`project-image-downloader/`](project-image-downloader/) | [installation and tests](project-image-downloader/README.md), [version record](project-image-downloader/docs/REPOSITORY_RECORD.md) | v1.1.1 complete source + packaged ZIP; synthetic tests reported passing; live Chrome UX still pending. Getty original downloads require licensing and are **not** auto-supported |
| **Z Studio Video Editor** | [`z-studio/`](z-studio/) | [`z-studio/README.md`](z-studio/README.md), [`z-studio/start.bat`](z-studio/start.bat) | Independent legacy video editor; source chunk assembler and Windows build scripts; **not** Z Builder |
| **Z CapCut engineering record** | [`Z_CapCut/`](Z_CapCut/) | [research index](Z_CapCut/README.md) | Native-draft/schema/effects research and lab source, **not** a standalone export application |

## Latest record merged into main

- Z Builder changes through merged [PR #17](https://github.com/dilshadshahsyed883-cmd/Rajudesktop/pull/17) are already present in `main`. `used=N` reports count verified CapCut draft exports, not final renders.
- Batch Voice → SRT through [PR #15](https://github.com/dilshadshahsyed883-cmd/Rajudesktop/pull/15) is already in `main`.
- This consolidation additionally copies, **without replacing existing application files**, the independent `project-image-downloader/`, `z-studio/` and `Z_CapCut/` directories from their most complete identified source branches.
- The original branches and commit history are retained for comparison and rollback; source ZIPs are historical build artifacts, not automatic production deployments.

## Noncanonical / intentionally excluded branch history

Do **not** merge old branches wholesale just because their commits differ from `main`: they can replace newer implementations, reintroduce reverted functionality, or contain experimental integrations.

- [`feature/full-desktop-studio-unified-20261022`](https://github.com/dilshadshahsyed883-cmd/Rajudesktop/tree/feature/full-desktop-studio-unified-20261022): large earlier Scene Desktop experiment; root entrypoints/dependencies differ from current `main`. Its original branch remains accessible.
- [`feature/z-builder-full-web-source-20261027`](https://github.com/dilshadshahsyed883-cmd/Rajudesktop/tree/feature/z-builder-full-web-source-20261027): closed, unmerged draft/WIP; not a verified upgrade to the current Z Builder.
- Earlier Edge TTS licensing/SRT/build branches and earlier single-file Voice-to-SRT EXE branch are not independently promoted over current `main` releases; consult their history for specific changes.

**Not included:** The separate *CapCut Independent Export App* source is not among the audited Rajudesktop app directories/branches in this consolidation. `Z_CapCut/` contains research rather than that executable application. Its latest independently delivered source must be provided or committed before it can be consolidated.

## Check and run

- Project Image Downloader: `cd project-image-downloader && npm test` (Node 22+). Install `extension/` as an unpacked Chrome extension per its README; browser acceptance is still pending.
- Z Studio launcher tests: `python -m unittest discover -s z-studio/tests -p 'test_*.py' -v`. The chunk assembler verifies its bundled source checksum; it is not an automatic build.
- Repo desktop regression tests: `python -m unittest discover -s tests -v` with dependencies from the relevant requirements files. Some GUI/media-dependent tests require a configured Windows runner.
- Z CapCut's research examples should not be presented as verified native CapCut runtime behavior. Its lab test file refers to local fixtures not committed in the research branch.

**Protection:** Never commit user footage, machine-specific paths, credentials, OAuth tokens, private CapCut draft data, or private project media. No deployment or production environment is modified by this source consolidation.
