"""Produce an immutable source-parity bundle; never touch a running VPS.

This phase captures the ENTIRE tracked Scene Builder web and worker source
(rather than the earlier stripped-down desktop rewrite) together with the
unmodified Z Studio CapCut draft writer. It does not claim runtime parity.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

UPSTREAM_REQUIRED = (
    "part01/app.py",
    "part01/director_v25.py",
    "part01/director_v25_execution.py",
    "part01/scene_media_library.py",
    "part01/scene_media_source_policy.py",
    "part01/templates/base.html",
    "part01/templates/queue.html",
    "part01/templates/scene_media_library.html",
    "part01/static/styles.css",
    "part02/api_server.py",
    "part02/director_v25_timing.py",
    "part02/director_v25_transitions.py",
    "part02/smart_scroll/v2_renderer.py",
    "part02/smart_scroll/v3_engine.py",
    "part02/smart_scroll/caption_sync.py",
    "part02/smart_scroll/lut_engine.py",
    "part02/smart_scroll/transition_engine.py",
)
CAPCUT_REQUIRED = (
    "z_builder/capcut-draft.js",  # original Z Studio module, not a rewrite
    "z_builder/capcut_bridge.js",
    "z_builder/capcut.py",
    "z_builder/bootstrap_node.py",
)
PRIVATE_NAMES = {".env", ".git", ".venv", "__pycache__", ".pytest_cache"}
PRIVATE_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12", ".pfx"}


class IncompleteSource(RuntimeError):
    pass


def _filemap(upstream: Path, repository: Path) -> dict[str, Path]:
    missing = [str(upstream / rel) for rel in UPSTREAM_REQUIRED
               if not (upstream / rel).is_file()]
    missing += [str(repository / rel) for rel in CAPCUT_REQUIRED
                if not (repository / rel).is_file()]
    if missing:
        raise IncompleteSource("Full web source or native Z Studio exporter missing:\n" + "\n".join(missing))

    selected: dict[str, Path] = {}
    # All tracked app files, not a filtered subset of Scene Builder features.
    for part in ("part01", "part02"):
        for candidate in sorted((upstream / part).rglob("*")):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            relative = candidate.relative_to(upstream)
            if any(component in PRIVATE_NAMES or component.startswith(".script-work-rollbacks")
                   for component in relative.parts):
                continue
            if candidate.suffix.lower() in PRIVATE_SUFFIXES:
                continue
            selected[f"Z-Builder/scene-builder-web/{relative.as_posix()}"] = candidate

    for rel in CAPCUT_REQUIRED:
        selected[f"Z-Builder/capcut/{Path(rel).name}"] = repository / rel
    return selected


def build(upstream: Path, repository: Path, target: Path, upstream_commit: str) -> dict:
    """Copy source byte-for-byte with SHA manifest. No installation/deployment."""
    upstream, repository, target = upstream.resolve(), repository.resolve(), target.resolve()
    if len(upstream_commit) != 40 or any(c not in "0123456789abcdef" for c in upstream_commit.lower()):
        raise ValueError("Pin a full 40-character source commit SHA")
    sources = _filemap(upstream, repository)
    manifest: dict = {
        "identity": "Z Builder full web source parity (integration workbench)",
        "upstream": "dilshadshahsyed883-cmd/vps1-deploy-control",
        "upstream_commit": upstream_commit,
        "note": "Source parity is verified; full Windows runtime and one-click CapCut integration are NOT yet verified.",
        "files": {},
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w", ZIP_DEFLATED, compresslevel=8) as archive:
        for name, path in sorted(sources.items()):
            data = path.read_bytes()
            archive.writestr(name, data)
            manifest["files"][name] = {"bytes": len(data), "sha256": sha256(data).hexdigest()}
        archive.writestr(
            "Z-Builder/SOURCE_PARITY.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-source", required=True, type=Path,
                        help="Checked-out upstream apps/scene-builder directory")
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--upstream-commit", required=True)
    args = parser.parse_args()
    result = build(args.upstream_source, args.repository, args.output, args.upstream_commit)
    print(f"Source parity archive: {args.output} ({len(result['files'])} verified files)")
