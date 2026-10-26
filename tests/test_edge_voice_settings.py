"""GUI-level regression tests for output storage and screenshot style (offline)."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication
from edge_voice_studio.window import StudioWindow, default_output_folder, stylesheet


class DesktopPreferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setApplicationName("Edge Voice Studio")
        cls.app.setOrganizationName("Rajudesktop")
        QStandardPaths.setTestModeEnabled(True)

    def test_documents_default(self):
        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation)
        self.assertEqual(default_output_folder(), Path(documents) / "EdgeVoiceStudio")
        self.assertIn("#102A4B", stylesheet("Navy Light"))
        self.assertIn("#1756D9", stylesheet("Navy Light"))
        self.assertIn("#FFFFFF", stylesheet("Navy Light"))

    def test_add_to_queue_opens_queue_and_selects_new_job(self):
        window = StudioWindow()
        window.title_input.setText("Queue redirect test")
        window.script.setPlainText("This narration should be added to the queue.")
        with patch.object(window, "_start_queue") as start:
            window.enqueue_current()
        self.assertEqual(window.stack.currentIndex(), 2)
        self.assertIsNotNone(window._selected_job())
        self.assertEqual(window.store.get(window._selected_job())["title"],
                         "Queue redirect test")
        start.assert_called_once()
        window.store.delete_job(window._selected_job())
        window.close()

    def test_queue_open_output_folder_without_selected_job(self):
        with tempfile.TemporaryDirectory() as td:
            window = StudioWindow()
            original = window.store.get_setting("output_folder", None)
            target = Path(td) / "Generated Voices"
            window.store.set_setting("output_folder", str(target))
            window._show_page(2)
            names = []
            for i in range(window.queue_table.rowCount()):
                window.queue_table.item(i, 0).setSelected(False)
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            with patch.object(QDesktopServices, "openUrl", return_value=True) as opener:
                window.open_output_folder()
                opener.assert_called_once()
                opened = opener.call_args.args[0]
                self.assertIsInstance(opened, QUrl)
                self.assertEqual(Path(opened.toLocalFile()).resolve(), target.resolve())
            self.assertTrue(target.is_dir())
            if original is None:
                with window.store.connect() as con:
                    con.execute("DELETE FROM settings WHERE key='output_folder'")
            else:
                window.store.set_setting("output_folder", original)
            window.close()

    def test_saved_custom_destination_persists(self):
        with tempfile.TemporaryDirectory() as td:
            first = StudioWindow()
            expected = str(default_output_folder())
            previous = first.store.get_setting("output_folder", expected)
            first.output_path.setText(str(Path(td) / "VoiceOutputs"))
            # Browsing alone must not change the committed destination.
            self.assertEqual(first.store.get_setting("output_folder", expected), previous)
            first.save_settings()
            self.assertEqual(first.store.get_setting("output_folder"), str(Path(td) / "VoiceOutputs"))
            first.close()
            second = StudioWindow()
            self.assertEqual(second.output_path.text(), str(Path(td) / "VoiceOutputs"))
            second.output_path.setText(str(Path(td) / "Unsaved"))
            self.assertEqual(second.store.get_setting("output_folder"), str(Path(td) / "VoiceOutputs"))
            # Restore the original stored destination for unrelated tests.
            second.output_path.setText(previous)
            second.save_settings()
            second.close()


if __name__ == "__main__":
    unittest.main()
