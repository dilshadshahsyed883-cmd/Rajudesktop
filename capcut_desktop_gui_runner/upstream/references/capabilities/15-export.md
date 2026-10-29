# Capability 15: Export (resolution, fps, bitrate, codec; verify the output file)

## Status
- **Ladder status:** approved (2026-09-15, "Approve, start Rung 16 (Recommended)")
- **CapCut version:** 9.4.0.4015
- **Demonstrated:** 2026-09-15 by Claude Code. `E:\videos\exports\0915-copy.mp4`: h264 Main
  1920×1080 30 fps (900 frames), AAC stereo 44.1 kHz, 30.00 s, 40 055 206 B. Cloud sync off; the
  project is unchanged.
- **Approved:** not yet
- **Practice project:** `0915-copy` (the approved rung-14 promo, 30 s). Exporting only reads the
  project; the draft must stay unchanged.
- **Evidence:** `evidence/2026-09-15/cap15/`

## Goal
Export an approved edit natively through CapCut's Export dialog with stated settings, to a
user-approved folder. Then verify the file itself with the bundled ffmpeg/ffprobe: container,
codec, resolution, frame rate, duration, audio stream, loudness, and frames that match the
timeline.

## Preconditions
- Rungs 0–14 approved.
- **Side effects:** exporting writes a file, which the user approved for this run: 1080p 30fps
  H.264 to `E:\videos\exports`.
  - ⚠ **"Sync exported videos to space"** is **checked by default** in the dialog. It uploads to
    CapCut cloud, which the standing rules forbid, so **uncheck it before Export**.
  - Also stop on any Pro/credit/upsell prompt (e.g. for Pro features used in the edit).
- **Known route** (rung 0, observed, never run):
  - The cyan **Export** button (top-right) or **Ctrl+E** opens a named window
    `Export-<project>` (id `ExportWindow_Container`, no child controls in UIA).
  - Right-hand fields: Name, **Export to** path + folder icon, and a Video section with
    Resolution ▾ (1080P), Bit rate ▾ (Recommended), Codec ▾ (H.264), Format ▾ (mp4), Frame rate ▾
    (30fps), Color space.
  - Also: the Sync-to-space checkbox, an Audio section (unchecked, MP3), and a footer with
    Duration/Size, **Export** and **Cancel**. The settings list scrolls.
- **Bundled tools:** `D:\Bytedance\CapCut\Apps\9.4.0.4015\ffmpeg.exe` (read-only analysis).
  Check whether an `ffprobe.exe` sits beside it; otherwise use `ffmpeg -i`.

## User choices (2026-09-15)
- **Project:** "0915-copy promo (Recommended)".
- **Settings:** "1080p 30fps H.264 (Recommended)", bitrate left at CapCut's Recommended.
- **Folder:** "E:\videos\exports (Recommended)", a new subfolder created only through CapCut's own
  export dialog.

## Plan
1. Baseline: all project mtimes, the `0915-copy` draft copy, and the state of the exports folder.
2. Open `0915-copy`; open the Export dialog (Ctrl+E); screenshot every section (scroll the list).
3. Set Name, Export to `E:\videos\exports` (create the folder via the dialog's folder picker if
   needed), and Resolution 1080P / Bit rate Recommended / Codec H.264 / Format mp4 / Frame rate
   30fps. **Uncheck Sync to space.** Screenshot the final settings before clicking Export.
4. Export; record the progress UI and duration; wait for the completion screen. Do not click any
   share/upload/publish buttons on it.
5. Verify the file: size, `ffmpeg -i` stream info (h264, 1920×1080, 30 fps, AAC audio, 30.0 s),
   ebur128 loudness, and frames extracted at key times (logo, 14:23 blend, 16:14 canvas blur)
   compared with the player frames from rung 14.
6. Verify the draft is unchanged and the other projects' mtimes; confirm nothing was uploaded
   (sync unchecked).
7. Write up, contact sheet, ask for approval.

## Procedure

### A. Baseline (read-only, 2026-09-15)
- **Project mtimes:** 16 projects saved to `cap15/mtimes-before.txt`.
- **Draft copy:** `cap15/draft-before-export.json` (the `0915-copy` draft as saved at the end of
  rung 14, 02:59:12).
