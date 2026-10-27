# 05 — CapCut 9.6.0.4097 root-binaries ZIP: static inspection

**Source:** user-supplied `9.6.0.4097.zip` (2026-10-27); 81 MiB compressed. Inspected read-only: ZIP central-directory entries and selected PE export tables. No executables loaded or run.

## Verified archive summary

| Metric | Value |
|---|---:|
| Files | 177 |
| Uncompressed total | 212,604,429 bytes |
| File entries in nested paths | 0 |
| .dll | 155 |
| .exe | 15 |
| .node | 3 |
| .js | 2 |
| .dmp (crash dumps) | 2 |
| ZIP CRC archive test | PASS |

Archive SHA-256: `8f07a34999f425674148aa3ab033cce789b8eb7546525b8b28da62a0fcd47d60`.

**Scope limitation:** This is a root-binary sample, **not a complete CapCut installation**. It contains no nested `Resources/`, `Tools/draft-converter/`, effects cache, user-project files, presets database or native draft JSON. Therefore it cannot by itself enumerate all animations, transitions, effects or the editing API.

## Native modules of interest (observed filenames and static exports)

| Component | Confirmed observation | What is NOT confirmed |
|---|---|---|
| `CapCut.exe` | PE executable, 90,536 bytes | That this alone is a complete portable application |
| `videoeditor_addon.node` | PE native Node module, 3,689,984 bytes; exports `napi_register_module_v1` and `node_api_module_get_api_version_v1` | Its application functions and any supported external SDK |
| `agent_runtime_addon.node` | Node addon present | Public agent API |
| `ttnet_frontier_addon.node` | Node addon present | Public network API |
| `lyra_cli_client.dll` | PE DLL, 10,809,256 bytes; export table exists | That any exported symbol is safe or publicly callable from Z Builder |
| `EffectPlatform.dll` | PE DLL, 1,576,872 bytes; export table exists | Complete effects inventory or stable render API |
| `DeepAgentsService.dll` | PE DLL, 4,421,032 bytes, observed `entryPoint` export | Standalone automation accessibility |
| `Tracking.dll` | PE DLL, 1,673,640 bytes; export table exists | Face/object tracking behavior or Z Builder portability |
| `clipflow_sdk.dll` | Native library, 3,352,488 bytes | Open developer SDK or documented API |
| `FusionUI.dll`, Qt6 libraries | Native GUI/runtime components present | Editable timeline layout via external scripting |

## Video and audio stack indicators

- FFmpeg family present: `ffmpeg.exe`, `ffmpeg.dll`, `avformat-61.dll`, `avfilter-10.dll`, `avutil-59.dll`, `avdevice-61.dll`, `swscale-8.dll` and `swresample-5.dll`.
- Codec/processing libraries observed: `SvtAv1Enc.dll`, `dav1d.dll`, `ByteVC1_dec.dll`, `jxl.dll`, `ttheif_dec.dll`, `libmp3lame-0.dll`, `libraw.dll`, `nvjpeg64_12.dll`, `openvino_intel_npu_plugin.dll`.
- This identifies bundled dependencies, **not** enabled features, codec licensing, renderer quality or user-visible workflow compatibility.
- `lynx_core.js` and `lynx_core_dev.js` are present; their presence does not establish CapCut timeline schema.

## Sensitive and security-conscious handling

- **Two `.dmp` crash dump files are in the archive.** They may include private process memory; do not upload, commit, paste or automatically index them.
- Do not add this 81 MiB installation archive, any included binaries, dumps or license-sensitive materials to the **public** Rajudesktop repository.
- Avoid executing native DLLs, developer helpers, unknown `*.exe` or JavaScript merely to probe features. This research has used metadata/static inspection only.
- Never infer effects support or external callable methods solely from a library filename or export existence.

## Impact on Z Builder

1. Native module evidence supplements the resource inventory and two draft samples; **draft JSON remains the actionable format evidence**.
2. Prefer Z Builder's independently generated, validated CapCut-compatible draft copies, not undocumented direct calls into installation DLLs.
3. Before promising effects and layer automation: obtain a **time-overlapping** two-track draft and perform CapCut reopen/render tests.
4. Maintain explicit pending status for complete effects inventory, open-ended API access, converter functionality, audio track support and persistent animation compatibility.

**Status: recorded research only; no Z Builder code or CapCut installation modified.**
