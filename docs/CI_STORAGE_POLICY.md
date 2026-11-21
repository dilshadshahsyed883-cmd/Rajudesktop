# CI and Actions storage

## Implemented scope

Upload steps retain PR artifacts for 3 days and other artifacts for 7 days. Z Builder V6.3 and Short Studio run their existing source regressions on PRs and reserve runtime bundling, EXE packaging and frozen smoke checks for push/manual builds. Other app pipelines retain their existing packaging triggers until their combined tests can be separated safely. Manual Scene Desktop Studio packages are excluded from source-run cancellation.

## Artifact lifecycle

These rules apply to newly uploaded artifacts after the workflow change reaches the branch used by the run. They do not delete or extend existing artifacts, GitHub Releases, branches, container images or live data. Retention is not a storage quota: frequent builds can still accumulate substantial storage within the window.

Before an active candidate expires, preserve its exact package, full source SHA, checksum and acceptance notes in a named prerelease. Keep current and previous verified releases available for rollback. Do not rely on an expiring development artifact as the only rollback copy. Stable downloads should come from a verified versioned release, never a guessed “latest successful run.”

## Verification and limits

Review the source tests separately from Windows frozen-binary or real GPU acceptance. The maintenance PR changes CI scheduling/retention only; it does not certify hardware acceptance or alter deployed services. Merging workflow changes may trigger the existing app-specific checks or publication behavior; inspect the exact event and path filters before merge.
