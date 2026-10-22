# GPU Live Preview — Acceptance & Performance Requirements

## Implemented

Two selectable modes now exist:

- GPU Live: Qt QOpenGLWidget and OpenGL-backed QPainter textured layer composition. Timeline seeks, play/pause, bounded asynchronous PyAV video decoding (up to three CPU threads), eight nearby frames per task, 96 MiB image cache, maximum 1280px decode side, image/video overlays, pan/zoom/keyframe geometry, mirror, rotation, fades/slides, approximate brightness grading and live text/karaoke.
- FFmpeg Accurate: existing cached FFmpeg composition matching full export for LUT, filters, noise and captions. Retained as the accuracy/compatibility fallback.

Video decoding in GPU Live is **CPU**, NOT NVDEC/QSV/D3D hardware decode. GPU Live accelerates texture compositing only, and some effects are approximated. On failure to create a hardware-candidate OpenGL context, or when a software renderer is reported, the app automatically falls back to FFmpeg Accurate.

Live audio mixes use up to 20-second sliding audio-only FFmpeg jobs, with narration/music/SFX/optional source-video sound played through Qt and corrected against the visual playhead. This does not by itself prove sub-frame audio synchronization.

The GPU diagnostics panel shows measured OpenGL draw FPS and renderer/vendor. These readings alone do not prove video-media-ready FPS or CapCut parity. Source files are closed after every batched decode task to prevent Windows file locks. Original user media is never modified.

## Owner Windows machine acceptance (currently UNVERIFIED)

1. Record GPU renderer/vendor, actual RAM, CPU/GPU hardware and supported source video codecs.
2. Use representative 1080p projects containing two simultaneous video layers, captions, narration/music and overlays.
3. Perform 30 random seeks across 5–20 minute projects; target p95 first usable video-frame latency below 250ms.
4. Run 60 seconds continuous multitrack playback at 30 FPS; target at least 27 media-ready FPS (90% of target), not merely widget repaint FPS. Measure CPU, GPU, peak RAM, dropped media frames and stutter.
5. Compare GPU visual frames to FFmpeg final exports at matching timestamps for positioning, transitions, LUTs, filters and captions; mark all visual mismatches. Validate mixed-audio drift under 100ms including seeks and audio-window boundaries.
6. Validate 16:9 and 9:16, VFR, high-resolution inputs, exported output, cancellation, source cleanup/file unlocking, and rollback.
7. Switch automatically to FFmpeg Accurate for software/unknown OpenGL, unsupported codecs or material preview mismatches.

## Coverage vs non-coverage

| Capability | GPU Live | FFmpeg Accurate |
| --- | --- | --- |
| Clip seek, layered images/videos, zoom, mirror, pan, slides | OpenGL textured composition, CPU frame decode | FFmpeg |
| Numeric zoom/brightness/saturation keyframes | Interactive approximation | FFmpeg filtergraph |
| Plain and word-highlighted captions | Qt text | FFmpeg drawtext / ASS |
| 23 color looks and .cube LUTs | Basic color cue only; NOT exact | FFmpeg final renderer |
| Film grain and advanced LUT effects | NOT parity-matched | FFmpeg final renderer |
| Audio tracks and source video sound | Sliding audio-only Qt playback, latency unverified | FFmpeg mixed audio |
| Hardware video decode NVDEC/QSV/D3D11 | NOT implemented | Not guaranteed |
| Hardware GPU compositing on owner's Windows PC | UNVERIFIED | Not applicable |

## GitHub CI proof vs physical-machine proof

The Windows runner can test math, PyAV frame decode/close, cache limits, Qt OpenGL/PyOpenGL package imports, audio mix, FFmpeg exports, and packaged EXE headless launch. Hosted Windows runners may use software rendering. These checks **cannot** certify actual GPU frame timing, visual effect equality, video decoding hardware acceleration, owner CPU/RAM/GPU suitability, or real-time audio synchronization.

No automatic Tailscale connection, production VPS changes or final branch merge are part of this GPU work. The owner will perform interactive Windows UAT after a separately authorized manual Tailscale install.

STATUS: GPU-backed interactive preview candidate, NOT certified full CapCut-level GPU parity.
