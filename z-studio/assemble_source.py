"""Assemble Z Studio Local source archive from verified GitHub binary chunks."""
from pathlib import Path
import argparse, hashlib, sys, zipfile

ROOT = Path(__file__).resolve().parent
EXPECTED = "cf83034ae1c61f56aab84487d1f21ba6d9200e8e7a908c297385e09923f0b09f"
def assemble(extract=False):
    parts = sorted((ROOT / "source-chunks").glob("part-*.bin"))
    if len(parts) != 10:
        raise SystemExit(f"Expected 10 source chunks, found {len(parts)}")
    archive = ROOT / "Z-Studio-Local-Source.zip"
    data = b"".join(p.read_bytes() for p in parts)
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED:
        raise SystemExit(f"Source checksum mismatch: {digest}")
    archive.write_bytes(data)
    if extract:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                path = (ROOT / info.filename).resolve()
                if not path.is_relative_to(ROOT.resolve()):
                    raise SystemExit(f"Unsafe ZIP member: {info.filename}")
            zf.extractall(ROOT)
    print(f"Z Studio local source verified: {archive} ({len(data)} bytes)")
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract", action="store_true", help="Unpack the source folder too")
    args = parser.parse_args()
    assemble(args.extract)
