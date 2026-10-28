CAPCUT INDEPENDENT RENDERER v0.4 - DRAFT STYLE + HDR LOOK
======================================================
Standalone Windows Python app; no CapCut automation or Z Builder integration.

START
1. Extract this ZIP to its own folder.
2. Python 3.10+ with Tkinter is required. No pip packages are needed.
3. Copy ffmpeg.exe and ffprobe.exe from your working previous app's tools folder
   into this app's tools folder, unless both are already on PATH. FFmpeg must
   include libass's ass filter. Binaries are not bundled.
4. Double-click start.bat. Add your original CapCut project folder.
5. Analyze selected, then run a 60-second test at your preferred quality.
6. Keep Apply mapped video effects ON to apply the mapped HDR look.
7. Added caption fade starts OFF on upgrade. Your supplied draft has no active
   caption animation, so leave this OFF when preserving that appearance.
8. Review the MP4. Uncheck Short test first to export the complete timeline.

FIXES BASED ON THE ACTUAL 1028 DRAFT
- All 404 captions specify black text and a yellow #ffdc00 background. v0.3
  omitted this background. v0.4 draws a timed, rounded, padded yellow box behind
  each caption, including transform, color/alpha and approximate padding/radius.
- Font family is read from the actual referenced .ttf/.otf font file, instead of
  silently selecting Arial because font_name is empty. Font files are loaded
  from the existing local CapCut resource path; no fonts are installed or bundled.
  A missing/unreadable font uses a documented system fallback in font_status.
- A full-text style range is no longer mislabeled as an unsupported word highlight.
- The 404 material_animations records in 1028 ALL have empty animations arrays.
  These are empty holders, not 404 active animations. Reports now distinguish
  empty and nonempty animation records. No missing animation is invented for them.
- Default/no-op companion records no longer create generic missing-effect warnings.
- The actual video effect is HDR, from 0 to 1107.533333 seconds. It is mapped to
  an explicitly independent FFmpeg eq + unsharp look, before caption compositing.
  Effect timing is included in frame-aligned render boundaries.
- HDR can be turned off for comparison. Reports list source parameters, actual
  generated filters, enabled/applied status and the approximation warning.
- Changing renderer version or effect setting triggers a fresh export; a prior
  v0.3 success will not cause the corrected render to be skipped.

IMPORTANT HDR LIMIT
The HDR mapping is an aesthetic approximation, NOT CapCut's HDR shader or an
HDR10/HDR-video encoding feature. Its equations are independent choices, not
reverse-engineered parameter meanings. Source values are retained for audit.
The mapping uses intensity/range/luminance/filter/size as documented below;
effects_adjust_number is NOT mapped. Do not assume native visual equivalence.

strength = clamp(source intensity * material value, 0, 1)
contrast = 1 + strength * (0.25 + 0.5 * range)
brightness = strength * luminance * 0.04
saturation = 1 + strength * filter * 0.3
sharpen amount = strength * (0.25 + 0.75 * size)

Your draft's intensity is 0.02, so the independent result is deliberately subtle.
Unknown effects, masked/bound HDR and animated effect parameters remain unsupported
and reported. Do not substitute this mapping for a claim of exact CapCut rendering.

PRIVATE DELIVERY PREVIEW
The owner's delivered ZIP contains a style preview made on an earlier test MP4.
Private project media, raw draft data, machine-specific reports, fonts and that
preview are deliberately excluded from this public repository and source build.
The independent code and synthetic tests below are the canonical source.

RETAINED FEATURES
- Video/image/audio importing, trimming, constant speed, transform and overlays.
- Plain/rich text captions and optional added simple fade.
- Missing media or unparsed captions block export rather than disappear silently.
- Saved FIFO queue, reordering, retry, one-instance lock and interrupted recovery.
- Completed jobs are skipped only for matching settings/draft and existing output.
- Temporary PCM audio, one final AAC encode and full MP4 decode verification.
- Windows system sleep hold during render when supported; no persistent power
  settings are changed. Keep the app running; power loss/manual sleep still stop it.

OUTPUTS
Default: Documents\CapCut_Independent_Exports (or selected output folder).
MP4 + .report.json + .summary.txt + .captions.ass, plus project analysis JSON.
Reports separate whole-project counts from captions/effects in the short export.
Original project/media files are read-only. Existing MP4s are never overwritten.
Repeated names receive a numeric suffix. Completed video verification proves
technical readability, not CapCut fidelity, visual correctness or lip sync.

QUEUE
State: %LOCALAPPDATA%\CapCutIndependentRenderer\queue.json
Press Start after opening the app; pending jobs do not launch automatically.
Interrupted projects restart from the beginning. Retry is required after editing
source media in place (media bytes are not fingerprinted). Draft JSON is hashed.
No scheduled-start timer is included; you can start the FIFO queue before leaving.

REMAINING LIMITS
- Exact CapCut font sizing, background padding/radius, rich style ranges, shadow
  direction/blur, letter spacing, complex scripts and wrapping may differ.
- Captions are above all media layers; complex mixed layer orders are approximate.
- Active proprietary animations, other effects, filters, transitions, templates,
  masks, stickers, variable speed ramps, complex keyframes and AI are not reproduced.
- Font collections/nonstandard fonts can fall back. Complex font shaping is done
  by libass; background width is estimated from font advances without full shaping.
- Corrupt/encrypted drafts are not supported.
- Temporary files are cleaned on handled completion/failure/cancellation. A power
  loss can leave capcut_render_* directories; remove only when no renderer runs.
- Windows GUI/launcher, exact source en.ttf and original media rerender are not
  validated in this Linux environment. See VALIDATION.txt.

TROUBLESHOOTING
Analyze selected shows backgrounds, mapped effects and empty animation counts.
If font_status says system_fallback, check that the font_path exists on your PC.
If media is missing, choose the Media relink folder then Recheck media.
Startup errors: %LOCALAPPDATA%\CapCutIndependentRenderer\startup_error.txt
SELF_TEST.bat runs the bundled synthetic regression suite.

REFERENCES
https://ffmpeg.org/ffmpeg-filters.html#ass
https://ffmpeg.org/ffmpeg-filters.html#eq
https://ffmpeg.org/ffmpeg-filters.html#unsharp
https://learn.microsoft.com/en-us/typography/opentype/spec/name
https://learn.microsoft.com/en-us/typography/opentype/spec/hmtx
