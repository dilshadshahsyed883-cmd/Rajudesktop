"""Read-only evidence probe for CapCut 9.7 Home QML / native background export.

No binary patching, process injection, draft access, network calls or rendering.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Mapping

VERSION = "9.7.0.4153"
EXPECTED_SHA256 = {
    "CapCut.exe": "fbc3ef1624351a0ac94795c6f7d664e286f3f4074ce0844cfb912515e618f92b",
    "cccreator.dll": "216245151a6dee4b350b7b4f45c6076f8ab7cb8891226b4ced4d9c53094d41a4",
    "VECreator.dll": "967fd06e60a1c68c055278cf6bb1ecd1bb078277d58167fcf6b4cfa2a1a27cf9",
    "videoeditor.dll": "592b5e03c1676e17d43665a433094120003a2be21d0e1951987f7aa829fb369a",
}
MARKERS = {
    "CapCut.exe": {},
    "cccreator.dll": {},
    "VECreator.dll": {
        "home_qml_model": b"property HomePageLocalDraftViewModel rootViewModel: null",
        "home_project_path": b'property string strProjectPath: ""',
        "home_project_id": b'property string draftId: ""',
        "native_task_enqueue": b"export_ns::BackEndExportImpl::pushTask",
        "native_serial_scheduler": b"export_ns::BackEndExportImpl::exportNextTask",
        "home_export_bridge": b"export_ns::BackEndExportImpl::clickDraftFromHomeView",
        "native_draft_path_route": b"[BGExportMgr] exportNextTask param is not null, exporting by draft path!",
        "home_background_export": b"[BGExportMgr] clickBackgroudExport in homepage",
    },
    "videoeditor.dll": {
        "engine_batch_export": b"ExportService::batchExportStart",
        "engine_multi_export": b"multiExportStart",
    },
}


def inspect_binary(path: Path, markers: Mapping[str, bytes], chunk_size: int = 1024 * 1024):
    """Hash and scan a binary in a single bounded-memory streaming pass."""
    digest = hashlib.sha256()
    missing = dict(markers)
    found = {key: False for key in markers}
    overlap = max((len(v) for v in markers.values()), default=1) - 1
    carry = b""
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            size += len(chunk)
            digest.update(chunk)
            haystack = carry + chunk
            for key, term in tuple(missing.items()):
                if term in haystack:
                    found[key] = True
                    del missing[key]
            carry = haystack[-overlap:] if overlap else b""
    return {"size_bytes": size, "sha256": digest.hexdigest(), "markers": found}


def audit(root: Path, expected: Mapping[str, str] = EXPECTED_SHA256):
    root = Path(root)
    results = {}
    all_valid = True
    for name, expected_hash in expected.items():
        path = root / name
        if not path.is_file():
            results[name] = {"present": False, "verified_exact_archive": False,
                             "markers": {key: False for key in MARKERS[name]}}
            all_valid = False
            continue
        details = inspect_binary(path, MARKERS[name])
        exact = details["sha256"] == expected_hash
        all_markers = all(details["markers"].values())
        results[name] = {"present": True, "verified_exact_archive": exact, **details}
        all_valid &= exact and all_markers
    return {
        "version": VERSION,
        "source": "read-only exact SHA-256 and embedded symbol/QML inspection",
        "status": "NATIVE_HOME_EXPORT_SYMBOLS_FOUND" if all_valid else "UNVERIFIED_OR_INCOMPLETE",
        "modules": results,
        "native_route_candidate": "VECreator HomeScene QML + BackEndExportImpl background task queue",
        "capcut_home_checkbox_patch_implemented": False,
        "callable_abi_verified": False,
        "live_mp4_export_verified": False,
        "original_files_changed": False,
        "note": "Binary string presence does not prove that these private methods are callable from QML. "
                "Do not patch signed files or invoke guessed ABIs before isolated Windows runtime validation."
    }


def default_root():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise ValueError("LOCALAPPDATA missing; use --root to select the extracted 9.7 directory")
    return Path(base) / "CapCut" / "Apps" / VERSION


def self_check():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fake_hashes = {}
        for name, markers in MARKERS.items():
            path = root / name
            path.write_bytes(b"start" + b"#".join(markers.values()) + b"end")
            fake_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        result = audit(root, fake_hashes)
        assert result["status"] == "NATIVE_HOME_EXPORT_SYMBOLS_FOUND"
        assert result["original_files_changed"] is False
        assert result["capcut_home_checkbox_patch_implemented"] is False
        return {"self_check": "PASS", "native_patch_available": False,
                "real_capcut_tested": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="CapCut 9.7 native Home export audit (read-only)")
    parser.add_argument("--root", type=Path, help="Installed/extracted 9.7.0.4153 folder")
    parser.add_argument("--json", type=Path, help="Optional machine-readable output (outside CapCut install)")
    parser.add_argument("--self-check", action="store_true", help="Self-test with synthetic files")
    args = parser.parse_args(argv)
    if args.self_check:
        result = self_check()
        code = 0
    else:
        try:
            root = args.root if args.root else default_root()
        except ValueError as error:
            parser.error(str(error))
        result = audit(root)
        code = 0 if result["status"] == "NATIVE_HOME_EXPORT_SYMBOLS_FOUND" else 2
    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.json:
        target = args.json.resolve()
        if not args.self_check and (target == root.resolve() or root.resolve() in target.parents):
            parser.error("Refusing to create reports inside the CapCut installation")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + "\n", encoding="utf-8")
    print(output)
    return code


if __name__ == "__main__":
    sys.exit(main())
