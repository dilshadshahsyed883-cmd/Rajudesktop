# CapCut 9.7 native Home draft queue — QML integration candidate

**User's intended result:** original CapCut 9.7.0.4153 Home view lists ready drafts with checkboxes, **Export selected in queue**, and sequential MP4 exports using the original CapCut render engine.

This folder is the **actual QML Home queue implementation**, not a separate GUI macro, not FFmpeg, and not a modified installer. **It is NOT yet installed/working inside CapCut.** It is deliberately isolated in source form until a real Qt Home adapter is proven on the owner's PC. No guessed native DLL method calls.

## Implemented

- Multi-select original draft objects (`draftId`, `strProjectPath`, `strTitle`), duplicate-key protection, and selected-only queue.
- Strictly one active render admission at a time. The next selected draft only starts after the host emits a **verified** MP4 completion event including output path and 64-digit SHA-256.
- Native admission must return `true`; errors/ambiguous status stop the queue and leave remaining drafts pending. No blind retry or manual UI automation.
- Stop-after-current, resume remaining, status and progress callbacks; accidental duplicate completion and foreign result signals are ignored.
- `snapshotChanged(snapshot)` emitted for host persistence. Persistence requires native host wiring; nothing here writes draft, timeline, media, preferences or original CapCut files.
- No external video render dependency. UI is disabled unless `nativeAdapter.submitExport` is genuinely provided.

## Durable queue recovery added (2026-11-01)

The QML panel now exposes `snapshot()` with a versioned JSON-compatible journal and `restoreSnapshot(jsonString)`. A real host must **persist each `snapshotChanged` value atomically** outside the original CapCut install, and supply saved JSON on startup. The view never silently auto-starts jobs from an old journal.

- Previously active draft becomes **Review**, and is **not** re-enqueued, because CapCut may have finished export while the UI was restarting.
- Previously queued drafts remain ordered and deduplicated. They restore **paused** and require explicit Resume.
- Previously completed outputs become **Review** on restore until the host checks actual MP4 existence/integrity (the view cannot do native file verification).
- Unknown/invalid draft keys are dropped; malformed or wrong-version journal is rejected.
- Recovery requiring review blocks Resume until explicit user acknowledgment. Reviewed drafts cannot be blindly selected for duplicate export.
- Unit tests use the actual Windows Qt QML engine; **no original CapCut MP4 has been rendered or installed by this component**.

## Original Home export callsite research access boundary

A guarded Windows Actions research job attempted to download the owner's **existing** original ZIP parts 005 and 006 from linked Drive files, reconstruct `VECreator.dll`, validate its exact SHA256, and identify real QML click handlers. **Google Drive did not permit anonymous access**, and the run reported `SOURCE_LINK_NOT_PUBLIC_OR_DOWNLOAD_FAILED`. No share permissions were changed and no original DLL/ZIP was committed or uploaded. The workflow is now manual-only to avoid repeated failed downloads. This does **not** mean the original files are invalid. The source of a callable in-process CapCut Home exporter remains unavailable outside the owner's authenticated Windows CapCut installation.

## Authenticated original-DLL export path (2026-11-01)

Using the owner's authenticated private Drive archive (parts 005 and 006), the exact original `VECreator.dll` was recovered, SHA-256 verified, and inspected without changing any executable. Its internal strings identify `ExportPanelEntryImpl::clickBackgroudExport` (including the explicit Home-origin log), `BackEndExportImpl::pushTask`, `exportNextTask`, and `clickDraftFromHomeView`. These identify the relevant private-native component family but **do not reveal a callable Qt/QML ABI**. See [ORIGINAL_NATIVE_EXPORT_ROUTE.md](ORIGINAL_NATIVE_EXPORT_ROUTE.md) for precise offsets, evidence and boundaries.

