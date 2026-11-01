"""Reconstruct read-only original VECreator.dll from owner's existing split archive
on a short-lived GitHub Actions runner, then identify Home QML export *call sites*.

No CapCut process launch, no binary patch, no original archive upload to GitHub.
No assumptions about Drive link being public: inaccessible links are reported.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import zlib

PART5_START = 4 * 167772160
PART_SIZE = 167772160
ENTRY_OFFSET = 766688433  # Original 9.7.0.4153 local-file-header offset
ENTRY_COMPRESSED_SIZE = 126060589
EXPECTED_BINARY_SHA256 = "967fd06e60a1c68c055278cf6bb1ecd1bb078277d58167fcf6b4cfa2a1a27cf9"
EXPECTED_BINARY_SIZE = 281017256

ANCHORS = [
    b"property HomePageLocalDraftViewModel rootViewModel: null",
    b"property string strProjectPath:",
    b"property string draftId:",
    b"property bool inExport:",
    b"BackEndExportImpl::pushTask",
    b"BackEndExportImpl::exportNextTask",
    b"BackEndExportImpl::clickDraftFromHomeView",
    b"clickBackgroudExport in homepage",
]
INTERESTING = re.compile(
    rb"(?i)(onClicked|onTriggered|Connections|rootViewModel|baseViewModel|"
    rb"export|render|background|draftId|strProjectPath|inExport|invokeMethod)"
)


def original_vecreator_bytes(part5: Path, part6: Path) -> bytes:
    """Verify exact SHA256 before interpreting anything as embedded source."""
    part5 = Path(part5)
    part6 = Path(part6)
    if part5.stat().st_size != PART_SIZE or part6.stat().st_size != 90568892:
        raise ValueError("Original archive part sizes do not match; refusing analysis")
    with part5.open("rb") as first, part6.open("rb") as second:
        first.seek(ENTRY_OFFSET - PART5_START)
        hdr = first.read(30)
        if len(hdr) != 30 or hdr[:4] != b"PK\\x03\\x04":
            raise ValueError("VECreator ZIP local header does not match expected offset")
        name_len, extra_len = struct.unpack_from("<HH", hdr, 26)
        name = first.read(name_len)
        first.read(extra_len)
        if not name.lower().endswith(b"vecreator.dll"):
            raise ValueError("ZIP entry is not VECreator.dll")
        first_pos = first.tell()
        remaining = ENTRY_COMPRESSED_SIZE
        output = bytearray()
        inflator = zlib.decompressobj(-15)
        while remaining > 0:
            stream = first if first_pos < PART_SIZE else second
            if stream is first:
                take = min(1024 * 1024, remaining, PART_SIZE - first_pos)
                chunk = stream.read(take)
                first_pos += len(chunk)
            else:
                chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("Archive truncated during DLL extraction")
            remaining -= len(chunk)
            output.extend(inflator.decompress(chunk))
        output.extend(inflator.flush())
        if not inflator.eof:
            raise ValueError("VECreator deflate stream incomplete")
        digest = hashlib.sha256(output).hexdigest()
        if len(output) != EXPECTED_BINARY_SIZE or digest != EXPECTED_BINARY_SHA256:
            raise ValueError("VECreator exact SHA256 mismatch; refusing QML interpretation")
        return bytes(output)


def _visible(data: bytes) -> str:
    decoded = data.decode("utf-8", errors="replace")
    return "".join(ch if ch.isprintable() else " " for ch in decoded).strip()


def evidence(data: bytes) -> dict:
    """Limited windows and counts; no proprietary DLL or full QML redistribution."""
    result = {
        "original_binary_verified": True,
        "original_binary_sha256": EXPECTED_BINARY_SHA256,
        "original_binary_size": len(data),
        "binary_patched": False,
        "native_mp4_tested": False,
        "qml_patch_installed": False,
        "anchors": {},
        "home_component": {},
        "export_call_candidates": [],
    }
    for anchor in ANCHORS:
        pos = data.find(anchor)
        result["anchors"][anchor.decode("ascii")] = pos
    start = result["anchors"][ANCHORS[0].decode("ascii")]
    if start < 0:
        result["status"] = "HOME_MODEL_ANCHOR_MISSING"
        return result
    # The original home card QML is close to anchor but could be concatenated
    # with other resources. Take bounded context, not entire resources.
    lo = max(0, start - 10000)
    hi = min(len(data), start + 45000)
    window = data[lo:hi]
    names = Counter()
    seen = set()
    for match in INTERESTING.finditer(window):
        key = match.group().decode("ascii", errors="replace").lower()
        names[key] += 1
        context = window[max(0, match.start()-125): match.end()+155]
        # Remove binary and long C++ symbol noise from candidate output.
        compact = _visible(context)
        if len(result["export_call_candidates"]) < 90 and (key in (
            "onclicked", "ontriggered", "connections", "export", "background",
            "rootviewmodel", "baseviewmodel", "invokeMethod"
        )):
            fingerprint = hashlib.sha256(compact.encode()).hexdigest()[:12]
            if fingerprint not in seen:
                result["export_call_candidates"].append({
                    "offset": lo + match.start(),
                    "term": key,
                    "context": compact[:310],
                })
                seen.add(fingerprint)
    result["home_component"] = {"window_start": lo, "window_end": hi,
                                "matched_terms": dict(names)}
    result["status"] = "SOURCE_ROUTE_EVIDENCE_ONLY"
    result["next_step"] = (
        "Identify actual Home QML model handler and verified Qt methods before "
        "creating a native adapter. Source excerpts alone do not prove a safe ABI."
    )
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--part5", type=Path, required=True)
    parser.add_argument("--part6", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = original_vecreator_bytes(args.part5, args.part6)
    info = evidence(data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("SOURCE_ROUTE_STATUS=" + info["status"])
    print("CAPCUT_DLL_VERIFIED=" + str(info["original_binary_verified"]).lower())
    print("HOME_MODEL_OFFSET=" + str(info["anchors"][ANCHORS[0].decode("ascii")]))
    print("INTERESTING_CONTEXTS=" + str(len(info["export_call_candidates"])))
    # Emit concise summaries only; complete bounded contexts go in JSON artifact.
    for item in info["export_call_candidates"]:
        if item["term"] in ("onclicked","ontriggered","connections","background"):
            print("CANDIDATE=" + str(item["offset"]) + ":" + item["context"][:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
