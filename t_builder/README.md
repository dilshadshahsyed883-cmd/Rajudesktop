# T Builder v0.1 — Sequential Timeline

Independent Windows keyword timeline generator. Launch `T_Builder.exe`; Python, Qt, FFmpeg and Node are bundled. CapCut must be installed separately for opening/playback. No Scene Plan or SRT is required.

1. Import a media folder in **Media Library**. Preview images/video, search, edit tags, and download Media Summary. Filenames are retained; `New York Family_12.jpg` belongs to `New York Family`.
2. In **Timeline Builder → Audio & Timeline Setup**, select the library folder, narration, an existing CapCut drafts folder and a new project name.
3. In **Media Selection**, check image keywords and set strengths. Selected strengths rebalance to exactly 100%. Optionally enable independent video keywords and coverage.
4. **Generate & Open in CapCut** validates feasibility, moves selected files into their original parent’s `used/`, creates and verifies a native editable draft, and optionally launches CapCut. Select the new project from CapCut Home, as in Z Builder.
5. **CapCut Controls** retains the canonical V6.3 Transitions and Scale/Position/Blur interface and engines, including project checks and backups.

**v0.1 — sequential timing:** Images fill only the spaces BETWEEN video clips, not under them. Every image-to-video cut is exact (`image.end == video.start`), every video-to-image cut is exact (`video.end == next_image.start`), and the combined visual timeline has no gaps or overlaps. Images are usually random 3–5s segments; short boundary pictures are used only when exact gap fitting requires them. Videos are muted 2.5–4s clips with no reuse, consecutive videos are separated by images, and successive video keywords differ. Requested video coverage is still the exact total duration across the narration; the video positions are randomized across the entire timeline, with image gaps kept. The two editable CapCut visual tracks remain separate, but never occupy the same timestamp. Impossible requests are rejected before media moves. Weighted selections are approximate; alternating video keywords can constrain the attainable weighting.

T Builder stores its catalog and move journal in its own Windows local application data directory and uses separate QSettings/Windows identity. Source lives in `t_builder/`; the canonical controls and JS writer are isolated copies. Z Builder files/settings/databases are not modified. Shared imports are read-only library helpers and existing transition/scale engines.

## Used media and cleanup

Only selected media moves, during generation. Original filenames are preserved and existing destinations are never overwritten. Drafts reference those actual moved paths. Failed generation leaves moved media in `used/`; the durable `last_generation.json` and SQLite moves table report incomplete work. Audio is referenced at its selected original path.

Previous-used cleanup defaults OFF. When enabled, a review dialog displays the full eligible file list and count before confirmation. Only T Builder-tracked files inside the selected library's direct `used/` locations can be recycled. Unrelated files and unused originals are excluded. Current/default/previously registered CapCut draft roots are inspected, including timeline copies; referenced files are protected and unreadable drafts block cleanup. Keep other active project locations registered through the CapCut Controls folder selector before cleanup. Cleanup never searches arbitrary PC folders. Clean Entire Library retains the canonical keep-files or Recycle Bin choices and final-render/typed confirmations; physical cleanup also blocks when any catalog file is referenced by a known active project. Move protection history is preserved.

## Development and validation

```
python -m pip install -r requirements-t-builder.txt
python launch_t_builder.py
python -m unittest discover -s t_builder/tests -v
python launch_t_builder.py --self-test-report smoke.json
```

The dedicated `t-builder-windows-exe.yml` workflow runs T Builder tests, existing Z Builder and transition/scale regressions, builds a one-file EXE, launches it with isolated settings and real synthetic media, verifies draft tracks/moves/cleanup/Scale, and publishes the executable, smoke report/screenshot and SHA256 digest as `T-Builder-Windows-Verified`.

Automated draft structure and packaged startup validation does not establish playback compatibility with the user's installed CapCut version. User-PC installation/playback has not been tested by CI.