The Home queue UI now requires `nativeAdapter.nativeBridgeVerified === true` **and** callable `submitExport(...)`. The first flag can only be supplied by a trusted, genuine in-process host after verification; exposing a method name alone must not enable the export UI. The synthetic Qt tests supply this field strictly as mock behavior and do not demonstrate CapCut integration.

## Native MP4 completion guard (source available; host integration pending)

`native_output_validation.py` supplies a **read-only** acceptance gate for a prospective original-engine render, not a renderer or a CapCut importer. A trusted in-process CapCut host must first establish the actual original export API and draft/output binding, then:

1. Call `begin_export(key, draftId, projectPath, intendedMp4Path)` before admitting the exact native task. Existing files and ambiguous/relative targets are rejected. Keep the returned ticket **only if original-engine admission is independently confirmed**.
2. On a native export-completed callback, call `verify_completed(ticket, reportedMp4Path)`. This checks exact target, file freshness, stability, a valid non-empty video stream, duration/resolution via read-only `ffprobe`, and SHA-256; it never renders anything.
3. Emit `exportVerified(key, outputPath, sha256)` to the QML queue **only** after verification and the in-process CapCut native admission evidence both succeed. Otherwise emit `exportFailed`, leaving remaining drafts paused for review.

`ffprobe` is a validation dependency only; this is **not** an FFmpeg or macro-based export engine. Eleven isolated Python tests cover success and fail-closed paths. A separate locally generated one-second MP4 passed the real `ffprobe` path, **but it was not exported with CapCut**. Windows QML CI runs the unit tests; no Windows CI job currently launches the original CapCut engine.

## Native adapter contract — **not yet implemented**

The verified CapCut 9.7 `VECreator.dll` contains `HomePageLocalDraftViewModel`, `draftId`, `strProjectPath`, `inExport` and `exportProgress`. The private `BackEndExportImpl::pushTask`, `exportNextTask`, `clickDraftFromHomeView` are embedded symbol strings but **not exported PE methods**. The same DLL exposes Qt `qml_register_types_HomeScene`. None of this establishes the signature or object identity for a callable enqueue method.

The **actual** in-process Qt adapter must own:

1. Verified Home draft identification and mapping into `panel.drafts` (no guessed draft ID).
2. A read-only Qt `nativeBridgeVerified` property, true only **after live in-process binding verification**, plus `bool submitExport(draftId, strProjectPath, key)` implemented only through the verified **existing native CapCut background-export API**. It must return `true` only after actual original-engine admission.
3. `exportProgress(key, percent)`, `exportFailed(key, reason)`, and `exportVerified(key, outputPath, sha256)` signals. **Do not** emit verified on 100% progress alone; verify native final MP4 and source linkage first.
4. Persist queue snapshots and reconcile an interrupted render in Review before any manual replay.
5. Preserve current CapCut project settings, effects, audio, transitions, and export settings without overriding them.

The app must not call arbitrary addresses in `VECreator.dll`, patch signed DLLs in place, or use Mouse/Keyboard automation. A safe deployment requires isolated-copy Windows acceptance proving one real MP4 render through the original engine and playback parity.

## Automated proof and limits

`tests/test_qml_runtime.py` loads the **real** QML component in a Windows Qt6/PySide6 engine (offscreen) and uses a purpose-built fake native adapter to test:

- No adapter => no native dispatch.
- Two drafts => only first initially admitted.
- Bad/foreign MP4 verification => queue halts; no further output.
- Valid verified event => second draft starts.
- Adapter refusal => queue halts.
- Stop-after-current => next draft waits for Resume.

Workflow: [CapCut Home QML queue — native-bound UI tests](../.github/workflows/capcut-home-qml-queue-windows.yml).

**This CI does not launch CapCut itself**, does not expose a CapCut background-render adapter and does not prove any MP4 export. Until those conditions are established, the original CapCut installation and user's drafts remain untouched. The existing [PR #58](https://github.com/dilshadshahsyed883-cmd/Rajudesktop/pull/58) stays draft.
