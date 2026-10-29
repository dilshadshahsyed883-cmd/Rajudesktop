"""Portable packaging/orchestration only. CapCut input is delegated to upstream cc.py."""
from __future__ import annotations
import argparse
import contextlib
import ctypes
import datetime as dt
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
UP = ROOT / 'upstream' / 'scripts'
BASELINE = '9.4.0.4015'
GLOBAL = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CapCut_GUI_Export_Runner'

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(temp, path)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def snapshot(project):
    # Only read source JSON. Do not copy private drafts into package/repository.
    return {str(p.relative_to(project)): sha(p) for p in sorted(project.rglob('*.json'))}

def load_cc():
    if sys.platform != 'win32':
        raise RuntimeError('CapCut desktop controls require Windows.')
    spec = importlib.util.spec_from_file_location('upstream_cc', UP / 'cc.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def version_info(cc):
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        cc.cmd_version(None)
    return json.loads(capture.getvalue())

def active_desktop():
    user = ctypes.windll.user32
    user.OpenInputDesktop.restype = ctypes.c_void_p
    user.SwitchDesktop.argtypes = [ctypes.c_void_p]
    user.CloseDesktop.argtypes = [ctypes.c_void_p]
    desktop = user.OpenInputDesktop(0, False, 0x0100)
    if not desktop:
        return False
    try:
        return bool(user.SwitchDesktop(desktop))
    finally:
        user.CloseDesktop(desktop)

def guard(cc):
    info = version_info(cc)
    running = info.get('running', [])
    if running != [BASELINE]:
        raise RuntimeError(f'INPUT BLOCKED: running={running}; upstream baseline={BASELINE}. Fresh interactive acceptance required. Read ACCEPTANCE.md.')
    if not active_desktop():
        raise RuntimeError('INPUT BLOCKED: an active unlocked Windows desktop is required.')
    return info

@contextlib.contextmanager
def batch_lock(folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / '.runner.lock'
    # OS releases the lock if process crashes; no stale-lock deletion required.
    with path.open('a+b') as f:
        f.seek(0)
        f.write(b'0')
        f.flush()
        f.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            f.seek(0)
            if os.name == 'nt':
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)

def prepare(folder, project):
    with batch_lock(GLOBAL):
        pointer = GLOBAL / 'current.json'
        if pointer.exists():
            previous = Path(json.loads(pointer.read_text())['folder']) / 'active.json'
            if not previous.exists() or json.loads(previous.read_text())['status'] != 'VERIFIED':
                raise ValueError('An unresolved global CapCut job blocks every batch folder.')
        job = _prepare(folder, project)
        save(pointer, {'folder': str(folder.resolve())})
        return job

def _prepare(folder, project):
    project = project.resolve(strict=True)
    if not (project / 'draft_content.json').is_file():
        raise ValueError('Select the exact project folder containing draft_content.json.')
    folder = folder.resolve()
    if folder == project or project in folder.parents or folder in project.parents:
        raise ValueError('Export folder must be separate from the source project.')
    with batch_lock(folder):
        state_path = folder / 'active.json'
        if state_path.exists():
            prev = json.loads(state_path.read_text())
            if prev['status'] not in ('VERIFIED', 'ABORTED_NO_EXPORT'):
                raise ValueError('Previous job is unresolved. Verify it or stop; next project is blocked.')
        job_id = dt.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:12]
        jobdir = folder / job_id
        jobdir.mkdir(exist_ok=False)
        data = json.loads((project / 'draft_content.json').read_text(encoding='utf-8-sig'))
        canvas = data.get('canvas_config', {})
        job = dict(id=job_id, status='PREPARED_AGENT_REQUIRED', project=str(project),
                   output=str(jobdir / 'export.mp4'), before=snapshot(project),
                   expected=dict(duration=float(data.get('duration', 0)) / 1_000_000,
                                 width=canvas.get('width'), height=canvas.get('height'),
                                 codec='h264', audio=True),
                   warning='No export started. Follow AGENT_EXPORT.md with visual checks.')
        if not job['expected']['duration'] or not canvas.get('width') or not canvas.get('height'):
            raise ValueError('Draft duration/canvas unavailable; cannot establish verification baseline.')
        save(jobdir / 'job.json', job)
        save(state_path, job)
        return job

def inspect_media(path, ffmpeg, expected):
    if path.suffix.lower() != '.mp4' or not path.is_file() or path.stat().st_size == 0:
        raise ValueError('Nonempty MP4 required.')
    probe = subprocess.run([str(ffmpeg), '-hide_banner', '-i', str(path)], capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=60)
    info = probe.stderr
    # Native bundled ffmpeg analysis is the upstream verification route (no renderer).
    if not re.search(r'Input #0,.*(?:mov|mp4)', info):
        raise ValueError('MP4 container not detected.')
    dur = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', info)
    video = re.search(r'Video: (\w+).*?\b(\d{2,5})x(\d{2,5})\b', info)
    audio = re.search(r'Audio: (\w+)', info)
    if not dur or not video:
        raise ValueError('Could not verify duration and video stream.')
    seconds = int(dur[1]) * 3600 + int(dur[2]) * 60 + float(dur[3])
    if not math.isfinite(seconds) or abs(seconds - expected['duration']) > max(.25, expected['duration'] * .001):
        raise ValueError(f'Duration mismatch: {seconds} vs {expected["duration"]}')
    if video[1] != expected['codec'] or int(video[2]) != expected['width'] or int(video[3]) != expected['height']:
        raise ValueError(f'Codec/resolution mismatch: {video.group(0)}')
    if expected['audio'] and not audio:
        raise ValueError('Required audio stream missing.')
    decode = subprocess.run([str(ffmpeg), '-v', 'error', '-xerror', '-i', str(path),
                             '-map', '0:v:0', '-map', '0:a:0?', '-f', 'null', '-'],
                            capture_output=True, text=True, timeout=max(120, seconds * 4))
    if decode.returncode != 0 or decode.stderr.strip():
        raise ValueError('Full video/audio decode failed: ' + decode.stderr[-1000:])
    return dict(duration=seconds, codec=video[1], width=int(video[2]), height=int(video[3]),
                audio_codec=audio[1] if audio else None, full_decode='PASS',
                bytes=path.stat().st_size, sha256=sha(path), stream_info=info)

