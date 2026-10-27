# Z Builder — Scene Plan + Voice → Media Selection & Timeline → Open in CapCut

A **small standalone Windows desktop app**, not a copy of the complete VPS Scene Builder. The UI has **three steps**:

1. **Input:** load a simple timed Scene Plan `.txt` and the final MP3/WAV voice file.
2. **Media Selection & Timeline:** select images/videos from the local Media Library (import folder/files, preview, tags, downloadable media summary). Exact filenames are matched automatically; keywords match only when an unambiguous item exists. Replace any selected shot manually. The preview table shows every planned start/end, video trim and image hold.
3. **Open in CapCut:** preflight voice/media/shot timings, create a new editable CapCut project using the **original Z Studio draft writer**, and open CapCut if available. The resulting project appears under CapCut Home → Projects.

## Simple Scene Plan format

See `EXAMPLE_SCENE_PLAN.txt` in the ZIP:

```text
name=My Video
aspect=16:9
fps=30
00:00.000 --> 00:02.500 | video | Clip 1.mp4 | in=1.250
00:02.500 --> 00:07.250 | image | Poster 1.jpg
00:07.250 --> 00:09.000 | video | keyword: tennis | in=0
```

Each row specifies **exact target timeline start and end**, the media type, and an **exact filename** or `keyword: ...` for automatic media selection. Videos may optionally specify `in=` to choose where to start inside the source clip (seconds). `text=...` adds an optional editable CapCut text caption. `resolution=1080p`/`720p` and `aspect=16:9`/`9:16` are optional. Times support SS, MM:SS or HH:MM:SS and up to three decimal places. Original `SCENE_PLAN_VERSION=2` plans remain accepted as a legacy compatibility format.

**The Scene Plan is the sole timing authority.** The timeline must start at 00:00.000 and have no gaps/overlaps. Voice length is checked against the total scene duration if the audio duration is readable (difference over 0.25 seconds blocks export).

### Four-second video source rule

All source video clips are assumed to be **4 seconds maximum**. For a **2.5-second scene**, Z Builder sets the source range to **2.5 seconds**, not four; if `in=1.250`, it uses source **1.250–3.750**, placed at the scene's exact target range. Images simply hold as long as their scenes require (even more than 4 seconds).

- No source media is cut or overwritten on disk; CapCut's editable source and target time ranges perform the trims.
- If `source in + required scene duration` exceeds 4 seconds, export is blocked. No speed-up, slow-motion, frozen footage or silent stretching.
- Real video file duration is checked at export when FFmpeg/FFprobe is available. If duration cannot be probed, the source is assumed to be 4 seconds **with a warning**.
- For a scene longer than the available video, split the scene into smaller slots with additional media or use an image. One four-second clip is never stretched to fill it.

## Run (Python files only, no EXE)

1. Extract the ZIP to a folder on Windows.
2. Double-click `start_z_builder.bat`. Python 3.11+ is recommended. This installs Python dependencies only when missing and uses installed Node or a verified official portable Node.js (internet needed for first setup).
3. Import a media folder in **2 → Media Library**, add the Scene Plan and voice in **1 → Input**, then click Next to inspect and resolve the timeline. Click **3 → Open in CapCut** after preflight.

The app's media catalog is stored in `Documents/Z Builder/library.sqlite3`. Original files are never moved/deleted by the catalog. CapCut export copies referenced files into a new draft; it does not modify any existing draft or the original Z Studio.

## Compatibility limitations

The Z Studio CapCut draft layout is based on CapCut 9.4 and needs testing against installed CapCut versions. CapCut offers no supported direct deep-link to open a specific project; the app starts CapCut, and the newly created project is chosen on its Home screen. Non-cut transitions, LUTs and word-level karaoke effects are not included by the native Z Studio exporter. They are reported as warnings rather than silently faked. Automatic Pexels download is out of scope; the library supplies the media. Only scene timing, source trims, media choices, optional captions and the supplied voice are sent to CapCut. Existing VPS Scene Builder remains unchanged.

## Tests

`python -m unittest discover -s tests -p 'test_z_builder*.py' -v`

Includes a real 4-second video → 2.5-second CapCut source trim / correct target times / image hold / voice timeline integration test when FFmpeg and Node are installed.
