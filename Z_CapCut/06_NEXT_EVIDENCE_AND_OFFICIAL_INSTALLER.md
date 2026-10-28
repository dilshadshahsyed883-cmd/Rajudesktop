# 06 — Next evidence requests, official installer sourcing, and archiving
Date: 2026-10-27

## Results and storage
- All previously supplied CapCut original ZIPs, JSON drafts, inventory CSV, screenshot and tools are stored in the **private** Google Drive folder: https://drive.google.com/drive/folders/1XmOgG1jY7_GI_UuXOC37zCLJsYbsdwdt
- Newly received `_internal.zip` (46 api-ms-win DLLs) and `icudtl(1).dat` (ICU runtime data, approximately 10 MiB) were uploaded to the same folder. Both are routine runtime support files; neither directly supplies timeline, animations or transition schemas.
- This GitHub research branch contains sanitized results; source binaries, crash dumps and identifying draft JSONs must never be committed to this **public** repository.
- The connected Google Doc `SCENE DESKTOP STUDIO — MASTER PLAN & DEVELOPMENT REGISTER — 2026-10-22` was updated in its new tab `07 — Z CapCut Research`: https://docs.google.com/document/d/1ux4Gm2N-9jC7e1xCtlLoHoRSpQ2AvZB29y4IfgPEOPk/edit

## Priority next *native sample projects* — not installation files

| Rank | Small user-created CapCut dummy sample | Purpose |
|---|---|---|
| P0 | Photo lower track covering 0–5 s; **video upper track overlapping at 1–3 s**, ideally video scaled smaller/transparency so both render simultaneously. Supply `draft_content.json` and one timeline+preview screenshot (optional `draft_meta_info.json`). | Prove actual visual z-order and track serialization. Existing 2-track example has no overlap. |
| P1 | 1920×1080 16:9 project with one image Fill-vs-Fit and a 4-s clip **trimmed to 2.5 s**. Supply small draft JSON and screenshot. | Verify canvas scale/crop and source/target timing rules. |
| P2 | Same short draft with a single MP3 audio track, plus its no-audio version. | Verify native CapCut audio schema and optional import. |
| P3 | A/B drafts changing **one feature at a time**: image animation, transition, two position/scale keyframes, color/blend adjustment. | Validate serialization of actual editable effects, avoid assuming presence from cache metadata. |

Do not ask again for `_internal`, ICU data or other system/runtime DLLs. Do not need user's full media library, personally identifying paths or crash dumps for these test cases. Use intentionally tiny throwaway local media.

## Official download attempt
Verified official desktop site: https://www.capcut.com/tools/desktop-video-editor. Download button redirects to CapCut's official `/activity/download_pc` / download guidance. An attempted direct fetch from this execution environment failed (network/DNS restriction); **no Windows installer was downloaded or installed here**. Only use CapCut's own domains and do not substitute unofficial mirrored or modified installers.

Even an official installer might be newer than the user's **9.6.0.4097** version; a fresh installer does not contain the user's cached effects, saved projects, or authenticated assets. Version-pin tests where possible.

## Development constraints
Z Builder belongs in Rajudesktop, independent from VPS_1; this `Z_CapCut` documentation is retained on its separate research branch. **Do not merge to main** by default. Generated editable CapCut projects must use copied output folders and demonstrate CapCut reopen/preview/editability before claiming support.
