# CapCut Native CLI Export — portable Windows package

**Status: portable launcher/source delivered; native export BLOCKED under the requested strict configuration-preservation contract. This is not a working-export release.**

Reuses the actual runnable MIT-licensed `capcut-cli` adapter from [Leis / reverse-cli-anything](https://github.com/leileqiTHU/reverse-cli-anything), pinned at **4dba879b2592828d24d09c9e9805926cc67b56e8**. This source exists and is distributable; it is not just a demo. All 77 vendored files are unchanged, with SHA-256 inventory in `UPSTREAM_FILES.json` and original attribution under `vendor/upstream/LICENSE`.

## Verified source limitations

| Constraint | Source evidence / behavior |
|---|---|
| Windows x64, **CapCut 9.5.0.4050** plus exact module hashes | `capcut-cli/adapter.json`, `capcut_store_worker.py: STORE_PINS` |
| Exact install directory **D:/Apps/CapCut2/CapCut/9.5.0.4050** | `capcut_store_agent.js: DIRECTORY` and loaded-module path guard; directory is hardcoded in the unchanged native export bridge |
| CapCut's configured draft root must be on **D:** | `capcut_store_agent.js: guard()`; this is checked by the upstream bridge during native session inspection |
| At most **300 seconds total** | `capcut_agent.py: main()` rejects larger timeouts; includes preparation/render/verification, so long exports may fail |
| Export saves CapCut's default export folder | `capcut_export_frontend_agent.js: exportconfigure()` explicitly invokes `saveExportPath` |
| Owner's recorded **9.6.0.4097** | Unsupported; refused before attachment. No guessed offsets, downgrade or install changes |

The requested preservation of CapCut configuration conflicts with the unmodified upstream native export implementation. `configuration_guard()` therefore **blocks the wrapper before any Frida attachment or export**, even on a matching installation. No configuration flag disables this guard. A new configuration-preserving upstream method or a later explicit change to the user's requirements would need a separate reviewed update. Do not manually bypass this guard to treat this package as accepted.

No CapCut executable/DLL, replacement renderer, binary patch, licensing/security bypass, project modification, batch queue or Z Builder change is included. Upstream Frida runtime instrumentation is preserved as source, but the guarded launcher does not execute it while the strict contract remains blocked.

## Download and use

Download the `CapCut_Native_CLI_Export` artifact from **CapCut Native CLI Portable Windows** in GitHub Actions. Extract the outer artifact, then fully extract `CapCut_Native_CLI_Export.zip` into a writable folder. Python 3.11.9 x64 and Frida 17.23.3 are included; no manual Python installation or admin access is required.

- Run `START.bat` and choose **1** to detect installed CapCut, read the exact executable file version and check compatibility. Discovery reads running processes, common install folders and uninstall-registry locations. Set `capcut_dir` in `config.json` for an unlisted custom location; a detected location is not automatically a supported bridge location.
- Choose **2** to check export readiness. Missing/unsupported installations, nonmatching fingerprints/install paths, invalid timeout and the strict configuration-preservation conflict produce explicit failure messages. **No native export is attempted.**
- `SETUP_MEDIA_TOOLS.bat` is an optional one-time Internet download for the included verification support. It downloads a pinned LGPL shared FFmpeg/FFprobe archive directly from BtbN, checks SHA-256 and retains the complete publisher distribution and licenses. These tools are not bundled in this ZIP. Running this setup does **not** resolve CapCut compatibility or the configuration blocker.

Without a batch pause:

```bat
python\python.exe -B runner.py doctor
python\python.exe -B runner.py export --config config.json
python\python.exe -B runner.py integrity
```

## Preserved export/verification path — blocked, not live validated

For a future separately authorized resolution of the configuration blocker, the source retains a narrowly scoped call to the original `editor export` implementation. It requires a CapCut-created duplicate with a different project ID, explicit active timeline/current PID, no embedded original-folder references and a new MP4 path outside both project folders. Raw folder copies retaining the original identity, symlinks/junctions, existing outputs and unverified results are refused.

Upstream native completion, full-file decode and unchanged-timeline flags are required. Additional FFprobe verification checks MP4/H.264, duration, resolution and audio metadata. The wrapper audits original-folder file hashes and uses atomic no-overwrite publication. Audio is required by default; intentional silent projects can set `require_audio: false`. `timeout_seconds` is restricted to 60..300 to preserve the upstream limit.

These publication/failure checks are tested with **mocks**, not live CapCut. They do not prove successful project export. They remain behind the configuration guard. No progress percentages are fabricated. If a future supported command is enabled, detailed native events/receipts would appear under `vendor/upstream/capcut-cli/.runtime/`, and wrapper records under `logs/<run>/`; treat all such logs as private. Unknown native outcomes/retained PID locks must never be blindly retried.

## Acceptance results

| Check | Result / evidence |
|---|---|
| Runnable/distributable upstream adapter source | **PASS**, inspected and pinned; author demonstrated native export on their environment |
| Upstream source byte integrity | **PASS**, 77 files; Windows checkout preserves their original bytes |
| Packaged Windows START.bat / embedded interpreter / Frida / upstream capabilities | Dedicated Windows CI; see BUILD_MANIFEST.json and current run |
| Real Windows executable file-version reader | Windows unit test reads CPython's real version resource; live CapCut detection **NOT TESTED** |
| Missing CapCut / unsupported version / hash / timeout / preservation blockers | Automated error-path tests; unsupported version and hash cases use fixtures/mocks |
| Independent FFprobe integration | Real FFmpeg-generated synthetic audio/video fixture, **not** a CapCut render |
| Native command invocation in a supported CapCut session | **NOT TESTED; wrapper BLOCKED** |
| Actual CapCut MP4/audio/duration/resolution, effects/captions, playback | **NOT TESTED** |
| Original project preservation in a real CapCut session | **NOT TESTED**; strict launcher performs no native action |
| Sequential multi-project, overnight, headless or locked-desktop reliability | **NOT TESTED / not enabled** |

## Build, source and attribution

The dedicated workflow `.github/workflows/capcut-native-cli-portable.yml` builds `CapCut_Native_CLI_Export.zip` on Windows, runs 30 runner tests, 7 unchanged upstream export regressions, starts the actual embedded launcher and tests a synthetic FFprobe fixture. It never installs CapCut. The source-only wrapper tests run with `python -B -m unittest discover -s capcut_native_cli_runner/tests -v` from repo root.

`build_portable.py` downloads official CPython embeddable 3.11.9 and records its received archive SHA-256, installs Frida 17.23.3 with distribution licenses, and creates the portable ZIP/checksum. The original upstream requirements are preserved. `imageio-ffmpeg==0.6.0` is its decoder fallback; this package selects the existing explicit `REVERSE_CLI_FFMPEG` configuration instead and does not redistribute that optional wheel or its media binary. No source-independent recreation of native calls has been added.

Licenses/source links: `THIRD_PARTY_NOTICES.md`. Uninstall/rollback: remove this independent extracted package. Existing Rajudesktop applications remain untouched.
