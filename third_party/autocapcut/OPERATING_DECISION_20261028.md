# Operating Decision — Use Original AutoCapCut v0.1.2 EXE

**Decision date:** 2026-10-28  
**Owner direction:** Use the existing third-party `AutoCapCut-0.1.2.exe` as a **standalone Windows application**. **Do not modify, replace, integrate, or repackage Z Builder** for this task.

## Scope and isolation

- Selected runtime: the exact existing third-party AutoCapCut v0.1.2 EXE; keep its installation, settings, project output and release/version identity separate from Rajudesktop products.
- `z_builder/`, `Z_BUILDER.md`, `Z_CapCut/` engine source, `capcut_independent_renderer/`, `capcut_native_export_app/` and VPS_1 **must remain unchanged** unless the owner gives a later explicit separate request.
- Do not migrate AutoCapCut features into Z Builder, create a Z Builder fork, alter Z Builder's Scene Plan workflow, or silently substitute another renderer.
- Third-party EXE/source is **not uploaded to this public GitHub repository**; retain the original via the owner's provided Drive file. GitHub stores only reference records, test notes, and independently written tooling.
- A recovered-source research archive does not grant permission to redistribute or rewrite proprietary code.

## Features visibly shown in owner's v0.1.2 screenshot

The UI is headed `TryAIToday-AutoCapCut`, shows `v0.1.2`, a `CapCut open` status, a project picker, the `Motion` area, and a `Build timeline` action. Its What's new modal states:

1. **Projects folder:** point AutoCapCut at CapCut's drafts on another drive; `Change folder` under project list.
2. **Video clip audio:** `Motion` tab has a volume slider to lower/mute video clips; background music is described as staying untouched.
3. **Edit file tab:** load a JSON file to specify transitions per cut; validation status reports `Will Apply`, `Missing`, `Skipped`, plus copy/export help.

These statements are **visible UI/product descriptions**, not independent confirmation of successful on-device runtime. Do not invent additional supported features or JSON schema. If owner supplies a working Edit file JSON example, inspect its precise schema before authoring one.

## Operational approach (original EXE, no code changes)

1. On the Windows PC, back up the target CapCut draft/project before testing; use a disposable duplicate for the first run.
2. Open the **original** AutoCapCut v0.1.2 app; set its `Projects folder` to the actual CapCut drafts directory if needed, then select the intended duplicate project.
3. If `CapCut open` is shown, close CapCut normally before `Build timeline` to avoid concurrent writes. Do not force editing of an active draft.
4. Use the EXE's own `Motion` and `Edit file` controls, with the app's own validation log. For JSON-per-cut transitions, do not assume every transition is installed: check `Will Apply` / `Missing` / `Skipped`.
5. Build the timeline using its existing button, reopen the duplicate draft in CapCut, and manually confirm footage timing, transitions, zoom, audio levels and editable project integrity.
6. Keep original project/draft and media untouched until a resulting render has been reviewed.

## Status

- **Decision recorded**: Yes.
- **Software installed on owner's PC by this GitHub change**: No.
- **App code modified, repackaged or redistributed**: No.
- **Z Builder modified**: No.
- **Windows GUI acceptance test for this workflow**: Not performed by this GitHub documentation update.
- **Audit reference**: [README.md](README.md) and [RECOVERY_FINDINGS_20261028.md](RECOVERY_FINDINGS_20261028.md).

This decision supersedes earlier **proposals to independently implement AutoCapCut-like motion/transition functionality inside Z Builder** for the current standalone AutoCapCut workflow. The historical Z Builder code and its independent use cases remain available unchanged.
