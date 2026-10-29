# CapCut Windows Automation — Deep Online Evidence (29 October 2026)

**Scope:** Public online evidence and engineering comparison only. No application code, Windows installation, CapCut project, or render was run or modified in this research pass.
**Local target context:** Existing Rajudesktop Z CapCut records mention CapCut Windows 9.6.0.4097; source examples below were tested against *different* versions. Do not extrapolate compatibility.
**Evidence convention:** **author-demonstrated** = a third party provides code, procedure, video, and/or result; **documented** = functionality in docs/code with incomplete live verification; **unverified locally** = no run on the owner's Windows build. A GitHub README is not independent certification.

## 1. Native internal command bridge — strongest non-GUI export demonstration

- Project: [reverse-cli-anything](https://github.com/leileqiTHU/reverse-cli-anything) · [CapCut native automation example](https://leileqithu.github.io/reverse-cli-anything/docs/native-automation-examples.html) · [full demo & checks](https://leileqithu.github.io/reverse-cli-anything/docs/demos/README.html) · [FAQ/limitations](https://leileqithu.github.io/reverse-cli-anything/docs/faq.html).
- **Claim and evidence:** Authors document Windows x64 **CapCut 9.5.0.4050**. A recorded 4:08 workflow runs project creation, media import, timeline trims, audio/captions, clip transforms, **CapCut-native MP4 export**, save/reopen and playback with **26 native/media acceptance checks**. The demo includes speech-recognition/translation *external helpers*; those do not mean CapCut itself provides these AI operations as a public API.
- **Mechanism:** Recover existing internal calls around `lyra_cli_client.dll`, editor/frontend modules, and active edit sessions; Frida instrumentation exposes selected commands for a CLI adapter, without ordinary mouse-click UI automation.
- **Boundary:** Unofficial reverse-engineered, *in-process* adapter; not a published/official CapCut SDK. Requires an **active running CapCut editing session**, is specifically version-qualified, and **does not prove headless/locked-desktop or CapCut 9.6 behavior**. Potential fragility/risk from runtime instrumentation, updates, and application security/licensing restrictions. Never run against originals or a production editing session without further approval.
- **Assessment:** **Author-demonstrated native export at 9.5.0.4050**; **unverified locally on 9.6.0.4097**. This is the standout finding; keep it separate from JSON project editors and keyboard macros.

## 2. Windows GUI agent — actual foreground editor, measured export

- Project: [capcut-desktop-editing](https://github.com/yousefomar724/capcut-desktop-editing) · [export procedure](https://github.com/yousefomar724/capcut-desktop-editing/blob/main/references/capabilities/15-export.md).
- The author reports **18 approved capability rungs (0–17)**, including 4K export, end-to-end horizontal/vertical editing, captioning, transitions and filters, with real footage and output verification. Documented baseline **CapCut 9.4.0.4015** on Windows.
- Control stack: Windows UI Automation where available, real key shortcuts, and screenshot/grid-driven clicks/drags for areas not exposed to UIA; `draft_content.json` is **read-only for independent verification**. CapCut Qt 6/QML/CEF may expose only the root of certain windows to UIA, explaining screenshot fallback.
- Known limits explicitly disclosed: **foreground keyboard/mouse control**, active desktop needed; locked screen and remote sessions may not work, editor updates shift controls; not headless, not safe to share interactive desktop mid-run.
- **Assessment:** **Author-demonstrated GUI exports**, stronger than a hypothetical AutoHotkey macro, but requires per-version regression tests and output file checks.

## 3. CapCut draft CLI — significant editing coverage, but export distinction matters

- Project: [capcut-cli](https://github.com/renezander030/capcut-cli) · [command reference](https://github.com/renezander030/capcut-cli/blob/master/docs/command-reference.md) · [security/version changelog](https://github.com/renezander030/capcut-cli/blob/master/CHANGELOG.md).
- Supports programmatic **local draft JSON** operations: create/compile, tracks, trim, captions, transitions, keyframes, FX/filters, timeline mirror synchronization, lint, backup/restore and JSONL job queue. These create **editable projects**, not necessarily final rendered media. The `render` command is an **FFmpeg preview/proxy**, **not CapCut's native renderer**.
- The documented **Windows `export --batch`** path opens draft files via PowerShell and sends CapCut's **Ctrl+E** export shortcut, but authors explicitly state **experimental**, with automated **script-generation tests only** and **host-dependent live render**. This is still GUI automation, not a native export API. One older command-reference section says macOS-only; subsequent CHANGELOG explicitly documents Windows support. Treat real Windows reliability as pending.
- Security note: changelog documents fixes for unsafe path handling and other issues in **0.17.1**, and redaction of device IDs in fixtures in **0.18.0**. Use reviewed, up-to-date releases, redact draft IDs/paths and avoid executing untrusted generated scripts.
- **Assessment:** **Documented/implemented draft CLI** with limited experimental export queue; **native final render not proven locally**.

## 4. Python draft editor and simple screen automation — separate classes

- [pyCapCut](https://github.com/GuanYixuan/pyCapCut) · [package documentation](https://pypi.org/project/pycapcut/): can generate/edit draft projects, but its own workflow explicitly says **open in CapCut and export manually; automated export unsupported**. It should not be cited as an export automation proof.
- [capcut-video-automation](https://github.com/godyjooce/capcut-video-automation): `pyautogui` template workflow replaces text, audio, images and triggers exports in batches; it needs `coordinates.json`, fixed screen layout, an active foreground application and tuned delays. This is a reproducible **author-documented GUI workflow** but much more fragile than named controls or an internal command bridge.
- Neither draft editing nor a scripted `Ctrl+E` click automatically proves repeatable unattended **CapCut native-render export**.

## Confidence/decision matrix

| Route | What the public evidence supports | Native final MP4 proof | Owner build 9.6 | Headless/locked |
|---|---|---|---|---|
| reverse-cli-anything internal bridge | Select native calls in a running editor at 9.5.0.4050 | **Author-demonstrated** video + checks | **Not tested** | **Not claimed** |
| capcut-desktop-editing | Real UI edits + validated foreground export at 9.4.0.4015 | **Author-demonstrated** | **Not tested** | **No** |
| capcut-cli | Draft generation/edit/validate + experimental Ctrl+E batch on Windows | **Not independently verified live for Windows batch** | **Not tested** | **No proof** |
| pyCapCut | Editable drafts | **No; manual export required** | Not established | No |
| capcut-video-automation | Coordinate-based GUI batch | **Author-described workflow** | Not established | No |

## Practical caveats for Rajudesktop

1. **Do not equate draft export with MP4 final export.** Z Builder's successful CapCut draft creation and `used=N` verified draft exports are **not** validated native render completions. Proxy FFmpeg `render` is not CapCut shader/effect parity.
2. **Version fingerprint is mandatory.** Owner's 9.6.0.4097 is not proven supported by 9.5.0.4050 bridge or 9.4.0.4015 GUI procedures. Application updates may invalidate DLL symbol addresses, Qt control paths and stored hotkeys.
3. **Unattended overnight batch remains unverified.** Real process safety would need isolated disposable drafts, serial queue, foreground unlocked Windows session for GUI route, timeout/error recovery, export-path check, ffprobe duration/codec/audio verification, output hashing and no paid/cloud operations.
4. **Never edit originals in a research test.** Lock down project copy, backup and rollback; keep user media and personally identifying draft metadata out of GitHub. Confirm license/terms and operational security before installing Frida/injection bridges.
5. **Documentation only, no implementation authorization inferred.** Existing Z Builder, CapCut Controls Studio, native export controller, independent renderer and desktop apps are untouched. No download/install/deploy, no project mutation, no replacement of selected owner approach.

## Research conclusion

**Yes, there is material online evidence of automated CapCut native export**: the reverse-engineered bridge has the strongest *non-mouse* author-demonstrated evidence, and the Windows GUI agent has separately demonstrated exports. **There is not yet evidence that either works universally, headlessly, on locked Windows, or on the owner's 9.6 build.** The word 'verified' in third-party documentation refers to that author's test, not an independent reproduction here.

Recorded: 2026-10-29. Recheck tool repository release notes and CapCut version prior to any experiment.
