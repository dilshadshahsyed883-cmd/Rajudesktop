# Z Builder — Scene Plan → Local Media Timeline → CapCut Projects

Standalone Windows desktop application (Python/PySide6), independent of the VPS. **Windows v9 retains the fourth main CapCut Controls tab with Transitions and Animations sub-tabs** while preserving the three existing production steps:

1. **Input:** import a simple timed Scene Plan `.txt`; voice MP3/WAV is optional.
2. **Media Selection & Timeline:** import images/videos into the included local Media Library, match scene filenames/keywords, manually replace missing items and inspect exact timing/trim.
3. **Open in CapCut:** choose **Create Editable CapCut Parts (5–7 min)** or **Create Complete Project in CapCut**. Both use the original Z Studio writer and preserve editable media/track timing.

## Fourth tab — CapCut Controls (Windows v6)

The fourth main tab is **4 CapCut Controls**, containing exactly two independent sub-tabs:

### Transitions
The existing owner-tested `z_builder/transitions_tab.py` panel and `autocapcut_transitions_only.transition_engine` are reused unchanged. Scan transitions from saved native CapCut projects, Single/Random mix, favorites, Edit File JSON, Preview/Log and Apply with guarded backups. Owner confirmed transitions applied while preserving video clips and timeline layers. Only same-track adjacent cuts are eligible. Close CapCut before Apply.

### Animations
A new PySide6 panel, `z_builder/animations_tab.py`, reuses the independently authored `autocapcut_animations_only.animation_engine` v0.2 unchanged.

- Detect only already-used native **Video → Animation → Combo → Trending** resources on PHOTO clips from locally saved CapCut projects; unavailable cache entries are marked Missing. No effect downloads or Pro bypass.
- Browse existing CapCut projects independently; search, favorite, select a native animation or several favorites.
- Apply **Single**, **Random selected**, or **Random all available**. **Randomize ALL images** targets every photo segment, freezes the preview assignments and avoids immediate duplicates where multiple presets exist.
- The **duration of the native animation record** is shortened to the existing photo clip duration where necessary; no modification of source or target clip time ranges.
- Preview & validate then explicit Apply after CapCut is closed. Timestamped backups, stale-project checking and rollback are provided by the standalone animation engine.
- Video clips are never animation targets. Existing videos, image order, tracks/layers, audio, transitions, motions and timings must be preserved by the engine's invariants.
- **Live validation boundary:** Automated engine tests and read-only CapCut 9.6 fixture checks have passed, but rendering of shortened animations on an actual Windows/CapCut installation is still awaiting user verification. Test a duplicate draft first.

The two sub-tabs are UI peers within the fourth main tab, **not separate Windows apps**; the first three workflow steps and scene/media exporter remain unchanged. The original third-party AutoCapCut EXE and previous Transitions Only source remain available for rollback.

**EXE:** GitHub Actions `Z Builder Windows EXE v6 — CapCut Controls` builds and tests portable `Z_Builder.exe` and publishes the v6 release on successful main-branch build. The v5 release remains available for rollback.

## Scene Plan effects summary for ChatGPT (Windows v7)

From **Step 1 → Input — Scene Plan + Voice**, click **Download CapCut Effects Summary .txt** before generating the Scene Plan. This **does not require importing a Scene Plan first**. Z Builder reads the CapCut project roots currently configured in the fourth **CapCut Controls → Transitions / Animations** sub-tabs, scans saved native materials, and saves a text file using a standard Windows Save dialog (default `Documents/Z Builder/CapCut_Effects_Summary.txt`).

The report includes:

- **Available** native **Combo → Trending photo animations** actually used in saved projects whose local cache paths exist: exact preset names, native resource/effect IDs, categories and original durations.
- **Missing-cache animations** in a separate DO NOT USE section.
- Native transitions found in saved CapCut draft materials: exact names, native effect IDs and categories, marked **cache not independently verified**. A listed transition is not a guarantee that the specific cut or installed effect will apply.
- A privacy-safe prompt instruction block (no absolute PC paths, original filenames, project names or cached-resource file paths).

