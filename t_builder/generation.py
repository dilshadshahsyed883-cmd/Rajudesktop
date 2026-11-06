"""Verified native CapCut export using the isolated V6.3 writer."""
from pathlib import Path
import json
import math
import os
import subprocess
import tempfile
import sys
from z_builder.capcut import probe, find_node as system_node


def find_node():
    bundled=Path(__file__).resolve().parents[1]/'.runtime'/'node'/'node.exe'
    if bundled.is_file():return str(bundled)
    if getattr(sys,'frozen',False):raise RuntimeError('Bundled Node runtime is missing from T_Builder.exe')
    return system_node()
from .timeline import plan_timeline, validate_timeline


def audio_duration(path):
    p=Path(path).resolve(strict=True)
    if not p.is_file():raise ValueError('Select an existing audio file')
    try:
        import mutagen
        media=mutagen.File(p)
        duration=float(media.info.length)
    except Exception:
        duration=float(probe(str(p))['duration'])
    if not math.isfinite(duration) or duration<=0: raise ValueError('Unable to read audio duration')
    return duration


def prepare(catalog, selected_root, audio, images, videos, coverage, name, drafts, log=lambda s:None, seed=None):
    audio=str(Path(audio).resolve(strict=True))
    if not name.strip() or name.strip() in ('.','..') or any(x in name for x in '\\/:*?"<>|'):
        raise ValueError('Enter a valid new project name')
    root=Path(selected_root).resolve(strict=True)
    if str(root) not in catalog.roots(): raise ValueError('Select an imported library folder')
    if not str(drafts).strip():raise ValueError('Select a CapCut draft destination')
    dest=Path(drafts).expanduser().resolve()
    if not dest.is_dir(): raise ValueError('Select an existing CapCut draft destination')
    if not find_node(): raise ValueError('Bundled Node runtime is missing')
    duration=audio_duration(audio)
    assets=[a for a in catalog.assets(False) if Path(a['path']).resolve().is_relative_to(root)]
    if videos is not None and coverage:
        for a in assets:
            if a['kind']=='video' and videos.get(a['keyword'],0) and not a['used']:
                log(f"Probing video: {a['filename']}")
                a['duration']=probe(a['path'])['duration']
    t=plan_timeline(assets,duration,images,videos,coverage,seed)
    from collections import Counter
    log('Image keyword allocation: '+str(dict(Counter(c.keyword for c in t.images))))
    if t.videos:
        log('Video keyword allocation: '+str(dict(Counter(c.keyword for c in t.videos))))
        log(f'Actual video coverage: {sum(c.duration for c in t.videos)/t.duration*100:.6f}%')
    log(f'Planned {len(t.images)} images, {len(t.videos)} videos; audio {duration:.6f}s')
    for warning in t.warnings: log('Warning: '+warning)
    return t,audio,dest,name.strip()


