"""Atomic, user-local queue persistence and one-instance lock."""
from pathlib import Path
import json
import os
import time
import hashlib


def state_folder():
    root = Path(os.environ.get('LOCALAPPDATA') or (Path.home()/'.local'/'share'))
    folder = root/'CapCutIndependentRenderer'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_state(path, data):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def load_state(path):
    path = Path(path)
    if not path.exists():
        return {}, ''
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('items', []), list):
            raise ValueError('Invalid queue structure')
        for item in data.get('items', []):
            if not isinstance(item, dict) or not all(k in item for k in ('path', 'name', 'length', 'media', 'status')):
                raise ValueError('Invalid queue item')
            if item['status'] in ('Analyzing', 'Rendering'):
                item['status'] = 'Interrupted - retry'
        return data, ''
    except (ValueError, OSError) as error:
        backup = path.with_name(f'queue_corrupt_{time.time_ns()}.json')
        try:
            path.replace(backup)
        except OSError:
            pass
        return {}, f'Could not restore queue: {error}. Original retained as {backup.name} when possible.'


def completed_for(item, settings):
    if not (item.get('status', '').startswith('Verified')
            and item.get('last_settings') == settings
            and Path(item.get('last_output') or '__no_output__').is_file()):
        return False
    try:
        signature=hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()
        return signature==item.get('last_source_sha256')
    except (OSError,KeyError):
        return False


class InstanceLock:
    def __init__(self, path):
        self.stream = open(path, 'a+b')
        self.stream.seek(0)
        if self.stream.read(1) == b'':
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError('The independent renderer is already running.')

    def close(self):
        self.stream.close()
