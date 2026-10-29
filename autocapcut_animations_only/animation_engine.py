"""Standalone, image-only native CapCut Combo animation editor.

Only already-used saved-project native Combo resources can be selected.
No source material files, videos, tracks, timing or transitions are edited.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


def default_projects_dir() -> Path:
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'CapCut' / 'User Data' / 'Projects' / 'com.lveditor.draft'


def read_json(path: Path) -> dict:
    val = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(val, dict):
        raise ValueError('Expected a JSON object: '+str(path))
    return val


def find_draft(project: Path) -> Path:
    for name in ('draft_content.json', 'draft_info.json'):
        p = project / name
        if p.is_file():
            return p
    raise FileNotFoundError('Missing CapCut draft in '+str(project))


def list_projects(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    result = []
    for child in root.iterdir():
        if child.is_dir():
            try:
                path = find_draft(child)
                result.append((path.stat().st_mtime_ns, child))
            except (FileNotFoundError, OSError):
                pass
    return [item[1] for item in sorted(result, reverse=True)]


def draft_paths(project: Path) -> tuple[Path, list[Path]]:
    main = find_draft(project)
    paths = [main]
    timeline_index = project / 'Timelines' / 'project.json'
    if timeline_index.is_file():
        idx = read_json(timeline_index)
        timeline_id = idx.get('main_timeline_id')
        if not isinstance(timeline_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', timeline_id):
            raise ValueError('Unsafe main timeline ID')
        mirror = project / 'Timelines' / timeline_id / main.name
        if not mirror.is_file():
            raise ValueError('Active timeline mirror is missing: '+str(mirror))
        paths.append(mirror)
    return paths[-1], paths


def load_project(project: Path) -> tuple[dict, list[Path], list[str]]:
    source, paths = draft_paths(project)
    raw = read_json(source)
    warnings = []
    if len(paths) > 1 and read_json(paths[0]) != raw:
        warnings.append('Top-level draft differs from active mirror; both will be backed up and synchronized using active timeline.')
    return raw, paths, warnings


def image_clips(draft: dict) -> list[dict]:
    """Restrict to genuine CapCut photo segments even when on a video-type track."""
    materials = {m.get('id'):m for m in draft.get('materials',{}).get('videos',[]) if isinstance(m,dict)}
    out = []
    for ti, track in enumerate(draft.get('tracks',[])):
        if track.get('type') != 'video':
            continue
        for si, segment in enumerate(track.get('segments',[])):
            material = materials.get(segment.get('material_id'),{})
            if material.get('type') != 'photo':
                continue
            duration = (segment.get('target_timerange') or {}).get('duration')
            out.append({'track_index':ti,'segment_index':si,'segment_id':segment.get('id'),
                        'material_id':segment.get('material_id'),
                        'name':str(material.get('material_name') or Path(str(material.get('path') or '')).name or 'Unnamed image'),
                        'duration_us':int(duration) if duration is not None else 0})
    return out


def _combo(material: dict, trending_only: bool = True) -> dict | None:
    if not isinstance(material,dict) or material.get('type') != 'sticker_animation':
        return None
    arr = material.get('animations')
    if not isinstance(arr,list) or len(arr) != 1 or not isinstance(arr[0],dict):
        return None
    item=arr[0]
    category=str(item.get('category_name') or '')
    if item.get('type') != 'group' or (trending_only and not category.casefold().startswith('trending')):
        return None
    if not str(item.get('id') or item.get('resource_id') or '') or not item.get('name'):
        return None
    return item


def harvest_animations(root: Path, trending_only: bool = True, *, project: Path | None = None) -> list[dict]:
    """Collect ONLY group animations currently referenced by photo clips in saved drafts."""
    found = {}
    for project in ([project] if project is not None else list_projects(root)):
        try:
            raw,_,_=load_project(project)
            materials={m.get('id'):m for m in raw.get('materials',{}).get('material_animations',[]) if isinstance(m,dict)}
            for clip in image_clips(raw):
                seg=raw['tracks'][clip['track_index']]['segments'][clip['segment_index']]
                for ref in seg.get('extra_material_refs') or []:
                    mat=materials.get(ref)
                    item=_combo(mat, trending_only)
                    if item is None:
                        continue
                    effect_id=str(item.get('resource_id') or item['id'])
                    if effect_id not in found:
                        found[effect_id]={'effect_id':effect_id,'name':str(item['name']),
                                          'category':str(item.get('category_name') or ''),
                                          'duration_us':int(item.get('duration') or 0),
                                          'path':str(item.get('path') or ''),
                                          'template':copy.deepcopy(mat),
                                          'source_project':project.name}
        except (OSError,ValueError,TypeError,KeyError):
            continue
    return sorted(found.values(),key=lambda x:(x['name'].casefold(),x['effect_id']))


def resource_is_available(entry: dict) -> bool:
    # CapCut effects used in source drafts may no longer exist on disk.
    path = str(entry.get('path') or '')
    return bool(path) and Path(path).exists()


def stable_media_fingerprint(draft: dict) -> str:
    """Everything except native Combo materials & their links on PHOTO segments."""
    raw=copy.deepcopy(draft)
    materials=raw.get('materials',{})
    old={m.get('id') for m in materials.get('material_animations',[]) if _combo(m,trending_only=False)}
    materials['material_animations']=[m for m in materials.get('material_animations',[]) if m.get('id') not in old]
    clips=image_clips(raw)
    for c in clips:
        seg=raw['tracks'][c['track_index']]['segments'][c['segment_index']]
        refs=seg.get('extra_material_refs')
        if isinstance(refs,list):
            seg['extra_material_refs']=[r for r in refs if r not in old]
    return hashlib.sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def make_plan(draft: dict, catalog: list[dict], selected: list[tuple[int, int]],
              effect_id: str | None = None, *, mode: str = 'single', seed: int | None = None, fit_to_clip: bool = False, end_gap_us: int = 0) -> tuple[list[dict], list[str]]:
    """Build a read-only per-image plan. Random choices are frozen in returned rows.

    mode='single' uses effect_id; mode='random' uses all catalog entries passed
    by the caller (which may be an explicit selected subset). Video segments are
    never eligible. All used resources must still be present on this PC.
    """
    if mode not in ('single', 'random'):
        raise ValueError('Unknown animation selection mode')
    if not isinstance(end_gap_us, int) or end_gap_us < 0 or (end_gap_us and not fit_to_clip):
        raise ValueError('End gap must be a non-negative integer in fit-to-clip mode')
    options={x['effect_id']:x for x in catalog}
    if mode == 'single' and effect_id not in options:
        raise ValueError('Selected animation is not in saved-project catalog')
    available=[x for x in catalog if resource_is_available(x) and int(x.get('duration_us') or 0)>0]
    if mode == 'random' and not available:
        raise ValueError('No locally available used animations for random mode')
    rng=random.Random(seed)
    clips={(c['track_index'],c['segment_index']):c for c in image_clips(draft)}
    rows=[];warnings=[]
    source_sha=hashlib.sha256(json.dumps(draft,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if not selected:
        warnings.append('No images selected.')
    previous_id=None
    for key in dict.fromkeys(selected):
        clip=clips.get(key)
        if clip is None:
            rows.append({'track_index':key[0],'segment_index':key[1], 'status':'Skipped', 'reason':'Not a photo segment'})
            continue
        if mode == 'single':
            entry=options[effect_id]
        else:
            pool=[e for e in available if e['effect_id'] != previous_id] if len(available)>1 else available
            entry=rng.choice(pool)
        duration_us=max(0, int(clip['duration_us']) - end_gap_us) if fit_to_clip else min(int(clip['duration_us']), int(entry.get('duration_us') or 0))
        row={**clip, 'fit_to_clip': fit_to_clip, 'end_gap_us': end_gap_us if fit_to_clip else 0, 'effect_id':entry['effect_id'], 'animation':entry['name'],
             'native_duration_us':int(entry.get('duration_us') or 0), 'applied_duration_us':duration_us, '_preview_source_sha':source_sha}
        if duration_us <= 0 or int(entry.get('duration_us') or 0) <= 0:
            row.update(status='Skipped',reason='Image is too short for requested animation end gap' if fit_to_clip and int(clip['duration_us']) <= end_gap_us else 'Invalid/zero image or animation duration')
        elif not resource_is_available(entry):
            row.update(status='Missing',reason='Original CapCut effect cache resource is unavailable on this PC')
        else:
            adjustment=(f' (ends {end_gap_us/1_000_000:g}s before image end)' if fit_to_clip and end_gap_us else
                        ' (shortened to fit image)' if duration_us < row['native_duration_us'] else '')
            row.update(status='Will Apply',reason=f"{entry['name']} — {duration_us/1e6:g}s{adjustment}")
            previous_id=entry['effect_id']
        rows.append(row)
    return rows,warnings


def apply_animation(draft: dict, catalog: list[dict], effect_id: str | None, rows: list[dict]) -> tuple[dict,dict]:
    """Apply the frozen plan without changing media, video tracks or timings."""
    valid=[x for x in rows if x.get('status')=='Will Apply']
    source=copy.deepcopy(draft)
    output=copy.deepcopy(draft)
    options={x['effect_id']:x for x in catalog}
    mats=output.setdefault('materials',{}).setdefault('material_animations',[])
    old_by_id={m.get('id'):m for m in mats if isinstance(m,dict)}
    count=0;already=0
    seen=set()
    images={(x['track_index'],x['segment_index']):x for x in image_clips(output)}
    for row in valid:
        ti,si=row['track_index'],row['segment_index']
        key=(ti,si)
        if key in seen:
            raise ValueError('Duplicate target image in preview')
        seen.add(key)
        current_image=images.get(key)
        if current_image is None or any(current_image.get(k)!=row.get(k)
                                        for k in ('segment_id','material_id','duration_us')):
            raise ValueError('Image clip identity changed since preview')
        chosen_id=row.get('effect_id',effect_id)
        entry=options.get(chosen_id)
        if entry is None:
            raise ValueError('Animation disappeared from the available catalog')
        end_gap_us=row.get('end_gap_us', 0)
        if not isinstance(end_gap_us, int) or end_gap_us < 0 or (end_gap_us and not row.get('fit_to_clip')):
            raise ValueError('Invalid animation end gap in preview')
        duration_us=max(0, int(current_image['duration_us']) - end_gap_us) if row.get('fit_to_clip') else min(int(current_image['duration_us']),int(entry.get('duration_us') or 0))
        if duration_us<=0 or int(entry.get('duration_us') or 0)<=0 or duration_us != int(row.get('applied_duration_us',duration_us)):
            raise ValueError('Animation duration changed since preview')
        segment=output['tracks'][ti]['segments'][si]
        refs=segment.get('extra_material_refs') or []
        if not isinstance(refs,list):
            raise ValueError('Unexpected extra_material_refs format')
        linked=[r for r in refs if _combo(old_by_id.get(r),trending_only=False)]
        if len(linked)==1:
            current=_combo(old_by_id[linked[0]],trending_only=False)
            if str(current.get('resource_id') or current.get('id'))==chosen_id and int(current.get('duration') or 0)==duration_us and (not row.get('fit_to_clip') or int(current.get('start') or 0)==0):
                already+=1;continue
        clone=copy.deepcopy(entry['template'])
        clone['id']=str(uuid.uuid4()).upper()
        # Retiming is limited to the nested native Combo animation duration.
        # Keep all downloaded resource IDs, cached paths and timeline durations
        # unchanged. Actual CapCut visual acceptance on short clips is pending.
        native=_combo(clone,trending_only=False)
        if native is None:
            raise ValueError('Invalid native Combo material template')
        native['duration']=duration_us
        if row.get('fit_to_clip') and 'start' in native:
            native['start']=0
        mats.append(clone)
        segment['extra_material_refs']=[r for r in refs if r not in linked]+[clone['id']]
        count+=1
    if stable_media_fingerprint(output)!=stable_media_fingerprint(source):
        raise AssertionError('Non-animation or video/timing/transition data was altered')
    return output,{'changed':count,'already_matching':already,'targets':len(valid)}

def capcut_running() -> bool:
    if sys.platform!='win32':
        return False
    try:
        r=subprocess.run(['tasklist','/FI','IMAGENAME eq CapCut.exe','/NH'],capture_output=True,text=True,timeout=6,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return bool(re.search(r'(^|\s)CapCut\.exe\s',r.stdout,re.I|re.M))
    except (OSError,subprocess.TimeoutExpired):
        return True


def _atomic(path: Path, content: bytes) -> None:
    fd,tmp=tempfile.mkstemp(prefix='.animations_only_',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def save(project: Path, catalog: list[dict], effect_id: str, preview: list[dict]) -> dict:
    """Backs up and changes only native animation JSON; CapCut must be closed."""
    if capcut_running():
        raise RuntimeError('CapCut is open. Close it before applying animations.')
    if not any(r.get('status')=='Will Apply' for r in preview):
        raise ValueError('No valid image animations to apply')
    catalog_by_id={e['effect_id']:e for e in catalog}
    for row in preview:
        if row.get('status')!='Will Apply':
            continue
        entry=catalog_by_id.get(row.get('effect_id',effect_id))
        if entry is None or not resource_is_available(entry):
            raise ValueError('One or more selected native animation resources are no longer available')
    project=project.resolve()
    lock=project/'.autocapcut_animations_only.lock'
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError as e:
        raise RuntimeError('Another animation operation is running') from e
    try:
        os.close(fd)
        source,paths,_=load_project(project)
        actual_clips={(x['track_index'],x['segment_index']):x for x in image_clips(source)}
        actual_sha=hashlib.sha256(json.dumps(source,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        for row in preview:
            if row.get('status')=='Will Apply' and row.get('_preview_source_sha') and actual_sha != row['_preview_source_sha']:
                raise RuntimeError('CapCut draft changed since preview. Refresh and validate again.')
            if row.get('status')!='Will Apply':continue
            current=actual_clips.get((row['track_index'],row['segment_index']))
            if not current or any(current.get(k)!=row.get(k) for k in ('segment_id','material_id','duration_us')):
                raise RuntimeError('Image clip changed since preview. Refresh first.')
            entry=catalog_by_id[row.get('effect_id',effect_id)]
            end_gap_us=row.get('end_gap_us', 0)
            if not isinstance(end_gap_us, int) or end_gap_us < 0 or (end_gap_us and not row.get('fit_to_clip')):
                raise RuntimeError('Invalid animation end gap in preview')
            expected_duration=max(0, current['duration_us'] - end_gap_us) if row.get('fit_to_clip') else min(current['duration_us'],int(entry.get('duration_us') or 0))
            if expected_duration<=0 or int(entry.get('duration_us') or 0)<=0 or expected_duration!=row.get('applied_duration_us',expected_duration):
                raise RuntimeError('Animation duration changed since preview; refresh first.')
        output,stats=apply_animation(source,catalog,effect_id,preview)
        if not stats['changed']:
            return {**stats,'saved':False,'backup_dir':None}
        writes={p:json.dumps(output,ensure_ascii=False,separators=(',',':')).encode('utf-8') for p in paths}
        meta=project/'draft_meta_info.json'
        now_us=int(datetime.now(timezone.utc).timestamp()*1_000_000)
        if meta.is_file():
            m=read_json(meta);m['tm_draft_modified']=now_us
            writes[meta]=json.dumps(m,ensure_ascii=False,separators=(',',':')).encode()
        root=project.parent/'root_meta_info.json'
        if root.is_file():
            root_data=read_json(root)
            norm=str(project).replace('\\','/').rstrip('/').casefold()
            target=None
            for x in root_data.get('all_draft_store') or []:
                if str(x.get('draft_fold_path') or '').replace('\\','/').rstrip('/').casefold()==norm:
                    target=x;break
            if target is not None:
                target['tm_draft_modified']=now_us
                writes[root]=json.dumps(root_data,ensure_ascii=False,separators=(',',':')).encode()
        originals={path:path.read_bytes() for path in writes}
        backup=project/'.animations_only_backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        backup.mkdir(parents=True,exist_ok=False)
        manifest=[]
        for i,(path,data) in enumerate(originals.items()):
            name=f'{i:02d}_{path.name}'
            (backup/name).write_bytes(data)
            manifest.append({'original':str(path),'backup':name,'sha256':hashlib.sha256(data).hexdigest()})
        (backup/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        if capcut_running():
            raise RuntimeError('CapCut opened after backup; no changes written')
        for path,orig in originals.items():
            if path.read_bytes()!=orig:
                raise RuntimeError('Project changed during operation; no changes written')
        written=[]
        try:
            for path,data in writes.items():
                _atomic(path,data);written.append(path)
            fresh,_,_=load_project(project)
            if fresh!=output or stable_media_fingerprint(fresh)!=stable_media_fingerprint(source):
                raise RuntimeError('Post-write verification failed')
        except BaseException:
            for path in reversed(written):
                _atomic(path,originals[path])
            raise
        return {**stats,'saved':True,'backup_dir':str(backup)}
    finally:
        lock.unlink(missing_ok=True)