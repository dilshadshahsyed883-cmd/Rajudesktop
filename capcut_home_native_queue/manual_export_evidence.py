"""Classify a user's original CapCut GUI export report without claiming native automation.

The JSON report is *self-reported evidence*, not a cryptographic proof that the
CapCut engine emitted the MP4 or that a private Qt ABI can be invoked. This
parser neither launches CapCut nor opens the user's reported MP4.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import PureWindowsPath
import re

EXPECTED_VERSION = "9.7.0.4153"
EXPECTED_KIND = "CAPCUT_ORIGINAL_GUI_MANUAL_ONE_EXPORT"
_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")


class EvidenceRejected(ValueError):
    """Report fails manual-export acceptance criteria."""


@dataclass(frozen=True)
class ManualExportAcceptance:
    status: str
    version: str
    mp4_size_bytes: int
    duration_seconds: float
    width: int
    height: int
    sha256: str
    native_qt_bridge_verified: bool = False
    automatic_batch_export_verified: bool = False


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvidenceRejected("Missing UTC timestamp")
    try:
        timestamp = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise EvidenceRejected("Invalid UTC timestamp") from error
    return timestamp.astimezone(timezone.utc)


def classify_manual_export(report: dict) -> ManualExportAcceptance:
    """Accept one *manual GUI* MP4 validation; never turn it into bridge proof."""
    if not isinstance(report, dict):
        raise EvidenceRejected("Evidence must be a JSON object")
    if report.get("evidence_type") != EXPECTED_KIND:
        raise EvidenceRejected("Unknown or non-manual evidence type")
    if report.get("result") != "MP4_FILE_VALIDATED":
        raise EvidenceRejected("MP4 was not reported validated")
    if report.get("capcut_version_requested") != EXPECTED_VERSION:
        raise EvidenceRejected("CapCut version does not match")
    if report.get("native_qt_bridge_verified") is not False:
        raise EvidenceRejected("Manual GUI evidence cannot attest a native bridge")
    if report.get("original_capcut_files_modified_by_test_script") is not False:
        raise EvidenceRejected("Original executable mutation not excluded")
    if report.get("external_uploads") is not False:
        raise EvidenceRejected("Evidence script reported external uploads")
    provenance = report.get("original_engine_provenance")
    if not isinstance(provenance, str) or not provenance.startswith(
            "Human-initiated GUI export;"):
        raise EvidenceRejected("Report is not human-initiated original GUI export")

    started, ended = _parse_time(report.get("started_utc")), _parse_time(
        report.get("ended_utc"))
    if not started < ended:
        raise EvidenceRejected("Export observation window invalid")

    for stage in ("capcut_processes_before", "capcut_processes_after"):
        processes = report.get(stage)
        if not isinstance(processes, list) or not processes:
            raise EvidenceRejected("Original CapCut process evidence absent")
        for process in processes:
            if not isinstance(process, dict):
                raise EvidenceRejected("Invalid process observation")
            executable = process.get("executable")
            if not isinstance(executable, str):
                raise EvidenceRejected("Missing process executable")
            path = PureWindowsPath(executable)
            if (path.name.lower() != "capcut.exe" or
                    path.parent.name != EXPECTED_VERSION):
                raise EvidenceRejected("CapCut process is not exact version")

    mp4 = report.get("mp4")
    if not isinstance(mp4, dict):
        raise EvidenceRejected("MP4 details missing")
    path_value = mp4.get("path")
    directory = report.get("output_directory")
    if not isinstance(path_value, str) or not isinstance(directory, str):
        raise EvidenceRejected("Output path evidence missing")
    file_path, output_folder = PureWindowsPath(path_value), PureWindowsPath(directory)
    if (not file_path.is_absolute() or not output_folder.is_absolute() or
            file_path.suffix.lower() != ".mp4" or file_path.parent != output_folder):
        raise EvidenceRejected("Output MP4 not bound to reported test folder")

    created = _parse_time(mp4.get("created_utc"))
    if not started <= created <= ended:
        raise EvidenceRejected("Output timestamp outside observation interval")
    if mp4.get("atoms_ftyp_moov_mdat") is not True:
        raise EvidenceRejected("MP4 atoms not validated")
    ffprobe = mp4.get("ffprobe")
    if not isinstance(ffprobe, dict) or (ffprobe.get("available") is not True or
                                         ffprobe.get("passed") is not True):
        raise EvidenceRejected("Read-only ffprobe validation missing")
    try:
        size = mp4["size_bytes"]
        seconds = ffprobe["duration_seconds"]
        width, height = ffprobe["width"], ffprobe["height"]
        if (type(size) is not int or size < 1024 or
                type(seconds) not in (int, float) or not 0 < seconds < float("inf") or
                type(width) is not int or width < 1 or
                type(height) is not int or height < 1):
            raise EvidenceRejected("MP4 measurements invalid")
    except (KeyError, TypeError) as error:
        raise EvidenceRejected("MP4 measurements absent") from error
    digest = mp4.get("sha256")
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise EvidenceRejected("SHA-256 evidence missing")

    # These false values are a deliberate contract, regardless of report text.
    return ManualExportAcceptance(
        status="MANUAL_GUI_MP4_EVIDENCE_ACCEPTED", version=EXPECTED_VERSION,
        mp4_size_bytes=size, duration_seconds=float(seconds),
        width=width, height=height, sha256=digest.lower())


def classify_json(content: str) -> ManualExportAcceptance:
    try:
        document = json.loads(content)
    except (TypeError, json.JSONDecodeError) as error:
        raise EvidenceRejected("Malformed JSON") from error
    return classify_manual_export(document)
