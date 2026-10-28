# CapCut Independent Renderer — source and acceptance record

Date: 28 October 2026. Canonical source after merge: `Rajudesktop/main`, `capcut_independent_renderer/`. Root app discovery: [`APP_INDEX.md`](../APP_INDEX.md).

## Accepted direction and feedback

The owner selected the standalone independent FFmpeg renderer, abandoned the CapCut UI-automation trial for this work, and requested that Z Builder remain untouched. After receiving v0.4, the owner reported “achha result mila” and asked to update Rajudesktop and master docs. Record this as **owner-reported good result for the tested delivery**, not a universal visual-equivalence or overnight/full-project certification.

## Evidence boundaries

| Evidence | What it establishes |
| --- | --- |
| Uploaded real draft audit | 404 parsed captions; black text + yellow background; 404 empty animation holders; zero nonempty holders; one HDR effect over 0–1107.533333 seconds |
| v0.3 owner-generated report | 23 captions within 60 seconds; no unparsed/missing media; 1920×1080/30 fps; full decode/metadata pass; 104-second render time |
| v0.4 local regressions | 26/26 synthetic/integration tests passed; background visibility/timing, font metadata, effect on/off pixel differences and prior queue/render safeguards |
| v0.4 private style proxy | 8-second 1080p render using the prior test MP4 as footage/audio proxy and real draft style/effect settings; decode passed; representative frame inspected |
| Latest owner message | Good result reported; repository and master-register update requested |

Source CI is added with this import. Do not label a GitHub run passed until it completes. It tests synthetic media and Windows GUI startup, not the owner's original projects or hardware.

## Limits retained

The HDR mapping is an independent aesthetic approximation; `effects_adjust_number` remains unmapped. It neither executes the CapCut shader nor produces HDR10 video. Font sizing, background geometry, shaping/spacing and rich styles can differ. Missing source fonts use a reported fallback. Other proprietary effects/active animations are unsupported. No claim is made of native CapCut pixel equivalence, complete 18-minute playback acceptance, lip sync certification or unattended queue acceptance.

The public repository intentionally excludes user footage, raw private draft JSON, machine-specific reports, proxy screenshots, font binaries and the media-containing private ZIP. Source packaging is rebuilt from an allowlist, with a new checksum; it is not byte-identical to the private delivery archive.

## Preservation

This import adds only the independent app, its source-only packaging/CI, a root launcher and app-index/documentation records. Existing Z Builder, native-export controller and other app implementation files remain unchanged. No remote PC installation, VPS work, Auto Script execution or deployment is authorized/performed by this record update.
