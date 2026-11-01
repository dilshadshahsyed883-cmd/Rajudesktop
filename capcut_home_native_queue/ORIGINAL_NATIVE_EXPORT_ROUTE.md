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

## Confirmed false UI triggers

The two original Home `onClicked` handlers at `156377425` and `156379561` invoke `viewModel.openRecycleBinWindow()` and `viewModel.openAutoUploadWindow(...)`, respectively. Neither is a video export trigger. Never map these to `submitExport`.

The original Home draft-card QML properties include `draftId`, `strProjectPath`, `inExport`, and `exportProgress`; these fields do not alone expose an export command.

## Integration gate (not completed)

A legitimate adapter must be instantiated by a **verified in-process CapCut Qt host**, map the live Home draft identity and exact project path, demonstrate a genuine native export admission route, and verify a completed original-engine MP4 before providing `nativeBridgeVerified === true` and `submitExport(...)`.

`HomeDraftQueuePanel.qml` now refuses to start exports when `submitExport` is merely present without `nativeBridgeVerified`. The Windows QML tests simulate the host property; they do **not** prove a real in-process bridge or native MP4 output.

**Current result:** identified the actual native export component family and removed the two false button candidates. The exact Qt-to-private-C++ dispatch/ABI, original Home integration, and real MP4 acceptance test remain unverified. PR #58 must remain draft and must not ship a modified CapCut binary.
