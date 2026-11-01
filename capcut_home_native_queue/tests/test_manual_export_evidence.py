"""Contract tests for a manual GUI export report; no genuine render launched."""
from copy import deepcopy
import json
import unittest

from capcut_home_native_queue.manual_export_evidence import (
    classify_json, classify_manual_export, EvidenceRejected,
)


def valid_report():
    # Synthetic fixture mirrors the owner's report schema, without personal
    # Windows username, real output filename, or personally unique MP4 digest.
    process = {"pid": 101, "executable": (
        r"C:\Users\TestUser\AppData\Local\CapCut\Apps\9.7.0.4153\CapCut.exe"),
        "command_line_redacted": True}
    return {
        "evidence_type": "CAPCUT_ORIGINAL_GUI_MANUAL_ONE_EXPORT",
        "result": "MP4_FILE_VALIDATED",
        "capcut_version_requested": "9.7.0.4153",
        "started_utc": "2026-11-01T13:49:49.7773234Z",
        "ended_utc": "2026-11-01T13:50:58.3993961Z",
        "capcut_processes_before": [process],
        "capcut_processes_after": [process],
        "output_directory": r"C:\Users\TestUser\Documents\CapCutNativeExportTest\Output",
        "mp4": {
            "path": r"C:\Users\TestUser\Documents\CapCutNativeExportTest\Output\test.mp4",
            "size_bytes": 27671982,
            "created_utc": "2026-11-01T13:50:30.8705849Z",
            "sha256": "a" * 64,
            "atoms_ftyp_moov_mdat": True,
            "ffprobe": {"available": True, "passed": True,
                        "duration_seconds": 15, "width": 1530, "height": 1080},
        },
        "native_qt_bridge_verified": False,
        "original_engine_provenance": (
            "Human-initiated GUI export; private BackEndExportImpl ABI not verified"),
        "original_capcut_files_modified_by_test_script": False,
        "external_uploads": False,
    }


class ManualEvidenceTests(unittest.TestCase):
    def test_accept_original_gui_mp4_without_enabling_bridge(self):
        evidence = classify_manual_export(valid_report())
        self.assertEqual(evidence.status, "MANUAL_GUI_MP4_EVIDENCE_ACCEPTED")
        self.assertEqual(evidence.duration_seconds, 15)
        self.assertEqual(evidence.mp4_size_bytes, 27671982)
        self.assertEqual((evidence.width, evidence.height), (1530, 1080))
        self.assertFalse(evidence.native_qt_bridge_verified)
        self.assertFalse(evidence.automatic_batch_export_verified)

    def test_json_parse(self):
        evidence = classify_json(json.dumps(valid_report()))
        self.assertEqual(evidence.version, "9.7.0.4153")

    def test_manual_report_cannot_claim_native_bridge(self):
        bad = valid_report()
        bad["native_qt_bridge_verified"] = True
        with self.assertRaisesRegex(EvidenceRejected, "native bridge"):
            classify_manual_export(bad)

    def test_unvalidated_and_wrong_version_rejected(self):
        for key, value in [("result", "MP4_NOT_FOUND"),
                           ("capcut_version_requested", "9.6.0.4097")]:
            with self.subTest(key=key):
                bad = valid_report()
                bad[key] = value
                with self.assertRaises(EvidenceRejected):
                    classify_manual_export(bad)

    def test_process_version_and_original_mutation_rejected(self):
        bad = deepcopy(valid_report())
        bad["capcut_processes_before"][0]["executable"] = (
            r"C:\Other\CapCut\Apps\9.6.0.4097\CapCut.exe")
        with self.assertRaises(EvidenceRejected):
            classify_manual_export(bad)
        bad = valid_report()
        bad["original_capcut_files_modified_by_test_script"] = True
        with self.assertRaises(EvidenceRejected):
            classify_manual_export(bad)

    def test_output_directory_or_timestamp_mismatch_rejected(self):
        bad = valid_report()
        bad["mp4"]["path"] = r"C:\OtherFolder\foreign.mp4"
        with self.assertRaises(EvidenceRejected):
            classify_manual_export(bad)
        bad = valid_report()
        bad["mp4"]["created_utc"] = "2026-11-01T17:00:00Z"
        with self.assertRaises(EvidenceRejected):
            classify_manual_export(bad)

    def test_missing_video_stream_validation_rejected(self):
        bad = valid_report()
        bad["mp4"]["ffprobe"]["passed"] = False
        with self.assertRaises(EvidenceRejected):
            classify_manual_export(bad)

    def test_bad_sha256_rejected(self):
        bad = valid_report()
        bad["mp4"]["sha256"] = "not-a-sha"
        with self.assertRaises(EvidenceRejected):
            classify_manual_export(bad)

    def test_uploaded_report_remains_untrusted_self_report(self):
        evidence = classify_manual_export(valid_report())
        self.assertNotIn("NATIVE", evidence.status)
        self.assertFalse(evidence.native_qt_bridge_verified)
        self.assertFalse(evidence.automatic_batch_export_verified)


if __name__ == "__main__":
    unittest.main()
