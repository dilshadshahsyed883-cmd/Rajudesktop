# AutoCapCut Animations Only — Release history

## v0.2 — October 28, 2026

- New **Randomize ALL images** button: applies a deterministic-in-preview random plan for all photos using locally available native Trending Combo animations already used on images in saved CapCut projects.
- **Random selected animations** mode: choose a subset with Ctrl/Shift; Single mode remains available.
- Fit 5-second native animation material duration to images shorter than 5 seconds via `min(native_duration, image_duration)`, without extending or trimming any image.
- Avoid adjacent duplicate animation choices when at least two saved effect resources are available.
- Revalidate resource paths, photo identities and draft fingerprint before writing; preview and apply use the same frozen assignments.
- Preserve video segments, layers, audio, transitions, trims, keyframes and all source/target clip timings.
- Native JSON updates remain backed up and atomically written with rollback.
- 15 unit tests passed locally; user-provided CapCut 9.6 AFTER snapshot passed read-only image-only and video/layer preservation dry run.
- **Native shortened animation appearance and final export are not yet confirmed in CapCut. Test on a duplicate.**
- Original third-party AutoCapCut, Transitions Only and Z Builder are unchanged.
