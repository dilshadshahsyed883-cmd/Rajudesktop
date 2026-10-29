# Test scope — 29 October 2026

| Check | Result / evidence |
|---|---|
| Upstream source reuse | Exact byte hashes checked against pinned MIT upstream commit |
| Windows launcher and dependencies | Dedicated Windows workflow; see WINDOWS_SMOKE.json in built ZIP |
| Original version/windows/help and inspector commands | Dedicated Windows workflow, no installed CapCut required |
| MP4/audio and full decode verification | Automated tests with disposable generated media; not a CapCut export |
| Changed project / unresolved batch / no-overwrite | Automated tests with disposable fixtures |
| Real Home project selection / export dialog / actual MP4 export | **NOT TESTED** — no suitable interactive CapCut session available |
| Owner CapCut 9.6.0.4097 acceptance | **NOT TESTED**, input blocked |
| Unexpected CapCut dialogs and overnight sequential GUI reliability | **NOT TESTED**, no autonomous agent bundled |

No real CapCut export PASS is inferred from CI or upstream's author demonstration.
