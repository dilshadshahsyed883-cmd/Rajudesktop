# Project Image Downloader — V1.1

A local-first Chrome Manifest V3 extension for video-project image collection.
Load `extension/` as an unpacked extension in desktop Chrome 120 or later.
No build step, npm dependencies, backend, Python or EXE is needed to use it.
See `INSTALL_FIRST.txt` for the installation and Roman Urdu usage guide.

## Included

- Multiple saved projects, unique stable output folders and full dashboard / side panel.
- Independent search query, filename prefix and requested quantity per keyword.
- CSV / TSV paste and file import, CSV export, row reorder, copy and delete.
- Project and row source preferences; direct Google Images / Getty search links.
- Explicit collection from the active page, original-link detection, gallery review,
  quality filters, assisted selection and manually supplied original URLs.
- Exact URL deduplication plus SHA-256 comparison of fetched image bytes.
- Byte signature detection and actual decoded dimensions before a download starts.
- Two concurrent workers, pause/resume/cancel/retry, real Chrome completion counts
  and download byte polling; durable state and download reconciliation on worker wake.
- Monotonic shared-prefix numbering, Windows filename sanitization and Chrome
  `uniquify` collision handling. PNG/JPEG/GIF/WebP/AVIF format is preserved.
- TXT summary, CSV attribution / status report, keyword export and JSON record export.

## Practical limits

This is an initial test build. Automated core and worker tests run with simulated
Chrome APIs, durable storage, network responses and image decoding. No installed
Chrome executable was available in the build environment; the browser download was
blocked. Live extension loading, side-panel behavior, permission prompts and current
Google/Getty page layouts remain unverified. Do not describe this build as browser
certified or production validated.

Google's displayed thumbnails do not always expose the original. Open a result's
preview, collect again, or add an original image URL. Collection examines the active
document's links, data attributes, image elements and JSON-LD. It does not evaluate
page JavaScript, type search queries, automate scrolling or bypass access controls.
Google internal JavaScript payloads, shadow roots and cross-origin frames are not
parsed. There is no unrestricted unattended bulk search. Getty previews are shown
for discovery and deliberately cannot enter the download queue. Obtain licensed
originals using Getty's own download flow.

Auto-selection uses known dimensions and original URLs. Unknown dimensions can be
selected manually; every download still must pass actual decoded dimensions. SHA-256
detects exact files, not visually similar or re-encoded photos. A duplicate leaves a
shortage for the user to fill with a distinct photo. Failed/cancelled URLs are retried explicitly. Auto mode tries a different untried
original after a failure/duplicate; it never loops against the same failed URL.

Images are fetched without credentials and with a 20-second timeout / 20 MiB cap;
servers requiring login or hotlink headers may reject them. The exact validated bytes
are passed to Chrome's Downloads API as an image data URL. This avoids a second remote
response silently replacing the checked image with HTML or different bytes. Chrome
policies, disk space, Safe Browsing and save-location settings remain in control.

Arbitrary silent filesystem destinations are not supported. Filenames are relative
to Chrome's configured Downloads directory. A short project ID separates projects
with the same name; renaming the project label preserves its existing output folder.
Changing subfolder settings affects new files. Failed dispatches can leave numbering
gaps. Repeated report exports receive collision suffixes; existing files are retained.

Projects stay inside the current Chrome profile. The JSON export is a record, not
an importable backup in this version. Uninstalling can remove extension storage.
Downloaded files are never removed by project cancellation/deletion.

## Architecture and state

`panel.js` → serialized `worker.js` messages → IndexedDB root state (`db.js`).
Chrome local storage only remembers the last active project. The worker owns state;
the panel never rewrites queue state. Every lifecycle transition is durably stored.

Queue: pending → validating → dispatching → downloading → complete.
Errors become failed; exact duplicates become duplicate; cancellation becomes
cancelled. Pausing validation returns it to pending. Dispatch reservations are saved
before calling Chrome. On restart, download IDs are reconciled against Chrome; an
interrupted dispatch without an ID is matched conservatively by filename/time or
flagged for review. Chrome completion, rather than an API call's return, drives counts.
Cancelled jobs are rechecked for a late completion event to avoid hiding saved files.

The script collector runs on explicit Collect or user-enabled Auto Download. Auto
collection reads the linked tab about every four seconds with the panel open, or on
the 30-second recovery alarm otherwise. It does not type, click results or scroll. Site access is optional
until the user starts search/collection/downloading. Broad HTTP(S) permission enables
images hosted on independent origins and is requested by the extension's UI. There
are no analytics, remote code, API keys or external services. Image previews load
from original sites, so their servers receive normal image requests.

## Tests

Node.js 22+:

```sh
npm test
```

The suite uses the Node built-in test runner and VM modules; no dependencies to install.
Synthetic PNG fixtures are generated test assets, not downloaded photographs. Tests
cover CSV, URL construction, filename safety, numbering, counts, exact byte validation,
deduplication, quality rejection, permission gating for Getty previews, pause/cancel,
retry, atomic edits, source reports and recovery with missed completion events.
See `docs/VALIDATION.md` for the remaining desktop-browser acceptance checklist.

## Official API references

- https://developer.chrome.com/docs/extensions/reference/api/sidePanel
- https://developer.chrome.com/docs/extensions/reference/api/downloads
- https://developer.chrome.com/docs/extensions/reference/api/permissions
- https://developer.chrome.com/docs/extensions/reference/api/scripting
- https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle


## V1.1 — Compact tabs and Auto Download

Keywords, Images, Queue, Settings and Files are separate tabs. The last tab is remembered.
Download controls sit above the gallery; the gallery scrolls within the available viewport.

Auto workflow:
1. Keywords: import/edit rows and Save changes.
2. Images: choose a keyword and source, then Open search.
3. Browse the page, open previews or scroll to load images.
4. Tick usage permission above the gallery, then press Auto Download.
5. Available originals are collected, validated and downloaded up to the keyword target.
6. A failure/duplicate causes the next untried original to be attempted. Unknown image
   dimensions are checked against decoded bytes before saving.
7. At the successful target Auto stops. With too few originals it reports the shortage
   and continues collecting newly loaded page originals while enabled.
8. Stop Auto cancels unfinished automatic work for this keyword. Queue offers project
   Pause/Resume/Cancel. Completed files remain. Auto intent persists across worker restarts.

Auto is enabled per keyword. It does not launch unattended multi-keyword searches.
Getty previews remain discovery-only and cannot be queued. Counts now distinguish
originals, selected images and Getty previews. The full dashboard can collect from
the linked source tab even while the dashboard tab itself is focused.

Update: replace files inside the SAME previously loaded extension folder, then Reload
in chrome://extensions. Do not uninstall or change the extension installation folder
if you want to retain existing project storage.

28 automated tests pass. Live browser UI and current Google/Getty page end-to-end
validation remain pending.

## V1.1.1 — Getty Editorial search

All Getty search buttons now generate the user-specified Editorial route:
`https://www.gettyimages.com/search/2/image?family=editorial&phrase=KEYWORD&sort=mostpopular`.
The actual search query is percent-encoded in `phrase`; filename prefixes remain independent.
Existing `getty` source settings and CSV values are compatible and now mean Editorial.
Choose Getty Editorial in the Images source dropdown or use the Getty Editorial button
in More controls. Saved Google-only source settings remain as configured.
Editorial filters do not alter the existing preview-only download handling.
Live verification of this Getty page was blocked by the web retrieval environment.