def verify(folder, ffmpeg, completion_seen, interval=2):
    with batch_lock(GLOBAL):
        return _verify(folder, ffmpeg, completion_seen, interval)

def _verify(folder, ffmpeg, completion_seen, interval=2):
    if not completion_seen:
        raise ValueError('Agent/operator must first visually confirm the actual completion screen.')
    with batch_lock(folder):
        state_path = folder / 'active.json'
        job = json.loads(state_path.read_text())
        if job['status'] == 'VERIFIED':
            raise ValueError('Already verified; previous success is immutable.')
        path = Path(job['output'])
        if snapshot(Path(job['project'])) != job['before']:
            raise ValueError('Source project JSON changed. Batch stopped; no source restoration attempted.')
        sizes = []
        for _ in range(3):
            sizes.append((path.stat().st_size, path.stat().st_mtime_ns))
            time.sleep(interval)
        if len(set(sizes)) != 1:
            raise ValueError('Output is still changing; do not advance.')
        media = inspect_media(path, ffmpeg, job['expected'])
        if snapshot(Path(job['project'])) != job['before'] or (path.stat().st_size, path.stat().st_mtime_ns) != sizes[0]:
            raise ValueError('Project or output changed during verification; batch stopped.')
        job.update(status='VERIFIED', media=media, completion='Visually attested by agent/operator',
                   verified_at=dt.datetime.now().isoformat())
        save(path.parent / 'job.json', job)
        save(state_path, job)
        return job

def self_test():
    import PIL, mss, comtypes, uiautomation
    cc = load_cc()
    cc.build_parser().parse_args(['version'])
    # Uses original read-only inspector, does not require installed CapCut.
    subprocess.run([sys.executable, str(UP / 'draft_inspect.py'), '--help'], check=True)
    print(json.dumps(dict(startup='PASS', dependencies='PASS', original_parser='PASS',
                          capcut_gui_export='NOT TESTED', unattended_batch='NOT TESTED')))

def main():
    p = argparse.ArgumentParser(description='CapCut GUI Export — portable AGENT-ASSISTED toolkit. Read README.md.')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('self-test')
    sub.add_parser('detect')
    sub.add_parser('guide')
    c = sub.add_parser('cc', help='Original upstream controls; screenshot decisions require an agent')
    c.add_argument('args', nargs=argparse.REMAINDER)
    d = sub.add_parser('inspect', help='Original read-only draft inspector')
    d.add_argument('args', nargs=argparse.REMAINDER)
    q = sub.add_parser('prepare', help='Reserve unique output for one project; DOES NOT start export')
    q.add_argument('--project', type=Path, required=True)
    q.add_argument('--folder', type=Path, required=True)
    v = sub.add_parser('verify')
    v.add_argument('--folder', type=Path, required=True)
    v.add_argument('--ffmpeg', type=Path, required=True, help='Installed CapCut bundled ffmpeg.exe, analysis/decode only')
    v.add_argument('--completion-seen', action='store_true')
    s = sub.add_parser('status')
    s.add_argument('--folder', type=Path, required=True)
    a = p.parse_args()
    if a.command == 'self-test':
        self_test()
    elif a.command == 'guide':
        print((ROOT / 'AGENT_EXPORT.md').read_text(encoding='utf-8'))
    elif a.command == 'detect':
        cc = load_cc()
        print(json.dumps(version_info(cc), indent=2))
    elif a.command == 'inspect':
        sys.argv = [str(UP / 'draft_inspect.py')] + a.args
        runpy.run_path(str(UP / 'draft_inspect.py'), run_name='__main__')
    elif a.command == 'cc':
        if not a.args:
            raise ValueError('Specify original cc.py command.')
        cc = load_cc()
        allowed = {'version', 'windows', 'tree', 'find', 'screenshot', 'wait', 'wait-for',
                   'focus', 'key', 'click', 'type', 'act', 'scroll'}
        if a.args[0] not in allowed:
            raise ValueError('Command excluded from export-only launcher. No editing utilities included.')
        # Screenshot itself may focus CapCut; fail closed for all input on other versions.
        if a.args[0] not in {'version', 'windows', 'tree', 'find', 'wait', 'wait-for'}:
            guard(cc)
        arg = cc.build_parser().parse_args(a.args)
        arg.fn(arg)
    elif a.command == 'prepare':
        print(json.dumps(prepare(a.folder, a.project), indent=2))
    elif a.command == 'status':
        print((a.folder / 'active.json').read_text(encoding='utf-8'))
    elif a.command == 'verify':
        print(json.dumps(verify(a.folder, a.ffmpeg, a.completion_seen), indent=2))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        log = ROOT / 'logs' / 'failures.log'
        log.parent.mkdir(exist_ok=True)
        with log.open('a', encoding='utf-8') as f:
            f.write(dt.datetime.now().isoformat() + ' STOP: ' + str(exc) + '\n')
        print(f'STOP: {exc}', file=sys.stderr)
        sys.exit(2)
