"""Build a source-only ZIP from an explicit allowlist; never traverse user media."""
import argparse
import hashlib
from pathlib import Path
import zipfile

FILES=(
    'app.py','engine.py','captions.py','effects.py','fontinfo.py','power.py','state.py',
    'start.bat','SELF_TEST.bat','requirements.txt','README.txt','README.md',
    'VALIDATION.txt','CHANGELOG.md','REPOSITORY_RECORD.md','build_source_zip.py',
    'tools/PLACE_FFMPEG_HERE.txt',
    'tests/test_engine.py','tests/test_captions.py','tests/test_queue.py','tests/test_styles_effects.py',
)


def build(output):
    root=Path(__file__).resolve().parent
    output=Path(output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    for name in FILES:
        if not (root/name).is_file():raise FileNotFoundError(name)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(root/name,'CapCut_Independent_Renderer_v04/'+name)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():raise RuntimeError('Archive CRC check failed')
    checksum=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(checksum+'  '+output.name+'\n',encoding='utf-8')
    print(output)
    print('SHA256 '+checksum)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    build(parser.parse_args().output)
