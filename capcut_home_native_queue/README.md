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

## Native adapter contract — **not yet implemented**

The verified CapCut 9.7 `VECreator.dll` contains `HomePageLocalDraftViewModel`, `draftId`, `strProjectPath`, `inExport` and `exportProgress`. The private `BackEndExportImpl::pushTask`, `exportNextTask`, `clickDraftFromHomeView` are embedded symbol strings but **not exported PE methods**. The same DLL exposes Qt `qml_register_types_HomeScene`. None of this establishes the signature or object identity for a callable enqueue method.

The **actual** in-process Qt adapter must own:

1. Verified Home draft identification and mapping into `panel.drafts` (no guessed draft ID).
2. `bool submitExport(draftId, strProjectPath, key)`, implemented only through the verified **existing native CapCut background-export API**, with return `true` only if the host actually admits the job.
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
