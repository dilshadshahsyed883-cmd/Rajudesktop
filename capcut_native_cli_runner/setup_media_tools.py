"""Download media verifiers directly from their publisher; no rendering fallback."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
URL = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-28-19-47/ffmpeg-n8.1.3-25-g611cec792a-win64-lgpl-shared-8.1.zip'
SHA256 = '0448c3f3b9bdc724cc0189d5ce6e6bfa5b8937e7ec408e1e97fb08719bdb3b92'


def main():
    target = ROOT / 'tools/ffmpeg'
    if target.exists():
        raise ValueError('tools/ffmpeg already exists; setup refuses to replace it.')
    (ROOT / 'tools').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='media-setup-', dir=ROOT / 'tools') as tmp:
        work = Path(tmp)
        archive = work / 'media.zip'
        print('Downloading LGPL FFmpeg/FFprobe from BtbN (about 82 MB)...', flush=True)
        urllib.request.urlretrieve(URL, archive)
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != SHA256:
                raise ValueError('Media archive SHA-256 mismatch; installation stopped.')
        unpack = work / 'unpacked'
        with zipfile.ZipFile(archive) as z:
            for item in z.infolist():
                dest = (unpack / item.filename).resolve()
                if not dest.is_relative_to(unpack.resolve()):
                    raise ValueError('Invalid archive path')
            z.extractall(unpack)
        roots = list(unpack.iterdir())
        if len(roots) != 1 or not (roots[0] / 'bin/ffprobe.exe').is_file() or not (roots[0] / 'bin/ffmpeg.exe').is_file():
            raise ValueError('Unexpected media archive layout')
        shutil.move(str(roots[0]), target)
    print(json.dumps({'status': 'PASS', 'archiveSha256': SHA256, 'installed': str(target)}))


if __name__ == '__main__':
    main()
