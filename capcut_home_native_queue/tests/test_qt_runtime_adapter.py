"""Actual Qt6 QObject/slot invocation tests with synthetic in-process model.

These use a FAKE Qt model in GitHub Windows CI, not the running proprietary
CapCut process. They test the real adapter implementation, never real export.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QObject, Slot, Signal

from capcut_home_native_queue.native_output_validation import VerifiedOutput, NativeOutputError
from capcut_home_native_queue.qt_runtime_adapter import (
    CurrentDraft, QtRuntimeAdapter, is_expected_original_qobject,
    same_windows_path,
)


class ExportCompileBottomViewModel(QObject):
    invoked = Signal()

    def __init__(self):
        super().__init__()
        self.calls = 0

    @Slot()
    def clickBackgroudExport(self):
        self.calls += 1
        self.invoked.emit()


class WrongExportModel(QObject):
    @Slot()
    def clickBackgroudExport(self):
        return None


class MissingMethod(QObject):
    pass


class QtRuntimeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = str(Path(self.temp.name) / "draft-project")
        Path(self.source).mkdir()
        self.output = str(Path(self.temp.name) / "output.mp4")
        self.model = ExportCompileBottomViewModel()
        self.draft = CurrentDraft("draft-A", self.source, self.model)
        self.key = "draft-A::" + self.source
        self.verified_receipts = []
        self.verification_allowed = True
        self.adapter = QtRuntimeAdapter(
            self.model,
            read_current_draft=lambda: self.draft,
            resolve_output=lambda draft_id, project: self.output,
            verify_native_runtime=lambda model: self.verification_allowed,
            receipt_verifier=self.fake_receipt,
        )
        self.admitted = []
        self.verified = []
        self.failed = []
        self.adapter.exportAdmitted.connect(lambda key, task: self.admitted.append((key, task)))
        self.adapter.exportVerified.connect(lambda key, path, sha: self.verified.append((key, path, sha)))
        self.adapter.exportFailed.connect(lambda key, reason: self.failed.append((key, reason)))

    def fake_receipt(self, ticket, path):
        # Synthetic stub on purpose; default adapter verifier uses real ffprobe
        # and SHA-256, but Windows CI cannot claim a CapCut-produced MP4.
        self.verified_receipts.append(ticket)
        if path != self.output:
            raise NativeOutputError("Foreign output rejected")
        # Production verify_completed returns the resolved ticket path,
        # which can differ from Windows 8.3 short-name temporary paths.
        return VerifiedOutput(ticket.key, str(ticket.output_path), "a" * 64,
                              32000, 15.0, 1530, 1080)

    def activate(self):
        self.assertTrue(self.adapter.verifyRuntime())
        self.assertTrue(self.adapter.nativeBridgeVerified)

    def test_real_qt_metaobject_lookup_and_original_void_slot_invocation(self):
        self.assertTrue(is_expected_original_qobject(self.model))
        self.activate()
        self.assertTrue(self.adapter.verifyCurrentDraftBinding("draft-A", self.source, self.key))
        self.assertTrue(self.adapter.requestExport("draft-A", self.source, self.key))
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(self.admitted, [], "Void method is not native task admission")
        self.assertEqual(self.verified, [])
        self.assertFalse(self.adapter.requestExport("draft-A", self.source, self.key),
                         "No double-dispatch for pending request")

    def test_no_runtime_attestation_never_invokes_export(self):
        self.assertFalse(self.adapter.nativeBridgeVerified)
        self.assertFalse(self.adapter.requestExport("draft-A", self.source, self.key))
        self.assertEqual(self.model.calls, 0)
        self.verification_allowed = False
        self.assertFalse(self.adapter.verifyRuntime())
        self.assertFalse(self.adapter.nativeBridgeVerified)

    def test_wrong_qobject_type_or_method_rejected(self):
        self.assertFalse(is_expected_original_qobject(WrongExportModel()))
        self.assertFalse(is_expected_original_qobject(MissingMethod()))

    def test_draft_mismatch_or_other_model_never_clicks(self):
        self.activate()
        self.draft = CurrentDraft("different-draft", self.source, self.model)
        self.assertFalse(self.adapter.requestExport("draft-A", self.source, self.key))
        self.draft = CurrentDraft("draft-A", self.source, ExportCompileBottomViewModel())
        self.assertFalse(self.adapter.verifyCurrentDraftBinding("draft-A", self.source, self.key))
        self.assertEqual(self.model.calls, 0)

    def test_reject_foreign_path_and_key(self):
        self.activate()
        wrong_path = str(Path(self.temp.name) / "other-draft")
        self.assertFalse(self.adapter.requestExport("draft-A", wrong_path, "draft-A::" + wrong_path))
        self.assertFalse(self.adapter.requestExport("draft-A", self.source, "mismatched-key"))
        self.assertEqual(self.model.calls, 0)

    def test_current_draft_path_comparison_is_windows_canonical(self):
        self.assertTrue(same_windows_path(r"C:\Projects\A\..\B",
                                          r"c:\projects\b"))
        self.assertFalse(same_windows_path(r"C:\Projects\A",
                                           r"C:\Projects\B"))
        self.assertFalse(same_windows_path("relative-folder", r"C:\Projects\B"))

    def test_native_scheduler_admission_is_separate_from_qt_void_dispatch(self):
        self.activate()
        self.assertTrue(self.adapter.requestExport("draft-A", self.source, self.key))
        self.assertFalse(self.adapter.nativeTaskAdmitted("foreign", "task-1", "draft-A", self.source))
        self.assertFalse(self.adapter.nativeTaskAdmitted(self.key, "", "draft-A", self.source))
        self.assertFalse(self.adapter.nativeTaskAdmitted(self.key, "task-1", "draft-B", self.source))
        self.assertEqual(self.admitted, [])
        self.assertTrue(self.adapter.nativeTaskAdmitted(self.key, "task-1", "draft-A", self.source))
        self.assertEqual(self.admitted, [(self.key, "task-1")])
        self.assertFalse(self.adapter.nativeTaskAdmitted(self.key, "task-1", "draft-A", self.source))

    def test_completion_requires_exact_admitted_task_id_and_receipt(self):
        self.activate()
        self.assertTrue(self.adapter.requestExport("draft-A", self.source, self.key))
        self.assertFalse(self.adapter.nativeTaskCompleted(self.key, "task-1", self.output))
        self.assertTrue(self.adapter.nativeTaskAdmitted(self.key, "task-1", "draft-A", self.source))
        self.assertFalse(self.adapter.nativeTaskCompleted(self.key, "foreign-task", self.output))
        accepted = self.adapter.nativeTaskCompleted(self.key, "task-1", self.output)
        self.assertTrue(accepted, "Native completion rejection: " + repr(self.failed))
        self.assertEqual(self.verified, [(self.key, str(Path(self.output).resolve()),
                                         "a" * 64)])
        self.assertEqual(len(self.verified_receipts), 1)
        self.assertFalse(self.adapter.nativeTaskCompleted(self.key, "task-1", self.output))

    def test_invalid_output_receipt_emits_failure_without_verified(self):
        self.activate()
        self.assertTrue(self.adapter.requestExport("draft-A", self.source, self.key))
        self.assertTrue(self.adapter.nativeTaskAdmitted(self.key, "task-1", "draft-A", self.source))
        self.assertFalse(self.adapter.nativeTaskCompleted(
            self.key, "task-1", str(Path(self.temp.name) / "wrong.mp4")))
        self.assertEqual(self.verified, [])
        self.assertEqual(len(self.failed), 1)

    def test_progress_requires_admitted_matching_task(self):
        self.activate()
        self.adapter.requestExport("draft-A", self.source, self.key)
        self.assertFalse(self.adapter.nativeTaskProgress(self.key, "task-1", 40))
        self.adapter.nativeTaskAdmitted(self.key, "task-1", "draft-A", self.source)
        self.assertFalse(self.adapter.nativeTaskProgress(self.key, "wrong-task", 40))
        self.assertFalse(self.adapter.nativeTaskProgress(self.key, "task-1", 120))
        self.assertTrue(self.adapter.nativeTaskProgress(self.key, "task-1", 40))

    def test_no_unproven_timeout_replay(self):
        self.activate()
        self.adapter.requestExport("draft-A", self.source, self.key)
        self.assertFalse(self.adapter.cancelUnadmittedRequest(self.key))
        self.assertFalse(self.adapter.requestExport("draft-A", self.source, self.key))
        self.assertEqual(self.model.calls, 1)
        self.assertFalse(self.adapter.nativeTaskFailed("wrong", "", "error"))
        self.assertTrue(self.adapter.nativeTaskFailed(self.key, "", "Native failed"))
        self.assertEqual(len(self.failed), 1)


if __name__ == "__main__":
    unittest.main()
