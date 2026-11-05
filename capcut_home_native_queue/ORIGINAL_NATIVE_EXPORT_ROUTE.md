# CapCut 9.7.0.4153 original-native export route: authenticated evidence

## Provenance and safety

On 2026-11-01 the owner's **existing private Drive archive** parts 005 and 006 were fetched through an authenticated connected Google Drive session to a temporary Linux analysis workspace. The original ZIP entry `9.7.0.4153/VECreator.dll` was extracted **read-only** and verified against the previously established exact binary fingerprint:

- Original DLL byte length: `281017256`
- SHA-256: `967fd06e60a1c68c055278cf6bb1ecd1bb078277d58167fcf6b4cfa2a1a27cf9`
- No binary or original project/draft was modified, committed, or distributed.
- Offset observations below refer to raw byte offsets within that **exact** unmodified DLL, not callable addresses.

## Confirmed strings in the genuine library

| Raw DLL offset | Observed native string | Correct interpretation |
| --- | --- | --- |
| `211744686` | `ExportPanelEntryImpl::clickBackgroudExport` | Private C++ export-panel entry log marker; not a proven QML invokable |
| `211744782` | `clickBackgroudExport in homepage` | Strong evidence of a Home-originated background export path, **not proof of a callable ABI** |
| `212777467` | `export_ns::BackEndExportImpl::pushTask` | Private background task admission log marker |
| `212780659` | `export_ns::BackEndExportImpl::exportNextTask` | Private serialized renderer scheduler log marker |
| `212781395` | `export_ns::BackEndExportImpl::clickDraftFromHomeView` | Private Home draft export-related marker |

The original library also contains C++ RTTI for `export_ns::IExportPanelEntry` and `ExportPanelEntryImpl`. This suggests a dependency-injection/service boundary and is **not** a Qt meta-object API. Earlier fully parsed PE export tables showed none of the named `BackEndExportImpl` methods as public exports.

## Newly recovered original Qt6 meta-object method (2026-11-01)

On a temporary server-side copy of the owner's existing **SHA-256 verified**
CapCut 9.7.0.4153 `VECreator.dll`, the original Qt6 moc data were
decoded directly, without running or modifying CapCut:

- Qt meta-object: `ExportCompileBottomViewModel`
- Static UTF-8 string table at original **file offset** `212657504`
- Qt MOC uint32 metadata table at original **file offset** `212658112`
- MOC revision **10**, class method count **18**, signal count **10**
- Method `clickBackgroudExport`: public access flag `0x02`, **zero
  arguments**, Qt return metatype **43 (void)**, **not a signal**
- Neighboring invokable methods: `pauseExport`, `resumeExport`, `cancel`
- `ExportPanelEntryImpl::clickBackgroudExport` and
  `BackEndExportImpl::pushTask` remain private C++ implementations/log
  markers, **not public PE exports or automatically callable QML objects**.

**Meaning:** CapCut's original **Export Compile Bottom** Qt view model
exposes an actual zero-argument public invokable method named
`clickBackgroudExport()`. This is more specific than log strings: its Qt
call signature is recorded. However, this object belongs to the **Export
panel**; the research has **not** located a live instance in the running
original CapCut process, shown that a Home draft's `draftId` and
`strProjectPath` can be mapped to the export panel, or established
programmatic queue admission for an arbitrary ready draft.

Do not implement `submitExport(draftId, path, key)` by blindly calling
this zero-argument method: without a proven live model and current-draft
binding it could export the **wrong project**, be a no-op, or change
the user's session. The non-administered CI cannot invoke CapCut's live
in-process QObject, and the manual MP4 test did not establish this link.

The source-only reproducible analyzer is
`inspect_original_export_moc.py`; it refuses **any version/hash mismatch**
and has synthetic signature-regression tests. No proprietary binary or user
report has been committed to GitHub. This is offline evidence, **not a
working patched CapCut EXE or batch renderer**.

## Export-Home controller Qt method (read-only original-DLL verification)

The owner's unchanged, SHA-256 verified `VECreator.dll` also has a
**different** Qt6 moc class, `ExportHomeBottomViewModel`, which was not
previously in the PR's version-locked checks:

- Original file string-table offset: `212600152`
- Original file Qt metadata offset: `212601744` (revision 10)
- 23 methods, 18 signals
- `compileClick()`: **public, zero arguments, void return** (moc flags
  `0x02`, return metatype `43`)
- `cancelClick()` is another public void action.
- `videoEnhanceCompileClick()` is public and returns `bool`, but this
  is a separate enhancement action and does not prove batch admission.

These are actual Qt meta-object signatures from the original 9.7.0.4153
binary, *not* vendor-documented extension APIs or call addresses.
`ExportHomeBottomViewModel.compileClick()` appears to be an export-panel
compile action by its registered name, **but it is not confirmed to
dispatch a particular Home draft**. It accepts neither `draftId` nor
`strProjectPath` and cannot replace the missing live original-object
binding, draft ownership verification, or original scheduler task
admission signal.

The same version-locked offline parser
`inspect_original_export_moc.py` verifies both original export-panel
classes; it rejects any changed DLL SHA-256/size or incompatible Qt moc
signatures. Do not equate two identified invokable methods with an
operational extension/injection interface. No original CapCut files,
installed process or user drafts were changed in this verification.

## Confirmed false UI triggers

The two original Home `onClicked` handlers at `156377425` and `156379561` invoke `viewModel.openRecycleBinWindow()` and `viewModel.openAutoUploadWindow(...)`, respectively. Neither is a video export trigger. Never map these to `submitExport`.

The original Home draft-card QML properties include `draftId`, `strProjectPath`, `inExport`, and `exportProgress`; these fields do not alone expose an export command.

## Integration gate (not completed)

A legitimate adapter must be instantiated by a **verified in-process CapCut Qt host**, map the live Home draft identity and exact project path, demonstrate a genuine native export admission route, and verify a completed original-engine MP4 before providing `nativeBridgeVerified === true` and `submitExport(...)`.

`HomeDraftQueuePanel.qml` now refuses to start exports when `submitExport` is merely present without `nativeBridgeVerified`. The Windows QML tests simulate the host property; they do **not** prove a real in-process bridge or native MP4 output.

**Current result:** identified the actual native export component family and removed the two false button candidates. The exact Qt-to-private-C++ dispatch/ABI, original Home integration, and real MP4 acceptance test remain unverified. PR #58 must remain draft and must not ship a modified CapCut binary.
