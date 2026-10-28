# 01 — CapCut installation inventory (Windows 9.6.0.4097)

**Source:** user-supplied `CapCut_Inventory.csv`. Static filesystem inventory, not executable/source-code reverse engineering.

## Counts

| Metric | Count |
|---|---:|
| Listed files | 4,741 |
| Listed total size | 1.780 GiB / 1,822.9 MiB |
| Files in Resources | 3,719 |
| Files in Resources/DefaultAdjustBundle | 1,801 |
| Immediate adjustment groups | 39 |
| Files in Tools/draft-converter | 209 |
| JSON files in installation | 605 |

### Areas by file count and size

| Folder group | Files | MiB |
|---|---:|---:|
| Resources | 3,719 | 404.87 |
| QtQuick | 408 | 7.20 |
| Tools | 209 | 22.32 |
| Root-level files | 190 | 1,032.81 |
| cef | 71 | 308.02 |
| _internal | 46 | 11.72 |
| plugins | 30 | 5.74 |
| Qt5Compat | 23 | 0.54 |
| Qt | 12 | 0.47 |
| QtQml | 12 | 0.26 |
| vm_sdk | 7 | 5.95 |
| Service | 4 | 3.80 |
| quickjs_cache | 2 | 0.51 |

### Extension distribution

| Extension | Files | Extension | Files |
|---|---:|---|---:|
| .json | 605 | .js | 481 |
| .qml | 354 | .dll | 344 |
| .material | 280 | .lua | 272 |
| .rt | 260 | .frag | 241 |
| .xshader | 223 | .vert | 205 |
| .config | 142 | .png | 121 |
| .mesh | 115 | .css | 107 |
| .scene | 99 | .py | 97 |
| no extension | 85 | .md | 83 |

## High-value installation paths

1. `Tools/draft-converter/draft-converter.exe`: binary exists. Its packaged Python runtime contains `opentimelineio` and related adapters. Actual supported CLI flags, import/export directions, and generated project compatibility **not tested**.
2. `Resources/common_agent/skills/timeline-draft-cli/SKILL.md`: bundled native timeline CLI guide (examined in deeper resource collection).
3. `Resources/common_agent/skills/canvas-node-cli/SKILL.md` and `references/commands.md`: Canvas node instructions, **not** interchangeable with native timeline editing.
4. `Resources/common_agent/skills/capcut-browser/SKILL.md`: named automation-related skill; executable interoperability not verified.
5. `Resources/DefaultAdjustBundle/`: 1,801 files under 39 groups, including color/adjustment resources; group count is **not** a count of separately licensed UI effects.
6. `Resources/image_h5_material_publish/`: publishing page resources for effects, text and caption animation, filters, video and templates. Page names do not enumerate available downloaded effects.
7. `Resources/MixMode/MixMode.json`: blend resource identifiers; parsed results in document 02.
8. `Resources/models/`: references to model assets (matting, tracking, search etc.); not proof that each feature is enabled or licensed.
9. `Resources/builtin_skills/`: material-understanding, music-alignment, speaker-related documentation names.

## Boundaries

- The CSV includes filenames, paths, sizes and timestamps, **not** implementation source contents or runtime traces.
- CapCut effects can be online, account-dependent, cache-dependent, paid, or version-dependent.
- Crash dumps (`.dmp`) may contain sensitive memory; should **never** be included in routine research sharing.
- No executable binary or PC folder was modified.
- CapCut draft locations vary; a common default is `%LOCALAPPDATA%/CapCut/User Data/Projects/com.lveditor.draft`, but confirm the actual project folder in the user's own settings.
- Project-format conclusions belong in [03_NATIVE_DRAFTS.md](03_NATIVE_DRAFTS.md), not inferred from filenames.