Upload `CapCut_Effects_Summary.txt` to ChatGPT alongside the **Media Summary TXT**, synchronized **SRT** and **Z Builder Master Scene Plan prompt**. ChatGPT should use only available listed animation IDs and documented transition names/IDs when proposing effects. Native Combo is restricted to image clips; same-track constraints apply to current transitions.

**Important:** This release adds a *downloadable catalog*, not yet direct Scene Plan effect application. The current timed Scene Plan parser **does not accept** `combo=` or `transition_after=` extras. The report tells ChatGPT to produce a valid timed Scene Plan and a separate shot-ID effect-intent mapping until the next parser/integration phase. This keeps current exports safe and compatible. This export is read-only; none of the transition/animation apply engines change.

## Scene Plan → automatic native CapCut effects (Windows v8+, single track in v9)

**New integrated export:** Import a valid simple timed Scene Plan, match media, then select **Create Editable CapCut Parts** or **Create Complete Project**. Z Builder now resolves native Combo animations and native transitions from saved local CapCut catalogs **before writing drafts**, creates the normal timed two-layer CapCut project, and attaches original native effects without rebuilding its clips.

The **Step 1 Download CapCut Effects Summary .txt** button remains the source of truth for ChatGPT to select actual saved effects. Use `CapCut_Effects_Summary.txt` + `Media_Summary.txt` + synchronized SRT + Master Prompt to generate the following *directly importable* Scene Plan fields:

```text
name=Scene Plan Native Effects
aspect=16:9
resolution=1080p
fps=30
combo_default=random_saved
transition_default=random_saved
combo_seed=42
transition_seed=43
transition_duration=0.5
00:00.000 --> 00:02.500 | image | photo1.jpg | combo=id:<real available animation ID>
00:02.500 --> 00:05.000 | image | photo2.jpg | transition_after=none
00:05.000 --> 00:09.000 | video | clip1.mp4 | in=0 | transition_after=none
```

Replace placeholder IDs with the **exact ID from the generated effects summary** and filenames with approved Media Library names. Use `transition_after=id:...` only when the next image or video shot is **adjacent on the same visual track within the same project part**. In v9 an outgoing image → video boundary is eligible because both clips share the same visual track. This example uses `transition_after=none` only as a deliberate per-shot opt-out.

**Rules:**
- `combo_default=random_saved` applies locally available native Trending Combo animations **to images only**; video clips are always excluded.
- `combo=<exact display name>` or `combo=id:<native resource ID>` selects a specific image animation; `combo=none` opts out. Native animation duration is fitted within the image time range without changing shot timing.
- `transition_default=random_saved` assigns saved native transitions to **eligible same-track adjacent outgoing cuts**; unsupported gapped or cross-part cuts are reported rather than silently rewritten. `transition_after=<exact name>` or `transition_after=id:<effect ID>` selects a cut; `transition_after=none` opts out.
- Seeds produce deterministic choices for a given plan and saved catalog. Exact effect names must be unambiguous. Unknown IDs, missing animation caches, explicit cross-part transitions or missing folders **block before creating drafts**.
- The original Scene Plan **`animation`** field remains reserved for pre-existing keyframe motions, not native Combo; old Scene Plans without these new directives retain their former export behavior.
- All new draft native effects are applied from verified saved-project templates to original generated segments and written to top-level + nested CapCut JSON with backups and readback verification. No timeline rebuild, clip deletion, retiming, audio or layer changes.
- The v7 effects summary, v6 CapCut Controls tab and previous EXE releases remain available for rollback. **Actual visual validation of short native Combo presets on the installed CapCut version is still recommended on a duplicate project.**

## Single-track timeline export — Windows v9

By owner request, **every new CapCut draft created by Z Builder** (both complete-project and 5–7-minute-part exports) contains **one mixed visual track** named `Images + Videos - Single Layer`. The original timed Scene Plan dictates clip order, image/video alternation, trim and timing. Audio and editable captions remain separate non-visual tracks if enabled.

