"""Read-only PE export and embedded QML bridge inspection for CapCut 9.7.

No DLL loading, process attachment, injection, Qt monkey-patching, or editing.
All analysis uses file reads and validates PE address bounds.
"""
from __future__ import annotations
import json
import mmap
import os
from pathlib import Path
import struct
from typing import Any

HOME_ANCHORS = {
    "draft_home_model": b"property HomePageLocalDraftViewModel rootViewModel: null",
    "draft_home_id": b'property string draftId: ""',
    "draft_home_path": b'property string strProjectPath: ""',
    "native_push_task": b"BackEndExportImpl::pushTask",
    "native_export_next": b"BackEndExportImpl::exportNextTask",
    "native_export_click": b"BackEndExportImpl::clickDraftFromHomeView",
    "homepage_export_log": b"clickBackgroudExport in homepage",
}
PUBLIC_EXPORT_WORDS = ("export", "draft", "qml", "home", "creator", "register")
WINDOW_LIMIT = 160
MAX_EXPORT_NAMES = 350_000  # bounded by verified PE section bytes as well
MAX_NAME_BYTES = 32_768   # C++ decorated exports can far exceed 320 bytes


class InvalidPE(ValueError):
    pass


def _u16(data, pos):
    if pos < 0 or pos + 2 > len(data):
        raise InvalidPE("Truncated PE 16-bit field")
    return struct.unpack_from("<H", data, pos)[0]


def _u32(data, pos):
    if pos < 0 or pos + 4 > len(data):
        raise InvalidPE("Truncated PE 32-bit field")
    return struct.unpack_from("<I", data, pos)[0]


def _str(data, pos, limit=MAX_NAME_BYTES):
    if pos < 0 or pos >= len(data):
        raise InvalidPE("Export name points outside file")
    end = data.find(b"\0", pos, min(len(data), pos + limit))
    if end == -1:
        raise InvalidPE("Unterminated export name")
    return bytes(data[pos:end]).decode("ascii", errors="replace")


def pe_export_details(data):
    """Parse PE32/PE32+ export names with bounds and partial-read diagnostics.

    A single malformed or unusually long export name must not discard all
    remaining names. Name counts are constrained by the backed PE section,
    not an arbitrary limit of 25,000, which was too small for real CapCut DLLs.
    """
    if len(data) < 256 or data[:2] != b"MZ":
        raise InvalidPE("Missing DOS MZ header")
    nt = _u32(data, 0x3C)
    if nt + 24 > len(data) or data[nt:nt + 4] != b"PE\0\0":
        raise InvalidPE("Missing PE signature")
    sections = _u16(data, nt + 6)
    opt_size = _u16(data, nt + 20)
    opt = nt + 24
    if opt + opt_size > len(data):
        raise InvalidPE("Truncated optional header")
    magic = _u16(data, opt)
    if magic == 0x20B:
        dd_offset = 112
    elif magic == 0x10B:
        dd_offset = 96
    else:
        raise InvalidPE("Unsupported PE optional header magic")
    if opt_size < dd_offset + 8:
        raise InvalidPE("No export data directory")
    export_rva = _u32(data, opt + dd_offset)
    export_size = _u32(data, opt + dd_offset + 4)
    if not export_rva or not export_size:
        return {"names": [], "declared_export_names": 0,
                "skipped_export_names": 0, "export_parse_complete": True}
    sec_base = opt + opt_size
    if sections > 96 or sec_base + sections * 40 > len(data):
        raise InvalidPE("Bad section table")
    segments = []
    for i in range(sections):
        start = sec_base + 40 * i
        virtual_size = _u32(data, start + 8)
        virtual_rva = _u32(data, start + 12)
        raw_size = _u32(data, start + 16)
        raw_offset = _u32(data, start + 20)
        if raw_size and raw_offset + raw_size <= len(data):
            segments.append((virtual_rva, max(virtual_size, raw_size), raw_offset, raw_size))

    def from_rva(rva, need=1):
        for va, vspan, raw, rsize in segments:
            delta = rva - va
            if delta >= 0 and delta + need <= vspan and delta + need <= rsize:
                return raw + delta
        raise InvalidPE("Export RVA outside backed section")

    export_at = from_rva(export_rva, 40)
    declared_count = _u32(data, export_at + 24)
    name_rva = _u32(data, export_at + 32)
    if declared_count > MAX_EXPORT_NAMES:
        raise InvalidPE(
            "Export table declares " + str(declared_count) +
            " names (safety cap " + str(MAX_EXPORT_NAMES) + ")")
    if declared_count == 0:
        return {"names": [], "declared_export_names": 0,
                "skipped_export_names": 0, "export_parse_complete": True}
    # from_rva validates that the entire table fits inside a file-backed section.
    table = from_rva(name_rva, declared_count * 4)
    names = []
    skipped = 0
    for i in range(declared_count):
        try:
            rva = _u32(data, table + 4 * i)
            names.append(_str(data, from_rva(rva)))
        except InvalidPE:
            skipped += 1
            # Continue safely, but never claim a complete callable export map.
    return {"names": names, "declared_export_names": declared_count,
            "skipped_export_names": skipped, "export_parse_complete": skipped == 0}


