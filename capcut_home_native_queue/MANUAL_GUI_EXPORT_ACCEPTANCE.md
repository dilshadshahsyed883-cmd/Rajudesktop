# Original CapCut 9.7 manual-GUI export acceptance — 2026-11-01

## Report acceptance

The owner supplied a Windows JSON report whose `evidence_type` is
`CAPCUT_ORIGINAL_GUI_MANUAL_ONE_EXPORT` and result is
`MP4_FILE_VALIDATED`. The source report is deliberately NOT committed:
it contains a private user-profile path and unique rendered-file identifier.

**Observed in the user-supplied report** (not independent native-process tracing):

- Requested and running CapCut: **9.7.0.4153**, with 8 observed CapCut.exe
  processes before and after the manual test.
- Export initiated by a human using the **original CapCut GUI**.
- Reported output size: **27,671,982 bytes**; duration **15 seconds**;
  dimensions **1530 × 1080**.
- MP4 `ftyp`, `moov`, `mdat` atoms detected; `ffprobe` available,
  and `ffprobe.passed == true`; SHA-256 format/value recorded in the
  owner's private report (not reproduced here).
- Creation timestamp falls within the report's roughly 69-second
  observation interval.
- Script reports no original CapCut modifications and no external upload.
- Explicitly `native_qt_bridge_verified == false`.

**Classification:** `MANUAL_GUI_MP4_EVIDENCE_ACCEPTED`.
This completes the **one-manual-GUI-export** milestone. It does **not**
verify private `BackEndExportImpl` ABI, Home QML injection, programmatic
enqueue, multiple-draft automation, output-provenance attestation, or a
modified CapCut.exe.

## Executable fail-closed acceptance logic

`manual_export_evidence.py` validates the report shape, exact executable
version, time ordering, destination containment, duration/dimensions,
SHA-256 format, MP4 atoms, ffprobe status, and unchanged-original-script
flags. It always returns
`native_qt_bridge_verified=False` and
`automatic_batch_export_verified=False`, regardless of the manual MP4
result. Its synthetic regression tests use a sanitized Windows username
and a dummy hash; no original report/media is committed.

## Remaining unproven integration boundary

A genuine automated native export requires a *verified original CapCut
in-process* Qt/Home binding, **not** arbitrary DLL symbol offsets,
GetProcAddress guesses, a synthetic Qt host or manual mouse/keyboard macro.

Next experimental gate: on an isolated Windows CapCut 9.7 runtime, locate
the actual registered, callable Home export interface; link its live draft
identity and admitted native task to a real render completion callback;
produce one MP4 **without manually pressing Export**. Confirm the resulting
file through `native_output_validation.py` and report private bridge
evidence before enabling the multi-select serial queue.

Do not merge PR #58 or distribute a modified CapCut binary until that
gate is genuinely satisfied. Keep user drafts and original installation
untouched throughout.
