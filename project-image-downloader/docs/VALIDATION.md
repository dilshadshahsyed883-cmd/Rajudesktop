# Validation record — 27 October 2026

Automated logic / worker tests use controlled fixtures and simulated Chrome APIs.
They do not prove real Chrome behavior or current remote website compatibility.

## Executed

- JavaScript syntax checks: extension worker, panel and collector.
- Node core + worker suite: see `test-results.txt` in this package.
- Format detection rejects HTML even when the URL ends with `.png`.
- Exact downloaded bytes match the validated bytes, rather than a second remote request.
- Same-prefix filename counters continue across rows and durable state.
- Chrome completion is required before successful counts change.
- Missed completion events reconcile on a new worker instance.
- Pause aborts validation, resume restarts it; cancel preserves completed files.
- HTTP failures, small images and exact duplicates remain shortages.
- Getty preview URLs cannot be queued.
- Collector DOM fixtures cover Google links / preview originals, Getty discovery,
  JSON-LD and generic image pages. These are synthetic, not live-site snapshots.

## Remaining desktop Chrome acceptance

1. Load the unmodified `extension/` folder in current stable Chrome; inspect the
   service-worker console and verify there are no install or CSP errors.
2. Open the toolbar side panel and the full dashboard; check widths around 390px
   and 1440px, keyboard navigation and the new-project dialog.
3. Grant and deny optional origins; verify denial does not start collection or downloads.
4. Import the sample CSV; verify 4 rows / target 23, edit, reorder and export/reimport.
5. Open Google searches from all rows. Verify no search-box typing occurs. Collect
   search links and then a selected image preview. Compare the actual original URLs.
6. Open Getty fallback and verify previews show a licensing label and cannot be queued.
7. Choose an original you are authorized to download; check actual on-disk dimensions,
   file signature, extension and filename. Check a non-JPG image keeps its own format.
8. Interrupt an in-progress download, pause/resume, close the panel and restart Chrome.
   Reopen the project and verify counts and actual saved files match, without duplicates.
9. Pre-create a same-named image and download; confirm Chrome creates a unique name
   and the source CSV records Chrome's actual path. Nothing is silently overwritten.
10. Verify source failures, unavailable originals and insufficient candidates display
    a shortage rather than complete status. Test image server redirects and permission
    differences for the redirected origin.
11. Reuse an image under a different URL and confirm identical bytes are rejected.
12. Export summary / source reports; open the files and confirm counts and source URLs.

Browser execution was unavailable in this build environment; these steps are pending.

## V1.1 update

28 automated tests pass, including Auto Download failure replacement, exact-duplicate
replacement, completion/target caps, stop behavior, Getty shortage reporting, active
source-page collection and worker-restart recovery. Live Chrome validation remains
pending. Check the five tabs at narrow/wide panel widths; ensure Download/Auto stay
above the gallery; verify new loaded page originals feed Auto; verify the target cap
and that reloading the SAME extension folder preserves existing projects.
