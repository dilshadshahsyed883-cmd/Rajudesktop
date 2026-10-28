# AutoCapCut — third-party reference (v0.1.2)

**Added:** 2026-10-28  
**Category:** External Windows/CapCut automation tool; **not a Rajudesktop product**  
**Status:** Installer fingerprinted and Electron ASAR application source recovered for private static inspection; runtime behavior **not verified**  
**Repository role:** Research reference for `Z_CapCut/` and `z_builder/` only. No integration or deploy is enabled.

## Source and identity

A user-provided Google Drive download named `AutoCapCut-0.1.2.exe` was available for read-only static analysis. The original binary is **not committed**, mirrored, distributed, executed, or installed. Do not publish its original Drive URL without permission. Product ownership, license, public source repository, and equivalence to independently described AutoCapCut demonstrations have **not** been established.

| Property | Observed value |
| --- | --- |
| Filename / apparent version | `AutoCapCut-0.1.2.exe` / 0.1.2 (from filename only) |
| File size | 73,231,678 bytes |
| SHA-256 | `ea0590f1a18d723792746d55260b83313b6e2feada04260effb6b31b04a99157` |
| Executable | Windows PE32, x86 (`0x014c`), GUI subsystem |
| Installer evidence | `Nullsoft` and `NSIS` embedded markers; NSIS installer as identified by `file` |
| Sections | `.text`, `.rdata`, `.data`, `.ndata`, `.rsrc` |
| Estimated data after PE sections | 73,150,270 bytes (likely packed installer payload; contents not inspected) |
| Authenticode | No certificate table recorded by this PE parser; not a complete trust assessment |
| Execution / extraction | **Not performed** |
| Source-code availability | **Recovered for private static inspection** as readable Electron modules; third-party source is **not** committed to this public repository |

**Update (28 Oct):** Read-only inspection found a valid embedded 7z archive, extracted `resources/app.asar`, and recovered 25 Electron application files with 17 JS/CJS modules passing syntax checks. See [verified recovery findings](RECOVERY_FINDINGS_20261028.md). The recovered source itself remains private; it was **not** committed or merged into Z Builder. This is not runtime validation.

A separately published [Try AI Today demonstration](https://www.youtube.com/watch?v=Mi8zOa3vFlQ) describes a similarly named AutoCap Cut workflow using time-coded images, automatic motion/transition insertion, and CapCut project editing. **It is not proven that this exact EXE is the same build as the demonstrated application.**

## Read-only analysis workflow

Python 3.10+; no third-party packages required:

```sh
python third_party/autocapcut/analyze_installer.py "/path/to/AutoCapCut-0.1.2.exe" --output report.json
python -m unittest discover -s third_party/autocapcut -p "test_*.py" -v
```

This utility never launches, extracts, or modifies the EXE. It calculates the file checksum, parses PE sections and signature *presence* metadata, and scans for a small allowlist of architecture/installer markers. It does **not** certify the software safe or recover proprietary code. Tests use synthetic PE fixtures instead of redistributing the installer. The exact observed report is in [audit_20261028.json](audit_20261028.json).

## Z Builder / Z CapCut engineering usefulness

| Target | Why examine | Actual status |
| --- | --- | --- |
| Native editable draft assembly | Ensure target/source ranges, image/video track layering, and real project import survive | Already separately covered by `z_builder/` + `Z_CapCut/` research; external EXE implementation unverified |
| Preset transitions | Discover stable identifiers and linked downloaded resources | **Needs clean A/B CapCut draft comparison**, not guessed from marketing or packed EXE |
| Still-image motions | Derive supported animation/keyframe fields, preserve editability | **Needs native CapCut fixture + round-trip rendering** |
| Resource persistence | Ensure previously downloaded effect IDs continue to resolve | Tested for a limited owner-provided effect, not all CapCut versions/effects |
| Audio/timeline timing | Voice optional; SRT / Scene Plan is authoritative | Existing Z Builder behavior must remain unchanged |
| Full effects parity / native export | Avoid mistaking an editable draft generator for a universal renderer | **Not claimed** by the installer scan |

### Guardrails

- Keep Rajudesktop `main` the source of truth; do not modify VPS_1.
- Do not copy/rehost proprietary EXE, unpacked app files, licensed effects, credentials, or other users' projects into this public repository.
- Never run an untrusted third-party binary on production, or automate elevation/permissions as a shortcut.
- If explicitly authorized local unpacking later becomes possible, first inspect extracted *file names and formats*, then isolate any source review; treat embedded artifacts as untrusted. Document whether it generates native `draft_content.json` or uses GUI actions **only after observed evidence**.
- Never change working Z Builder/CapCut code based solely on this reference; use reproducible fixture tests and guard rollback.

## Verified recovery update

Read [RECOVERY_FINDINGS_20261028.md](RECOVERY_FINDINGS_20261028.md) for the additional extraction evidence, high-level transition/keyframe/draft-write behavior and clean-room integration test plan. The original binary/source remain excluded from this public repository.
