# CapCut 9.7 Home queue — native resource investigation

**Scope:** Direct Home page integration, not a separate exporter or a macro. This is a **read-only binary probe**, *not* a modified/working CapCut EXE.

## Evidence from owner's original CapCut 9.7.0.4153 archive

Recovered the complete ZIP central directory using genuine Drive part 6 (all 6,061 entries), and separately extracted original binaries from Drive parts 1, 5 and 6. Archive was previously SHA-256/CRC verified in [PR #57](https://github.com/dilshadshahsyed883-cmd/Rajudesktop/pull/57). Binaries are **not** committed.

| Original binary | Size | SHA-256 |
| --- | ---: | --- |
| `CapCut.exe` | 90,536 B | `fbc3ef1624351a0ac94795c6f7d664e286f3f4074ce0844cfb912515e618f92b` |
| `cccreator.dll` | 158,644,136 B | `216245151a6dee4b350b7b4f45c6076f8ab7cb8891226b4ced4d9c53094d41a4` |
| `VECreator.dll` | 281,017,256 B | `967fd06e60a1c68c055278cf6bb1ecd1bb078277d58167fcf6b4cfa2a1a27cf9` |
| `videoeditor.dll` | 72,971,176 B | `592b5e03c1676e17d43665a433094120003a2be21d0e1951987f7aa829fb369a` |

The small `CapCut.exe` is not where the Home draft-card UI source lives. In `VECreator.dll`, actual embedded QML contains `HomePageLocalDraftViewModel`, `draftId`, `strProjectPath`, and `HomePageCommonButton`. This supports targeting HomeScene resources rather than editing the launcher alone.

**Most important discovery:** the same DLL contains native background-export service symbols `BackEndExportImpl::pushTask`, `exportNextTask`, `clickDraftFromHomeView`, as well as logging that `exportNextTask` can export by **draft path**. The binary also contains `clickBackgroudExport in homepage`. Thus there is a **separate native background export route** worth investigating without relying on the previously failing `lyra-cli` ProjectAdapter. `videoeditor.dll` also contains `ExportService::batchExportStart`, but **this may refer to multi-clip export within a draft; do not claim it exports multiple projects**.

## Implementation route and strict limits

- Proposed UI: On existing Home project cards, allow selecting multiple finished drafts; keep the existing native single-project editor and original render/export settings untouched.
- Proposed action: `Export Selected in Queue` should enqueue selected **verified** draft paths through CapCut's existing `BGExportMgr` scheduler, not via mouse/keyboard macros or an independent renderer.
- **Not yet proven:** callable QML-to-background-export bridge, acceptable function signatures, use of saved export settings, clean sequential completion across different drafts, module signature/load implications. Static strings cannot establish a runnable API.
- Never patch installed signed DLLs in place, modify owner drafts, or distribute copyrighted CapCut binaries. Test an isolated local copy with explicit fingerprint and crash recovery only after proving the runtime interface.

## Read-only Windows probe

Run on installed version 9.7.0.4153:

```powershell
CapCut_Home_Native_Probe.exe --json "$env:USERPROFILE\Desktop\capcut-home-probe.json"
```

The EXE calculates **exact source DLL hashes** and checks QML / background-export markers without launching CapCut, editing drafts, changing configuration, or touching installed binaries. Passing means **only** `NATIVE_HOME_EXPORT_SYMBOLS_FOUND`, not that a native queue patch is usable.

Local Python usage: `python -m capcut_home_native_probe.probe --root "C:\path\to\9.7.0.4153"`; `python -m unittest discover -s capcut_home_native_probe/tests -v`.

The Windows workflow packages the standalone read-only probe, synthetic self-test and checksum. Future Home UI patch work must be separate and must pass a real Windows CapCut render test before claiming success.