- **`E:\videos\exports` does not exist yet.** `E:\videos` has one subfolder (the Arabic-titled
  project's export folder) and 48 top-level mp4 files. The new folder will be created only through
  CapCut's dialog.
- **No `ffprobe.exe`** beside the bundled ffmpeg, so file verification uses `ffmpeg -i` (stream
  info on stderr), `ebur128` and frame extraction.

### B. Open the project and the Export dialog (2026-09-15)
1. From Home (`scroll 1000 700 -3`, `00-home-projects.png`), click the **`0915-copy`** card
   ≈(383,793). `MainWindow` appears after 4 s; then `focus --maximize` (`01-editor-opened.png`).
2. **Ctrl+E.** `wait-for --id ExportWindow_Container --depth 3` matches in **0.2 s** (0.8 s wall).
   **Tree:**
   - `Window "Export-0915-copy"` id `ExportWindow_Container`, cls `ExportWindow_QMLTYPE_2223`,
     rect **(510,101)–(1410,929)**, a child of MainWindow
   - `cc.py windows` also lists it as a top-level `Qt622QWindowIcon` titled `Export-0915-copy`
   - as in rung 0, no child controls are exposed, so the dialog is **screenshot-only**
     (`02-export-dialog.png`)
3. **Dialog layout and defaults** (dialog rect (510,101)–(1410,929)):
   - **Left:** cover preview with **Edit cover**, showing the first frame with the logo.
   - Export timeline: Timeline 01.
   - **Name** ≈(1238,227): `0915-copy`.
   - **Export to** ≈(1220,273): `E:/videos/0915-copy.mp4`, the last-used folder. Folder icon
     ≈(1371,273).
   - **Video** ✓ (≈967,342):
     - Resolution ≈(1229,389): **1080P**
     - Bit rate ≈(1229,437): **Recommended**
     - Codec ≈(1229,484): **H.264**
     - Format ≈(1229,532): **mp4**
     - Frame rate ≈(1229,579): **30fps**
     - Color space: Rec. 709 SDR (read-only)

     **The defaults already match the user's 1080p / 30fps / H.264 choice.**
   - ⚠ **Sync exported videos to space ✓** ≈(967,696): checked by default.
   - **Audio** ☐ ≈(967,764), Format MP3 (greyed). This is a separate audio-only file option; the
     mp4 carries the soundtrack regardless.
   - **Footer:** "Duration: 30s | Size: about 30 MB" (the estimate implies ≈8 Mbps at
     Recommended), **Export** ≈(1244,895), **Cancel** ≈(1344,895).
4. **Draft unchanged by opening:** the mtime is still 02:59:12.029 and the diff vs
   `draft-before-export.json` shows no differences.

### C. Uncheck cloud sync and pick the export folder (2026-09-15)
1. **Uncheck "Sync exported videos to space":** click the checkbox ≈(967,696).
   - **Observed** (`03-sync-unchecked.png`, dialog crop): the box is **empty**. Everything else is
     unchanged: 1080P / Recommended / H.264 / mp4 / 30fps, Audio ☐, "about 30 MB".
2. **Folder icon** ≈(1371,273) opens a **native Windows folder picker**, and unlike the Export
   dialog it is **fully exposed to UIA**:
   - `cc.py windows`: `#32770` **"Select exporting path"** (518,101)–(1462,693), owned by
     CapCut.exe.
   - It opens in **E:\videos**, the last export folder. The address bar is
     `ToolBar "Address: E:\videos"`, with breadcrumb SplitButtons "This PC › New Volume (E:) ›
     videos".
   - Toolbar buttons: **Organize**, **`Button "New folder"`** ≈(688,202), Views, Help.
   - Left: `Tree "Tree View"` (Quick access, This PC, drives…). Right: `List "Items View"`, which
     here shows only the Arabic-titled project's folder.
   - **`Edit "Folder:"` id 1152** ≈(1080,622), **`Button "Select Folder"` id 1**
     ≈(1249,660), **`Button "Cancel"` id 2** ≈(1386,660).
   - Note: `tree --root focused` shows only the Folder: edit. Use the default roots with depth 16
     to see the whole dialog (`04-folder-picker.png`).
3. **Create the folder inside the picker:** `act invoke --type Button --name "New folder" --depth 20`.
   - A "New folder" item appears in rename mode (`05-new-folder-rename.png`); then
     `type "exports"` and `key enter`.
   - **Agent-verified:** `E:\videos\exports` exists and is **empty**, with **no stray
     `E:\videos\New folder`**. The picker lists the **exports** folder selected and Folder: reads
     `exports` (`06-folder-created.png`).
4. **Select it:** `act set-value --type Edit --id 1152 --value "E:\videos\exports"`, then
   `act invoke --type Button --id 1 --name "Select Folder"`.
   - The picker (`#32770`) is gone on the first 0.5 s poll.
   - **Observed** (`07-export-to-set.png`): **Export to `E:/videos/exports/0915-copy.mp4`** (the
     Name is kept, and CapCut writes forward slashes).
   - **Sync still ☐**; 1080P / Recommended / H.264 / mp4 / 30fps; "Duration: 30s | Size: about
     30 MB". These are the final settings checked before clicking Export.

### D. Export and the completion screen (executed 2026-09-15, user-approved export)
1. **Click Export** ≈(1244,895). Monitoring: file size and window list every ≈2 s, stopping after 3
   stable polls (`export-monitor.txt`).
   - **Fast:** at the **first poll (t≈2 s)** `E:\videos\exports\0915-copy.mp4` already existed at its
     final size, **40 055 206 B (≈38.2 MiB)**, mtime 03:16:34.105. It was stable through t≈9.8 s.
   - The 30 s 1080p clip rendered in under ≈2 s, most likely hardware encoding.
   - **No new windows** at any poll: no cost/credit/upsell dialog, no sync prompt.
2. **Completion screen**, in the same `Export-0915-copy` window, which moved to (510,120)–(1410,911)
   (`08-progress-2.png`, `09-export-done.png`):
   - The header reads "Video is saved to your desktop or laptop. You can share it now."
   - **Left:** radio **Original** (selected, playing a preview), then radio **"9:16 (TikTok video
     size)"** with a **Pro diamond**. Its preview showed **"Generating… 52 %"** and then played a
     reframed 9:16 preview.
     - ⚠ The Pro 9:16 variant generated automatically, but **no second file was written**:
       `E:\videos\exports` holds only `0915-copy.mp4`.
   - **Right:** a **share form** with TikTok / YouTube tabs, "Go to TikTok Studio for full settings",
     Account **Sign in**, Name, Visibility Private, Allow Comment/Duet/Stitch, Check copyright.
     ⚠ This publishes externally, so **never touch it without explicit permission**.
   - **Footer:** **Open folder** ≈(586,876), **Share** ≈(1244,876), **Close** ≈(1344,876).
