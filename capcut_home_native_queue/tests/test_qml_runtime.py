"""Offscreen *real Qt 6 QML runtime* acceptance tests for the Home queue panel.

Runs with PySide6-Essentials on a Windows GitHub runner. It DOES NOT start CapCut.
The fake host proves selection/serialization/verification event handling only;
it does not stand in for a real CapCut native bridge.
"""
import os
import json
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl, Signal, Slot, Property
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine

QML = Path(__file__).resolve().parents[1] / "HomeDraftQueuePanel.qml"


class FakeNativeAdapter(QObject):
    exportAdmitted = Signal(str, str)
    exportVerified = Signal(str, str, str)
    exportFailed = Signal(str, str)
    exportProgress = Signal(str, float)

    def __init__(self, bridge_verified=True):
        super().__init__()
        self.calls = []
        self.accept = True
        self.auto_admit = True
        self._bridge_verified = bridge_verified
        self.bound = True
        self.binding_calls = []

    @Slot(str, str, str, result=bool)
    def verifyCurrentDraftBinding(self, draft_id, path, key):
        self.binding_calls.append((draft_id, path, key))
        return self.bound

    @Property(bool, constant=True)
    def nativeBridgeVerified(self):
        # Synthetic test-only attestation. It does NOT verify CapCut's ABI.
        return self._bridge_verified

    @Slot(str, str, str, result=bool)
    def requestExport(self, draft_id, path, key):
        self.calls.append((draft_id, path, key))
        if self.accept and self.auto_admit:
            # Synthetic host callback only, never native CapCut evidence.
            self.exportAdmitted.emit(key, "mock-task-" + draft_id)
        return self.accept


class NativeHomePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlEngine()
        self.component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(QML)))
        error = "\n".join(str(e) for e in self.component.errors())
        self.assertEqual(self.component.status(), QQmlComponent.Status.Ready, error)
        self.panel = self.component.create()
        self.assertIsNotNone(self.panel, "\n".join(str(e) for e in self.component.errors()))
        self.items = [
            {"draftId": "a", "strProjectPath": "D:/CapCut/A", "strTitle": "Draft A"},
            {"draftId": "b", "strProjectPath": "D:/CapCut/B", "strTitle": "Draft B"},
        ]
        self.panel.setProperty("drafts", self.items)
        self.app.processEvents()

    def tearDown(self):
        self.panel.deleteLater()
        self.engine.deleteLater()
        self.app.processEvents()

    def result_for(self, key):
        states = self.panel.property("results")
        if hasattr(states, "toVariant"):
            states = states.toVariant()
        return states[key]

    def test_no_native_adapter_means_no_dispatch(self):
        self.assertFalse(self.panel.property("adapterReady"))
        self.assertTrue(self.panel.setSelected(self.items[0], True))
        self.assertFalse(self.panel.startSelected())
        self.assertEqual(self.panel.property("activeKey"), "")
        self.assertIn("unavailable", self.panel.property("statusLine").lower())

    def test_callable_adapter_without_native_proof_remains_disabled(self):
        adapter = FakeNativeAdapter(bridge_verified=False)
        self.panel.setProperty("nativeAdapter", adapter)
        self.app.processEvents()
        self.assertFalse(self.panel.property("adapterReady"))
        self.assertTrue(self.panel.setSelected(self.items[0], True))
        self.assertFalse(self.panel.startSelected())
        self.assertEqual(adapter.calls, [])
        self.assertEqual(self.panel.property("activeKey"), "")
        self.assertIn("unavailable", self.panel.property("statusLine").lower())

    def test_serial_two_drafts_requires_verified_native_mp4_event(self):
        adapter = FakeNativeAdapter()
        self.panel.setProperty("nativeAdapter", adapter)
        self.app.processEvents()
        self.assertTrue(self.panel.property("adapterReady"))
        self.assertTrue(self.panel.setSelected(self.items[0], True))
        self.assertTrue(self.panel.setSelected(self.items[1], True))
        self.assertTrue(self.panel.startSelected())
        self.assertEqual(len(adapter.calls), 1, "Only first native job can start")
        first = adapter.calls[0][2]
        self.assertEqual(first, "a::D:/CapCut/A")
        self.assertFalse(self.panel.nativeVerified(first, "out.mp4", "not-a-sha256"))
        self.assertEqual(len(adapter.calls), 1, "Invalid verification halts queue")
        self.assertTrue(self.panel.property("pauseAfterCurrent"))

    def test_second_starts_only_after_real_completion_event(self):
        adapter = FakeNativeAdapter()
        self.panel.setProperty("nativeAdapter", adapter)
        self.assertTrue(self.panel.setSelected(self.items[0], True))
        self.assertTrue(self.panel.setSelected(self.items[1], True))
        self.assertTrue(self.panel.startSelected())
        self.assertEqual(len(adapter.calls), 1)
        first_key = adapter.calls[0][2]
        self.assertFalse(self.panel.nativeVerified("foreign", "bad.mp4", "a" * 64))
        self.assertEqual(len(adapter.calls), 1)
        adapter.exportVerified.emit(first_key, "D:/exports/a.mp4", "a" * 64)
        self.app.processEvents()
        self.assertEqual(len(adapter.calls), 2)
        self.assertEqual(adapter.calls[1][0], "b")
        self.assertEqual(self.panel.property("activeKey"), adapter.calls[1][2])

    def test_wrong_current_draft_binding_blocks_export(self):
        adapter = FakeNativeAdapter()
        adapter.bound = False
        self.panel.setProperty("nativeAdapter", adapter)
        self.panel.setSelected(self.items[0], True)
        self.panel.setSelected(self.items[1], True)
        self.assertTrue(self.panel.startSelected())
        self.assertEqual([call[0] for call in adapter.binding_calls], ["a"])
        self.assertEqual(adapter.calls, [], "Must not click Export for wrong draft")
        self.assertFalse(self.panel.property("running"))
        self.assertTrue(self.panel.property("pauseAfterCurrent"))
        self.assertIn("not bound", self.panel.property("statusLine"))

    def test_sequential_jobs_revalidate_draft_identity(self):
        adapter = FakeNativeAdapter()
        self.panel.setProperty("nativeAdapter", adapter)
        self.panel.setSelected(self.items[0], True)
        self.panel.setSelected(self.items[1], True)
        self.assertTrue(self.panel.startSelected())
        self.assertEqual(len(adapter.calls), 1)
        adapter.bound = False  # Host must rebind after first render finishes.
        adapter.exportVerified.emit(adapter.calls[0][2],
                                    "D:/exports/a.mp4", "a" * 64)
        self.app.processEvents()
        self.assertEqual([call[0] for call in adapter.binding_calls], ["a", "b"])
        self.assertEqual(len(adapter.calls), 1,
                         "Second draft must never use first panel binding")
        self.assertTrue(self.panel.property("pauseAfterCurrent"))

    def test_completion_without_native_task_admission_is_ignored(self):
        adapter = FakeNativeAdapter()
        adapter.auto_admit = False
        self.panel.setProperty("nativeAdapter", adapter)
        self.panel.setSelected(self.items[0], True)
        self.panel.setSelected(self.items[1], True)
        self.assertTrue(self.panel.startSelected())
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(self.result_for("a::D:/CapCut/A"),
                         "Submitting")
        first = adapter.calls[0][2]
        self.assertFalse(self.panel.nativeVerified(first, "out.mp4", "c" * 64))
        self.assertEqual(len(adapter.calls), 1)
        self.assertFalse(self.panel.nativeAdmitted("foreign", "task-elsewhere"))
        self.assertFalse(self.panel.nativeAdmitted(first, ""))
        self.assertTrue(self.panel.property("pauseAfterCurrent"))
        self.assertFalse(self.panel.property("running"))
        self.assertEqual(len(adapter.calls), 1)

    def test_native_admission_timeout_fails_closed(self):
        adapter = FakeNativeAdapter()
        adapter.auto_admit = False
        self.panel.setProperty("nativeAdapter", adapter)
        self.panel.setSelected(self.items[0], True)
        self.panel.setSelected(self.items[1], True)
        self.assertTrue(self.panel.startSelected())
        self.assertTrue(self.panel.nativeAdmissionTimedOut())
        self.assertTrue(self.panel.property("pauseAfterCurrent"))
        self.assertFalse(self.panel.property("running"))
        self.assertEqual(len(adapter.calls), 1)
        self.assertIn("admission not confirmed", self.panel.property("statusLine"))

    def test_delayed_admission_gates_verified_completion(self):
        adapter = FakeNativeAdapter()
        adapter.auto_admit = False
        self.panel.setProperty("nativeAdapter", adapter)
        self.panel.setSelected(self.items[0], True)
        self.panel.setSelected(self.items[1], True)
        self.assertTrue(self.panel.startSelected())
        first = adapter.calls[0][2]
        self.assertFalse(self.panel.nativeVerified(first, "out.mp4", "a" * 64))
        adapter.exportAdmitted.emit(first, "live-task-A")
        self.app.processEvents()
        self.assertEqual(self.panel.property("admittedTaskId"), "live-task-A")
        self.assertEqual(self.result_for(first), "Rendering")
        self.assertFalse(self.panel.nativeAdmitted(first, "duplicate-task"))
        adapter.exportVerified.emit(first, "D:/exports/a.mp4", "a" * 64)
        self.app.processEvents()
        self.assertEqual(self.panel.property("results")[first], "Completed")
        self.assertEqual(len(adapter.calls), 2)
        second = adapter.calls[1][2]
        self.assertFalse(self.panel.nativeVerified(second, "D:/exports/b.mp4",
                                                   "b" * 64))
        self.assertTrue(self.panel.nativeAdmitted(second, "live-task-B"))
        self.assertTrue(self.panel.nativeVerified(second, "D:/exports/b.mp4",
                                                  "b" * 64))

    def test_adapter_rejects_job_and_halts_without_retry(self):
        adapter = FakeNativeAdapter()
        adapter.accept = False
        self.panel.setProperty("nativeAdapter", adapter)
        self.panel.setSelected(self.items[0], True)
        self.panel.setSelected(self.items[1], True)
        self.assertTrue(self.panel.startSelected())
        self.assertEqual(len(adapter.calls), 1)
        self.assertTrue(self.panel.property("pauseAfterCurrent"))
        self.assertEqual(self.panel.property("activeKey"), "")

    def test_crash_recovery_does_not_auto_repeat_active_job(self):
        adapter = FakeNativeAdapter()
        self.panel.setProperty("nativeAdapter", adapter)
        journal = {
            "version": 2,
            "activeKey": "a::D:/CapCut/A",
            "pendingKeys": ["b::D:/CapCut/B"],
            "selectedKeys": ["a::D:/CapCut/A", "b::D:/CapCut/B"],
            "results": {"a::D:/CapCut/A": "Rendering",
                        "b::D:/CapCut/B": "Queued"},
            "paused": False,
            "recoveryReviewRequired": False,
        }
        self.assertTrue(self.panel.restoreSnapshot(json.dumps(journal)))
        self.assertEqual(len(adapter.calls), 0,
                         "Restoring journal must never start original engine")
        self.assertEqual(self.panel.property("activeKey"), "")
        self.assertTrue(self.panel.property("pauseAfterCurrent"))
        self.assertTrue(self.panel.property("recoveryReviewRequired"))
        self.assertFalse(self.panel.resume())
        self.assertFalse(self.panel.startSelected())
        self.assertTrue(self.panel.acknowledgeRecovery(True))
        self.assertTrue(self.panel.resume())
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(adapter.calls[0][0], "b",
                         "Interrupted A must NOT be repeated automatically")

    def test_recovery_restores_paused_queue_without_dispatch(self):
        adapter = FakeNativeAdapter()
        self.panel.setProperty("nativeAdapter", adapter)
        journal = {"version": 2, "activeKey": "", "pendingKeys": [
            "a::D:/CapCut/A", "b::D:/CapCut/B", "a::D:/CapCut/A"],
            "selectedKeys": ["a::D:/CapCut/A"], "results": {},
            "paused": True, "recoveryReviewRequired": False}
        self.assertTrue(self.panel.restoreSnapshot(json.dumps(journal)))
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.panel.property("recoveryReviewRequired"))
        pending = self.panel.property("pending")
        if hasattr(pending, "toVariant"):
            pending = pending.toVariant()
        self.assertEqual(len(pending), 2)
        self.assertTrue(self.panel.resume())
        self.assertEqual(len(adapter.calls), 1)

    def test_recovered_completed_requires_output_reverification(self):
        adapter = FakeNativeAdapter()
        self.panel.setProperty("nativeAdapter", adapter)
        journal = {"version": 2, "activeKey": "",
            "pendingKeys": ["b::D:/CapCut/B"],
            "selectedKeys": [], "results": {"a::D:/CapCut/A": "Completed"},
            "paused": False, "recoveryReviewRequired": False}
        self.assertTrue(self.panel.restoreSnapshot(json.dumps(journal)))
        self.assertTrue(self.panel.property("recoveryReviewRequired"))
        self.assertFalse(self.panel.resume())
        self.assertFalse(self.panel.setSelected(self.items[0], True))
        self.assertEqual(adapter.calls, [])

    def test_corrupt_or_wrong_version_journal_rejected(self):
        self.assertFalse(self.panel.restoreSnapshot(None))
        self.assertFalse(self.panel.restoreSnapshot({"version": 999}))
        self.assertFalse(self.panel.restoreSnapshot({
            "version": 2, "pendingKeys": "not-array",
            "selectedKeys": [], "results": {}}))
        self.assertEqual(self.panel.property("activeKey"), "")

    def test_stop_after_current_then_resume(self):
        adapter = FakeNativeAdapter()
        self.panel.setProperty("nativeAdapter", adapter)
        self.panel.setSelected(self.items[0], True)
        self.panel.setSelected(self.items[1], True)
        self.panel.startSelected()
        self.panel.pause()
        adapter.exportVerified.emit(adapter.calls[0][2], "D:/exports/a.mp4", "b"*64)
        self.app.processEvents()
        self.assertEqual(len(adapter.calls), 1)
        pending = self.panel.property("pending")
        if hasattr(pending, "toVariant"):
            pending = pending.toVariant()
        self.assertEqual(len(pending), 1)
        self.assertTrue(self.panel.resume())
        self.assertEqual(len(adapter.calls), 2)


if __name__ == "__main__":
    unittest.main()
