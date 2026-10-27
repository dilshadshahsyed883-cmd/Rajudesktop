# 03 — Native CapCut draft JSON: two-user-sample comparison

**Sources:** two user-supplied, read-only `draft_content.json` samples (original and second variant). **Neither original JSON is committed** because draft metadata contains private local paths and persistent hardware/device identifiers. The details below are intentionally sanitized; filenames are replaced with Video A / Photo A / Photo B.

## Project-level schema

Both samples: `draft_type="video"`, CapCut app `9.6.0`, schema `version=360000`, `new_version="189.0.0"`, `fps=30`, `canvas_config={width:1920,height:1362,ratio:"original"}`.

This canvas is **not 1920×1080 / 16:9**. Target timeline and source trim quantities in the sample are **integer microseconds** (`1_000_000` per second). A media's own `materials.videos[].duration` is not the rendered segment duration.

### Draft A: one common track

| Track | Material type | Timeline start | Target length | Timeline end | Source trim |
|---:|---|---:|---:|---:|---:|
| 0 | Video A | 0.0s | 4.0s | 4.0s | 0–4.0s |
| 0 | Photo A | 4.0s | 5.0s | 9.0s | 0–5.0s |
| 0 | Photo B | 9.0s | 5.0s | 14.0s | 0–5.0s |

- Total project duration **14.0 seconds**, 1 video track, 3 segments; no empty gaps.
- Photo A segment references a material animation named **Pendulum 1**, resource ID `6811007755785081357`, configured 5 seconds, through `extra_material_refs`.
- Photo A segment also references **Halo Shift**, resource ID `7683535350479817991`, 2 seconds with `is_overlap=true`. The transition's JSON presence does **not** establish a proven visually rendered overlap duration or effects portability.
- `materials.transitions` has one entry; `materials.material_animations` has an active group entry. Both samples have no `materials.audios` items or audio tracks. Project video keyframe arrays are empty.

### Draft B: two separate tracks

| Track array index | Track flag | Segment `render_index` | Material type | Start | Duration | End |
|---:|---:|---:|---|---:|---:|---:|
| 0 | 0 | 0 | Photo A | 0.0s | 5.0s | 5.0s |
| 0 | 0 | 0 | Photo B | 9.4s | 5.0s | 14.4s |
| 1 | 2 | 1 | Video A | 5.2s | 4.0s | 9.2s |

- Total project duration **14.4 seconds**, 2 video tracks, 3 segments.
- Segment `track_render_index` also equals 0 for photos and 1 for video.
- The sample therefore **observably serializes photos and video into separate tracks with distinct indices**. It is consistent with the desired lower-photo / higher-video layout, but **rendered foreground priority remains unproven**: no sample items from different tracks overlap at the same timestamp.
- **Uncovered timeline gaps:** 5.0–5.2 s and 9.2–9.4 s (each 0.2 s). The absence of segments at these moments is verified. Whether CapCut displays black or configured background there requires preview confirmation.
- Draft B retains the **Pendulum 1** animation on Photo A, but **`materials.transitions=[]`** and the Halo Shift transition reference has been removed.
- Main-track adsorption config changed from `maintrack_adsorb=true` in A to `false` in B; no causal claim about the editor UI is proven by that difference.
- This sample remains audio-free and has no explicit video keyframes.

## Native field mapping (observed)

| Purpose | JSON path | Notes |
|---|---|---|
| Project length | `duration` | Microseconds |
| Timeline frame rate | `fps` | Both examples use 30 |
| Canvas | `canvas_config.width/height/ratio` | Both `original`, 1920×1362 |
| Track list | `tracks[]` | `type="video"`; sample B has two tracks |
| Track placement metadata | `tracks[].flag`; segment `render_index`, `track_render_index` | 0 and 1 in second sample; visual stacking untested |
| Timeline position/duration | `tracks[].segments[].target_timerange.start/duration` | Microseconds |
| Source trimming | `tracks[].segments[].source_timerange.start/duration` | Microseconds |
| Media link | `tracks[].segments[].material_id` → `materials.videos[].id` | Referential link by ID |
| Media type and local location | `materials.videos[].type/path` | Type `video` or `photo`; local path is PC-specific |
| Clip motion/transform | `segments[].clip.scale/transform/flip/rotation/alpha` | Structural fields observed; visual modification not tested |
| Animation reference | `segments[].extra_material_refs[]` → `materials.material_animations[].id` | Photo A in both samples |
| Transition reference | `segments[].extra_material_refs[]` → `materials.transitions[].id` | Draft A only |
| Speed controls | `segments[].speed` and `materials.speeds[]` | All observed speeds 1.0 |
| Audio | `materials.audios[]` | Empty, no audio tracks in either sample |
| Keyframes | `common_keyframes`, `keyframe_refs`, `keyframes` | Empty; no editable keyframe example |

## Key engineering conclusions

1. Set exact timeline placement using **target** ranges, not source file duration. Scene Plan governs duration; avoid hardcoded 2.5 seconds.
2. Clip trimming can be represented separately with `source_timerange`; test an actual short trim before claiming CapCut behavioral success.
3. Photos use the `materials.videos` table in these drafts. Do not assume `materials.images` holds them.
4. Preserve/generate unique asset/material/segment IDs, consistent `extra_material_refs` and file paths when experimenting with generated drafts.
5. Two tracks are serialized in B, but to prove top-over-bottom visual compositing obtain an **overlapping** image/video test draft and render/reopen a clone.
6. Keep no-gap timeline validation and optional-audio handling separate from effects. Do not infer black output solely from missing clips.
7. Resource IDs for installed animation/transition may depend on the local effect cache or CapCut servers. Do not assume portable availability.
8. Edit only a separate copy of a draft/project. Success requires CapCut to reopen and visually render the generated copy without changes disappearing.

## Open tests

- Overlapping upper-video/lower-photo true visual layering and track z-order.
- Native MP3/audio track example, including mute and track positioning.
- Video trim to 2.5 s, audio sync and fractional-frame rounding.
- Ken Burns/keyframe structures; exact named animations and transitions; canvas fill at real 1920×1080; effect offline availability.
- Draft package contents and handoff into CapCut without overwriting a user project.
