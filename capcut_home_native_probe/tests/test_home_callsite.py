"""Synthetic Windows-independent QML callsite tests; never launch CapCut."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from capcut_home_native_probe import home_callsite


class HomeCallsiteTests(unittest.TestCase):
    def test_extract_only_names_and_offsets(self):
        sample = (b"Item { onClicked: rootViewModel.openDraft(draftId)\n"
                  b"Connections { onExportProgress: baseViewModel.refreshProgress() }\n"
                  b"onTriggered: rootViewModel.exportDraft(draftId) }")
        report = home_callsite.analyze_home_slice(sample, 200)
        self.assertIn("rootViewModel.openDraft", report["viewmodel_call_counts"])
        self.assertIn("rootViewModel.exportDraft", report["viewmodel_call_counts"])
        self.assertIn("baseViewModel.refreshProgress", report["viewmodel_call_counts"])
        self.assertEqual(report["qml_handlers_counts"]["onClicked"], 1)
        self.assertEqual(report["connection_count_in_window"], 1)
        self.assertFalse(any("context" in item for item in report["viewmodel_calls"]))

    def test_verify_sha_before_interpreting_vendor_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "VECreator.dll"
            data = b"garbage" + home_callsite.ANCHOR
            p.write_bytes(data)
            report = home_callsite.scan_original(p)
            self.assertEqual(report["status"], "BLOCKED_UNVERIFIED_VECREATOR_DLL")
            self.assertFalse(report["capcut_modified"])
            self.assertFalse(report["native_render_verified"])
            verified = home_callsite.scan_original(
                p, expected_sha=hashlib.sha256(data).hexdigest())
            self.assertEqual(verified["status"], "HOME_QML_METHOD_CANDIDATES")
            self.assertEqual(verified["anchor_offset"], 7)
            self.assertFalse(verified["native_render_verified"])

    def test_missing_original_qml_anchor_does_not_claim_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "VECreator.dll"
            data = b"Original synthetic fixture only"
            p.write_bytes(data)
            report = home_callsite.scan_original(
                p, expected_sha=hashlib.sha256(data).hexdigest())
            self.assertEqual(report["status"], "HOME_DRAFT_QML_NOT_FOUND")
            self.assertFalse(report["native_render_verified"])

    def test_file_is_unchanged_after_original_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "VECreator.dll"
            data = b"A" * 500 + home_callsite.ANCHOR + b"\n" + (
                b"onClicked: rootViewModel.clickDraftFromHomeView(draftId)\n")
            p.write_bytes(data)
            before = (p.read_bytes(), p.stat().st_mtime_ns)
            report = home_callsite.scan_original(
                p, expected_sha=hashlib.sha256(data).hexdigest())
            self.assertIn("rootViewModel.clickDraftFromHomeView",
                          report["viewmodel_call_counts"])
            self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns), before)


if __name__ == "__main__":
    unittest.main()
