"""Bounded, read-only analysis of CapCut 9.7 Home QML call sites.

The previous scan proved that BackEndExportImpl methods are private PE symbols.
This module looks for callable *QML expressions* near the genuine Home draft
card component, rather than repeating static DLL symbol discovery.

Neither importing nor scanning this module starts CapCut, loads its DLL,
modifies a draft, or invokes private C++ functions.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import mmap
from pathlib import Path
import re

VE_SHA256 = "967fd06e60a1c68c055278cf6bb1ecd1bb078277d58167fcf6b4cfa2a1a27cf9"
ANCHOR = b"property HomePageLocalDraftViewModel rootViewModel: null"
WINDOW_BACK = 12000
WINDOW_FORWARD = 100000

# Only names and offsets, not the vendor's QML implementation/body text.
HANDLER = re.compile(rb"\b(onClicked|onPressed|onTriggered|onDoubleClicked|onAccepted)\s*:")
METHOD = re.compile(
    rb"\b(rootViewModel|baseViewModel)\.([a-zA-Z_][a-zA-Z_0-9]*)\s*\("
)
OBJECT_PROPERTY = re.compile(
    rb"\b(rootViewModel|baseViewModel)\.([a-zA-Z_][a-zA-Z_0-9]*)\b"
)
CONNECTIONS = re.compile(rb"\bConnections\s*\{")
SIGNAL = re.compile(rb"\bon([A-Z][a-zA-Z0-9_]*)\s*:")
EXPORT_TERMS = re.compile(rb"(?i)\b(backgroundexport|clickbackgroundexport|clickdraftfromhomeview|exportdraft|startexport|onexport\w*)\b")
MAX_PER_CATEGORY = 70


def _records(pattern, data, origin, limit=MAX_PER_CATEGORY):
    counts = Counter()
    found = []
    for m in pattern.finditer(data):
        label = ".".join(g.decode("ascii") for g in m.groups() if g)
        if not label:
            label = m.group(0).decode("ascii", errors="replace")
        counts[label] += 1
        if len(found) < limit:
            found.append({"name": label, "file_offset": origin + m.start()})
    return found, dict(counts)


def analyze_home_slice(data, origin=0):
    """Extract QML names, not vendor source; safe for synthetic fixtures."""
    handlers, handler_counts = _records(HANDLER, data, origin)
    methods, method_counts = _records(METHOD, data, origin)
    properties, property_counts = _records(OBJECT_PROPERTY, data, origin)
    signals, signal_counts = _records(SIGNAL, data, origin)
    export_terms, export_counts = _records(EXPORT_TERMS, data, origin)
    connections, _ = _records(CONNECTIONS, data, origin)
    return {
        "window_start": origin,
        "window_bytes": len(data),
        "qml_handlers": handlers,
        "qml_handlers_counts": handler_counts,
        "viewmodel_calls": methods,
        "viewmodel_call_counts": method_counts,
        "viewmodel_properties": properties,
        "viewmodel_property_counts": property_counts,
        "qml_signals": signals,
        "qml_signal_counts": signal_counts,
        "explicit_export_tokens": export_terms,
        "explicit_export_token_counts": export_counts,
        "connection_count_in_window": len(connections),
    }


def scan_original(path, expected_sha=VE_SHA256):
    """Require an exact known binary before attributing names to CapCut 9.7."""
    path = Path(path)
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != expected_sha:
            return {
                "status": "BLOCKED_UNVERIFIED_VECREATOR_DLL",
                "expected_sha256": expected_sha, "sha256": digest,
                "capcut_modified": False, "native_render_verified": False,
            }
        handle.seek(0)
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as buf:
            pos = buf.find(ANCHOR)
            if pos < 0:
                return {
                    "status": "HOME_DRAFT_QML_NOT_FOUND",
                    "original_binary_verified": True,
                    "capcut_modified": False, "native_render_verified": False,
                }
            start = max(0, pos - WINDOW_BACK)
            end = min(len(buf), pos + WINDOW_FORWARD)
            segment = bytes(buf[start:end])
            report = analyze_home_slice(segment, start)
            report.update({
                "status": "HOME_QML_METHOD_CANDIDATES",
                "original_binary_verified": True,
                "anchor_offset": pos,
                "sha256": digest,
                "capcut_modified": False,
                "native_render_verified": False,
                "direct_qt_bridge_verified": False,
                "interpretation": (
                    "This identifies QML method names, NOT an invokable "
                    "BackEndExportImpl method. Further isolated Windows "
                    "runtime confirmation is necessary."
                ),
            })
            return report
