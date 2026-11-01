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

    def test_traces_multiline_click_action_signal_and_nested_calls(self):
        sample = (b"Rectangle { id: card\n"
                  b"signal requestDraftExport(var draftId)\n"
                  b"MouseArea { id: openButton\n"
                  b"onClicked: {\n"
                  b"  if (ready) { root.requestDraftExport(draftId) }\n"
                  b"  // fake } comment\n"
                  b"  console.log('ok')\n"
                  b"}\n"
                  b"} }\n")
        result = home_callsite.analyze_home_slice(sample, 900)
        actions = result["click_handler_actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["nearest_id"], "openButton")
        self.assertIn("root.requestDraftExport", actions[0]["candidate_calls"])
        self.assertIn("console.log", actions[0]["candidate_calls"])
        self.assertFalse(actions[0]["body_truncated"])
        self.assertEqual(result["local_signal_declarations"][0]["signal"], "requestDraftExport")
        self.assertFalse(result["candidate_export_entrypoint_verified"])

    def test_trace_handler_expression_and_quoted_braces(self):
        sample = (b'Button { id: exportButton\n'
                  b'onClicked: root.submitDraft("literal } brace")\n'
                  b'onClicked: { console.log("}") ; root.exportItem(draftId) }\n}')
        result = home_callsite.analyze_home_slice(sample, 40)
        actions = result["click_handler_actions"]
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["candidate_calls"], ["root.submitDraft"])
        self.assertFalse(actions[0]["body_truncated"])
        self.assertIn("root.exportItem", actions[1]["candidate_calls"])
        self.assertFalse(actions[1]["body_truncated"])

    def test_unclosed_handler_reports_truncation_not_fake_native_binding(self):
        sample = b"Item { onClicked: { x.openDraft(1) "
        result = home_callsite.analyze_home_slice(sample)
        self.assertTrue(result["click_handler_actions"][0]["body_truncated"])
        self.assertFalse(result["candidate_export_entrypoint_verified"])

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