3. **Close** ≈(1344,876) dismisses it (`10-after-close.png`).

### E. File verification (bundled ffmpeg, read-only)
- **`ffmpeg -i`** (`ffmpeg-info.txt`):
  - Container: `isom` mp4, encoder `Lavf61.1.100`, **Duration 00:00:30.00**, overall ≈10 681 kb/s.
  - **Video:** **h264 (Main)**, yuv420p (tv, **bt709**, progressive), **1920×1080** SAR 1:1 DAR
    16:9, ≈10 479 kb/s, **30 fps**.
  - **Audio:** **AAC LC**, 44 100 Hz, **stereo**, ≈195 kb/s.
  - The size estimate ("about 30 MB") was low: the actual file is ≈38 MiB, since Recommended bitrate
    came out ≈10.5 Mbps.
- **Loudness** (`ebur128=peak=true`, `ffmpeg-ebur128.txt`): **I −14.2 LUFS**, LRA 23.1 LU, true
  peak **−1.4 dBFS**.
  - This matches the untreated talk source (rung-11 reference clip 0: −14.2 LUFS / TP −1.4). The
    rung-11 −23 LUFS normalization lives only on the master project, not on `0915`.
  - The high LRA comes from the quiet desk section after 15 s.
- **Frame count:** a full decode (`-map 0:v:0 -f null -progress`) gives **frame=900**,
  out_time 00:00:30.000000. That is exactly 30 s × 30 fps, with no dropped or duplicated frames.
  The audio stream also ends at 30.000000.
- **Frames extracted** at 2.000, 13.467, 14.000, 14.767, 15.200, 16.467, 19.967 and 29.500 s
  (`file-frames/*.png`, full 1920×1080), compared with the rung-14 player frames
  (`rung15-contact-sheet.png`):
  - **13.467 s:** the sharp cut-out speaker is over the blurred room with the Auto adjust
    brightness; the **logo** is crisp top-right at the expected size and margins.
  - **14.767 s:** the **Cross Fade** blend renders in the file: a semi-transparent speaker (overlay
    Fade Out) ghosted with the incoming portrait desk shot. It matches the player's 14:23.
  - **16.467 s / 19.967 s:** the portrait desk clip with the **canvas blur** fill (no black bars) and
    the logo readable on it; stabilized framing.
  - The file matches the edit at every checked point, at higher detail than the Medium player
    preview.
- **Draft untouched by exporting:** the `0915-copy` mtime is still 02:59:12.029 and the diff vs
  `draft-before-export.json` shows no differences.
