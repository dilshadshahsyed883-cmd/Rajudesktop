# Project Image Downloader — repository record

Snapshot: version 1.1.1, saved 28 October 2026.

Includes complete Chrome extension source, sample keyword CSV, installation/update
guide, tests with synthetic image fixtures, validation notes, and the exact delivered ZIP
with SHA-256 checksum. No user photographs, browser sessions, tokens or private inputs
are included. This app is independent from the repository's Windows editors.

Confirmed scope: project-based multi-keyword image collection, independent query/name/qty,
direct search URLs without search-box typing, per-keyword target counts, shared-prefix
numbering, compact tabs, original-image Auto Download with replenishment and durable queue.
Getty searches use family=editorial and preserve the complete percent-encoded phrase.

Validation: 28 automated core/collector/worker tests pass using simulated Chrome APIs.
Current live-browser adapter and UI validation remain pending. Getty previews remain
discovery-only; licensed Getty original auto-download is not implemented.

Latest feedback: user wants a simpler experience comparable to Imageye 7.4.6; current
custom extension experience is unsatisfactory. That feedback is recorded, and no Imageye
source has been copied or analyzed in this snapshot. Further UX changes remain pending.

Run tests from this folder with npm test (Node 22+; no dependency install required).
Load extension/ as an unpacked desktop Chrome extension. To update an existing install,
replace its files in the same folder and Reload; do not uninstall and lose stored projects.
