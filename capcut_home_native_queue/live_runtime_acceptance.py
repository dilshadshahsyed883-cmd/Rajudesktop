"""Classify read-only live CapCut process reports without overstating capability.

A local TCP listener, Qt DLL, or debugging argument cannot prove that the
original CapCut process exposes a callable Qt QObject/exporter. This module
never connects to CapCut and always rejects claims of completed automation.
"""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA = "capcut-9.7-live-qt-bridge-feasibility-v1"
VERSION = "9.7.0.4153"


class LiveRuntimeEvidenceError(ValueError):
    """Report is incomplete or contradicts the read-only contract."""


@dataclass(frozen=True)
class FeasibilityResult:
    status: str
    running_capcut_processes: int
    qt_runtime_observed: bool
    debugger_argument_observed: bool
    loopback_candidate_ports: int
    native_bridge_verified: bool = False
    batch_export_verified: bool = False


def classify(report: dict) -> FeasibilityResult:
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise LiveRuntimeEvidenceError("Unknown live-process evidence schema")
    if report.get("target_version") != VERSION:
        raise LiveRuntimeEvidenceError("Unrecognized original CapCut version")
    must_be_false = (
        "original_capcut_files_modified", "drafts_read_or_modified",
        "process_injection_or_attachment_attempted",
        "debugger_port_connection_attempted", "external_network_calls",
        "live_qobject_verified", "native_export_scheduler_abi_verified",
        "unattended_capcut_mp4_export_verified",
    )
    if any(report.get(field) is not False for field in must_be_false):
        raise LiveRuntimeEvidenceError("Unsafe or unsupported report claim")

    processes = report.get("processes")
    count = report.get("running_target_process_count")
    if not isinstance(processes, list) or type(count) is not int or len(processes) != count:
        raise LiveRuntimeEvidenceError("Process count does not match observations")

    debug_count = 0
    qt = False
    matching_port_count = 0
    for process in processes:
        if not isinstance(process, dict):
            raise LiveRuntimeEvidenceError("Process entry is invalid")
        if process.get("exact_version_exe_path_matched") is not True:
            raise LiveRuntimeEvidenceError("Wrong CapCut process version")
        if process.get("qml_debugger_argument_present") not in (True, False):
            raise LiveRuntimeEvidenceError("Missing debugger argument observation")
        debug_count += int(process["qml_debugger_argument_present"])
        modules = process.get("qt_runtime_module_names")
        ports = process.get("loopback_listening_ports")
        if not isinstance(modules, list) or not isinstance(ports, list):
            raise LiveRuntimeEvidenceError("Missing module or port inventory")
        if any(not isinstance(name, str) for name in modules):
            raise LiveRuntimeEvidenceError("Invalid module entry")
        if any(type(port) is not int or not 1 <= port <= 65535 for port in ports):
            raise LiveRuntimeEvidenceError("Invalid local port entry")
        qt |= any(module.lower() == "qt6qml.dll" for module in modules)
        claimed = process.get("debugger_requested_port")
        if claimed is not None:
            if type(claimed) is not int or claimed not in range(1, 65536):
                raise LiveRuntimeEvidenceError("Invalid requested debugger port")
            if claimed in ports and process["qml_debugger_argument_present"]:
                matching_port_count += 1

    if type(report.get("observed_loopback_debug_port_candidates")) is not int:
        raise LiveRuntimeEvidenceError("Missing candidate count")
    if matching_port_count != report["observed_loopback_debug_port_candidates"]:
        raise LiveRuntimeEvidenceError("Candidate evidence mismatched")
    if count == 0:
        expected = "ORIGINAL_CAPCUT_NOT_RUNNING"
    elif matching_port_count:
        expected = "LOCAL_DEBUG_PORT_CANDIDATE_PROTOCOL_UNVERIFIED"
    elif debug_count:
        expected = "DEBUG_ARGUMENT_PRESENT_NO_MATCHING_LOOPBACK_PORT"
    else:
        expected = "NO_LIVE_QML_DEBUG_ENTRYPOINT_OBSERVED"
    if report.get("status") != expected:
        raise LiveRuntimeEvidenceError("Report status inconsistent with observations")
    return FeasibilityResult(
        status=expected, running_capcut_processes=count,
        qt_runtime_observed=qt, debugger_argument_observed=debug_count > 0,
        loopback_candidate_ports=matching_port_count,
    )