- **Scope:** all **16** projects unchanged (`mtimes-after-export.txt`); `E:\videos` still has 48
  top-level mp4 files. The only new file on disk is `E:\videos\exports\0915-copy.mp4`, in the new
  `exports` folder.
- **No upload:** Sync to space was unchecked, and no share or sign-in controls were used.

## Wait conditions
- **Export dialog:** `wait-for --id ExportWindow_Container --depth 3` (≈0.2 s).
- **Folder picker:** `#32770` "Select exporting path" appears in `cc.py windows` within ≈2.5 s. It is
  closed when it drops out of the list (first 0.5 s poll after Select Folder).
- **Render:** poll the output file's size until it is unchanged for 3 polls (≈2 s apart). Here the
  file was complete at the first poll (a 30 s 1080p clip in under 2 s). Longer timelines need a
  longer timeout: scale by duration and allow minutes for the 7:31 master.
- **Done:** the Export window switches to the share/completion layout ("Video is saved to your
  desktop or laptop"). The Pro 9:16 preview may show "Generating… N %" there; that is not the
  export and is not needed.

## Verification
**Agent-verified 2026-09-15** (details in E):
- Output file present in the approved folder with exactly the chosen settings: h264, 1920×1080,
  30 fps, mp4, and **30.00 s / 900 frames**, with an AAC stereo track.
- Frames decoded from the file match the edit (logo, transition blend, overlay fade, canvas blur,
  Auto adjust look): `rung15-contact-sheet.png`.
- Loudness measured: I −14.2 LUFS, true peak −1.4 dBFS.
- The project draft is unchanged, all 16 projects' mtimes are unchanged, and no other files were
  added to `E:\videos`.
- Cloud sync was unchecked before Export, and no Share, TikTok, YouTube or Sign-in control was
  clicked.

## Parameters
| Parameter | Value used | Universal or shot-specific | How to judge it |
|---|---|---|---|
| Resolution | 1080P (default) | match the canvas (1920×1080 here) | ffmpeg stream size |
| Bit rate | Recommended (≈10.5 Mbps video here) | default; raise for heavy grain/motion | file ≈38 MiB for 30 s |
| Codec / Format | H.264 / mp4 (defaults) | universal upload default | `h264 (Main)`, `isom` |
| Frame rate | 30fps (default = timeline) | match the timeline fps | frame count = duration × fps |
| Sync exported videos to space | **unchecked** (default is checked) | **always uncheck** unless the user asks | screenshot before Export |
| Export to | `E:\videos\exports\<name>.mp4`, created via the picker's New folder | user-approved per run | file appears only there |
| Audio-only file | off | only if the user wants a separate audio file | — |

## Undo / recovery
- Exporting does not modify the project (diff = none), so nothing needs undoing in CapCut.
- The only artefacts are the file `E:\videos\exports\0915-copy.mp4` and the new `exports` folder.
  Removing them is a deletion and needs the user's confirmation. They were left in place as the
  deliverable.
- CapCut remembers the last export folder (it defaulted to `E:/videos`), so the next export will
  default to `E:\videos\exports`. Check the path on every run.

## Failure modes seen
| Symptom | Cause | Recovery |
|---|---|---|
| The Export dialog has no UIA children | QML window | Screenshot + coordinates within the dialog rect; verify every field by crop before Export |
| "Sync exported videos to space" pre-checked | CapCut default (Auto sync on for exported videos) | Click to uncheck, confirm by crop; recheck after changing the folder |
| The size estimate ("about 30 MB") was lower than the real 38 MiB | The estimate is rough | Measure the actual file |
| The completion screen auto-generates a Pro 9:16 preview and shows a TikTok/YouTube share form | CapCut's share upsell | Ignore it; no file is written; press **Close** only |
| `ffmpeg -c copy -f null` printed no frame= line through PowerShell | PS 5.1 stderr handling | Use `-progress -` with a decode (`-f null`), which prints `frame=900` on stdout |

## Tree coverage notes
- **UIA-exposed:** the `ExportWindow_Container` presence and rect, and the **entire native folder
  picker** (`#32770`: New folder button, Folder: edit id 1152, Select Folder id 1, Cancel id 2,
  address breadcrumbs, tree/list items).
- **Screenshot-only:** every Export dialog control (Name, Export to, the Video dropdowns, Sync
  checkbox, Audio, Export/Cancel), the completion/share screen, and the Open folder / Share / Close
  buttons.

## Open questions for the user
- None. Loudness from rung 11 ("decide at export") doesn't apply to this project because it carries
  no normalization. It stays open for the master/short exports in rungs 16–17.