**Native transitions now work across immediately adjacent photo↔video, video↔photo, photo↔photo and video↔video cuts on this visual track**, subject to the existing local native transition availability and strict cut/time validation. No transitions are invented at boundaries between separate CapCut parts. Native Combo/Trending animations still apply **to images only**, never videos. Previously installed native effects are reused; no resources downloaded or entitlements bypassed.

The native writer verifies one visual track, correct chronological media types, and unchanged source/target ranges. Automatic CI tests check real Node draft exports, 345-clip part splits and Scene Plan effect attachments. A versioned v8 EXE remains available for rollback. New v9 exports are different from previously exported projects; **no existing CapCut drafts are edited/migrated automatically**.

## CapCut visual tracks, splitting and optional audio

- **Single visual track (v9):** images and videos go onto the **same visual track**, in exact Scene Plan order. There is no layer toggle in this export. Original scene start/end times are retained; each part's draft starts at 00:00. This only changes Z Builder's opt-in writer mode, not Z Studio's legacy mixed-track mode.
- **Split export:** target **6 minutes (360 seconds)**, with **5–7 minutes (300–420 seconds)** preferred. Scenes are **never split mid-shot**. Each exported part is **never longer than 7 minutes**. The last leftover part may be shorter than 5 minutes; if a single Scene Plan scene exceeds 7 minutes, export blocks and asks for a shorter plan shot.
- **Complete project:** writes **one** native CapCut project under the Scene Plan's name, even when the plan exceeds seven minutes. It preserves the full timeline with no part offsets, and uses the same single image/video visual track. This is an alternative to split export, not an automatic additional copy.\n- **Export progress:** a built-in animated busy bar and stage label stay on Step 3, showing preparation, per-draft creation, and genuine verified draft counts. It never displays a made-up percentage. Windows Node/FFmpeg subprocesses use hidden consoles so they do not flash over the UI.\n- **Voice:** `Include Voice in CapCut export` is a checkbox in Step 3, **OFF by default**. If OFF, no narration file or audio track is exported even when voice was selected in Input. If ON, each part receives its properly trimmed section of the source MP3/WAV (the source in-point equals that part's absolute starting time). No audio is fabricated. Source-video audio is muted. You may leave voice unselected and add audio during final editing/rendering.
- Split mode creates separate CapCut Home → Projects drafts named `Your Project - Part 01`, `Your Project - Part 02`, etc., with `Z_Builder_Part_Info.json`. Complete mode creates one draft with `Z_Builder_Project_Info.json`. Both include `Z_Builder_Timeline.csv` and `Z_Builder_Warnings.txt`.
- The exporter uses the source asset files **non-destructively** and verifies written JSON, media and track assignments. Actual compatibility with installed CapCut versions must be tested on the user's PC.

## Used Media — manual cleanup after final CapCut rendering

- A local asset is marked **Exported ×N** only after all CapCut draft(s) for the chosen mode finish successfully and verification passes; merely adding it to the library or matching a Scene Plan never makes it eligible for cleanup.
- **Download Summary .txt** writes `used=N` alongside every image and video name/ID: `used=0` for never used, `used=1`, `used=2`, etc. for the number of verified CapCut exports that included the asset. Multiple appearances within one export count once, not once per timeline occurrence. The report also gives the total number of never-used assets.
- In **Step 2 → Media Library**, select the **Used in CapCut Export** filter. Select individual rows with Ctrl/Shift or use **Select All Used Media**.
- After you manually finish and inspect your **final rendered video in CapCut**, check **Final video rendered and checked in CapCut**, then click **Delete Selected Used Media (Recycle Bin)**.
- Z Builder displays original filenames, counts, total size, and a final destructive-action confirmation. Only those selected original PC files are moved to the **Windows Recycle Bin** using `send2trash` and removed from the catalog. No automatic cleanup, permanent deletion, or change to unselected media.
- **Important:** CapCut draft creation is not final rendering; Z Builder cannot detect whether your manual CapCut render has actually completed. If media is used by another project or you intend to re-edit it, keep the original files. CapCut draft folders and exported final videos are not deleted. Re-import a recovered file if required.

