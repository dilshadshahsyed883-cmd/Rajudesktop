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
    rb"\b(rootViewModel|baseViewModel|viewModel)\.([a-zA-Z_][a-zA-Z_0-9]*)\s*\("
)
OBJECT_PROPERTY = re.compile(
    rb"\b(rootViewModel|baseViewModel|viewModel)\.([a-zA-Z_][a-zA-Z_0-9]*)\b"
)
CONNECTIONS = re.compile(rb"\bConnections\s*\{")
SIGNAL = re.compile(rb"\bon([A-Z][a-zA-Z0-9_]*)\s*:")
EXPORT_TERMS = re.compile(rb"(?i)\b(backgroundexport|clickbackgroundexport|clickdraftfromhomeview|exportdraft|startexport|onexport\w*)\b")
MAX_PER_CATEGORY = 70

# Target the *observed* onClicked handlers, not another global symbol scan.
CALL_EXPR = re.compile(rb"\b([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*){0,4})\s*\(")
SIGNAL_DECL = re.compile(rb"\bsignal\s+([A-Za-z_][A-Za-z_0-9]*)\s*\(")
LOCAL_ID = re.compile(rb"\bid\s*:\s*([A-Za-z_][A-Za-z_0-9]*)")
HANDLER_LIMIT = 24
BODY_LIMIT = 2400
SOURCE_EXCERPT_LIMIT = 420


def _qml_handler_expression(data, colon_end):
    """Bound one QML handler body without assuming a particular Qt ViewModel."""
    cursor = colon_end
    while cursor < len(data) and data[cursor] in b" \t\r\n":
        cursor += 1
    if cursor >= len(data):
        return b"", True

    if data[cursor] != ord("{"):
        end = cursor
        while end < len(data) and end - cursor < BODY_LIMIT and data[end] not in b"\r\n;":
            end += 1
        return bytes(data[cursor:end]), end - cursor >= BODY_LIMIT

    start = cursor
    depth = 0
    quote = None
    in_line_comment = False
    in_block_comment = False
    while cursor < len(data) and cursor - start < BODY_LIMIT:
        ch = data[cursor]
        nxt = data[cursor + 1] if cursor + 1 < len(data) else -1
        if in_line_comment:
            if ch == 10:
                in_line_comment = False
        elif in_block_comment:
            if ch == 42 and nxt == 47:
                in_block_comment = False
                cursor += 1
        elif quote is not None:
            if ch == 92:
                cursor += 1
            elif ch == quote:
                quote = None
        elif ch in (34, 39, 96):
            quote = ch
        elif ch == 47 and nxt == 47:
            in_line_comment = True
            cursor += 1
        elif ch == 47 and nxt == 42:
            in_block_comment = True
            cursor += 1
        elif ch == 123:
            depth += 1
        elif ch == 125:
            depth -= 1
            if depth == 0:
                cursor += 1
                return bytes(data[start:cursor]), False
        cursor += 1
    return bytes(data[start:cursor]), True


def _excerpt(expression):
    # Short local QML excerpt, never a source dump or entire proprietary component.
    text = expression[:SOURCE_EXCERPT_LIMIT].decode("utf-8", errors="replace")
    return "".join(c if c.isprintable() else " " for c in text).strip()


def _clicked_handler_details(data, origin, limit=HANDLER_LIMIT):
    details = []
    for m in HANDLER.finditer(data):
        if len(details) >= limit:
            break
        expression, truncated = _qml_handler_expression(data, m.end())
        calls = []
        for candidate in CALL_EXPR.finditer(expression):
            name = candidate.group(1).decode("ascii", errors="replace")
            if name not in calls:
                calls.append(name)
        prelude = data[max(0, m.start() - 450):m.start()]
        ids = list(LOCAL_ID.finditer(prelude))
        # The original owner's 9.7 report shows these are unrelated UI
        # handlers, not the native background-export entry point.
        if "viewModel.openRecycleBinWindow" in calls:
            kind = "RECYCLE_BIN_NOT_EXPORT"
        elif "viewModel.openAutoUploadWindow" in calls:
            kind = "AUTO_UPLOAD_WINDOW_NOT_EXPORT"
        else:
            kind = "UNRESOLVED_NO_NATIVE_PROOF"
        details.append({
            "classification": kind,
            "native_export_verified": False,
            "handler": m.group(1).decode("ascii"),
            "file_offset": origin + m.start(),
            "nearest_id": ids[-1].group(1).decode("ascii") if ids else None,
            "candidate_calls": calls[:24],
            "body_excerpt": _excerpt(expression),
            "body_truncated": truncated,
            "conclusion": "STATIC_QML_ONLY_NOT_VERIFIED_NATIVE_EXPORT",
        })
    return details


def _signal_declarations(data, origin):
    records = []
    for m in SIGNAL_DECL.finditer(data):
        if len(records) >= 32:
            break
        records.append({
            "signal": m.group(1).decode("ascii"),
            "file_offset": origin + m.start()
        })
    return records


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
        "click_handler_actions": _clicked_handler_details(data, origin),
        "local_signal_declarations": _signal_declarations(data, origin),
        "candidate_export_entrypoint_verified": False,
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
