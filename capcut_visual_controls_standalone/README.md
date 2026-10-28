# CapCut Visual Controls — Standalone V2 (6 functions)

**Separate from Z Builder.** A Windows Tkinter app (Python 3.10+; standard library only) that edits an **existing CapCut desktop draft**, not a video renderer. Start with `start.bat`. Close CapCut before applying. A disposable project duplicate is strongly recommended for the first test.

## Functions

1. Canvas Blur on every image/video: native canvas blur levels 1–4 (default medium). Blurs only **exposed canvas background**, not the foreground.
2. Video uniform scale: 115–125%, deterministic per clip.
3. Video position: X=0; Y randomly within −220 to −120 **pixels**.
4. Image uniform scale: 105–110%; Y −50 to 0 pixels (X preserved).
5. **Detect native Filters** (`materials.video_effects` with `type: "filter"`): preview name, track, scope, current duration and selected full duration. Checkbox to stretch each eligible existing dedicated filter track to **start 0 → audio timeline endpoint**.
6. **Detect native Effects** (`type: "video_effect"`): same operation, independently controlled.

### Target duration

The endpoint is computed from actual `tracks[type=audio].segments[].target_timerange.start + duration` (max across audio segments); `draft.duration` is *not* trusted. If there is no valid audio segment, the last existing visual segment endpoint is used, with a clear **visual fallback** label. The app does **not** extend/truncate/rebuild any audio or visual segment. When audio exceeds visual material, the effect can extend over a blank part of the timeline; check the source project itself.

Only pre-existing, directly linked, unambiguous single-segment **effect/filter tracks** are resized. Original native effect IDs, values, intensity, keyframes and cached resources are preserved. The source timerange duration is also kept in sync when it exists and has safe `start=0`. If target type is per clip, the FX segment is animated, has invalid timing, multiple segments share the same FX track, the track/material types disagree, or no endpoint is available, **no duration edit occurs**. Segment-attached FX and cached-but-unreferenced materials are *detected and reported*, not silently promoted into a new track. No downloaded CapCut resources or invented effects are used.

### Run and verify

1. Extract the ZIP; run `start.bat` (Python 3.10+ required). Choose CapCut's projects directory or a specific *project folder*.
2. For a filter/effects-only test, uncheck blur, video/image scale and positioning controls. Leave **Extend detected FILTER tracks** and/or **EFFECT tracks** on.
3. Click **Scan + Preview changes**. The **Detected Filters + Effects** tab shows exactly which existing native FX will extend, their original range, target and explicit skip reasons.
4. Ensure CapCut is **closed**, choose **Apply**. The app hashes selected draft files from preview, creates a backup of each changed native JSON plus project metadata, updates the **active nested timeline** and root draft, atomically writes and verifies content, and rolls back on mismatch. Backup folder: `.visual_controls_backups/<UTC-timestamp>` under the selected project.
5. Open CapCut and visually inspect the effect/filter duration, audio alignment and real playback/export on the duplicate. **Live CapCut 9.6 visual acceptance is not yet proven by unit tests.**

No Z Builder changes, no third-party recovered code. Does not apply effects not already present in a CapCut timeline, and does not render MP4. Position sign can vary between native CapCut versions: use **Invert Y** only when needed after manual verification.

### Tests

```powershell
py -3 -m unittest discover -s tests -v
```

Fifteen automated tests cover existing six controls, audio-vs-visual length, independent filter/effect checkboxes, safe skip cases, read-only detection, idempotence, mirrored drafts, metadata, backups and stale-preview rejection.

