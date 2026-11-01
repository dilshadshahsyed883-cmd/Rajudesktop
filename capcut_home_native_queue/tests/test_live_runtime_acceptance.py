"""No private owner report stored: synthetic fixtures exercise live check."""
import unittest
from copy import deepcopy

from capcut_home_native_queue.live_runtime_acceptance import (
    classify, LiveRuntimeEvidenceError,
)


def report():
    return {
        "schema": "capcut-9.7-live-qt-bridge-feasibility-v1",
        "target_version": "9.7.0.4153",
        "status": "NO_LIVE_QML_DEBUG_ENTRYPOINT_OBSERVED",
        "running_target_process_count": 2,
        "processes": [
            {
                "process_id": 101, "exact_version_exe_path_matched": True,
                "qml_debugger_argument_present": False,
                "debugger_requested_port": None,
                "qt_runtime_module_names": ["Qt6Core.dll", "Qt6Qml.dll"],
                "loopback_listening_ports": [7263],
            },
            {
                "process_id": 102, "exact_version_exe_path_matched": True,
                "qml_debugger_argument_present": False,
                "debugger_requested_port": None,
                "qt_runtime_module_names": ["Qt6Qml.dll"],
                "loopback_listening_ports": [],
            },
        ],
        "observed_loopback_debug_port_candidates": 0,
        "original_capcut_files_modified": False,
        "drafts_read_or_modified": False,
        "process_injection_or_attachment_attempted": False,
        "debugger_port_connection_attempted": False,
        "external_network_calls": False,
        "live_qobject_verified": False,
        "native_export_scheduler_abi_verified": False,
        "unattended_capcut_mp4_export_verified": False,
    }


class LiveBridgeAcceptanceTests(unittest.TestCase):
    def test_local_listener_7263_is_not_export_abi(self):
        result = classify(report())
        self.assertTrue(result.qt_runtime_observed)
        self.assertEqual(result.running_capcut_processes, 2)
        self.assertFalse(result.debugger_argument_observed)
        self.assertEqual(result.loopback_candidate_ports, 0)
        self.assertFalse(result.native_bridge_verified)
        self.assertFalse(result.batch_export_verified)

    def test_matching_local_debug_argument_remains_unverified(self):
        r = report()
        r["processes"][0]["qml_debugger_argument_present"] = True
        r["processes"][0]["debugger_requested_port"] = 7263
        r["observed_loopback_debug_port_candidates"] = 1
        r["status"] = "LOCAL_DEBUG_PORT_CANDIDATE_PROTOCOL_UNVERIFIED"
        result = classify(r)
        self.assertTrue(result.debugger_argument_observed)
        self.assertEqual(result.loopback_candidate_ports, 1)
        self.assertFalse(result.native_bridge_verified)
        self.assertFalse(result.batch_export_verified)

    def test_debug_flag_without_matching_socket_unverified(self):
        r = report()
        r["processes"][0]["qml_debugger_argument_present"] = True
        r["processes"][0]["debugger_requested_port"] = 9999
        r["status"] = "DEBUG_ARGUMENT_PRESENT_NO_MATCHING_LOOPBACK_PORT"
        self.assertFalse(classify(r).native_bridge_verified)

    def test_untrusted_self_report_cannot_claim_completed_export(self):
        for claim in ("live_qobject_verified", "native_export_scheduler_abi_verified",
                      "unattended_capcut_mp4_export_verified"):
            r = report()
            r[claim] = True
            with self.subTest(claim=claim), self.assertRaises(LiveRuntimeEvidenceError):
                classify(r)

    def test_report_inconsistency_rejected(self):
        for field, value in (
            ("status", "LOCAL_DEBUG_PORT_CANDIDATE_PROTOCOL_UNVERIFIED"),
            ("running_target_process_count", 8),
            ("observed_loopback_debug_port_candidates", 1),
            ("target_version", "9.6.0.4097"),
        ):
            r = report()
            r[field] = value
            with self.subTest(field=field), self.assertRaises(LiveRuntimeEvidenceError):
                classify(r)

    def test_untrusted_process_version_rejected(self):
        r = report()
        r["processes"][1]["exact_version_exe_path_matched"] = False
        with self.assertRaises(LiveRuntimeEvidenceError):
            classify(r)


if __name__ == "__main__":
    unittest.main()
