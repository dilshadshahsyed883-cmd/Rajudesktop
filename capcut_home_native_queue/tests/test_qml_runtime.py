"""Offscreen *real Qt 6 QML runtime* acceptance tests for the Home queue panel.

Runs with PySide6-Essentials on a Windows GitHub runner. It DOES NOT start CapCut.
The fake host proves selection/serialization/verification event handling only;
it does not stand in for a real CapCut native bridge.
"""
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine

QML = Path(__file__).resolve().parents[1] / "HomeDraftQueuePanel.qml"


class FakeNativeAdapter(QObject):
    exportVerified = Signal(str, str, str)
    exportFailed = Signal(str, str)
    exportProgress = Signal(str, float)

    def __init__(self):
        super().__init__()
        self.calls = []
        self.accept = True

    @Slot(str, str, str, result=bool)
    def submitExport(self, draft_id, path, key):
        self.calls.append((draft_id, path, key))
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

    def test_no_native_adapter_means_no_dispatch(self):
        self.assertFalse(self.panel.property("adapterReady"))
        self.assertTrue(self.panel.setSelected(self.items[0], True))
        self.assertFalse(self.panel.startSelected())
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
        self.assertEqual(len(self.panel.property("pending")), 1)
        self.assertTrue(self.panel.resume())
        self.assertEqual(len(adapter.calls), 2)


if __name__ == "__main__":
    unittest.main()
