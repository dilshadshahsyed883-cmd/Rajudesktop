# Z Builder — Scene Plan → Local Media Timeline → CapCut Projects

Small standalone Windows desktop application (Python/PySide6), independent of the VPS. The UI has **three steps**:

1. **Input:** import a simple timed Scene Plan `.txt`; voice MP3/WAV is optional.
2. **Media Selection & Timeline:** import images/videos into the included local Media Library, match scene filenames/keywords, manually replace missing items and inspect exact timing/trim.
3. **Open in CapCut:** choose **Create Editable CapCut Parts (5–7 min)** or **Create Complete Project in CapCut**. Both use the original Z Studio writer and preserve editable media/track timing.

## Fixed CapCut tracks, splitting and optional audio

- **Fixed visual layering:** still images always go onto the **lower visual track**, videos onto the **upper visual track** when both types exist. There is **no toggle to reverse** the layers. Original scene start/end times are retained; each part's draft starts at 00:00. This only changes Z Builder's opt-in writer mode, not Z Studio's legacy mixed-track mode.
- **Split export:** target **6 minutes (360 seconds)**, with **5–7 minutes (300–420 seconds)** preferred. Scenes are **never split mid-shot**. Each exported part is **never longer than 7 minutes**. The last leftover part may be shorter than 5 minutes; if a single Scene Plan scene exceeds 7 minutes, export blocks and asks for a shorter plan shot.
- **Complete project:** writes **one** native CapCut project under the Scene Plan's name, even when the plan exceeds seven minutes. It preserves the full timeline with no part offsets, and uses the same lower-image / upper-video track order. This is an alternative to split export, not an automatic additional copy.\n- **Export progress:** a built-in animated busy bar and stage label stay on Step 3, showing preparation, per-draft creation, and genuine verified draft counts. It never displays a made-up percentage. Windows Node/FFmpeg subprocesses use hidden consoles so they do not flash over the UI.\n- **Voice:** `Include Voice in CapCut export` is a checkbox in Step 3, **OFF by default**. If OFF, no narration file or audio track is exported even when voice was selected in Input. If ON, each part receives its properly trimmed section of the source MP3/WAV (the source in-point equals that part's absolute starting time). No audio is fabricated. Source-video audio is muted. You may leave voice unselected and add audio during final editing/rendering.
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

Tests cover the 4-second video → 2.5-second source/target trim, fixed image/video track ordering, 345-shot → 3-part splitting, complete-project export beyond 7 minutes, genuine progress callbacks, default muted/absent audio, and optional voice source offset across multiple projects.
