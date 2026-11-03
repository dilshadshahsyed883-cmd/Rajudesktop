# Original Concat — Windows PC test package

**Purpose:** distribute the original, unmodified Windows x86-64 Concat editor for a basic local PC test. This is separate from every other Rajudesktop app.

- **Upstream:** https://github.com/jub0t/Concat
- **Pinned version:** v0.2.8, https://github.com/jub0t/Concat/releases/tag/v0.2.8
- **Binary:** `Concat-0.2.8-windows-x86_64-setup.exe`, straight from the upstream release
- **Integrity:** download upstream `SHA256SUMS`; enforce exact matching SHA-256, nontrivial size, and Windows PE header
- **Build method:** package/verify the upstream-produced binary on a Windows GitHub Actions runner. **This workflow does not compile source or modify Concat.**
- **Artifact:** `Concat-v0.2.8-Windows-x64` from the `Concat Original Windows EXE (verified upstream)` workflow.

## Install and test on a Windows 64-bit PC

1. Open the Rajudesktop **Actions** tab, select **Concat Original Windows EXE (verified upstream)**, then choose the newest successful run and download its artifact ZIP.
2. Extract ZIP. Run `Concat-0.2.8-windows-x86_64-setup.exe`.
3. In original Concat, create a project, import MP4/image/audio, edit on its timeline and export a 30-second MP4.
4. Check the exported MP4 in a player. Keep your original media files unchanged.

Windows SmartScreen may warn because the upstream installer is not code-signed. Only run after checking the source, version and SHA-256. Do not disable organization-managed application protections.

This is the **original full Concat editor**, not a new JSON batch-rendering UI. Its built-in automation features remain those provided by upstream.

**Licensing:** Concat is AGPL-3.0-or-later, and its bundled third-party dependencies have their own terms. Source, licenses and notices are at the upstream repository/release. Do not redistribute it under a proprietary license.

**Isolation:** no Rajudesktop application is replaced, no production deployment runs, and no credentials or user media are committed.
