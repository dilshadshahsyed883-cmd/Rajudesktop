# AutoCapCut — Animations Only (Images)

**Standalone source prototype v0.2, 28 October 2026.** This is an independent application that leaves the original AutoCapCut EXE, **Transitions Only**, **Z Builder**, and all other project apps unchanged. Source uses Python 3.10+ and Tkinter, no third-party runtime dependencies.

## Exact scope

- Detect **only native Combo → Trending animation presets actually used on a photo/image clip in an existing saved CapCut project**. No scanning or downloading the CapCut global preset catalog, no creating fake effects.
- For each eligible clip in a target project, identify **only `materials.videos[].type == "photo"`**. No video clips can be selected for animation.
- An image can be on any CapCut visual track, but all tracks, layering, clips and timings remain untouched.
- Reuse the saved native material content, generating a fresh **outer** material UUID. Add that UUID to the target image segment's `extra_material_refs`; if an image already has a Combo animation, replace only that reference. Preserve transitions, In/Out animations, video segments, keyframes, audio, volume, trims and unrelated metadata.
- Original effect cache directory must exist on the same PC. Unavailable assets show **Missing**.
- **Fit animation duration to image automatically:** original native 5-second animations are shortened to a 1.7, 2, 2.5, 3, 3.6 or 4-second image by adjusting **only** nested native `animations[].duration`. The clip itself is never extended or shortened. If an image is longer than the original preset, the original animation duration is retained.
- **Random All Images:** assign randomly among every already-used **locally available** Combo → Trending preset. Avoid back-to-back repeats where at least two distinct presets exist. The preview freezes random assignments until the next Preview action.
- **Random Selected:** Ctrl/Shift-select only the animation presets you want included; target specific images or use Select all images. Single mode is still available.
- **Compatibility caveat:** retimed native animation JSON is structurally valid in our tests but its visual playback and rendering must be verified in the user's CapCut. A saved effect resource can have internal timing constraints not visible in JSON. Test with a duplicate project first.
- Back up all draft JSON and affected metadata, guard against CapCut being open, write active nested draft and main draft together, verify output, roll back on errors. Reapply of the same resource is idempotent.

## Run on Windows

1. Unzip the folder and run **`start.bat`**; Python 3.10+ must be installed with Tkinter.
2. Create a **duplicate** CapCut test project. Use CapCut itself to save at least one **Trending → Combo** animation on a **photo** clip in any saved project on that PC. Then **close CapCut**.
3. In the app, use **Change projects folder** if your drafts are stored on D: or another path. Select the duplicate target project.
4. The scanner detects native animations already used on saved image clips. **Missing** means its local CapCut cache asset was not found. In Single mode select exactly one animation; in Random selected mode Ctrl/Shift-select several; in Random all available mode no selection is required.
5. Choose exactly which images to animate, or click **Randomize ALL images** for one-click selection + random assignment preview. Video clips are *not displayed as targets*.
6. **Preview & validate** and check the exact image → animation assignments, fitted duration, and **Will Apply / Missing / Skipped** results. Random choices remain fixed between Preview and Apply.
7. Click **Apply animations to selected images**; a backup folder is created under `<Project>/.animations_only_backups/`. Reopen the project in CapCut and verify animations visually before using it on an important project.

## Verified tests

- **15/15 automated synthetic tests PASS**: image-only filter, no video changes, no track or trim changes, no transition or audio changes, cache resource validation, existing other animation preservation, idempotency, CapCut running guard, backup/mirror synchronization, stale preview refusal.
- **Real sample, read-only dry-run PASS:** CapCut 9.6 `after.zip` used to randomly assign three native Combo animations to the three photos in memory. All three MP4 segments, both visual layers, source/target timings, transitions and all non-animation data remained identical. Also tested a simulated 2.5-second photo with a 5-second preset: only copied material `animations[].duration` became 2.5s. No actual project was modified in this dry-run.
- **Not yet completed:** actual Windows/CapCut live acceptance of programmatically shortened and randomly assigned native animations, plus final export. Do not assume every Trending/Pro preset or short image duration is supported without checking it in CapCut. Test only on a disposable project first.

## Technical details

Observed CapCut v9.6 layout:

```text
materials.material_animations[]
  id: outer material UUID
  type: sticker_animation
  animations[]
    id / resource_id: native asset ID
    type: group
    category_name: Trending-3
    path: local CapCut effect cache
tracks[].segments[]
  [only photo segments] extra_material_refs[] -> outer material UUID
```

This app filters the records to **used on photo clips** and `group` + `Trending*`. A resource present in the draft but never linked to a saved image is not offered. Any original CapCut project ZIPs, proprietary AutoCapCut files, machine-specific paths or media files are **not** distributed with the app.

## Recover a project

The app writes a `manifest.json` listing original paths, backup filenames and SHA-256 values. If rollback is needed, close CapCut and restore backed-up copies to exactly the original paths. Make a duplicate before manual restore; don't overwrite a draft currently open in CapCut.