## Clean Entire Library

In **Step 2 → Media Library**, press **Clean Entire Library**. This operates on **all**
cataloged images and videos (not just media used in a CapCut draft). Choose one mode:

1. **Clear Library Only (default and safest)** — removes all Z Builder library
   entries, search tags, and export-history flags. **Original PC files are kept.**
   It does not delete CapCut drafts, exported videos, project files, or voice files.
2. **Move All Library Original Files to Windows Recycle Bin** — moves both used and
   unused library media from their actual PC folders into Recycle Bin. This requires
   manually confirming your final CapCut videos are rendered and checked, a Yes/No
   dialog, and typing **DELETE ALL**. Missing originals are forgotten; locked or
   unsafe original files are skipped and left in the library for retry. Other
   CapCut projects may still rely on these sources, so do not choose this mode
   until all relevant edits are finished.

**Neither mode runs automatically.** Clean Entire Library is separate from the
existing **Delete Selected Used Media** action. The app cannot independently
confirm render completion.

## Simple Scene Plan format

```text
name=My Video
aspect=16:9
resolution=1080p
fps=30
00:00.000 --> 00:02.500 | video | Clip 1.mp4 | in=1.250
00:02.500 --> 00:07.250 | image | Poster 1.jpg
00:07.250 --> 00:09.000 | video | keyword: tennis | in=0
```

Each row defines authoritative **absolute start/end** timings and one image/video filename or keyword. Video `in=` (seconds) controls source trim start; optional `text=...` adds an editable caption. Times accept SS, MM:SS or HH:MM:SS with up to 3 decimals. `SCENE_PLAN_VERSION=2` input remains supported for legacy Scene Plans, but its `animation_duration` fallback is only a provisional shot duration, not voice alignment.

Every row must be continuous, with no overlap or gap. Original 4-second video clips are trimmed (not re-encoded) to the scene duration, subject to `source in + slot duration <= 4 seconds`. Images hold for their exact slot length. Real source length is checked where FFmpeg can read it; unknown length yields a warning, not a claim of verification.

## Run

**Source build**: on Windows (Python 3.11+), extract ZIP and run `start_z_builder.bat`, which installs dependencies if required and bootstraps the official portable Node runtime when needed. The app's catalog lives in `Documents/Z Builder/library.sqlite3` and does not delete original PC media unless you explicitly invoke render-confirmed Recycle Bin cleanup. To build from source: `pip install -r requirements-z-builder.txt && python launch_z_builder.py`.

**Windows EXE build**: the `Z Builder Windows EXE` GitHub Actions workflow builds a portable PyInstaller one-file executable with PySide6, the original Z Studio Node exporter and bundled Node runtime. No separate system Python/Node installation is needed for that EXE. Windows SmartScreen may warn because the build is not code-signed. The official CapCut application must still be installed. The EXE is a Windows-only CI artifact, not locally built on Linux.

## Limitations

The Z Studio CapCut JSON layout was modeled on CapCut 9.4; validate the produced draft against your installed CapCut version. CapCut does not support a specific-project deep link, so Z Builder opens CapCut but you select the new draft(s) from its Home screen. Advanced LUTs, transitions and karaoke animations are not transferred to CapCut; relevant warnings are saved. No Pexels downloader, no unrequested VPS changes, and no modification of your original media or previous drafts.

## Test

`python -m unittest discover -s tests -p 'test_z_builder*.py' -v`

Tests cover the 4-second video → 2.5-second source/target trim, single mixed-image/video track ordering, 345-shot → 3-part splitting, complete-project export beyond 7 minutes, genuine progress callbacks, default muted/absent audio, and optional voice source offset across multiple projects.
