"""Native Qt window smoke: construction and core controls, no user PC access."""
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from scene_desktop.studio_window import StudioWindow


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_unified_window_has_tracks_library_and_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("scene_desktop.studio_window.app_directory",
                       return_value=__import__("pathlib").Path(tmp)):
                window = StudioWindow()
                self.assertEqual(window.left.count(), 2)
                self.assertEqual(window.workspace_tabs.count(), 2)
                self.assertEqual(window.workspace_tabs.tabText(1), "Self Media Library (Offline)")
                self.assertFalse(window.offline_sml_service.process)
                self.assertEqual(len(window.project.tracks), 6)
                self.assertIsNotNone(window.timeline.scene())
                self.assertIsNotNone(window.player)
                window.close()


if __name__ == "__main__":
    unittest.main()
