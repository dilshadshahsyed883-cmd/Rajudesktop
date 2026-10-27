# Z Builder — Standalone Windows Scene Plan to CapCut

Z Builder combines **Director V25 Scene Plan**, a **local Media Library**, deterministic **shot-by-shot media matching**, and the **original Z Studio CapCut draft writer**. It does not modify the VPS Scene Builder, SML or Z Studio.

## Run (source, no EXE)

1. Extract ZIP and double-click `start_z_builder.bat` (or `pip install -r requirements-z-builder.txt && python launch_z_builder.py`). Python 3.11+ recommended.
2. The launcher reuses installed Node.js or downloads verified official portable Node.js (first launch only, internet required). The **native CapCut draft export** uses Z Studio's original pure-Node `capcut-draft.js`; no rewriting of CapCut's fragile JSON format.
3. Import a folder of images/videos; optional tags; download catalog summary TXT.
4. Import Director V25 TXT (`SCENE_PLAN_VERSION=2`). Review provisional shot duration warnings.
5. In Media Selection, match **exact approved filenames** or manually replace missing/ambiguous scenes.
6. Add optional voice narration, run preflight, and choose **Create Editable CapCut Project**. It appears in **CapCut Home > Projects**; CapCut has no supported deep link to open one draft directly.

The local catalog DB is under `Documents/Z Builder/library.sqlite3`. Import never moves/deletes original assets. The CapCut exporter copies only referenced media into a new draft folder and verifies it. Deleting catalog entries only removes their database records.

## Source handling and limitations

- `library_only`: unresolved shots block export. **Never** calls Pexels.
- `scene_first`: unresolved shots explicitly show the V25 Pexels query but are **not silently downloaded**. Manually supply matching footage before export. External stock search needs a separate API-backed implementation.
- V25 `animation_duration` is used as a **provisional** shot duration only if no explicit `shot_duration_seconds` / `duration_seconds` exists. It is not an automatic speech-to-time alignment engine.
- The implemented keyframe animations are `pan_left`, `pan_right`, `right_zoom`, `zoom_1`, `zoom_in`, `zoom_out`; unsupported animation types remain warnings, not fake successful effects.
- Non-cut transitions, LUTs and karaoke word highlighting are **not carried into CapCut** by the original Z Studio writer. Their omissions are listed in each exported draft's `Z_Builder_Warnings.txt`; spoken scene text is exported as simple editable caption blocks.
- Z Studio's CapCut draft layout was derived from CapCut 9.4. Newer/other installed CapCut versions may be incompatible; desktop confirmation is necessary. No installed CapCut is required for unit testing drafts to a chosen folder.
- Source-video audio is muted to avoid overlapping narration, but the separate narration audio track is preserved when supplied. Video duration probing uses bundled imageio-ffmpeg (or FFprobe/FFmpeg on PATH) for accurate source trim/duration; run preflight after media assignment.

## Tests

`python -m unittest discover -s tests -p 'test_z_builder.py' -v`

The portable source ZIP includes the Z Studio CapCut module, which retains its original header comments and attribution. There is no proprietary Z Studio licensing logic or credentials included.
