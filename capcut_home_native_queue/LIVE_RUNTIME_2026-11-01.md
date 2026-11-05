# Original CapCut 9.7 live Qt bridge feasibility — owner report

**Evidence date:** 2026-11-01 15:21:30 UTC. The user ran the repo's
`CapCut_Live_Bridge_Check.ps1` on Windows 10 with the original running
CapCut **9.7.0.4153**. The private raw JSON report is NOT committed.

## Observed by owner-side read-only script

- Status: `NO_LIVE_QML_DEBUG_ENTRYPOINT_OBSERVED`.
- Eight running `CapCut.exe` processes matched the exact version suffix.
- `Qt6Qml.dll`, `Qt6Quick.dll` and original editing engine DLLs
  appeared among loaded modules of the original process.
- Zero `-qmljsdebugger` startup arguments, zero matching local QML
  debugger listener-port candidates.
- One process listened on loopback TCP port **7263**. This is **not**
  identified as a Qt QML debugger server. The test deliberately never
  connects to that or any other port.
- Original installation contains `qmldbg_*.dll` tooling files.
  Bundling Qt debugging plugins alone does not establish that the vendor
  build activates a debug endpoint or permits custom QML loading.
- Report asserts no original install/draft changes, injection, debugger
  connection or external network calls.

## Classification, limits and engineering decision

The report supports the narrow conclusion that no **usable live QML
debugging entrypoint was observed**. It does NOT prove that CapCut
cannot be extended by any means, or that port 7263 is safe/useful.
It does NOT prove the original `ExportCompileBottomViewModel` object,
a supported in-process adapter, admitted scheduler task, or unattended
MP4 render.

Current original-CapCut constraints for the requested **Home checkboxes +
native serial batch export**:
1. Existing QML queue logic and PySide6 adapter are source-only.
2. A separate Python process has no ability to dereference a native Qt
   `QObject` owned by the original CapCut process.
3. The exact original Qt export methods identified offline are
   zero-argument `void` methods, not a public draft-bound export API.
4. The live process exposes no observed documented/debug bridge
   enabling the trusted host to invoke them.
5. The successful owner manual GUI MP4 proves CapCut can render, not
   programmatic task admission.

**Decision:** Keep `nativeBridgeVerified=false`, Home queue export
disabled, and PR #58 **Draft/unmerged**. Do not repeat the same scanner,
guess a DLL address, inject code, open a QML debugger port, claim the
loopback listener is an export API, edit/replace signed CapCut binaries,
or ship a fake modified EXE.

`live_runtime_acceptance.py` and its sanitized fixture tests ensure
this report cannot accidentally mark the batch feature as complete.
Any real release needs a trusted, safely verifiable original-CapCut
in-process extension route plus one unattended original-engine MP4.
If none is available, the native-only no-macro/no-external-renderer
request remains technically blocked rather than complete.
