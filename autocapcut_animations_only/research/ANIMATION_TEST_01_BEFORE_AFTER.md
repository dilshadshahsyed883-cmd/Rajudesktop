# AutoCapCut Animations Only — native Combo animation fixture study

**Status:** Source evidence verified from user-provided `before.zip` and `after.zip` for project `Animation_Test_01` (28 October 2026). **Analysis only: no animation app built or existing app modified.**

## Experimental setup and boundaries

- CapCut Windows project version from `platform.app_version`: **9.6.0**.
- `before.zip` project: **3 JPG photos**, **3 MP4 videos**, **2 video-type tracks**, **no native animation materials**.
- `after.zip` project: the same clips and tracks, **3 added native Combo animations**, all applied to the **three JPG photo clips**. None of the three MP4 clips received an animation in this experiment.
- Both ZIPs include top-level `draft_content.json` and active `Timelines/<id>/draft_content.json`; the top-level and active nested drafts matched **within each archive**. Both were compared **read-only**.
- No original ZIP, actual project content, machine user directory, device identifier or media file is uploaded here.

## Exact observed animations

| Source media | Native animation name | Resource ID | Duration (microseconds) |
| --- | --- | --- | --- |
| Photo 1 | Pendulum 1 | `6811007755785081357` | `5000000` |
| Photo 2 | Pendulum 2 | `6811007833069326862` | `5000000` |
| Photo 3 | Sway Out | `6789167998700622350` | `5000000` |

The observed JSON model is:

```text
draft_content.json
  materials.material_animations[]   [before: 0, after: 3]
    id                            unique material UUID
    type                          "sticker_animation"
    animations[]
      id                          native resource ID
      type                        "group"
      start                       0 (microseconds)
      duration                    5000000 (microseconds)
      name                        "Pendulum 1" / "Pendulum 2" / "Sway Out"
      category_name               "Trending-3"
      category_id                 "2037708290"
      panel                       "video"
      material_type               "video"
      resource_id                 same native ID as animations[].id
      third_resource_id           same native ID
      path                        absolute local CapCut effect cache path
  tracks[0].segments[0..2].extra_material_refs[]
    -> corresponding unique materials.material_animations[].id
```

Note: `animations[].material_type: "video"` is present **even on JPG photo segments**. It is not proof that MP4 clips have been tested. `category_name: "Trending-3"` is the category label **observed in this CapCut version**; do not rely on it as a universal future label.

## Before / after integrity checks

- **Total tracks unchanged:** 2.
- **Images unchanged:** 3/3.
- **Videos unchanged:** 3/3.
- **Clip identity, order, source ranges, target ranges:** identical.
- **`materials.videos` source records:** identical.
- **Overall draft duration:** unchanged.
- **Animation materials:** 0 → 3.
- **Native animation material UUIDs attached to only the 3 photo clips; the 3 video clips' segment records were unchanged.**

CapCut's save operation also altered unrelated metadata:
- `materials.loudnesses`: 0 → 3 disabled records.
- `materials.sound_channel_mappings`: six `type` values changed.
- `materials.vocal_separations`: three IDs regenerated.
- Auxiliary draft/cover/backup files were updated or created.

**These unrelated changes must not be copied by a transition/animation-only editor.** They are independent save side-effects, not evidence of animation necessities.

## Native animation editor research conclusion

An independently authored, non-destructive editor can be **designed for a controlled duplicate-project test** around two narrow modifications:

1. Copy an **already-used** native animation material into `materials.material_animations`, generating a new unique **outer** material ID for each clip while preserving verified resource/animation identifiers.
2. Add that outer ID to the chosen existing clip's `extra_material_refs`, without replacing the clip, the whole track, source/target time ranges, transitions, keyframes, or audio.

Also require: same-PC path availability check for existing `Cache/effect/<resource_id>/<resource_hash>`; preview/validation; safe active-timeline mirror and top-level draft writes; idempotency; backup and rollback; and explicit no-write while CapCut runs. Never fetch extra effects or attempt Pro entitlement bypass.

**Not yet proven:** Whether cloned animation records apply successfully to MP4 clips, handling of 4-second target clips versus 5-second source animation, reuse across multiple CapCut versions, effect rendering, and whether fields such as `request_id` require regeneration. The user-provided ZIPs **do not contain the actual downloaded cache resources**.

## Smallest next fixture

In the same test project, apply **one saved native Trending → Combo animation to Video 1 (.mp4)**, save, fully close CapCut, and provide the new **after_video.zip** snapshot. No new empty baseline is needed, because the supplied `after.zip` already serves as the before-state for this next experiment. Compare:
- MP4 clip reference to `material_animations`,
- record schema and `duration`,
- whether existing photo animations and all media/timing remain unchanged.

**Change control:** The existing original AutoCapCut v0.1.2 EXE, Transitions Only v0.1, Z Builder, and VPS projects remain untouched. A standalone Animations Only application should be built only after fixture-based compatibility verification.
