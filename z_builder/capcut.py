"""Z Studio's original (CapCut 9.4) writer, called via a small Node subprocess.
The writer copies media into a new draft and never mutates user source or old drafts.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import tempfile

from .core import Plan, preflight, write_timeline_csv, timeline, MAX_VIDEO_CLIP_SECONDS, TIMING_EPSILON


SUPPORTED_ANIMATIONS = {'none', 'pan_left', 'pan_right', 'right_zoom', 'zoom_1', 'zoom_in', 'zoom_out'}


def find_node() -> str:
    exe = shutil.which('node')
    if exe:
        return exe
    for base in (Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'nodejs' / 'node.exe',
                 Path(__file__).resolve().parents[1] / '.runtime' / 'node' / 'node.exe'):
        if base.is_file():
            return str(base)
    return ''


def probe(path: str) -> dict:
    """Probe basic media dimensions/seconds if local ffprobe/ffmpeg exists."""
    info = {'duration': 0, 'w': 0, 'h': 0, 'hasAudio': True}
    if Path(path).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}:
        try:
            from PySide6.QtGui import QImageReader
            dims = QImageReader(path).size()
            info['w'], info['h'] = dims.width(), dims.height()
        except (ImportError, RuntimeError):
            pass
    exe = shutil.which('ffprobe')
    if exe:
        cmd = [exe, '-v', 'error', '-show_entries', 'format=duration:stream=width,height,codec_type', '-of', 'json', path]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=25, check=True)
            data = json.loads(p.stdout)
            info['duration'] = float(data.get('format', {}).get('duration') or 0)
            for s in data.get('streams', []):
                if s.get('codec_type') == 'video':
                    info['w'] = int(s.get('width') or 0)
                    info['h'] = int(s.get('height') or 0)
                if s.get('codec_type') == 'audio':
                    info['hasAudio'] = True
            return info
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    exe = shutil.which('ffmpeg')
    if not exe:
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, OSError, RuntimeError):
            pass
    if exe:
        try:
            p = subprocess.run([exe, '-hide_banner', '-i', path], capture_output=True, text=True, timeout=25)
            m = re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)', p.stderr)
            if m:
                info['duration'] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
            dims = re.search(r'Video:.*?(\d{2,5})x(\d{2,5})', p.stderr)
            if dims:
                info['w'], info['h'] = int(dims[1]), int(dims[2])
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return info


def animated(shot) -> tuple[dict, str]:
    animation = shot.animation.casefold().strip()
    duration = shot.duration
    kf = {}
    transform = {'scale': 1, 'x': 0, 'y': 0}
    if animation in {'pan_left', 'pan_right'}:
        x0, x1 = (0.06, -0.06) if animation == 'pan_left' else (-0.06, 0.06)
        transform['scale'] = 1.12
        kf['px'] = [{'t': 0, 'v': x0}, {'t': duration, 'v': x1}]
    elif animation in {'right_zoom', 'zoom_1', 'zoom_in', 'zoom_out'}:
        outward = animation == 'zoom_out'
        kf['sc'] = [{'t': 0, 'v': 1.10 if outward else 1},
                    {'t': duration, 'v': 1 if outward else 1.10}]
        if animation == 'right_zoom':
            kf['px'] = [{'t': 0, 'v': 0}, {'t': duration, 'v': 0.03}]
    if animation not in SUPPORTED_ANIMATIONS:
        return {'transform': transform, 'kfs': kf}, f'{shot.section}: animation "{shot.animation}" cannot be sent to CapCut; open in editor to add it.'
    return {'transform': transform, 'kfs': kf}, ''


def build_request(plan: Plan, drafts_root: str = '', launch: bool = False) -> tuple[dict, list[str]]:
    failures = preflight(plan)
    if failures:
        raise ValueError('Preflight blocked:\n' + '\n'.join(failures[:30]))
    images, captions, media = [], [], {}
    warnings = list(plan.warnings)
    current = 0.0
    for start, end, shot in timeline(plan):
        motion, warning = animated(shot)
        if warning:
            warnings.append(warning)
        if shot.transition.casefold() not in {'none', 'hard_cut', 'cut', ''}:
            warnings.append(f'{shot.section}: transition {shot.transition} is not exported by Z Studio CapCut writer.')
        entry = {'image': shot.assigned_path,
                 'kind': 'video' if shot.media_type == 'video' else 'image',
                 'start': start, 'end': end,
                 'trimStart': round(shot.source_in_seconds, 3) if shot.media_type == 'video' else 0,
                 'zoom': 'none', 'hasAudio': False, 'muted': True,
                 **motion}
        images.append(entry)
        if shot.narration.strip():
            captions.append({'text': shot.narration.strip(), 'start': start,
                             'end': end, 'pos': 'bottom',
                             'size': 45, 'color': '#ffffff', 'weight': 'bold'})
        media.setdefault(shot.assigned_path, probe(shot.assigned_path))
        if shot.media_type == 'video':
            actual = media[shot.assigned_path]['duration']
            required = shot.source_in_seconds + shot.duration
            if actual > 0 and required > actual + 0.035:
                raise ValueError(f'{shot.section}: video has {actual:.3f}s available, but requested source 0:{required:.3f}. Choose another clip or shorten shot.')
            if not actual:
                media[shot.assigned_path]['duration'] = MAX_VIDEO_CLIP_SECONDS
                warnings.append(f'{shot.section}: video duration could not be read; assumed 4.000s. Confirm in CapCut.')
        current = end
    voice = None
    if plan.narration_path:
        media[plan.narration_path] = probe(plan.narration_path)
        audio_length = media[plan.narration_path]['duration']
        voice = {'file': plan.narration_path, 'start': 0,
                 'dur': audio_length if audio_length > 0 else current, 'volume': 1}
        if not audio_length:
            media[plan.narration_path]['duration'] = current
            warnings.append('Voice duration not probed; timeline duration assumed. Install FFmpeg to read accurate duration.')
        elif (plan.sections.get('_FORMAT', {}).get('type') == 'simple_timed_v1'
              and abs(audio_length - current) > 0.25):
            raise ValueError(f'Input voice is {audio_length:.3f}s but Scene Plan ends at {current:.3f}s. Fix the Scene Plan timing before exporting.')
        elif abs(audio_length - current) > 1:
            warnings.append(f'Voice length ({audio_length:.1f}s) differs from visual timeline ({current:.1f}s); timings need review.')
    captions_mode = plan.sections.get('CAPTIONS', {})
    if captions_mode.get('caption_style', '').casefold() == 'karaoke':
        warnings.append('Karaoke word-highlighting cannot export: captions become plain editable CapCut subtitle clips.')
    if plan.sections.get('LOOK', {}).get('lut_enabled', '').casefold() == 'true':
        warnings.append('Scene Plan LUT cannot be exported by Z Studio draft writer; apply it in CapCut.')
    payload = {'name': plan.name, 'W': plan.width, 'H': plan.height, 'fps': plan.fps,
               'images': images, 'captions': captions, 'voice': voice, 'music': [], 'sfx': []}
    return {'payload': payload, 'media': media, 'drafts_root': drafts_root, 'launch': launch}, warnings


def export_capcut(plan: Plan, drafts_root: str = '', launch: bool = False) -> dict:
    node = find_node()
    if not node:
        raise RuntimeError('Node.js not available. Install Node or use Z Studio portable Node runtime; no project was modified.')
    js = Path(__file__).with_name('capcut_bridge.js')
    engine = Path(__file__).with_name('capcut-draft.js')
    if not js.is_file() or not engine.is_file():
        raise RuntimeError('Z Studio CapCut engine missing from this distribution.')
    request, warnings = build_request(plan, drafts_root, launch)
    with tempfile.TemporaryDirectory(prefix='zb-capcut-') as directory:
        input_path, output_path = Path(directory) / 'request.json', Path(directory) / 'result.json'
        input_path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
        done = subprocess.run([node, str(js), str(input_path), str(output_path)],
                              capture_output=True, text=True, timeout=1800)
        if done.returncode and not output_path.is_file():
            raise RuntimeError('CapCut draft creation failed:\n' + done.stderr[-2500:])
        output = json.loads(output_path.read_text(encoding='utf-8'))
        output['warnings'] = warnings + output.get('notes', [])
        if done.returncode or output.get('verify_issues'):
            raise RuntimeError('Draft written but failed verification:\n' + '\n'.join(output.get('verify_issues') or [done.stderr]))
        write_timeline_csv(plan, Path(output['folder']) / 'Z_Builder_Timeline.csv')
        (Path(output['folder']) / 'Z_Builder_Warnings.txt').write_text('\n'.join(output['warnings']) + '\n', encoding='utf-8')
        return output
