"""Install verified official portable Node.js LTS locally, without admin rights.

Only required when Windows cannot find a working ``node`` and ``npm``.
Downloads directly from HTTPS nodejs.org, checks the SHA-256 published on the
same official distribution server, and installs into ``.runtime/node``.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile

APP_ROOT = Path(__file__).resolve().parent
DIST_BASE = "https://nodejs.org/dist"
FALLBACK_LTS = "v24.21.0"  # official known Node 24 LTS release, only used if metadata is unavailable
MAX_INDEX_BYTES = 3_000_000
MAX_SUMS_BYTES = 100_000


def get_bytes(url: str, max_bytes: int) -> bytes:
    req = Request(url, headers={"User-Agent": "Z-Studio-Local-Setup/1.0"})
    with urlopen(req, timeout=40) as response:
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError("Unexpectedly large metadata response")
    return payload


def win_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        return "x64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    raise RuntimeError("Unsupported Windows CPU architecture: " + machine)


def node_release(arch: str) -> str:
    """Resolve a supported Node 24 LTS release, using the official JSON index."""
    try:
        releases = json.loads(get_bytes(f"{DIST_BASE}/index.json", MAX_INDEX_BYTES))
        for item in releases:
            version = str(item.get("version", ""))
            if (re.fullmatch(r"v24\.\d+\.\d+", version)
                    and item.get("lts")
                    and f"win-{arch}-zip" in item.get("files", [])):
                return version
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        print(f"Notice: release index unavailable ({exc}); using verified LTS fallback.", flush=True)
    return FALLBACK_LTS


def sha_from_official_file(shasums: bytes, filename: str) -> str:
    pattern = re.compile(r"^([0-9a-fA-F]{64})\s+\*?" + re.escape(filename) + r"\s*$", re.MULTILINE)
    m = pattern.search(shasums.decode("utf-8"))
    if not m:
        raise ValueError(f"Official SHA-256 file does not list {filename}")
    return m.group(1).lower()


def fetch_to_file(url: str, path: Path) -> str:
    """Stream binary and compute SHA-256 (no large in-memory binaries)."""
    digest = hashlib.sha256()
    req = Request(url, headers={"User-Agent": "Z-Studio-Local-Setup/1.0"})
    with urlopen(req, timeout=60) as response, path.open("wb") as output:
        downloaded = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            digest.update(chunk)
            downloaded += len(chunk)
            if downloaded % (5 * 1024 * 1024) < len(chunk):
                print(f"Downloaded {downloaded // (1024 * 1024)} MB...", flush=True)
    return digest.hexdigest()


def validated_extract(archive: Path, destination: Path, expected_folder: str) -> None:
    """Allow only regular files within the official archive's own root."""
    with ZipFile(archive) as zf:
        for member in zf.infolist():
            name = member.filename.replace("\\", "/")
            pure = Path(name)
            if (name.startswith("/") or ".." in pure.parts
                    or not (name == expected_folder + "/" or name.startswith(expected_folder + "/"))):
                raise ValueError(f"Unsafe archive entry: {name}")
            if len(name) > 250:
                raise ValueError("Unexpectedly long archive member name")
        zf.extractall(destination)


def install(root: Path = APP_ROOT) -> Path:
    if os.name != "nt":
        raise RuntimeError("This Node.js bootstrap is intended for Windows desktop")
    runtime = root / ".runtime"
    target = runtime / "node"
    if (target / "node.exe").is_file() and (target / "npm.cmd").is_file():
        print("Portable Node.js/npm already available.")
        return target
    runtime.mkdir(parents=True, exist_ok=True)
    arch = win_arch()
    release = node_release(arch)
    archive_name = f"node-{release}-win-{arch}.zip"
    official_base = f"{DIST_BASE}/{release}"
    expected = sha_from_official_file(
        get_bytes(f"{official_base}/SHASUMS256.txt", MAX_SUMS_BYTES), archive_name
    )
    print(f"Installing verified Node.js {release} ({arch}) from nodejs.org", flush=True)
    with tempfile.TemporaryDirectory(prefix="zstudio-node-", dir=runtime) as stage_str:
        stage = Path(stage_str)
        archive = stage / archive_name
        actual = fetch_to_file(f"{official_base}/{archive_name}", archive)
        if actual.lower() != expected:
            raise ValueError("Official Node.js SHA-256 verification failed")
        print("Verified Node.js SHA-256 checksum.", flush=True)
        validated_extract(archive, stage, archive_name[:-4])
        source_dir = stage / archive_name[:-4]
        if not (source_dir / "node.exe").is_file() or not (source_dir / "npm.cmd").is_file():
            raise FileNotFoundError("Official archive missing node.exe/npm.cmd")
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(source_dir), str(target))
    print(f"Portable runtime ready: {target}", flush=True)
    return target


if __name__ == "__main__":
    try:
        install()
    except Exception as exc:
        print(f"Node.js setup failed: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
