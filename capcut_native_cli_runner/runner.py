"""Guarded portable front door to the unmodified reverse-cli-anything adapter."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT / 'vendor/upstream'
SUPPORTED = '9.5.0.4050'
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_sources():
    for name, expected in read(ROOT / 'UPSTREAM_FILES.json').items():
        if digest(UPSTREAM / name) != expected:
            raise ValueError('Upstream source integrity failed: ' + name)


def powershell(script):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, encoding='utf-8', timeout=30,
                            creationflags=FLAGS)
    if result.returncode:
        raise ValueError('Windows discovery failed: ' + result.stderr.strip())
    return json.loads(result.stdout.lstrip('\ufeff') or '[]')


def installed():
    # No app launch, DLL load or instrumentation during discovery.
    return powershell(r'''[Console]::OutputEncoding=[Text.UTF8Encoding]::new();
    $paths = @();
    $paths += Get-CimInstance Win32_Process -Filter "Name='CapCut.exe'" | ForEach-Object {$_.ExecutablePath};
    $roots = @("$env:LOCALAPPDATA\CapCut\Apps", "$env:ProgramFiles\CapCut", 'D:\Apps\CapCut', 'D:\Apps\CapCut2\CapCut');
    foreach ($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*')) {
      Get-ItemProperty $key -ErrorAction SilentlyContinue | Where-Object {$_.DisplayName -like '*CapCut*'} | ForEach-Object {if ($_.InstallLocation) {$roots += $_.InstallLocation}};
    }
    foreach ($root in ($roots | Select-Object -Unique)) {if (Test-Path -LiteralPath $root) {
      $paths += Get-ChildItem -LiteralPath $root -Filter CapCut.exe -Recurse -Depth 3 -ErrorAction SilentlyContinue | ForEach-Object {$_.FullName}
    }}
    @($paths | Where-Object {$_} | Select-Object -Unique) | ConvertTo-Json -Compress''')


def file_version(exe):
    api = ctypes.WinDLL('version', use_last_error=True)
    api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    api.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    api.GetFileVersionInfoW.restype = wintypes.BOOL
    api.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    api.VerQueryValueW.restype = wintypes.BOOL
    unused = wintypes.DWORD()
    size = api.GetFileVersionInfoSizeW(str(exe), ctypes.byref(unused))
    if not size:
        raise ValueError('Cannot read CapCut.exe file version')
    data = ctypes.create_string_buffer(size)
    if not api.GetFileVersionInfoW(str(exe), 0, size, data):
        raise ValueError('Cannot read CapCut.exe version resource')
    ptr, length = ctypes.c_void_p(), wintypes.UINT()
    if not api.VerQueryValueW(data, '\\', ctypes.byref(ptr), ctypes.byref(length)) or length.value < 52:
        raise ValueError('Invalid CapCut version resource')
    words = ctypes.cast(ptr, ctypes.POINTER(wintypes.DWORD))
    if words[0] != 0xFEEF04BD:
        raise ValueError('Invalid CapCut version signature')
    return '.'.join(map(str, (words[2] >> 16, words[2] & 65535, words[3] >> 16, words[3] & 65535)))


def check_build(directory):
    directory = Path(directory).resolve()
    exe = directory / 'CapCut.exe'
    if not exe.is_file():
        raise ValueError('CapCut.exe missing. Install CapCut separately or set capcut_dir in config.json.')
    version = file_version(exe)
    if version != SUPPORTED:
        raise ValueError(f'Unsupported CapCut {version}; upstream supports only {SUPPORTED}. No attachment attempted.')
    sys.path.insert(0, str(UPSTREAM / 'capcut-cli'))
    from capcut_store_worker import STORE_PINS
    for name, expected in STORE_PINS.items():
        if not (directory / name).is_file() or digest(directory / name) != expected:
            raise ValueError('Unsupported native module fingerprint: ' + name + '. No attachment attempted.')
    return {'directory': str(directory), 'version': version, 'moduleHashes': STORE_PINS}


def select_build(config):
    if os.name != 'nt' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('Windows x64 required. No CapCut action attempted.')
    if config.get('capcut_dir'):
        return check_build(config['capcut_dir'])
    paths = installed()
    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        raise ValueError('CapCut not found. Set capcut_dir to the folder containing CapCut.exe.')
    reports, errors = [], []
    for path in paths:
        try:
            reports.append(check_build(Path(path).parent))
        except (OSError, ValueError) as exc:
            errors.append(f'{path}: {exc}')
    if len(reports) != 1:
        raise ValueError('Set capcut_dir explicitly. Discovery: ' + '; '.join(errors or [str(r) for r in reports]))
    return reports[0]


def project_pair(original, duplicate, timeline):
    original, duplicate = Path(original).resolve(), Path(duplicate).resolve()
    if original == duplicate or original in duplicate.parents or duplicate in original.parents:
        raise ValueError('Original and duplicate must be separate, non-nested project folders.')
    for directory in (original, duplicate):
        if not directory.is_dir() or any(p.is_symlink() or (os.name == 'nt' and p.stat().st_file_attributes & 0x400)
                                         for p in [directory, *directory.rglob('*')]):
            raise ValueError('Project folders must exist and contain no symlinks/junctions/reparse points.')
    a, b = (read(p / 'draft_meta_info.json') for p in (original, duplicate))
    if not a.get('draft_id') or not b.get('draft_id') or a['draft_id'] == b['draft_id']:
        raise ValueError('Use CapCut Duplicate to create a distinct project ID; a raw folder copy is insufficient.')
    # Reject embedded original paths, including media paths, conservatively.
    needle = str(original).replace('\\', '/').casefold().rstrip('/')
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for v in value.values():
                yield from strings(v)
        elif isinstance(value, list):
            for v in value:
                yield from strings(v)
    for p in duplicate.rglob('*.json'):
        for value in strings(read(p)):
            if needle in value.replace('\\', '/').casefold():
                raise ValueError('Duplicate still references original folder. Relink/copy project-local media using CapCut first.')
    project = read(duplicate / 'Timelines/project.json')
    if timeline not in [t['id'] for t in project['timelines'] if not t.get('is_marked_delete')]:
        raise ValueError('Select an existing active timeline ID from duplicate/Timelines/project.json.')
    doc = read(duplicate / 'Timelines' / timeline / 'draft_content.json')
    if doc.get('id') != timeline or not isinstance(doc.get('duration'), int) or doc['duration'] <= 0:
        raise ValueError('Invalid or empty duplicate timeline.')
    return original, duplicate, doc


def snapshot(directory):
    return {str(p.relative_to(directory)): digest(p) for p in directory.rglob('*') if p.is_file()}


def adapter(build, args, logdir, timeout):
    env = os.environ.copy()
    env.update(CAPCUT_DIR=build['directory'], REVERSE_CLI_REGISTRY=str(ROOT / 'registry.json'),
               REVERSE_CLI_STATE_DIR=str(ROOT / 'state'),
               REVERSE_CLI_FFMPEG=str(ROOT / 'tools/ffmpeg/bin/ffmpeg.exe'),
               PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    command = [sys.executable, '-B', str(UPSTREAM / 'capcut-cli/capcut_agent.py'),
               '--capcut-dir', build['directory'], '--timeout', str(timeout), *args]
    # Stream upstream stdout/stderr to disk; worker state/progress lives in its .runtime logs.
    with (logdir / 'adapter.stdout.json').open('xb') as stdout, (logdir / 'adapter.stderr.log').open('xb') as stderr:
        result = subprocess.run(command, env=env, cwd=ROOT, stdout=stdout, stderr=stderr,
                                timeout=timeout + 20, creationflags=FLAGS)
    response = read(logdir / 'adapter.stdout.json')
    if result.returncode or response.get('ok') is not True:
        raise ValueError('Upstream export failed or outcome unknown. Inspect logs before retry: ' + json.dumps(response))
    return response


def verify_probe(probe, doc, require_audio):
    streams = probe.get('streams', [])
    videos = [s for s in streams if s.get('codec_type') == 'video']
    audios = [s for s in streams if s.get('codec_type') == 'audio']
    if len(videos) != 1 or videos[0].get('codec_name') != 'h264' or 'mp4' not in probe.get('format', {}).get('format_name', '').split(','):
        raise ValueError('FFprobe: expected one H.264 MP4 video stream.')
    video = videos[0]
    canvas = doc['canvas_config']
    if (video.get('width'), video.get('height')) != (canvas['width'], canvas['height']):
        raise ValueError('FFprobe: resolution mismatch.')
    duration = float(probe['format']['duration'])
    tolerance = max(0.1, 2 / float(doc['fps']))
    if not math.isfinite(duration) or abs(duration - doc['duration'] / 1e6) > tolerance:
        raise ValueError('FFprobe: duration mismatch.')
    if require_audio and not audios:
        raise ValueError('FFprobe: audio stream required but missing.')
    for audio in audios:
        if int(audio.get('sample_rate', 0)) <= 0 or int(audio.get('channels', 0)) <= 0:
            raise ValueError('FFprobe: invalid audio metadata.')
    return {'durationSeconds': duration, 'width': video['width'], 'height': video['height'],
            'audioStreams': len(audios), 'audioRequired': require_audio}


def export(config):
    verify_sources()
    build = select_build(config)  # Always before attaching or touching project state.
    if not isinstance(config.get('pid'), int) or config['pid'] <= 0:
        raise ValueError('Set pid to the running CapCut editor process ID shown by Task Manager Details.')
    timeout = config.get('timeout_seconds', 1800)
    if not isinstance(timeout, int) or not 60 <= timeout <= 86400:
        raise ValueError('timeout_seconds must be 60..86400.')
    if not isinstance(config.get('require_audio', True), bool):
        raise ValueError('require_audio must be true or false.')
    original, duplicate, doc = project_pair(config['original_project'], config['duplicate_project'], config['timeline_id'])
    output = Path(config['output']).resolve()
    if output.exists() or output.suffix.lower() != '.mp4' or not output.parent.is_dir():
        raise ValueError('Choose a NEW .mp4 in an existing output folder; overwrite is forbidden.')
    if any(p == output or p in output.parents for p in (original, duplicate)):
        raise ValueError('Export destination must be outside both project folders.')
    ffprobe = ROOT / 'tools/ffmpeg/bin/ffprobe.exe'
    ffmpeg = ROOT / 'tools/ffmpeg/bin/ffmpeg.exe'
    if not ffprobe.is_file() or not ffmpeg.is_file():
        raise ValueError('FFprobe/FFmpeg missing. Run SETUP_MEDIA_TOOLS.bat once (Internet required).')
    logdir = ROOT / 'logs' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    logdir.mkdir(parents=True)
    before = snapshot(original)
    (logdir / 'original-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    # Upstream publishes its validated file here first; user output is only published after FFprobe.
    stage = output.parent / ('.native-cli-' + uuid.uuid4().hex + '.mp4')
    report = {'status': 'FAIL', 'build': build, 'originalUnchanged': None, 'stagedOutput': str(stage)}
    print('Native CapCut export running. Logs:', logdir, flush=True)
    print('Upstream event/state logs: vendor/upstream/capcut-cli/.runtime (no invented progress percentage).', flush=True)
    try:
        response = adapter(build, ['editor', 'export', '--pid', str(config['pid']), '--project', str(duplicate),
                                  '--timeline', config['timeline_id'], '--output', str(stage)], logdir, timeout)
        result = response.get('result', {})
        if result.get('fullDecodeVerified') is not True or result.get('timelineUnchanged') is not True or result.get('native', {}).get('nativeCompletionVerified') is not True:
            raise ValueError('Upstream did not verify native completion, full decode and unchanged timeline.')
        probed = subprocess.run([str(ffprobe), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(stage)],
                                capture_output=True, text=True, encoding='utf-8', timeout=60, creationflags=FLAGS)
        (logdir / 'ffprobe.json').write_text(probed.stdout, encoding='utf-8')
        (logdir / 'ffprobe.stderr.log').write_text(probed.stderr, encoding='utf-8')
        if probed.returncode:
            raise ValueError('FFprobe failed. Staged output retained.')
        verified = verify_probe(json.loads(probed.stdout), doc, config.get('require_audio', True))
        if snapshot(original) != before:
            raise ValueError('Original project changed during export; final output withheld. Inspect original externally; no automatic restore.')
        os.link(stage, output)  # Atomic no-overwrite on Windows; retain stage on any failure.
        report.update(status='PASS', originalUnchanged=True, ffprobe=verified, output=str(output), sha256=digest(output))
        try:
            stage.unlink()
        except OSError as error:
            report['cleanupWarning'] = str(error)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['originalUnchanged'] = snapshot(original) == before
        (logdir / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description='CapCut native CLI runner; upstream version pinned; safe duplicate only.')
    parser.add_argument('command', choices=['menu', 'doctor', 'export', 'integrity'], nargs='?', default='menu')
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    args = parser.parse_args()
    try:
        if args.command == 'integrity':
            verify_sources()
            print(json.dumps({'status': 'PASS', 'check': 'vendored upstream integrity'}))
            return 0
        config = read(args.config) if args.config.is_file() else {}
        command = args.command
        if command == 'menu':
            print('CapCut Native CLI Export | upstream build 9.5.0.4050 only')
            print('1. Detect CapCut / check compatibility\n2. Export configured safe duplicate\n3. Exit')
            choice = input('Choose: ').strip()
            if choice == '3':
                return 0
            command = {'1': 'doctor', '2': 'export'}.get(choice)
            if command is None:
                raise ValueError('Choose 1, 2 or 3.')
        if command == 'doctor':
            verify_sources()
            print(json.dumps({'status': 'PASS', 'build': select_build(config), 'nativeExport': 'NOT TESTED'}, indent=2))
        else:
            print(json.dumps(export(config), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error), 'success': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
