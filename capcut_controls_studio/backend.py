"""UI-free native operations, original V6.1 engines and one guarded write lane."""
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path

from .engines import animations, transitions, visual


@dataclass(frozen=True)
class Snapshot:
    project: Path
    fingerprint: dict
    raw: dict
    transitions: list
    animations: list
    warnings: list


def fingerprint(project):
    _, paths, _ = visual.load_project(project)
    index = project / 'Timelines' / 'project.json'
    if index.is_file():
        paths.append(index)
    return visual.project_fingerprint(paths)


def require_current(snapshot):
    if snapshot is None or fingerprint(snapshot.project) != snapshot.fingerprint:
        raise ValueError('Project changed. Refresh and preview again before applying.')


def load_snapshot(project):
    project = Path(project).resolve(strict=True)
    before = fingerprint(project)
    raw, _, warnings = visual.load_project(project)
    tr = transitions.harvest_transitions(project.parent, project=project)
    an = animations.harvest_animations(project.parent, trending_only=False, project=project)
    for entry in an:
        entry['available'] = animations.resource_is_available(entry)
    if before != fingerprint(project):
        raise ValueError('Project changed during detection; refresh again.')
    return Snapshot(project, before, raw, tr, an, warnings)


def scan(root, selected=None, previous=None):
    projects = visual.list_projects(root)
    selected = Path(selected).resolve() if selected else None
    if selected not in projects:
        selected = projects[0] if projects else None
    snapshot = None
    if selected:
        if previous and previous.project == selected and fingerprint(selected) == previous.fingerprint:
            snapshot = previous
        else:
            snapshot = load_snapshot(selected)
    return projects, snapshot, visual.capcut_running()


@contextmanager
def operation_lock(project):
    """Serialize this app's operations across windows/processes on one project."""
    project = Path(project).resolve(strict=True)
    lock = project / '.capcut_controls_studio.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(f'pid={os.getpid()}\n')
        for peer in ['.autocapcut_transitions_only.lock', '.autocapcut_animations_only.lock', '.visual_controls_test.lock']:
            if (project / peer).exists():
                raise RuntimeError('Another native editor is writing this project. Try again when it finishes.')
        yield
    finally:
        lock.unlink(missing_ok=True)


def preview_transitions(snapshot, mode, ids, duration, spec):
    require_current(snapshot)
    if mode == 'single' and len(ids) != 1:
        raise ValueError('Select exactly one transition for Single mode.')
    if mode == 'mix' and not ids:
        raise ValueError('Select transitions or favorites for Random mix.')
    plan = transitions.plan_transitions(snapshot.raw, snapshot.transitions, mode, ids, duration, spec)
    plan.warnings = snapshot.warnings + plan.warnings
    require_current(snapshot)
    return plan


def apply_transitions(snapshot, plan):
    if not plan or not plan.chosen:
        raise ValueError('Preview a valid transition selection before Apply.')
    with operation_lock(snapshot.project):
        require_current(snapshot)
        return transitions.save_transitions(snapshot.project, snapshot.transitions, plan)


def preview_animations(snapshot, selected, mode, ids, seed):
    require_current(snapshot)
    if mode == 'single':
        entries = [e for e in snapshot.animations if e['effect_id'] in ids]
        if len(entries) != 1:
            raise ValueError('Select exactly one native Combo animation.')
        effect_id, native_mode = entries[0]['effect_id'], 'single'
    else:
        entries = [e for e in snapshot.animations if mode == 'random_all' or e['effect_id'] in ids]
        if not entries:
            raise ValueError('Select one or more native Combo animations.')
        effect_id, native_mode = None, 'random'
    rows, warnings = animations.make_plan(snapshot.raw, entries, selected, effect_id,
                                          mode=native_mode, seed=seed, fit_to_clip=True)
    require_current(snapshot)
    return rows, entries, effect_id, snapshot.warnings + warnings


def apply_animations(snapshot, result):
    rows, entries, effect_id, _ = result
    with operation_lock(snapshot.project):
        require_current(snapshot)
        return animations.save(snapshot.project, entries, effect_id, rows)


def preview_scale(snapshot, options):
    require_current(snapshot)
    result = visual.create_preview(snapshot.raw, options)
    require_current(snapshot)
    return result


def apply_scale(snapshot, options):
    with operation_lock(snapshot.project):
        require_current(snapshot)
        _, paths, _ = visual.load_project(snapshot.project)
        return visual.save_project(snapshot.project, options, visual.project_fingerprint(paths))
