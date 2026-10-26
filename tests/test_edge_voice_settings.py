"""GUI-level regression tests for output storage and screenshot style (offline)."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

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

    def test_saved_custom_destination_persists(self):
        with tempfile.TemporaryDirectory() as td:
            first = StudioWindow()
            expected = str(default_output_folder())
            first.output_path.setText(str(Path(td) / "VoiceOutputs"))
            # Browsing alone must not change the committed destination.
            self.assertEqual(first.store.get_setting("output_folder", expected), expected)
            first.save_settings()
            self.assertEqual(first.store.get_setting("output_folder"), str(Path(td) / "VoiceOutputs"))
            first.close()
            second = StudioWindow()
            self.assertEqual(second.output_path.text(), str(Path(td) / "VoiceOutputs"))
            second.output_path.setText(str(Path(td) / "Unsaved"))
            self.assertEqual(second.store.get_setting("output_folder"), str(Path(td) / "VoiceOutputs"))
            # Put defaults back for unrelated tests.
            second.output_path.setText(expected)
            second.save_settings()
            second.close()


if __name__ == "__main__":
    unittest.main()
