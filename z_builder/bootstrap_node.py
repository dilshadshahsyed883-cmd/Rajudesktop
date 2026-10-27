"""Verified local Node 24 LTS bootstrap for Z Builder, adapted from Z Studio.
Downloads official nodejs.org ZIP and verifies SHASUMS256 before installing.
No system PATH changes, no admin permissions, and no global installation.
"""
from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DIST = 'https://nodejs.org/dist'
FALLBACK = 'v24.21.0'


def request(url, limit):
    with urlopen(Request(url, headers={'User-Agent': 'Z-Builder-Node-Setup/1.0'}), timeout=45) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError(f'Oversized remote response from {url}')
    return data


def architecture():
    machine = platform.machine().lower()
    if machine in {'amd64', 'x86_64'}:
        return 'x64'
    if machine in {'arm64', 'aarch64'}:
        return 'arm64'
    raise RuntimeError('Unsupported Windows CPU architecture: ' + machine)


def latest_lts(arch):
    try:
        releases = json.loads(request(f'{DIST}/index.json', 3_000_000))
        return next(x['version'] for x in releases if x.get('lts') and
                    re.fullmatch(r'v24\.\d+\.\d+', x.get('version', '')) and
                    f'win-{arch}-zip' in x.get('files', []))
    except (OSError, ValueError, StopIteration) as exc:
        print(f'Official release index unavailable ({exc}); using checksum-verified {FALLBACK}')
        return FALLBACK


def install():
    if os.name != 'nt':
        raise RuntimeError('Portable setup is only needed on Windows')
    dest = ROOT / '.runtime' / 'node'
    if (dest / 'node.exe').is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    arch = architecture()
    version = latest_lts(arch)
    name = f'node-{version}-win-{arch}.zip'
    base = f'{DIST}/{version}'
    shasums = request(f'{base}/SHASUMS256.txt', 100_000).decode('utf-8')
    match = re.search(r'^([0-9a-fA-F]{64})\s+\*?' + re.escape(name) + r'\s*$', shasums, re.M)
    if not match:
        raise RuntimeError('Official SHA256 listing does not contain ' + name)
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix='.zb-node-') as temp:
        archive = Path(temp) / name
        sha = hashlib.sha256()
        print('Downloading official Node runtime ' + version, flush=True)
        with urlopen(Request(f'{base}/{name}', headers={'User-Agent': 'Z-Builder-Node-Setup/1.0'}), timeout=60) as response, archive.open('wb') as output:
            while chunk := response.read(1 << 20):
                output.write(chunk)
                sha.update(chunk)
        if sha.hexdigest().lower() != match[1].lower():
            raise RuntimeError('Node ZIP SHA256 verification FAILED; no runtime installed')
        print('Checksum verified', flush=True)
        top = name[:-4]
        with ZipFile(archive) as z:
            for item in z.infolist():
                path = item.filename.replace('\\', '/')
                if (path.startswith('/') or '..' in path.split('/') or
                        not path.startswith(top + '/') or len(path) > 255):
                    raise RuntimeError('Unsafe ZIP entry: ' + path)
            z.extractall(temp)
        source = Path(temp) / top
        if not (source / 'node.exe').is_file():
            raise RuntimeError('Official runtime ZIP missing node.exe')
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(source), str(dest))
    print('Portable Node available at ' + str(dest), flush=True)
    return dest


if __name__ == '__main__':
    try:
        install()
    except Exception as exc:
        print('Node setup failed: ' + str(exc), file=sys.stderr)
        sys.exit(1)
