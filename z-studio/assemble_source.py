"""Reassemble the original verified source chunks plus current launcher fixes.

Z Studio binaries are stored as Git blobs to avoid API upload limits. The
immutable base archive is verified before a small, versioned launcher overlay
is applied. Output ZIP always includes the automatic Node/npm bootstrap.
"""
from pathlib import Path, PurePosixPath
from io import BytesIO
import argparse
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parent
EXPECTED_BASE_SHA256 = "cf83034ae1c61f56aab84487d1f21ba6d9200e8e7a908c297385e09923f0b09f"
PATCH_FILES = {
    "Z-Studio-Local/start.bat": "launcher/start.bat",
    "Z-Studio-Local/bootstrap_node.py": "launcher/bootstrap_node.py",
    "Z-Studio-Local/README.txt": "launcher/README.txt",
}


def assemble(extract=False):
    parts = sorted((ROOT / "source-chunks").glob("part-*.bin"))
    if len(parts) != 10:
        raise SystemExit(f"Expected 10 source chunks, found {len(parts)}")
    source_data = b"".join(p.read_bytes() for p in parts)
    actual = hashlib.sha256(source_data).hexdigest()
    if actual != EXPECTED_BASE_SHA256:
        raise SystemExit(f"Source checksum mismatch: {actual}")

    patches = {target: (ROOT / path).read_bytes() for target, path in PATCH_FILES.items()}
    source = BytesIO(source_data)
    result = BytesIO()
    with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(result, "w") as output:
        existing = set()
        for entry in original.infolist():
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts:
                raise SystemExit(f"Unsafe source ZIP member: {entry.filename}")
            existing.add(entry.filename)
            output.writestr(entry, patches.get(entry.filename, original.read(entry.filename)))
        for name, content in patches.items():
            if name not in existing:
                output.writestr(name, content, compress_type=zipfile.ZIP_DEFLATED)

    archive = ROOT / "Z-Studio-Local-Source.zip"
    archive.write_bytes(result.getvalue())
    if extract:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(ROOT)
    print(f"Z Studio verified with auto-Node startup: {archive} ({archive.stat().st_size} bytes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract", action="store_true", help="Extract verified source to Z-Studio-Local")
    args = parser.parse_args()
    assemble(args.extract)