def pe_exports(data):
    """Backwards compatible public-name list; skips malformed names."""
    return pe_export_details(data)["names"]


def qml_anchors(data, markers=HOME_ANCHORS):
    """Report compact evidence, NOT proprietary QML source extraction."""
    report = {}
    for label, needle in markers.items():
        hits = []
        start = 0
        while len(hits) < 3:
            pos = data.find(needle, start)
            if pos < 0:
                break
            # Only 160 bytes either side to identify the component boundary.
            left = bytes(data[max(0, pos-WINDOW_LIMIT):pos]).split(b"\0")[-1]
            right = bytes(data[pos + len(needle):pos + len(needle) + WINDOW_LIMIT]).split(b"\0")[0]
            visible = (left[-WINDOW_LIMIT:] + needle + right).decode("utf-8", errors="replace")
            # Source can contain binary characters: collapse for readable diagnostics.
            context = "".join(ch if ch.isprintable() else " " for ch in visible)
            hits.append({"offset": pos, "context": context[:350]})
            start = pos + len(needle)
        report[label] = {"found": bool(hits), "hits": hits}
    return report


def inspect_module(path, include_qml=False):
    """Read-only and memory-mapped: works on low-memory 8GB Windows laptops."""
    with Path(path).open("rb") as handle:
        if not handle.read(1):
            raise InvalidPE("Empty binary")
        handle.seek(0)
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
            details = pe_export_details(data)
            exports = details["names"]
            relevant = [s for s in exports if any(w in s.lower() for w in PUBLIC_EXPORT_WORDS)]
            refs = qml_anchors(data) if include_qml else {}
            direct = [name for name in exports if
                      "BackEndExportImpl" in name and any(w in name for w in
                      ("pushTask", "exportNextTask", "clickDraftFromHomeView"))]
            return {"file": Path(path).name,
                    "size_bytes": len(data),
                    "pe_export_count": len(exports),
                    "declared_export_names": details["declared_export_names"],
                    "skipped_export_names": details["skipped_export_names"],
                    "export_parse_complete": details["export_parse_complete"],
                    "relevant_public_exports": relevant[:150],
                    "target_backend_exports": direct,
                    "qml_and_native_string_evidence": refs,
                    "direct_callable_export_proven": bool(direct)}


def inspect_install(root):
    root = Path(root)
    result = {"version": "9.7.0.4153",
              "mode": "read-only offline static PE/QML bridge inspection",
              "dll_loading": False, "capcut_launched": False,
              "installation_modified": False, "native_export_verified": False,
              "home_ui_patch_implemented": False, "modules": {}, "errors": {}}
    for name in ("VECreator.dll", "cccreator.dll", "videoeditor.dll"):
        try:
            result["modules"][name] = inspect_module(root / name, include_qml=name == "VECreator.dll")
        except (OSError, InvalidPE, ValueError) as exc:
            result["errors"][name] = str(exc)
    target = result["modules"].get("VECreator.dll", {})
    evidence = target.get("qml_and_native_string_evidence", {})
    all_anchors = all(v.get("found") for v in evidence.values()) if evidence else False
    incomplete_export_tables = any(
        not module.get("export_parse_complete", False)
        for module in result["modules"].values()
    )
    result["bridge_level"] = (
        "INCOMPLETE_STATIC_EVIDENCE" if result["errors"] else
        "PARTIAL_EXPORT_TABLE" if incomplete_export_tables else
        "PUBLIC_PE_EXPORT_PRESENT_UNVALIDATED" if target.get("direct_callable_export_proven")
        else "EMBEDDED_SYMBOLS_ONLY" if all_anchors else "INCOMPLETE_STATIC_EVIDENCE"
    )
    result["next_required_proof"] = (
        "A callable Qt/QML bridge verified inside isolated CapCut 9.7 Windows runtime, "
        "with one successful native MP4 render. String presence alone cannot prove this."
    )
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="CapCut 9.7 Home QML/native queue: offline bridge evidence")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", type=Path, help="JSON report outside CapCut installation")
    args = parser.parse_args(argv)
    out = args.out.resolve() if args.out else None
    root = args.root.resolve()
    if out is not None and (out == root or root in out.parents):
        parser.error("Report must not be written inside the CapCut installation")
    result = inspect_install(root)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    elif __import__("sys").stdout is not None:
        print(json.dumps(result, indent=2))
    return 0 if not result["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
