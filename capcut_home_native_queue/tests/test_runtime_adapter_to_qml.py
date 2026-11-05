"""End-to-end genuine Qt QML + QObject adapter contract, with synthetic host.

Loads the real HomeDraftQueuePanel.qml and invokes a Qt QObject @Slot via
QtRuntimeAdapter. No CapCut proprietary DLL is loaded and no MP4 is rendered.
"""
from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine

from capcut_home_native_queue.native_output_validation import VerifiedOutput
from capcut_home_native_queue.qt_runtime_adapter import CurrentDraft, QtRuntimeAdapter

QML_PATH = Path(__file__).resolve().parents[1] / "HomeDraftQueuePanel.qml"


class ExportCompileBottomViewModel(QObject):
    def __init__(self):
        super().__init__()
        self.clicks = 0

    @Slot()
    def clickBackgroudExport(self):
        self.clicks += 1


class RuntimeToQmlIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = QQmlEngine()
        self.component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(QML_PATH)))
        self.assertEqual(self.component.status(), QQmlComponent.Status.Ready,
                         "\n".join(map(str, self.component.errors())))
        self.panel = self.component.create()
        self.assertIsNotNone(self.panel)
        self.model = ExportCompileBottomViewModel()
        self.sources = [
            str(Path(self.temp.name) / "draft-A"),
            str(Path(self.temp.name) / "draft-B"),
        ]
        for source in self.sources:
            Path(source).mkdir()
        self.drafts = [
            {"draftId": "A", "strProjectPath": self.sources[0], "strTitle": "A"},
            {"draftId": "B", "strProjectPath": self.sources[1], "strTitle": "B"},
        ]
        self.panel.setProperty("drafts", self.drafts)
        self.output_paths = {
            "A": str(Path(self.temp.name) / "render-A.mp4"),
            "B": str(Path(self.temp.name) / "render-B.mp4"),
        }
        self.state = {"active": CurrentDraft("A", self.sources[0], self.model)}
        self.adapter = QtRuntimeAdapter(
            self.model,
            read_current_draft=lambda: self.state["active"],
            resolve_output=lambda draft_id, path: self.output_paths[draft_id],
            verify_native_runtime=lambda model: True,  # TEST HOST ONLY
            receipt_verifier=lambda ticket, path: VerifiedOutput(
                ticket.key, str(ticket.output_path), "a" * 64, 40000, 15, 1530, 1080),
        )
        self.assertTrue(self.adapter.verifyRuntime())
        self.panel.setProperty("nativeAdapter", self.adapter)
        self.app.processEvents()

    def tearDown(self):
        self.panel.deleteLater()
        self.engine.deleteLater()
        self.app.processEvents()

    def test_qml_serial_drafts_with_independent_admission_and_completion(self):
        self.assertTrue(self.panel.property("adapterReady"))
        for draft in self.drafts:
            self.assertTrue(self.panel.setSelected(draft, True))
        self.assertTrue(self.panel.startSelected())
        self.assertEqual(self.model.clicks, 1)
        first_key = "A::" + self.sources[0]
        second_key = "B::" + self.sources[1]
        # First invoked Qt method returns void; cannot complete yet.
        self.assertEqual(self.panel.property("admittedTaskId"), "")
        self.assertFalse(self.panel.nativeVerified(first_key, "output.mp4", "a" * 64))
        self.assertEqual(self.model.clicks, 1)
        self.assertTrue(self.adapter.nativeTaskAdmitted(
            first_key, "trusted-task-A", "A", self.sources[0]))
        self.app.processEvents()
        self.assertEqual(self.panel.property("admittedTaskId"), "trusted-task-A")

        # A genuine integration host must rebind the next Home draft before
        # its export model can be reused for the following queued job.
        self.state["active"] = CurrentDraft("B", self.sources[1], self.model)
        self.assertTrue(self.adapter.nativeTaskCompleted(
            first_key, "trusted-task-A", self.output_paths["A"]))
        self.app.processEvents()
        self.assertEqual(self.model.clicks, 2)
        self.assertEqual(self.panel.property("activeKey"), second_key)
        self.assertEqual(self.panel.property("admittedTaskId"), "")
        self.assertFalse(self.adapter.nativeTaskCompleted(
            second_key, "foreign-task", self.output_paths["B"]))
        self.assertTrue(self.adapter.nativeTaskAdmitted(
            second_key, "trusted-task-B", "B", self.sources[1]))
        self.assertTrue(self.adapter.nativeTaskCompleted(
            second_key, "trusted-task-B", self.output_paths["B"]))
        self.app.processEvents()
        self.assertEqual(self.panel.property("activeKey"), "")
        self.assertEqual(self.model.clicks, 2)

    def test_second_draft_not_exported_without_exact_rebinding(self):
        self.panel.setSelected(self.drafts[0], True)
        self.panel.setSelected(self.drafts[1], True)
        self.assertTrue(self.panel.startSelected())
        first_key = "A::" + self.sources[0]
        self.assertTrue(self.adapter.nativeTaskAdmitted(first_key, "task-A", "A", self.sources[0]))
        # Leaving model bound to A must halt rather than export B.
        self.assertTrue(self.adapter.nativeTaskCompleted(
            first_key, "task-A", self.output_paths["A"]))
        self.app.processEvents()
        self.assertEqual(self.model.clicks, 1)
        self.assertTrue(self.panel.property("pauseAfterCurrent"))
        self.assertEqual(self.panel.property("activeKey"), "")


if __name__ == "__main__":
    unittest.main()
