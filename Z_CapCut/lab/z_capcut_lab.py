#!/usr/bin/env python3
"""Z CapCut practical schema lab: inspect and explicitly write COPY-ONLY drafts.

No external packages, no CapCut process/IPC calls. Works on JSON drafts only.
This is an experimental structure test, NOT a validated CapCut runtime importer.

Usage:
  python z_capcut_lab.py audit draft_content.json
  python z_capcut_lab.py experiment draft_content-2.json --out /tmp/draft_experiment.json

experiment NEVER replaces an existing file; it only supports image-to-image preset
animation cloning when the source has exactly one nonempty preset and the destination
has a linked empty material_animations placeholder, and adds two per-property scale
keyframe lists. It does NOT download effects or media. It does not edit the source.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import pathlib
import sys
import uuid

KNOWN_MOTION_TYPES = {'KFTypeScaleX', 'KFTypeScaleY', 'UNIFORM_SCALE',
                      'KFTypePositionX', 'KFTypePositionY', 'KFTypeRotation'}


def data_hash(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_by_id(draft):
    found = {}
    duplicates = []
    for category, objects in draft.get('materials', {}).items():
        if not isinstance(objects, list):
            continue
        for obj in objects:
            if isinstance(obj, dict) and obj.get('id'):
                i = obj['id']
                if i in found:
                    duplicates.append({'category': category, 'id': i})
                found[i] = (category, obj)
    return found, duplicates


def segments(draft):
    for track_i, track in enumerate(draft.get('tracks', [])):
        for seg_i, seg in enumerate(track.get('segments', [])):
            yield track_i, seg_i, track, seg


def audit(draft):
    indexed, duplicates = object_by_id(draft)
    errors, warnings = [], []
    if duplicates:
        errors.append(f"duplicate material ids: {len(duplicates)}")
    top_duration = draft.get('duration')
    if not isinstance(top_duration, int) or top_duration < 0:
        errors.append('project duration missing/invalid')
    media_counts = {'photo': 0, 'video': 0, 'audio': 0, 'other': 0}
    intervals = []
    track_rows = []
    effect_materials = {'animations': 0, 'transitions': 0, 'filters': 0, 'effects': 0}
    for arr in draft.get('materials', {}).get('material_animations', []):
        effect_materials['animations'] += len(arr.get('animations', []))
    effect_materials['transitions'] = len(draft.get('materials', {}).get('transitions', []))
    effect_materials['filters'] = sum(1 for bucket in ('effects', 'video_effects')
                                      for m in draft.get('materials', {}).get(bucket, [])
                                      if m.get('type') == 'filter')
    effect_materials['effects'] = sum(1 for bucket in ('effects', 'video_effects')
                                      for m in draft.get('materials', {}).get(bucket, [])
                                      if m.get('type') == 'video_effect')
    for ti, si, tr, s in segments(draft):
        mat_id = s.get('material_id')
        cat, material = indexed.get(mat_id, ('missing', {}))
        if cat == 'missing':
            errors.append(f'track {ti} segment {si}: material_id not found')
        if cat == 'videos':
            typ = material.get('type', 'other')
        elif cat == 'audios':
            typ = 'audio'
        else:
            typ = 'other'
        media_counts[typ if typ in media_counts else 'other'] += 1
        for ref in s.get('extra_material_refs', []):
            if ref not in indexed:
                errors.append(f'track {ti} segment {si}: missing extra material ref')
        tg = s.get('target_timerange') or {}
        st, duration = tg.get('start'), tg.get('duration')
        if not isinstance(st, int) or not isinstance(duration, int) or duration <= 0 or st < 0:
            errors.append(f'track {ti} segment {si}: invalid target timerange')
            continue
        if isinstance(top_duration, int) and st + duration > top_duration:
            errors.append(f'track {ti} segment {si}: extends beyond project duration')
        sr = s.get('source_timerange') or {}
        if sr and (not isinstance(sr.get('start'), int) or not isinstance(sr.get('duration'), int)):
            errors.append(f'track {ti} segment {si}: invalid source timerange')
        for kf in s.get('common_keyframes', []):
            offsets = [k.get('time_offset') for k in kf.get('keyframe_list', [])]
            if any(not isinstance(v, int) or v < 0 or v >= duration for v in offsets):
                warnings.append(f'track {ti} segment {si}: offset may be outside clip')
            if offsets != sorted(offsets):
                errors.append(f'track {ti} segment {si}: unsorted keyframe offsets')
        intervals.append((st, st + duration))
        track_rows.append({'track': ti, 'segment': si, 'type': typ,
                           'start_us': st, 'duration_us': duration,
                           'render_index': s.get('render_index'),
                           'anim_ref_count': sum(indexed.get(r, (None,))[0] == 'material_animations'
                                                 for r in s.get('extra_material_refs', [])),
                           'keyframe_properties': [kf.get('property_type') for kf in s.get('common_keyframes', [])]})
    # Global visual-coverage gaps: exclude audio/text/filter tracks because they're overlays.
    visual_intervals = sorted((x['start_us'], x['start_us']+x['duration_us'])
                              for x in track_rows if x['type'] in ('photo', 'video'))
    gaps = []
    cursor = 0
    for start, end in visual_intervals:
        if start > cursor:
            gaps.append([cursor, start])
        cursor = max(cursor, end)
    if isinstance(top_duration, int) and cursor < top_duration:
        gaps.append([cursor, top_duration])
    return {'valid_structure': not errors, 'errors': errors, 'warnings': warnings,
            'project_version': draft.get('version'), 'fps': draft.get('fps'),
            'duration_us': top_duration, 'canvas': draft.get('canvas_config'),
            'track_count': len(draft.get('tracks', [])), 'segment_count': len(track_rows),
            'media_counts': media_counts, 'effect_material_counts': effect_materials,
            'visual_gaps_us': gaps, 'segments': track_rows}


def _photo_suitable_segments(draft):
    idx, _ = object_by_id(draft)
    images = []
    for _, _, _, s in segments(draft):
        item = idx.get(s.get('material_id'))
        if item and item[0] == 'videos' and item[1].get('type') == 'photo':
            images.append(s)
    return images


def _animation_slot(segment, matidx):
    for rid in segment.get('extra_material_refs', []):
        category, material = matidx.get(rid, ('', {}))
        if category == 'material_animations':
            return material
    return None


def _keyframe_list(prop: str, start: float, end: float, duration_us: int, fps: int):
    # Don't put the final keyframe beyond last visible frame.
    frame_us = round(1_000_000 / max(fps, 1))
    ending = max(1, duration_us - frame_us)
    return {'id': str(uuid.uuid4()).upper(), 'property_type': prop,
            'keyframe_list': [
                {'id': str(uuid.uuid4()).upper(), 'curveType': 'Line',
                 'time_offset': 0, 'values': [start], 'string_value': '', 'graphID': ''},
                {'id': str(uuid.uuid4()).upper(), 'curveType': 'Line',
                 'time_offset': ending, 'values': [end], 'string_value': '', 'graphID': ''}]}


def experiment(draft):
    """Return modified in-memory independent object + operation summary.

    Require a target photo linked to empty animation material: safe minimal delta.
    """
    candidate = copy.deepcopy(draft)
    before = audit(candidate)
    if not before['valid_structure']:
        raise ValueError('Refusing mutation of invalid draft')
    if candidate.get('version') != 360000:
        raise ValueError('Unsupported/unverified draft schema version')
    photos = _photo_suitable_segments(candidate)
    if len(photos) < 2:
        raise ValueError('Need two photos in native draft')
    idx, _ = object_by_id(candidate)
    source = next((s for s in photos if (slot := _animation_slot(s, idx)) and slot.get('animations')), None)
    dest = next((s for s in photos if (slot := _animation_slot(s, idx)) is not None
                 and not slot.get('animations') and s is not source), None)
    if source is None or dest is None:
        raise ValueError('Need one animated photo and one unanimated photo with an empty animation material slot')
    fromslot = _animation_slot(source, idx)
    toslot = _animation_slot(dest, idx)
    # Copy *metadata only*; the installed CapCut effect cache may not exist on another PC.
    copied_animations = copy.deepcopy(fromslot['animations'])
    for a in copied_animations:
        # Keep CapCut preset resource IDs; don't forge resource data.
        dur = dest['target_timerange']['duration']
        a['duration'] = min(a['duration'], dur)
    toslot['animations'] = copied_animations
    # Add two explicit X/Y scale properties. Avoid possibly version-specific UNIFORM_SCALE
    # until the owner confirms actual generated draft in the editor.
    if dest.get('common_keyframes'):
        raise ValueError('Destination already has keyframes; refuse to replace')
    duration_us = dest['target_timerange']['duration']
    fps = int(candidate.get('fps') or 30)
    dest['common_keyframes'] = [
        _keyframe_list('KFTypeScaleX', 1.0, 1.06, duration_us, fps),
        _keyframe_list('KFTypeScaleY', 1.0, 1.06, duration_us, fps)]
    after = audit(candidate)
    if not after['valid_structure']:
        raise ValueError('Post-mutation structure audit failed: ' + '; '.join(after['errors']))
    def timeline_signature(doc):
        return [(ti, si, s.get('id'), s.get('material_id'),
                 s.get('source_timerange'), s.get('target_timerange'), s.get('render_index'))
                for ti, si, _track, s in segments(doc)]
    if timeline_signature(draft) != timeline_signature(candidate):
        raise AssertionError('Timeline changed during copy-only experiment!')
    return candidate, {'copied_preset_name': [a.get('name') for a in copied_animations],
                       'recipient_photo_position': len(photos) - 1,
                       'added_keyframe_types': ['KFTypeScaleX', 'KFTypeScaleY'],
                       'timeline_signature_unchanged': True,
                       'project_duration_unchanged': candidate['duration'] == draft['duration'],
                       'track_count_unchanged': len(candidate['tracks']) == len(draft['tracks']),
                       'media_material_count_unchanged': len(candidate['materials']['videos']) == len(draft['materials']['videos']),
                       'refs_valid_after': after['valid_structure'],
                       'runtime_reopen_tested': False,
                       'actual_render_tested': False}



def bulk_experiment(draft, max_images=1000):
    """Copy existing owner preset metadata to unanimated photos in an independent object.

    Doesn't replace the owner's original video/track/timing data. This is a
    structural stress test only: CapCut UI rendering and resource availability
    must be verified later.
    """
    result=copy.deepcopy(draft)
    checked=audit(result)
    if not checked['valid_structure'] or result.get('version') != 360000:
        raise ValueError('Refusing unsupported or structurally invalid input')
    images=_photo_suitable_segments(result)
    if len(images)>max_images:
        raise ValueError(f'Refusing {len(images)} images above max_images={max_images}')
    idx,_=object_by_id(result)
    source=next((s for s in images if (a := _animation_slot(s, idx)) and a.get('animations')),None)
    if source is None:
        raise ValueError('Need an existing photo preset animation as source')
    original_anims=copy.deepcopy(_animation_slot(source,idx)['animations'])
    changes=0
    created_slots=0
    for image in images:
        if image is source:
            continue
        slot=_animation_slot(image,idx)
        if slot and slot.get('animations'):
            continue
        if slot is None:
            slot={'id':str(uuid.uuid4()).upper(),'type':'sticker_animation',
                  'animations':[],'multi_language_current':'none'}
            result['materials'].setdefault('material_animations',[]).append(slot)
            image.setdefault('extra_material_refs',[]).append(slot['id'])
            created_slots+=1
        slot['animations']=copy.deepcopy(original_anims)
        for item in slot['animations']:
            item['duration']=min(item.get('duration',image['target_timerange']['duration']),
                                 image['target_timerange']['duration'])
        changes+=1
    after=audit(result)
    if not after['valid_structure']:
        raise ValueError('Bulk postcondition failed: '+str(after['errors']))
    def timings(d):
        return [(i,k,s['target_timerange'],s.get('source_timerange'))
                for i,k,_,s in segments(d)]
    if timings(draft)!=timings(result):
        raise AssertionError('Timing unexpectedly changed')
    if result['duration']!=draft['duration']:
        raise AssertionError('Duration unexpectedly changed')
    return result,{'photo_count':len(images),'animations_added':changes,
                   'new_animation_material_slots':created_slots,
                   'timeline_unchanged':True,'all_material_references_valid':True,
                   'capcut_reopen_tested':False,'capcut_export_tested':False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('audit'); a.add_argument('input', type=pathlib.Path)
    e = sub.add_parser('experiment'); e.add_argument('input', type=pathlib.Path)
    e.add_argument('--out', type=pathlib.Path, required=True, help='MUST be a new output file')
    b = sub.add_parser('bulk'); b.add_argument('input',type=pathlib.Path)
    b.add_argument('--out',type=pathlib.Path,required=True, help='New file only')
    b.add_argument('--max-images',type=int,default=1000)
    args = p.parse_args()
    original = args.input.resolve()
    draft = json.loads(original.read_text(encoding='utf-8-sig'))
    if args.cmd == 'audit':
        print(json.dumps(audit(draft), indent=2))
        return 0 if audit(draft)['valid_structure'] else 2
    output = args.out.resolve()
    if output == original:
        p.error('Original overwrite forbidden')
    if output.exists():
        p.error('Output must not already exist')
    before_hash = data_hash(original)
    patched, summary = (experiment(draft) if args.cmd == 'experiment' else bulk_experiment(draft, args.max_images))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as f:
        json.dump(patched, f, ensure_ascii=False, indent=2)
        f.write('\n')
    after_hash = data_hash(original)
    if before_hash != after_hash:
        raise AssertionError('Original file unexpectedly changed!')
    print(json.dumps({'copy_written': str(output), 'summary': summary,
                      'source_sha256_unchanged': True}, indent=2))
    print('WARNING: COPY-ONLY schema experiment, not a verified CapCut-openable or render-tested project.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())