# CapCut Independent Renderer v0.4

Standalone Python/Tkinter app that reads local CapCut draft JSON and produces an independent FFmpeg MP4. It neither launches CapCut nor modifies Z Builder.

**Owner feedback, 28 October 2026:** the owner reports a good result and requested that this version be recorded in Rajudesktop and its master register. This is acceptance of the tested result, not proof of universal CapCut equivalence.

## Run

Use [`../start_capcut_independent_renderer.bat`](../start_capcut_independent_renderer.bat) or [`start.bat`](start.bat). Python 3.10+ with Tkinter, FFmpeg and FFprobe are required. Caption rendering requires FFmpeg's libass `ass` filter. No pip packages are needed. Place the two executables in `tools/` or on PATH.

See [README.txt](README.txt) for full controls, output files, queue recovery and known limits.

## Current capabilities

- Independent media/audio rendering, saved FIFO queue, cancellation and verified MP4 publication.
- Timed captions with source colors, rounded backgrounds and available source font files.
- Explicit HDR-look approximation before captions, controlled by an on/off setting and source effect timerange.
- Reports distinguish active/nonempty animation records from empty holders. The tested draft contained 404 empty holders, not 404 active animations.

The HDR look is an independent `eq`/`unsharp` mapping. It is **not** CapCut's proprietary shader or HDR10 output. Source parameter `effects_adjust_number` is unmapped. Background geometry, font sizing and rich styles remain approximate; other proprietary effects/animations remain unsupported.

## Verify and package

```bash
python -m unittest discover -s capcut_independent_renderer/tests -v
python capcut_independent_renderer/build_source_zip.py --output /path/to/CapCut_Independent_Renderer_v04_source.zip
```

The source builder uses a fixed file allowlist and emits a SHA-256 file. CI tests Linux and Windows, performs a Windows Tkinter startup smoke, and packages source only. It never installs to an owner PC or deploys to a VPS.

The public source build excludes private footage, draft JSON, font binaries, previews and machine-specific reports. [REPOSITORY_RECORD.md](REPOSITORY_RECORD.md), [CHANGELOG.md](CHANGELOG.md) and [VALIDATION.txt](VALIDATION.txt) separate development evidence, user feedback and remaining verification.
