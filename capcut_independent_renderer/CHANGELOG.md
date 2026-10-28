# Changes

## v0.4 — 28 October 2026

Owner reports a good result and approves updating repository/master records.

- Restore the supplied draft's black text and yellow rounded caption backgrounds; v0.3 had omitted the backgrounds.
- Read the font's embedded family from an available source font file; disclose system fallback.
- Map the HDR video effect to an independent FFmpeg look with explicit timing and approximation metadata.
- Correct the earlier animation warning: the tested 404 animation holders all contain empty animation lists.
- Stop treating a full-caption style range or inactive companion material as a missing animation/effect.
- Retain FIFO persistence, cancellation, technical/full-decode verification and no-overwrite MP4 publication.
- Force a fresh export after renderer/effect settings change, including upgrade from v0.3.
- Repository Windows hardening: catch a second instance's denied lock-byte read and close that file handle before reporting that the app is already running.

Local development validation: 26/26 tests passed before repository import. The Windows lock cleanup regression raises the repository suite to 27 tests. Source CI results are authoritative only after the corresponding GitHub run completes.

## v0.3 — prior private delivery

Added common plain/rich captions, atomic saved queue, source-draft fingerprinting, PCM temporary chunks, final AAC encoding and full output decode verification. The supplied 60-second owner report recorded 23 captions, zero unparsed captions, 1080p/30 fps, 60.000 seconds, metadata/full-decode pass and 104-second render time. These are report observations, not a controlled performance benchmark.

## Direction

The owner abandoned native CapCut UI automation for this work and selected this independent renderer. Historical native-export controller/research source is retained separately; no Z Builder code is changed.
