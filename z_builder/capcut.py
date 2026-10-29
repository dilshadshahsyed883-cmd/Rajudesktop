"""Z Studio's original (CapCut 9.4) writer, called via a small Node subprocess.
The writer copies media into a new draft and never mutates user source or old drafts.
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import NamedTuple

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
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=25, check=True,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
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
            p = subprocess.run([exe, '-hide_banner', '-i', path], capture_output=True, text=True, timeout=25,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
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


def build_request(plan: Plan, drafts_root: str = '', launch: bool = False,
                  include_voice: bool = False, voice_source_start: float = 0) -> tuple[dict, list[str]]:
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
        if shot.assigned_path not in media:
            media[shot.assigned_path] = probe(shot.assigned_path)
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
    if include_voice:
        if not plan.narration_path:
            raise ValueError('Include voice is ON but no voice file is selected; choose one or turn it OFF.')
        media[plan.narration_path] = probe(plan.narration_path)
        audio_length = media[plan.narration_path]['duration']
        global_end = voice_source_start + current
        if audio_length and global_end > audio_length + 0.25:
            raise ValueError(f'Voice audio ends at {audio_length:.3f}s, but this part requests through {global_end:.3f}s.')
        voice = {'file': plan.narration_path, 'start': 0,
                 'trimStart': round(voice_source_start, 3), 'dur': current, 'volume': 1}
        if not audio_length:
            media[plan.narration_path]['duration'] = global_end
            warnings.append('Voice duration could not be probed; final synchronization needs review in CapCut.')
    captions_mode = plan.sections.get('CAPTIONS', {})
    if captions_mode.get('caption_style', '').casefold() == 'karaoke':
        warnings.append('Karaoke word-highlighting cannot export: captions become plain editable CapCut subtitle clips.')
    if plan.sections.get('LOOK', {}).get('lut_enabled', '').casefold() == 'true':
        warnings.append('Scene Plan LUT cannot be exported by Z Studio draft writer; apply it in CapCut.')
    payload = {'name': plan.name, 'W': plan.width, 'H': plan.height, 'fps': plan.fps,
               'images': images, 'captions': captions, 'voice': voice, 'music': [], 'sfx': [],
               'separateLayers': False, 'singleVisualTrack': True}
    return {'payload': payload, 'media': media, 'drafts_root': drafts_root, 'launch': launch}, warnings


# Default split policy: aim at six minutes, keep complete Scene Plan shots, and
# never exceed seven minutes. The final remaining piece may be shorter than five.
PART_MIN_SECONDS = 300.0
PART_TARGET_SECONDS = 360.0
PART_MAX_SECONDS = 420.0


class Part(NamedTuple):
    index: int
    start_seconds: float
    end_seconds: float
    plan: Plan


def split_into_parts(plan: Plan) -> list[Part]:
    """Partition only at existing scene boundaries, without gaps or overlaps.

    Prefer five-to-seven-minute parts when possible; penalize an unnecessarily
    short final part. A single scene > 7 min is rejected instead of cut.
    """
    shots = list(timeline(plan))
    if not shots:
        raise ValueError('No scenes to export')
    n = len(shots)
    starts = [start for start, _, _ in shots]
    ends = [end for _, end, _ in shots]
    if any(end - start > PART_MAX_SECONDS + 0.002 for start, end, _ in shots):
        raise ValueError('A scene exceeds 7 minutes. Split that scene in the Scene Plan first.')
    # Last part can be shorter; other parts should be between 5-7 minutes.
    # Minimize the number of parts first and keep durations near 6 minutes,
    # with a large penalty for a very short leftover part.
    best: list[tuple[float, list[tuple[int, int]]] | None] = [None] * (n + 1)
    best[n] = (0.0, [])
    for i in range(n - 1, -1, -1):
        for j in range(i + 1, n + 1):
            duration = round(ends[j - 1] - starts[i], 3)
            if duration > PART_MAX_SECONDS + 0.002:
                break
            if j < n and duration < PART_MIN_SECONDS - 0.002:
                continue
            following = best[j]
            if following is None:
                continue
            # Prefer proper 5-7m chunks; allow a final short tail when needed.
            short_penalty = ((PART_MIN_SECONDS - duration) ** 2 * 10
                             if duration < PART_MIN_SECONDS else 0)
            score = following[0] + 10000 + (duration - PART_TARGET_SECONDS) ** 2 + short_penalty
            if best[i] is None or score < best[i][0]:
                best[i] = (score, [(i, j)] + following[1])
    if best[0] is None:
        raise ValueError('Cannot split at scene boundaries into <=7-minute parts; revise exceptionally long scenes.')
    result = []
    for index, (i, j) in enumerate(best[0][1], 1):
        absolute_start = starts[i]
        absolute_end = ends[j - 1]
        sub = Plan.from_dict(plan.to_dict())
        sub.name = f'{plan.name} - Part {index:02d}'
        sub.shots = [replace(sh, start_seconds=round(start - absolute_start, 3))
                     for start, _, sh in shots[i:j]]
        result.append(Part(index, absolute_start, absolute_end, sub))
    return result


def export_capcut(plan: Plan, drafts_root: str = '', launch: bool = False,
                  include_voice: bool = False, mode: str = 'parts',
                  progress_callback=None) -> dict:
    """Create either verified 5-7 minute drafts or one complete editable draft.

    Progress events report real completed/verified draft counts. The UI stays
    responsive while the Node writer copies media in a background thread.
    """
    if mode not in {'parts', 'complete'}:
        raise ValueError('CapCut export mode must be parts or complete.')
    node = find_node()
    if not node:
        raise RuntimeError('Node.js not available. Install Node or use Z Studio portable Node runtime.')
    js = Path(__file__).with_name('capcut_bridge.js')
    engine = Path(__file__).with_name('capcut-draft.js')
    if not js.is_file() or not engine.is_file():
        raise RuntimeError('Z Studio CapCut engine missing from this distribution.')
    failures = preflight(plan)
    if failures:
        raise ValueError('Preflight blocked:\n' + '\n'.join(failures[:30]))
    if include_voice and not plan.narration_path:
        raise ValueError('Select Voice MP3/WAV or uncheck Include Voice in CapCut.')
    if mode == 'parts':
        parts = split_into_parts(plan)
    else:
        slots = list(timeline(plan))
        if not slots:
            raise ValueError('No scenes to export')
        parts = [Part(1, slots[0][0], slots[-1][1], Plan.from_dict(plan.to_dict()))]
    if progress_callback:
        progress_callback(0, len(parts), 'Preparing CapCut timeline and source media...')
    prepared = []
    for part in parts:
        request, warnings = build_request(part.plan, drafts_root, False,
                                         include_voice=include_voice, voice_source_start=part.start_seconds)
        prepared.append((part, request, warnings))
    output_parts = []
    all_warnings = []
    compatibility = {}
    # Each part is verified before the next is created; on failure report exact
    # created drafts, leaving them visible instead of secretly deleting data.
    for part, request, warnings in prepared:
        if progress_callback:
            label = ('Complete project' if mode == 'complete' else f'Part {part.index}/{len(parts)}')
            progress_callback(len(output_parts), len(parts), f'Creating {label}: copying media and writing draft...')
        request['launch'] = launch and part.index == len(parts)
        with tempfile.TemporaryDirectory(prefix='zb-capcut-') as directory:
            input_path, output_path = Path(directory) / 'request.json', Path(directory) / 'result.json'
            input_path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
            done = subprocess.run([node, str(js), str(input_path), str(output_path)],
                                  capture_output=True, text=True, timeout=1800,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if done.returncode and not output_path.is_file():
                created = '\n'.join(p['folder'] for p in output_parts)
                raise RuntimeError(f'Part {part.index} failed. Earlier drafts remain:\n{created}\n' + done.stderr[-2500:])
            out = json.loads(output_path.read_text(encoding='utf-8'))
            combined_warnings = warnings + out.get('notes', [])
            if done.returncode or out.get('verify_issues'):
                raise RuntimeError(f'Part {part.index} failed verification at {out.get("folder", "?")}:\n'
                                   + '\n'.join(out.get('verify_issues') or [done.stderr]))
            folder = Path(out['folder'])
            write_timeline_csv(part.plan, folder / 'Z_Builder_Timeline.csv')
            (folder / 'Z_Builder_Warnings.txt').write_text('\n'.join(combined_warnings) + '\n', encoding='utf-8')
            info = {'index': part.index, 'folder': str(folder),
                    'original_start_seconds': part.start_seconds,
                    'original_end_seconds': part.end_seconds,
                    'duration_seconds': round(part.end_seconds - part.start_seconds, 3),
                    'tracks': out['tracks'], 'segments': out['segments'],
                    'voice_included': include_voice}
            info['mode'] = mode
            info_file = 'Z_Builder_Project_Info.json' if mode == 'complete' else 'Z_Builder_Part_Info.json'
            (folder / info_file).write_text(json.dumps(info, indent=2), encoding='utf-8')
            output_parts.append(info)
            all_warnings += combined_warnings
            compatibility = out.get('capcut', {})
        if progress_callback:
            progress_callback(len(output_parts), len(parts),
                              f'Verified {len(output_parts)}/{len(parts)} CapCut draft(s)')
    return {'parts': output_parts, 'count': len(output_parts), 'mode': mode,
            'warnings': list(dict.fromkeys(all_warnings)),
            'capcut': compatibility, 'launched': bool(launch and output_parts)}
