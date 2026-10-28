"""Scene Plan driven native CapCut image Combo animations and same-track transitions.

Effects are resolved against ACTUAL previously-used saved-draft material catalogs.
The Z Studio timeline writer remains the authority for media, tracks and timing;
we only attach native transition/Combo materials to its newly verified output.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autocapcut_animations_only.animation_engine import (
    apply_animation, harvest_animations, image_clips, load_project,
    make_plan, resource_is_available, stable_media_fingerprint,
)
from autocapcut_transitions_only.transition_engine import (
    Plan as TransitionPlan, apply_plan as attach_transitions,
    cut_inventory, harvest_transitions, immutable_snapshot,
)

from .core import Plan, Shot, timeline


def _root_setting(plan: Plan, key: str, default: str) -> str:
    return str((plan.sections.get('CAPCUT_EFFECTS') or {}).get(key, default)).strip()


def _seed(plan: Plan, key: str, default: int) -> int:
    try:
        num = int(_root_setting(plan, key, str(default)))
    except ValueError as exc:
        raise ValueError(f'CAPCUT_EFFECTS.{key}: seed must be an integer') from exc
    if not 0 <= num < 2**63:
        raise ValueError(f'CAPCUT_EFFECTS.{key}: seed must be 0..2^63-1')
    return num


def _resolve_preset(token: str, entries: list[dict], kind: str) -> dict:
    token = token.strip()
    if token.casefold().startswith('id:'):
        target = token[3:].strip()
        candidates = [e for e in entries if str(e.get('effect_id')) == target]
    else:
        candidates = [e for e in entries if str(e.get('name', '')).casefold() == token.casefold()]
    if not candidates:
        raise ValueError(f'{kind}: "{token}" is not in saved CapCut projects. Download Effects Summary again.')
    if len(candidates) != 1:
        raise ValueError(f'{kind}: "{token}" is ambiguous; use id:<exact native effect ID>.')
    return candidates[0]


def _is_random(token: str) -> bool:
    return token.casefold() in {'random', 'random_saved', 'random_available'}


def needs_native_effects(plan: Plan) -> bool:
    if any(x.native_combo.strip() or x.native_transition_after.strip() for x in plan.shots):
        return True
    return any(_root_setting(plan, key, 'none').casefold() not in ('none', '', 'off')
               for key in ('combo_default', 'transition_default'))


def prepare_effects(plan: Plan, parts: list, animation_root: str | Path,
                    transition_root: str | Path) -> dict:
    """Preflight all requested effects BEFORE writing any CapCut draft.

    Returns frozen, deterministic per-shot effect IDs. Cross-layer explicit
    transitions fail safely; random transitions only choose eligible cuts.
    """
    if not needs_native_effects(plan):
        return {'active': False, 'animations': {}, 'transitions': {}, 'warnings': [],
                'animation_catalog': [], 'transition_catalog': []}
    anim_root, trans_root = Path(animation_root), Path(transition_root)
    animations = harvest_animations(anim_root, trending_only=True) if anim_root.is_dir() else []
    animations = [a for a in animations if resource_is_available(a) and int(a.get('duration_us') or 0) > 0]
    transitions = harvest_transitions(trans_root) if trans_root.is_dir() else []
    combo_default = _root_setting(plan, 'combo_default', 'none')
    trans_default = _root_setting(plan, 'transition_default', 'none')
    combo_rng = random.Random(_seed(plan, 'combo_seed', 42))
    trans_rng = random.Random(_seed(plan, 'transition_seed', 43))
    results: dict[str, dict] = {'active': True, 'animations': {}, 'transitions': {},
                                'warnings': [], 'animation_catalog': animations,
                                'transition_catalog': transitions}
    errors = []
    previous_anim = None
    previous_trans = None
    all_shots = [shot for part in parts for shot in part.plan.shots]
    sections = [x.section for x in all_shots]
    if len(set(sections)) != len(sections):
        raise ValueError('Each Scene Plan shot must have a unique section / shot ID')
    for i, shot in enumerate(all_shots):
        combo = (shot.native_combo.strip() or combo_default).strip()
        transition = (shot.native_transition_after.strip() or trans_default).strip()
        if combo.casefold() not in {'', 'none', 'off'}:
            if shot.media_type != 'image':
                if shot.native_combo.strip():
                    errors.append(f'{shot.section}: native Combo animations are for images only')
            else:
                try:
                    if _is_random(combo):
                        pool = [a for a in animations if a['effect_id'] != previous_anim] or animations
                        if not pool:
                            raise ValueError('no already-used Combo animation has an available local cache')
                        entry = combo_rng.choice(pool)
                    else:
                        entry = _resolve_preset(combo, animations, f'{shot.section} Combo animation')
                    results['animations'][shot.section] = entry['effect_id']
                    previous_anim = entry['effect_id']
                except ValueError as exc:
                    errors.append(str(exc))
        if transition.casefold() in {'', 'none', 'off', 'hard_cut', 'cut'}:
            continue
        # A transition attaches to the outgoing segment only if the next shot
        # abuts it on the same track INSIDE THE SAME CAPCUT PROJECT.
        current_part = next(p for p in parts if any(s.section == shot.section for s in p.plan.shots))
        group = current_part.plan.shots
        local_index = next(j for j, s in enumerate(group) if s.section == shot.section)
        eligible = local_index + 1 < len(group) and group[local_index + 1].media_type == shot.media_type
        if not eligible:
            msg = (f'{shot.section}: no adjacent same-track cut in this CapCut part; '
                   'cross-layer or cross-part transitions cannot safely be applied.')
            if shot.native_transition_after.strip():
                errors.append(msg)
            else:
                results['warnings'].append(msg)
            continue
        try:
            if _is_random(transition):
                pool = [t for t in transitions if t['effect_id'] != previous_trans] or transitions
                if not pool:
                    raise ValueError('no saved native transitions are available')
                entry = trans_rng.choice(pool)
            else:
                entry = _resolve_preset(transition, transitions, f'{shot.section} transition')
            results['transitions'][shot.section] = entry['effect_id']
            previous_trans = entry['effect_id']
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError('SCENE PLAN NATIVE EFFECTS PREFLIGHT BLOCKED:\n' + '\n'.join(errors[:30]))
    return results


def _segment_mapping(draft: dict, part) -> dict[str, tuple[int, int]]:
    """Exact local start/duration and media TYPE mapping, never fuzzy filenames."""
    video_mats = {m.get('id'): m for m in draft.get('materials', {}).get('videos', []) if isinstance(m, dict)}
    by_range: dict[tuple[int, int, str], list[tuple[int, int]]] = {}
    for ti, track in enumerate(draft.get('tracks', [])):
        if track.get('type') != 'video':
            continue
        for si, seg in enumerate(track.get('segments', [])):
            m = video_mats.get(seg.get('material_id'), {})
            typ = m.get('type')
            if typ not in {'photo', 'video'}:
                continue
            t = seg.get('target_timerange') or {}
            key = (int(t['start']), int(t['duration']), typ)
            by_range.setdefault(key, []).append((ti, si))
    result = {}
    for start, end, shot in timeline(part.plan):
        kind = 'photo' if shot.media_type == 'image' else 'video'
        key = (round(start * 1_000_000), round((end - start) * 1_000_000), kind)
        candidate = by_range.get(key, [])
        if len(candidate) != 1:
            raise ValueError(f'{shot.section}: cannot uniquely map generated CapCut clip (found {len(candidate)} matches)')
        result[shot.section] = candidate[0]
    if len(result) != len(part.plan.shots):
        raise ValueError('Incomplete shot-to-CapCut-segment mapping')
    return result


def apply_effects_in_memory(draft: dict, part, prepared: dict) -> tuple[dict, dict]:
    """Apply native effects without rebuilding a single timeline segment."""
    if not prepared.get('active'):
        return copy.deepcopy(draft), {'animations': 0, 'transitions': 0}
    mapping = _segment_mapping(draft, part)
    work = copy.deepcopy(draft)
    acat = prepared['animation_catalog']
    tcat = prepared['transition_catalog']
    animation_rows = []
    # Reuse the previously tested animation engine's preview/apply validation.
    for shot in part.plan.shots:
        eid = prepared['animations'].get(shot.section)
        if eid:
            rows, _ = make_plan(work, acat, [mapping[shot.section]], eid, mode='single')
            if len(rows) != 1 or rows[0].get('status') != 'Will Apply':
                reason = rows[0].get('reason', 'no image clip') if rows else 'no matching image'
                raise ValueError(f'{shot.section}: animation cannot apply: {reason}')
            animation_rows.extend(rows)
    if animation_rows:
        before = copy.deepcopy(work)
        work, a_stats = apply_animation(work, acat, None, animation_rows)
        if stable_media_fingerprint(before) != stable_media_fingerprint(work):
            raise AssertionError('Animation changed non-animation project data')
    else:
        a_stats = {'changed': 0}
    requested = {}
    allowed_cuts = {(x['track_index'], x['segment_index']) for x in cut_inventory(work)[0]}
    for shot in part.plan.shots:
        eid = prepared['transitions'].get(shot.section)
        if not eid:
            continue
        key = mapping[shot.section]
        if key not in allowed_cuts:
            raise ValueError(f'{shot.section}: native transition cut is not adjacent on the same track')
        duration_s = float((part.plan.sections.get('CAPCUT_EFFECTS') or {}).get('transition_duration', '0.5'))
        if not 0.1 <= duration_s <= 10.0:
            raise ValueError('CAPCUT_EFFECTS.transition_duration must be 0.1–10 seconds')
        requested[key] = {'effect_id': eid, 'durationUs': round(duration_s * 1_000_000)}
    if requested:
        before = copy.deepcopy(work)
        transition_plan = TransitionPlan(chosen=requested)
        work, t_stats = attach_transitions(work, tcat, transition_plan)
        if immutable_snapshot(before) != immutable_snapshot(work):
            raise AssertionError('Transition changed non-transition project data')
    else:
        t_stats = {'changed': 0}
    # Explicit primary integrity guarantee: no clip/track data besides native refs.
    before_tracks = copy.deepcopy(draft.get('tracks', []))
    after_tracks = copy.deepcopy(work.get('tracks', []))
    for tracks in (before_tracks, after_tracks):
        for track in tracks:
            for seg in track.get('segments', []):
                seg.pop('extra_material_refs', None)
    if before_tracks != after_tracks:
        raise AssertionError('Native effect application modified timeline clips, timing, layers or motion')
    return work, {'animations': a_stats['changed'], 'transitions': t_stats['changed']}


def _atomic_replace(file: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix='.scene_native_effect_', dir=str(file.parent))
    try:
        with os.fdopen(fd, 'wb') as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, file)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def apply_effects_to_draft(project: Path, part, prepared: dict) -> dict:
    """One all-or-nothing native-effects transaction per newly generated draft.

    The built-in exporters have already verified original clip order, timing and
    integrity. Both effects are applied in memory, backed up and synced together.
    """
    if not prepared.get('active'):
        return {'animations': 0, 'transitions': 0, 'saved': False}
    from autocapcut_animations_only.animation_engine import capcut_running
    if capcut_running():
        raise RuntimeError('Close CapCut while applying native Scene Plan effects')
    source, paths, _ = load_project(project)
    updated, totals = apply_effects_in_memory(source, part, prepared)
    if not any(totals.values()):
        return {**totals, 'saved': False}
    outgoing = json.dumps(updated, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    original = {p: p.read_bytes() for p in paths}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    backup = project / '.scene_plan_effects_backups' / stamp
    backup.mkdir(parents=True, exist_ok=False)
    for index, (path, blob) in enumerate(original.items()):
        (backup / f'{index:02d}_{path.name}').write_bytes(blob)
    (backup / 'manifest.json').write_text(json.dumps([
        {'original': str(path), 'backup': f'{i:02d}_{path.name}',
         'sha256': hashlib.sha256(blob).hexdigest()}
        for i, (path, blob) in enumerate(original.items())
    ], indent=2), encoding='utf-8')
    if capcut_running() or any(p.read_bytes() != original[p] for p in paths):
        raise RuntimeError('CapCut/draft changed during effects preflight; abort before writing')
    written = []
    try:
        for path in paths:
            _atomic_replace(path, outgoing)
            written.append(path)
        actual, _, _ = load_project(project)
        if actual != updated:
            raise RuntimeError('Readback verification of native effects failed')
    except BaseException:
        for path in reversed(written):
            _atomic_replace(path, original[path])
        raise
    return {**totals, 'saved': True, 'backup_dir': str(backup)}
