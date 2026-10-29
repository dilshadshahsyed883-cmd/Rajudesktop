# AutoCapCut UI/UX reference audit — 29 October 2026

The owner's reference screenshot supplies the dark rounded surface, compact project selector, status badge, horizontal tabs and prominent light action button. CapCut Controls Studio uses a wider resizable layout to accommodate the existing native controls and tables.

| Reference | Audited revision | Files inspected | Patterns adopted |
| --- | --- | --- | --- |
| [hntt2510/autoCapcut](https://github.com/hntt2510/autoCapcut) | `676336ae87ffc367384215518a17d56f4e2cd133` | README, pyproject.toml, src/auto_capcut/ui/main_window.py, workers/project_worker.py, repository tree | Compact grouped controls; project-focused flow; native UI kept separate from background QObject/QThread work; progress/finished/failure signals; disabled conflicting actions during work |
| [giapdang/autocapcut](https://github.com/giapdang/autocapcut) | `ca589e563087f113fddc83a08ad52c49d2f65ce2` | README, views/main_window.py, views/components.py, controllers/main_controller.py, repository tree | Distinct controller/view/service responsibilities; persistent configuration; explicit progress, status and completion handling; project-oriented interaction |

These repositories implement different applications: the primary reference is PyQt6/native draft generation and the additional reference uses CustomTkinter with export automation. Neither backend is substituted for the existing CapCut Controls logic. No timeline rebuild, draw rendering, effect pipeline or Windows automation is imported.

## License verification and reuse decision

At these exact revisions, neither recursive tree contains a LICENSE/COPYING file. The primary pyproject does not declare a license. The additional README claims MIT and refers to a LICENSE file, but that file is absent from the inspected tree. Therefore no third-party source code, assets or packaging scripts are copied or bundled. The general UI/UX patterns above are implemented independently in PySide6. Working engines and existing native control widgets come from the owner's Rajudesktop V6.1 source. There is no dependency on either reference repository.

This records the observed repository metadata at the audited revisions; it does not infer an additional permission requirement for the owner's repository.