def write_native(t, audio, drafts, name, launch=False):
    validate_timeline(t)
    clips=[];media={}
    for c in t.images+t.videos:
        info=media.setdefault(c.path,probe(c.path))
        if not Path(c.path).is_file(): raise ValueError(f'Missing moved media: {c.path}')
        clips.append({'image':c.path,'kind':c.kind,'start':c.start/1e6,'end':c.end/1e6,
                      'trimStart':c.trim/1e6,'muted':True,'hasAudio':False,'zoom':'none'})
    media[audio]={'duration':t.duration/1e6,'hasAudio':True}
    req={'payload':{'name':name,'W':1920,'H':1080,'fps':30,'separateLayers':True,
          'images':clips,'voice':{'file':audio,'start':0,'dur':t.duration/1e6,'volume':1},'captions':[]},
          'media':media,'drafts_root':str(drafts),'launch':False}
    with tempfile.TemporaryDirectory(prefix='tb-draft-') as directory:
        src,out=Path(directory)/'request.json',Path(directory)/'result.json'
        src.write_text(json.dumps(req),encoding='utf-8')
        result=subprocess.run([find_node(),str(Path(__file__).with_name('capcut_bridge.js')),str(src),str(out)],
              capture_output=True,text=True,timeout=1800,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        data=json.loads(out.read_text()) if out.exists() else {}
        if result.returncode or data.get('verify_issues') or not data.get('folder'):
            raise RuntimeError(f"Draft creation/verification failed at {data.get('folder','unknown')}: {data.get('verify_issues',[])} {result.stderr[-2500:]}")
    folder=Path(data['folder'])
    verify_native(folder,t,audio)
    (folder/'T_Builder_Timeline.json').write_text(json.dumps(t.to_dict(),indent=2),encoding='utf-8')
    # Launch only after both native and T Builder validations have passed.
    data['launched']=False
    if launch:
        script="const e=require(process.argv[1]);const d=e.detect();process.exit(d.exe&&e.launch(d.exe)?0:3);"
        p=subprocess.run([find_node(),'-e',script,str(Path(__file__).with_name('capcut-draft.js'))],capture_output=True,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        data['launched']=p.returncode==0
    return data


def verify_native(folder,t,audio):
    raw=json.loads((Path(folder)/'draft_content.json').read_text(encoding='utf-8'))
    timeline=Path(folder)/'Timelines'/raw['id']/'draft_content.json'
    if json.loads(timeline.read_text(encoding='utf-8'))!=raw: raise ValueError('Timeline content differs')
    if abs(raw['duration']-t.duration)>1000: raise ValueError('Draft duration differs from audio')
    mats={m['id']:m for kind in ('videos','audios') for m in raw['materials'][kind]}
    visual=[tr for tr in raw['tracks'] if tr['type']=='video']
    expected=[('Images - Lower Layer',t.images)]+([('Videos - Upper Layer',t.videos)] if t.videos else [])
    if len(visual)!=len(expected): raise ValueError('Wrong visual track count')
    # Two editable video/image tracks are permitted, but their combined
    # visible ranges must form ONE continuous, non-overlapping sequence.
    merged=sorted((s['target_timerange']['start'],s['target_timerange']['duration'])
                  for track in visual for s in track['segments'])
    cursor=0
    for start,duration in merged:
        if start!=cursor or duration<=0:
            raise ValueError('Native draft contains image/video overlap or an uncovered gap')
        cursor+=duration
    if cursor!=t.duration: raise ValueError('Native visual sequence misses narration endpoint')
    for tr,(name,clips) in zip(visual,expected):
        if tr['name']!=name or len(tr['segments'])!=len(clips): raise ValueError('Wrong layer placement')
        for s,c in zip(tr['segments'],clips):
            m=mats[s['material_id']]
            if Path(m['path']).resolve()!=Path(c.path).resolve(): raise ValueError('Draft must reference actual moved path')
            if abs(s['target_timerange']['start']-c.start)>1000 or abs(s['target_timerange']['duration']-c.duration)>1000:
                raise ValueError('Draft timing changed')
            if c.kind=='video' and (s['volume']!=0 or abs(s['source_timerange']['start']-c.trim)>1000):
                raise ValueError('Video mute or source trim changed')
    aud=[s for tr in raw['tracks'] if tr['type']=='audio' for s in tr['segments']]
    if len(aud)!=1 or Path(mats[aud[0]['material_id']]['path']).resolve()!=Path(audio).resolve():
        raise ValueError('Narration track missing')
    if aud[0]['target_timerange']['start']!=0 or abs(aud[0]['target_timerange']['duration']-t.duration)>1000:
        raise ValueError('Narration timing changed')
    for m in mats.values():
        if not Path(m['path']).is_file(): raise ValueError('Draft references missing media')
    return raw


def generate(catalog, prepared, launch=True, log=lambda s:None):
    t,audio,drafts,name=prepared
    catalog.remember_drafts(drafts)
    journal=catalog.db_path.parent/'last_generation.json'
    journal.write_text(json.dumps({'status':'moving','timeline':t.to_dict()},indent=2),encoding='utf-8')
    selected_originals={c.path for c in t.images+t.videos}
    try:
        mapping=catalog.move_selected(t,log)
        log('Writing editable native CapCut draft...')
        result=write_native(t,audio,drafts,name,launch)
        catalog.mark_project(mapping.values(),result['folder'])
        journal.write_text(json.dumps({'status':'verified','result':result,'timeline':t.to_dict()},indent=2),encoding='utf-8')
        log('Verified project: '+result['folder'])
        if launch and not result['launched']: log('CapCut could not be launched. Open the verified project from CapCut Home.')
        return result
    except Exception as exc:
        with catalog._connect() as c:
            moved=[dict(zip(('path','original','project','status'),r)) for r in c.execute('SELECT * FROM moves') if r[1] in selected_originals and Path(r[0]).is_file()]
        report={'status':'incomplete','error':str(exc),'moved_files_still_in_used':moved}
        journal.write_text(json.dumps(report,indent=2),encoding='utf-8')
        raise RuntimeError(f'Generation incomplete: {exc}\nMoved media remains in used/. Accurate move report: {journal}') from exc
