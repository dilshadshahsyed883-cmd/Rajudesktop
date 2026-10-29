# CapCut Native CLI Export — portable Windows runner

Independent application. Uses the **actual runnable** MIT-licensed `capcut-cli` adapter from [Leis / reverse-cli-anything](https://github.com/leileqiTHU/reverse-cli-anything), pinned at **4dba879b2592828d24d09c9e9805926cc67b56e8**. It is not merely a video demo. All vendored files are unchanged, with SHA-256 inventory in `UPSTREAM_FILES.json` and original MIT attribution under `vendor/upstream/LICENSE`.

**Supported environment: Windows x64, CapCut 9.5.0.4050, and the four exact upstream native module fingerprints. Owner's previously recorded 9.6.0.4097 is unsupported and is refused before attachment.** No downgrade, CapCut download, proprietary binary redistribution, application patch on disk, licensing bypass, replacement renderer or Z Builder modification.

## Download and start

Download the `CapCut_Native_CLI_Export` artifact from the dedicated **CapCut Native CLI Portable Windows** GitHub Actions run. Extract the outer artifact, then fully extract `CapCut_Native_CLI_Export.zip` to a writable folder, preferably on D:. Python 3.11.9 x64 is included; do not install Python manually. No admin access required.

1. Run `START.bat`, choose **1** to detect CapCut and verify version/module hashes. Custom locations can be set in `config.json` as `capcut_dir` (folder containing CapCut.exe). Discovery reads running processes, common install paths and uninstall registry locations; it does not launch or attach.
2. Only on the supported build, run `SETUP_MEDIA_TOOLS.bat` once with Internet available. It downloads an exact **LGPL shared** FFmpeg/FFprobe archive from BtbN, validates the pinned SHA-256 and retains the complete upstream distribution/license files locally. These tools are not bundled into this ZIP. They verify/decode output; they never substitute for CapCut rendering. No API keys/accounts to this runner.
3. In **CapCut itself**, duplicate the intended project. Keep the original closed. Open the duplicate in the editor and activate the intended timeline. This is deliberately a manual CapCut duplicate: raw file copies retaining the original project ID are refused. Relink project-local media into a safe location if the duplicate references the original project folder. Keep shared external source media unchanged.
4. Edit `config.json`: exact `original_project`, `duplicate_project`, `timeline_id`, current editor `pid` (Task Manager → Details → CapCut.exe), and a **new** `.mp4` output path in an existing folder outside both projects. Timeline IDs are listed in the duplicate's `Timelines/project.json`; use the active one. `require_audio: true` is the default; set false only for an intentionally silent project. Default total upstream timeout is 1800 seconds, configurable up to 86400.
5. Run `START.bat`, choose **2**. Leave CapCut running on the duplicate and do not edit it during the export. The exact upstream `editor export` command attaches using its Frida worker. Native session/project/timeline checks and module pins remain in place. The application may display its native export panel. No headless/locked-desktop reliability claim.

Command line without pauses:

```bat
python\python.exe -B runner.py doctor
python\python.exe -B runner.py export --config config.json
```

## Completion and logs

Upstream observes native render start/completion, validates H.264 dimensions/fps/duration with its native probe, fully decodes the file using FFmpeg and verifies timeline content is unchanged. The runner then independently checks **FFprobe MP4/video codec, duration, resolution and audio metadata**, audits the original folder's complete file hashes and atomically publishes the final path without overwrite. PASS requires every gate. No synthetic completion or fabricated progress percentage.

`logs/<run>/result.json` is the runner's authoritative PASS/FAIL record. `adapter.stdout.json`, `adapter.stderr.log`, `ffprobe.json` and `original-before.json` explain the result. Detailed upstream native events/status/receipts remain in `vendor/upstream/capcut-cli/.runtime/`; they can be inspected while running. Treat these logs as private: they may contain local project paths and IDs. Do not upload private drafts or media to GitHub.

On failure/timeout, keep the stage file and logs for diagnosis. **Do not blindly retry**: an unknown native outcome may retain the upstream PID lock. Inspect CapCut and upstream receipts first. This runner does not remove locks, auto-replay, delete media, restore drafts, or overwrite exports. A failed final verification can leave `.native-cli-*.mp4` / `.capcut-export-*` staging artifacts; they are never announced as successful exports. Both the upstream worker and wrapper audit saved content, but the original must remain closed and untouched by other software during a run.

## What this package does and does not establish

| Check | Evidence |
|---|---|
| Runnable upstream adapter/native export source | Available and vendored unchanged at the pinned SHA |
| Native MP4 demonstration | Upstream author on 9.5.0.4050; see original examples/evidence |
| Windows packaged launcher, embedded Python, dependency import, capabilities, negative guards | Automated dedicated Windows CI; consult run and BUILD_MANIFEST.json |
| FFprobe integration | Real FFmpeg-generated **synthetic test fixture**, not CapCut render evidence |
| Actual export of owner's project, effects/captions/audio playback and visual parity | **NOT TESTED** in this environment |
| CapCut 9.6.0.4097 | **Unsupported / blocked**; no guessed commands or addresses |
| Sequential multi-project / overnight / locked desktop | **Not enabled or certified**; source has project commands, but that is not a proven overnight queue |

Runtime instrumentation is upstream's supported method: Frida attaches to the running process and installs scoped observers/native calls, including its temporary guard against unwanted automatic post-export AI crop. The guard is not a license/security bypass. On-disk CapCut executables, DLLs and installation/configuration are not patched by this runner. A native export can update the **duplicate's** normal editor/export metadata; semantic timeline integrity is checked upstream. Originals are never passed to an upstream mutation command.

## Source and rebuild

`build_portable.py` runs on Windows with build-time Python/pip (GitHub Actions provides them), downloads official CPython embeddable 3.11.9, installs Frida **17.23.3** and retains its distribution licenses. It starts and tests the actual embedded interpreter/package before creating the ZIP and SHA256SUMS. The Python archive digest is recorded in BUILD_MANIFEST. The original upstream requirements are preserved; `imageio-ffmpeg==0.6.0` is the upstream optional decoder fallback. This distribution selects the upstream-supported explicit `REVERSE_CLI_FFMPEG` configuration instead, so the imageio wheel and its bundled FFmpeg are not needed or redistributed.

Run source tests: `python -B -m unittest discover -s capcut_native_cli_runner/tests -v` from repo root. Upstream export guard/lifecycle regressions are also run in CI. No live CapCut export test is possible on a GitHub-hosted machine without the licensed supported installation and an active editable project.

Third-party sources/licenses: `THIRD_PARTY_NOTICES.md`. Rollback: remove this independent folder/ZIP; existing Rajudesktop apps remain unchanged.
