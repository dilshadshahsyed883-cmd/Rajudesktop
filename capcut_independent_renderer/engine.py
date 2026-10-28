"""Standalone, read-only CapCut draft -> basic FFmpeg MP4 renderer.

This is intentionally NOT a CapCut-equivalent renderer. Unknown features are reported.
Requires a recent ffmpeg/ffprobe executable on PATH or alongside the app.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable
from collections import Counter
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import threading
import urllib.parse
import unicodedata
import hashlib
from captions import parse_caption, write_ass, filter_path
from fontinfo import read_font, fallback_font
from effects import parse_effect

VIDEO_EXTS = {'.mp4','.mov','.mkv','.avi','.webm','.m4v','.ts','.mts','.mpg','.mpeg'}
IMAGE_EXTS = {'.jpg','.jpeg','.png','.webp','.bmp','.tiff','.gif'}
AUDIO_EXTS = {'.mp3','.m4a','.wav','.flac','.aac','.ogg','.opus','.wma'}
DRAFT_NAMES = ('draft_content.json','draft_info.json')
MICROS = 1_000_000


def executable(name: str) -> str | None:
    candidate = Path(__file__).resolve().parent / 'tools' / (name + ('.exe' if os.name == 'nt' else ''))
    return str(candidate) if candidate.is_file() else shutil.which(name)


def safe_name(s: str) -> str:
    s = unicodedata.normalize('NFKC',str(s))
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_',s).strip(' .')[:85] or 'Project'
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',name): name='_'+name
    return name


def num(x, default=0):
    try:
        y=float(x)
        return y if math.isfinite(y) else default
    except (ValueError,TypeError):
        return default


def asdict_safe(v):
    return v if isinstance(v,dict) else {}


def aslist(v):
    return v if isinstance(v,list) else []


@dataclass
class Segment:
    track: int
    kind: str
    start: float
    end: float
    path: str
    source_start: float
    speed: float
    volume: float
    material_type: str
    transform_x: float = 0.0
    transform_y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0
    flip_x: bool = False
    flip_y: bool = False
    alpha: float = 1.0
    identifier: str = ''


class Draft:
    def __init__(self, source: str, media_folder: str = ''):
        p = Path(source).expanduser().resolve()
        if p.is_dir():
            candidates = [p / x for x in DRAFT_NAMES]
            p = next((x for x in candidates if x.is_file()), candidates[0])
        if not p.is_file():
            raise FileNotFoundError(f'No draft JSON at: {p}')
        self.path = p
        self.root = p.parent
        try:
            content=p.read_bytes()
            self.source_sha256=hashlib.sha256(content).hexdigest()
            self.raw = json.loads(content.decode('utf-8-sig'))
        except (OSError, ValueError, UnicodeError) as e:
            raise ValueError(f'Cannot parse draft JSON ({p.name}). It may be encrypted or invalid: {e}') from e
        if not isinstance(self.raw,dict) or not isinstance(self.raw.get('tracks'),list):
            raise ValueError('This is not a recognized CapCut draft (tracks array not found).')
        self.name = str(self.raw.get('name') or self.root.name)
        self.media_folder = Path(media_folder).resolve() if media_folder else None
        canvas = asdict_safe(self.raw.get('canvas_config'))
        self.width = int(num(canvas.get('width') or self.raw.get('width'),1920))
        self.height = int(num(canvas.get('height') or self.raw.get('height'),1080))
        if self.width < 64 or self.height < 64 or self.width > 16384 or self.height > 16384:
            self.width,self.height=1920,1080
        self.fps = max(1,min(60,int(num(self.raw.get('fps'),30))))
        self.warnings=[]
        self.missing=[]
        self.segments=[]
        self.captions=[]
        self.caption_errors=[]
        self.font_files=[]
        self.font_status=[]
        self._font_cache={}
        self.effects=[]
        self.effect_errors=[]
        self.animation_empty=0
        self.animation_active=0
        self._index = None
        self._parse()

    def _resolve(self, value: str) -> str | None:
        if not value or not isinstance(value,str): return None
        raw=value.strip().strip('"')
        if raw.lower().startswith('file://'):
            raw=urllib.parse.unquote(urllib.parse.urlsplit(raw).path)
            if os.name == 'nt' and re.match(r'^/[a-zA-Z]:/',raw): raw=raw[1:]
        raw = os.path.expandvars(raw)
        candidates=[Path(raw), self.root / raw, self.root / raw.replace('\\','/')]
        if self.media_folder:
            candidates += [self.media_folder / raw, self.media_folder / raw.replace('\\','/')]
        for candidate in candidates:
            if candidate.is_file(): return str(candidate.resolve())
        # Windows absolute paths on other machines cannot be tested under POSIX,
        # and the source asset may have been moved to a media folder.
        basename=raw.replace('\\','/').split('/')[-1]
        if basename:
            for folder in (self.root, self.media_folder):
                if folder:
                    for candidate in (folder/basename, folder/'assets'/basename):
                        if candidate.is_file(): return str(candidate.resolve())
            if self._index is None:
                self._index={}
                for folder in (self.root,self.media_folder):
                    if folder and folder.exists():
                        for base, dirs, files in os.walk(folder):
                            dirs[:] = [d for d in dirs if d not in ('.git','node_modules','__pycache__')]
                            for file in files:
                                self._index.setdefault(file.casefold(), []).append(str(Path(base)/file))
            matches=self._index.get(basename.casefold(),[])
            if len(matches)==1: return matches[0]
            if len(matches)>1:
                self.warnings.append(f'Ambiguous media basename {basename!r}; found {len(matches)} copies. Please relink explicitly.')
        return None

    def _caption_font(self,caption):
        requested=caption.font_path
        if requested not in self._font_cache:
            resolved=self._resolve(requested) if requested else None
            original=bool(resolved)
            resolved=resolved or fallback_font()
            family=caption.font
            if resolved:
                try:family=read_font(resolved).family
                except Exception:
                    original=False
                    resolved=fallback_font()
                    if resolved: family=read_font(resolved).family
            status={'requested_path':requested,'resolved_path':resolved or '',
                    'family':family,'status':'source_font' if original else 'system_fallback'}
            self._font_cache[requested]=status
            self.font_status.append(status)
            if resolved:self.font_files.append(resolved)
            if not original and requested:
                self.warnings.append('Requested caption font unavailable/unreadable; a system fallback is used. Check font_status.')
        status=self._font_cache[requested]
        caption.font_path=status['resolved_path']
        caption.font=re.sub(r'[\x00-\x1f,{}\\]','',status['family'])[:100] or 'Arial'

    @staticmethod
    def _companion_active(group,material,segment):
        if group=='material_animations':return bool(material.get('animations'))
        if group=='speeds':return bool(material.get('curve_speed'))
        if group=='canvases':return bool(material.get('color') or material.get('image') or num(material.get('blur')))
        if group=='material_colors':return bool(material.get('is_color_clip') or material.get('is_gradient'))
        if group=='vocal_separations':return num(material.get('choice'))!=0
        if group=='sound_channel_mappings':return material.get('type','none')!='none' or num(material.get('audio_channel_mapping'))!=0
        if group=='placeholder_infos':return material.get('meta_type','none')!='none'
        if group=='beats':return False  # analysis metadata, not an active video effect
        return True

    def _parse(self):
        materials = asdict_safe(self.raw.get('materials'))
        lookup = {}
        for name in materials:
            for m in aslist(materials.get(name)):
                if isinstance(m,dict) and m.get('id'):
                    lookup[str(m['id'])] = (name,m)
        max_end = 0.0
        dropped = Counter()
        for track_no,t in enumerate(aslist(self.raw['tracks'])):
            if not isinstance(t,dict): continue
            tt = str(t.get('type') or '').lower()
            for seg in aslist(t.get('segments')):
                if not isinstance(seg,dict): continue
                target=asdict_safe(seg.get('target_timerange'))
                start=max(0,num(target.get('start'))/MICROS)
                dur=max(0,num(target.get('duration'))/MICROS)
                if dur<=0: continue
                end=start+dur
                max_end=max(max_end,end)
                if seg.get('visible') is False:continue
                material_type,m=lookup.get(str(seg.get('material_id') or ''),('',{}))
                if tt=='text':
                    try:
                        caption, notes=parse_caption(m,seg,start,end,track_no)
                        self.captions.append(caption)
                        self.warnings.extend(notes)
                        self._caption_font(caption)
                        if seg.get('common_keyframes') or seg.get('keyframe_refs'):
                            self.warnings.append('Caption keyframe animation is not reproduced.')
                    except ValueError as error:
                        self.caption_errors.append(f'Text segment {seg.get("id", "?")}: {error}')
                    continue
                if tt=='effect':
                    try:
                        effect=parse_effect(m,seg,start,end)
                        self.effects.append(effect)
                        self.warnings.append(f'Effect {effect.name}: independent FFmpeg approximation, not native CapCut or HDR10 output. See effect_mappings.')
                    except ValueError as error:
                        self.effect_errors.append(str(error))
                        self.warnings.append('Unsupported effect: '+str(error))
                        dropped['effect']+=1
                    continue
                if tt not in ('video','image','audio'):
                    dropped[tt or 'unknown']+=1
                    continue
                if not m:
                    self.missing.append(f'{tt} segment {seg.get("id","?")}: material ID not found')
                    continue
                raw_path=next((m.get(k) for k in ('path','file_path','local_path','source','media_path','source_path') if isinstance(m.get(k),str) and m.get(k)),None)
                if not raw_path:
                    self.missing.append(f'{tt} segment: no media path in material {m.get("id")}')
                    continue
                p=self._resolve(raw_path)
                if not p:
                    self.missing.append(f'Missing media: {raw_path}')
                    continue
                if tt=='audio' or material_type=='audios': kind='audio'
                elif Path(p).suffix.lower() in IMAGE_EXTS or str(m.get('type','')).lower() in ('photo','image'): kind='image'
                else: kind='video'
                if Path(p).suffix.lower() not in VIDEO_EXTS|IMAGE_EXTS|AUDIO_EXTS:
                    self.warnings.append(f'Unusual media format: {p}')
                source=asdict_safe(seg.get('source_timerange'))
                clip=asdict_safe(seg.get('clip'))
                tr=asdict_safe(clip.get('transform'))
                sc=asdict_safe(clip.get('scale'))
                flip=asdict_safe(clip.get('flip'))
                speed=max(.05,min(25,num(seg.get('speed'),1)))
                self.segments.append(Segment(track_no,kind,start,end,p,max(0,num(source.get('start'))/MICROS),speed,
                    max(0,min(3,num(seg.get('volume'),1))),material_type,
                    num(tr.get('x')),num(tr.get('y')),max(.02,min(12,num(sc.get('x'),1))),
                    max(.02,min(12,num(sc.get('y'),1))),num(clip.get('rotation')),
                    bool(flip.get('horizontal')),bool(flip.get('vertical')),
                    max(0,min(1,num(clip.get('alpha'),1))),str(seg.get('id') or '')))
                if seg.get('reverse'): self.warnings.append(f'Reverse clip is not reproduced: {seg.get("id")}')
                if seg.get('common_keyframes') or seg.get('keyframe_refs'):
                    self.warnings.append(f'Keyframe animation is not reproduced: {seg.get("id")}')
                refs=[lookup.get(str(ref),('',{})) for ref in aslist(seg.get('extra_material_refs'))]
                if any(self._companion_active(group,material,seg) for group,material in refs):
                    self.warnings.append(f'Clip companion effects/animations may be omitted: {seg.get("id")}')
                for feature in ('audio_fade','mask','color_adjust','curve_speed'):
                    if seg.get(feature): self.warnings.append(f'Unsupported segment feature {feature}: {seg.get("id")}')
        animations=aslist(materials.get('material_animations'))
        self.animation_active=sum(bool(m.get('animations')) for m in animations if isinstance(m,dict))
        self.animation_empty=len(animations)-self.animation_active
        if self.animation_active:self.warnings.append(f'Unsupported CapCut materials: material_animations ({self.animation_active})')
        for name in ('transitions','filters','stickers','masks','color_curves','text_templates'):
            n=len(aslist(materials.get(name)))
            if n: self.warnings.append(f'Unsupported CapCut materials: {name} ({n})')
        for tt,n in dropped.items(): self.warnings.append(f'Unsupported track type {tt}: {n} segments skipped')
        if self.captions:
            self.warnings.append('Caption background padding/radius, font sizing, rich styles and layer order are approximate; source colors and available font files are used, captions above media.')
        self.duration=max(max_end,num(self.raw.get('duration'))/MICROS)
        if self.duration <=0: raise ValueError('Draft has zero timeline duration.')
        if self.duration >12*3600: raise ValueError('Timeline exceeds safety limit (12 hours).')
        self.warnings=list(dict.fromkeys(self.warnings))
        self.missing=list(dict.fromkeys(self.missing))

    def summary(self):
        kinds=Counter(s.kind for s in self.segments)
        companion_count=sum('Clip companion effects/animations may be omitted:' in w for w in self.warnings)
        unsupported=[w for w in self.warnings if w.startswith(('Unsupported CapCut materials:', 'Unsupported track type'))]
        return {'name':self.name,'draft_file':str(self.path),'duration_seconds':round(self.duration,3),
            'size':[self.width,self.height],'fps':self.fps,'video_segments':kinds['video'],
            'image_segments':kinds['image'],'audio_segments':kinds['audio'],
            'media_status':'MISSING' if self.missing else 'READY',
            'supported_media_segments':len(self.segments),
            'text_segments_parsed':len(self.captions),'text_segments_unparsed':len(self.caption_errors),
            'caption_backgrounds':sum(bool(c.background_color and c.background_alpha>0) for c in self.captions),
            'font_status':self.font_status,
            'animation_materials_empty':self.animation_empty,'animation_materials_active':self.animation_active,
            'effects_mapped':len(self.effects),'effect_mappings':[e.summary() for e in self.effects],
            'effects_unmapped':self.effect_errors,
            'caption_errors':self.caption_errors,
            'render_readiness':'BLOCKED' if self.missing or self.caption_errors else 'READY_WITH_LIMITATIONS' if self.warnings else 'READY',
            'capcut_companion_effect_warnings':companion_count,
            'unsupported_feature_summary':unsupported,
            'missing':self.missing,'warnings':self.warnings,
            'audio_note':('No separate audio track parsed; video clips may still have audio. '
                          'A silent output is possible. Check the MP4 manually.' if kinds['audio']==0 else
                          'Audio clips detected; verify synchronization in playback.'),
            'notes':'Independent approximation; not a pixel-exact CapCut render.'}


def get_dimensions(draft:Draft, preset:str):
    w,h=draft.width,draft.height
    if preset=='Test 480p': limit=854
    elif preset=='720p': limit=1280
    elif preset=='1080p': limit=1920
    else: limit=8192
    scale=min(1.0,limit/max(w,h))
    return max(2,int(w*scale)//2*2), max(2,int(h*scale)//2*2)


def run_command(args, log, cancel:threading.Event, expected_file=None, cwd=None):
    """Run FFmpeg with responsive cancellation and bounded error diagnostics."""
    if cancel.is_set(): raise InterruptedError('Cancelled')
    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    with tempfile.TemporaryFile(mode='w+t', encoding='utf-8', errors='replace') as stderr:
        proc=subprocess.Popen(args, stdout=subprocess.DEVNULL,stderr=stderr,
                              stdin=subprocess.DEVNULL,creationflags=creationflags,cwd=cwd)
        try:
            while proc.poll() is None:
                if cancel.is_set():
                    proc.terminate()
                    try: proc.wait(timeout=3)
                    except subprocess.TimeoutExpired: proc.kill();proc.wait()
                    raise InterruptedError('Cancelled')
                time.sleep(0.12)
            if proc.returncode!=0 or (expected_file and (not Path(expected_file).exists() or Path(expected_file).stat().st_size<100)):
                stderr.seek(0)
                tail=stderr.readlines()[-16:]
                raise RuntimeError(f'FFmpeg command failed (code {proc.returncode}):\n'+''.join(tail))
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def has_audio(path, ffprobe, cache, cancel):
    if path in cache:return cache[path]
    if cancel.is_set(): raise InterruptedError('Cancelled')
    try:
        p=subprocess.run([ffprobe,'-v','error','-select_streams','a','-show_entries','stream=index',
                          '-of','csv=p=0',path],text=True,capture_output=True,timeout=15,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if p.returncode:
            raise RuntimeError('Could not inspect source audio: '+p.stderr[-500:])
        cache[path] = bool(p.stdout.strip())
    except (OSError,subprocess.TimeoutExpired) as error:
        raise RuntimeError(f'Could not inspect source audio: {path}: {error}') from error
    return cache[path]


def audio_tempo(speed):
    factors=[]
    while speed>2.0: factors.append(2.0);speed/=2.0
    while speed<.5: factors.append(.5);speed/= .5
    factors.append(speed)
    return ','.join('atempo=%.7f'%n for n in factors)


def make_chunk(ffmpeg,ffprobe,active,begin,end,w,h,fps,out,cache,cancel,subtitle=None,effects=()):
    dur=end-begin
    args=[ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-y',
          '-f','lavfi','-i',f'color=c=black:s={w}x{h}:r={fps}:d={dur:.6f}']
    filters=['[0:v]format=yuv420p[base0]']
    video_layers=[]
    audio_layers=[]
    input_index=1
    for seg in sorted(active,key=lambda s:s.track):
        offset=max(0,seg.source_start+(begin-seg.start)*seg.speed)
        # same input can feed video and audio streams
        if seg.kind=='image': args+=['-loop','1','-framerate',str(fps),'-i',seg.path]
        else: args+=['-ss',f'{offset:.6f}','-i',seg.path]
        idx=input_index
        input_index+=1
        if seg.kind!='audio':
            outtag=f'v{idx}'
            sx=seg.scale_x
            sy=seg.scale_y
            tw=max(2,round(w*sx/2)*2)
            th=max(2,round(h*sy/2)*2)
            if seg.track==min((v.track for v in active if v.kind!='audio'),default=seg.track):
                # fill canvas on lower visual track (a sensible rough default)
                filt=f'[{idx}:v]setpts=(PTS-STARTPTS)/{seg.speed:.8f},fps={fps},format=rgba,scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}'
            else:
                filt=f'[{idx}:v]setpts=(PTS-STARTPTS)/{seg.speed:.8f},fps={fps},format=rgba,scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=black@0'
            if seg.flip_x: filt+=',hflip'
            if seg.flip_y: filt+=',vflip'
            if abs(seg.rotation)>0.01:
                filt+=f',rotate={seg.rotation:.5f}*PI/180:ow=rotw({seg.rotation:.5f}*PI/180):oh=roth({seg.rotation:.5f}*PI/180):c=black@0'
            filt+=f',tpad=stop_mode=clone:stop_duration=1,trim=duration={dur:.6f},setpts=PTS-STARTPTS,format=rgba'
            if seg.alpha<.999:
                filt+=f',colorchannelmixer=aa={seg.alpha:.6f}'
            filters.append(filt+f'[{outtag}]')
            x=f'(W-w)/2+({seg.transform_x:.5f})*W/2'
            y=f'(H-h)/2-({seg.transform_y:.5f})*H/2'
            video_layers.append((outtag,x,y))
        if seg.kind=='audio' or (seg.kind=='video' and seg.volume>.001 and has_audio(seg.path,ffprobe,cache,cancel)):
            atag=f'a{idx}'
            a_filter=f'[{idx}:a]asetpts=PTS-STARTPTS,{audio_tempo(seg.speed)},aresample=44100,apad,atrim=duration={dur:.6f},asetpts=PTS-STARTPTS,volume={seg.volume:.6f}[{atag}]'
            audio_layers.append(atag)
            filters.append(a_filter)
    previous='base0'
    for ix,(tag,x,y) in enumerate(video_layers):
        nexttag='merged'+str(ix)
        filters.append(f'[{previous}][{tag}]overlay=x={x}:y={y}:shortest=0:eof_action=pass:format=auto[{nexttag}]')
        previous=nexttag
    for index,effect in enumerate(effects):
        tag=f'effect{index}'
        filters.append(f'[{previous}]{effect.filter()}[{tag}]')
        previous=tag
    if subtitle:
        # ASS events stay on the full timeline while each chunk uses local PTS.
        filters.append(f'[{previous}]setpts=PTS+{begin:.8f}/TB,ass=filename={filter_path(subtitle)}:fontsdir={filter_path(Path(subtitle).parent / "fonts")},setpts=PTS-{begin:.8f}/TB[captioned]')
        previous='captioned'
    filters.append(f'[{previous}]format=yuv420p,trim=duration={dur:.8f},setpts=PTS-STARTPTS[vout]')
    if audio_layers:
        filters.append(''.join(f'[{a}]' for a in audio_layers)+f'amix=inputs={len(audio_layers)}:normalize=0:duration=longest,aresample=44100,atrim=duration={dur:.6f}[aout]')
    else:
        # predictable audio stream on every chunk -> safe concat
        args+=['-f','lavfi','-i','anullsrc=r=44100:cl=stereo']
        filters.append(f'[{input_index}:a]atrim=duration={dur:.6f},asetpts=PTS-STARTPTS[aout]')
    args+=['-filter_complex_threads','2','-filter_complex',';'.join(filters),'-map','[vout]','-map','[aout]',
           '-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p',
           '-threads','2','-r',str(fps),'-c:a','pcm_s16le','-ar','44100','-ac','2',
           '-t',f'{dur:.8f}',str(out)]
    run_command(args, None, cancel, out)


def chunk_times(draft:Draft, limit:float, per_chunk:float=60.0):
    # Quantize all boundaries to the same frame grid; never discard tiny spans.
    fps=draft.fps
    frames=max(1,math.ceil(limit*fps-1e-7))
    boundaries={0,frames}
    for segment in [*draft.segments,*draft.effects]:
        for value in (segment.start,segment.end):
            frame=max(0,min(frames,round(value*fps)))
            if 0<frame<frames: boundaries.add(frame)
    step=max(1,round(per_chunk*fps))
    boundaries.update(range(step,frames,step))
    ordered=sorted(boundaries)
    return [(a/fps,b/fps) for a,b in zip(ordered,ordered[1:])]


def unique_path(folder,name):
    candidate=folder/name
    if not candidate.exists(): return candidate
    base=Path(name).stem
    ext=Path(name).suffix
    for i in range(1,1000):
        candidate=folder/f'{base}_{i:02d}{ext}'
        if not candidate.exists(): return candidate
    raise RuntimeError('Too many matching output names')


def verify_mp4(path:Path, ffprobe:str, expected_duration:float) -> dict:
    """Check a completed MP4 really contains video and has a plausible duration.

    A decodable video track is not proof of accurate CapCut visual parity.
    """
    process=subprocess.run([ffprobe,'-v','error','-show_entries',
        'format=duration,size:stream=index,codec_type,codec_name,width,height',
        '-of','json',str(path)],capture_output=True,text=True,timeout=40,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if process.returncode:
        raise RuntimeError('FFprobe could not read exported MP4: '+process.stderr[-500:])
    try: info=json.loads(process.stdout)
    except (ValueError,TypeError) as e:
        raise RuntimeError('FFprobe returned invalid metadata') from e
    streams=info.get('streams') or []
    video=[x for x in streams if x.get('codec_type')=='video']
    audios=[x for x in streams if x.get('codec_type')=='audio']
    actual=num(asdict_safe(info.get('format')).get('duration'),0)
    if not video or actual<=0:
        raise RuntimeError('Export check failed: no readable video stream or zero duration.')
    # Allow small encoder rounding differences, but reject obviously partial results.
    if abs(actual-expected_duration)>0.15:
        raise RuntimeError(f'Export duration mismatch: expected {expected_duration:.2f}s, got {actual:.2f}s')
    return {'status':'metadata_pass','actual_duration_seconds':round(actual,3),
            'video_codec':video[0].get('codec_name'),
            'width':video[0].get('width'),'height':video[0].get('height'),
            'audio_streams':len(audios),'size_bytes':path.stat().st_size,
            'note':'Metadata verified only; visually inspect CapCut effects, image layout, audio and transitions.'}


def capability_check(ffmpeg):
    process=subprocess.run([ffmpeg,'-hide_banner','-filters'],capture_output=True,text=True,
                           timeout=20,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if process.returncode:
        raise RuntimeError('Cannot inspect FFmpeg filters: '+process.stderr[-300:])
    return any(re.search(r'\bass\s+V->V',line) for line in process.stdout.splitlines())


def render(draft:Draft, output_folder:str, preset:str, test_seconds:int,
           progress:Callable[[float,str],None], cancel:threading.Event,
           caption_fade:bool=False, effects_enabled:bool=True):
    ffmpeg=executable('ffmpeg')
    ffprobe=executable('ffprobe')
    if not ffmpeg or not ffprobe:
        raise FileNotFoundError('FFmpeg/ffprobe not found. Put both executables inside app/tools or install on PATH.')
    if draft.missing:
        raise ValueError(f'{len(draft.missing)} media files missing. Select the media folder and analyze again.\n'+'\n'.join(draft.missing[:10]))
    if draft.caption_errors:
        raise ValueError(f'{len(draft.caption_errors)} captions could not be parsed. Export blocked to prevent silent caption loss.\n'+'\n'.join(draft.caption_errors[:10]))
    if not any(s.kind!='audio' for s in draft.segments) and not draft.captions:
        raise ValueError('No visual segments or captions found.')
    if draft.captions and not capability_check(ffmpeg):
        raise RuntimeError('Captions require FFmpeg with the libass/ass filter. Install a full FFmpeg build; captions will not be silently omitted.')
    outdir=Path(output_folder).expanduser().resolve()
    outdir.mkdir(parents=True,exist_ok=True)
    limit=min(draft.duration,float(test_seconds)) if test_seconds else draft.duration
    if limit<=0: raise ValueError('Export duration must be positive.')
    w,h=get_dimensions(draft,preset)
    fps=draft.fps
    intervals=chunk_times(draft,limit)
    if len(intervals)>10000: raise ValueError('Too many media timeline boundaries (>10000).')
    suffix=f'_TEST_{int(limit)}s' if test_seconds else ''
    destination=unique_path(outdir,safe_name(draft.name)+suffix+'.mp4')
    report=destination.with_suffix('.report.json')
    started=time.time()
    cache={}
    count=0
    sidecar=None
    with tempfile.TemporaryDirectory(prefix='capcut_render_',dir=outdir) as folder:
        tmp=Path(folder)
        subtitle=None
        if draft.captions:
            subtitle=tmp/'captions.ass'
            count=write_ass(subtitle,draft.captions,w,h,limit,caption_fade)
            fontdir=tmp/'fonts';fontdir.mkdir()
            for index,font in enumerate(dict.fromkeys(draft.font_files)):
                shutil.copyfile(font,fontdir/(str(index)+'_'+Path(font).name))
        clips=[]
        for i,(a,b) in enumerate(intervals):
            if cancel.is_set(): raise InterruptedError('Cancelled by user')
            midpoint=(a+b)/2
            active=[s for s in draft.segments if s.start<=midpoint<s.end]
            chunk=tmp/f'chunk_{i:05}.mkv'
            progress(a/limit*90,f'Part {i+1}/{len(intervals)} | {a:.1f}-{min(b,limit):.1f}s | captions {count}')
            active_effects=[e for e in draft.effects if e.start<=midpoint<e.end] if effects_enabled else []
            make_chunk(ffmpeg,ffprobe,active,a,b,w,h,fps,chunk,cache,cancel,subtitle,active_effects)
            clips.append(chunk)
        progress(90,'Combining video; encoding audio once...')
        manifest=tmp/'concat.txt'
        # All generated chunk filenames are simple relative paths; no path escaping required.
        manifest.write_text(''.join("file '"+c.name+"'\n" for c in clips),encoding='utf-8')
        almost=tmp/'combined.mp4'
        run_command([ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-y','-f','concat','-safe','1',
                     '-i',str(manifest),'-c:v','copy','-c:a','aac','-b:a','192k','-t',f'{limit:.8f}',
                     '-movflags','+faststart',str(almost)],None,cancel,almost)
        progress(94,'Verifying streams, duration, resolution and full decode...')
        check=verify_mp4(almost,ffprobe,limit)
        if [check['width'],check['height']]!=[w,h] or check['audio_streams']!=1:
            raise RuntimeError('Output stream dimensions or audio stream count mismatch.')
        run_command([ffmpeg,'-v','error','-xerror','-nostdin','-i',str(almost),'-f','null','-'],None,cancel)
        check['status']='metadata_and_decode_pass'
        check['note']='Complete decode passed. Visual fidelity and lip synchronization require manual review.'
        if cancel.is_set(): raise InterruptedError('Cancelled')
        # Publish only a verified file. No partial MP4 is left in the output folder on failure.
        if destination.exists(): raise FileExistsError('Output appeared during render; refusing to overwrite it.')
        # Atomic no-overwrite reservation protects against another producer using the same name.
        descriptor=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        os.close(descriptor)
        try:
            os.replace(almost,destination)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        if subtitle:
            sidecar=destination.with_suffix('.captions.ass')
            shutil.copyfile(subtitle,sidecar)
    record=draft.summary()
    record.update({'app_version':'0.4','status':'completed','visual_fidelity':'approximation',
                   'mp4_verification':check,'output':str(destination),
                   'output_size_bytes':destination.stat().st_size,'render_seconds':round(time.time()-started,1),
                   'export_seconds':limit,'export_dimensions':[w,h],'fps':fps,'preset':preset,
                   'test_seconds':test_seconds,'text_segments_in_export':count,
                   'caption_sidecar':str(sidecar) if sidecar else None,'caption_fade_applied':caption_fade,
                   'effects_enabled':effects_enabled,
                   'effects_applied_in_export':sum(e.start<limit and e.end>0 for e in draft.effects) if effects_enabled else 0,
                   'caption_backgrounds_in_export':sum(c.start<limit and c.end>0 and bool(c.background_color) and c.background_alpha>0 for c in draft.captions),
                   'verification_scope':'Technical decode only; native CapCut visual equivalence is not claimed.',
                   'disclaimer':'Mapped HDR look is an independent approximation; other proprietary effects, active animations, transitions, templates, masks and speed ramps are not reproduced.'})
    report.write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
    summary=destination.with_suffix('.summary.txt')
    summary.write_text(
        f'CAPCUT INDEPENDENT EXPORT SUMMARY - v0.4\nProject: {draft.name}\n'
        f'Output: {destination.name}\nDuration: {limit:.3f} seconds\n'
        f'Resolution: {w} x {h} | FPS: {fps}\n'
        f'Video segments in project: {record["video_segments"]}\nImage segments in project: {record["image_segments"]}\n'
        f'Audio segments in project: {record["audio_segments"]}\n'
        f'Captions in project: {len(draft.captions)} | In this export: {count} | Unparsed: {len(draft.caption_errors)}\n'
        f'Technical check: {check["status"]}\nRender time: {record["render_seconds"]} seconds\n'
        f'Visual fidelity: approximation; compare with your source project.\n'
        f'Original caption backgrounds in this export: {record["caption_backgrounds_in_export"]}\n'
        f'Effects applied (approximation): {record["effects_applied_in_export"]}\n'
        f'Active animation materials: {draft.animation_active} | Empty placeholders: {draft.animation_empty}\n'
        f'Optional added caption fade: {caption_fade}\n\nLIMITATIONS\n'+
        '\n'.join(draft.warnings or ['No known warnings detected; visual equivalence is still not certified.'])+
        '\n\nMEDIA FILES\n'+'\n'.join(sorted(set(s.path for s in draft.segments)))+'\n',encoding='utf-8')
    progress(100,f'Completed with technical verification: {destination.name}')
    return destination,report
