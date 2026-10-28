"""Offscreen test for the Step 1 TXT download button; never edits a draft."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from z_builder.ui import Window


class ScenePlanEffectsSummaryQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_step_one_downloads_summary_using_both_configured_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            report_file = str(Path(temp) / "CapCut_Effects_Summary.txt")
            with (mock.patch("z_builder.transitions_tab.list_projects", return_value=[]),
                  mock.patch("z_builder.transitions_tab.harvest_transitions", return_value=[]),
                  mock.patch("z_builder.transitions_tab.capcut_running", return_value=False),
                  mock.patch("z_builder.animations_tab.list_projects", return_value=[]),
                  mock.patch("z_builder.animations_tab.harvest_animations", return_value=[]),
                  mock.patch("z_builder.animations_tab.capcut_running", return_value=False)):
                win = Window()
            try:
                self.assertIsNone(win.plan)
                self.assertEqual(win.tabs.tabText(0), "1  Input — Scene Plan + Voice")
                self.assertEqual(win.effects_summary_button.text(),
                                 "Download CapCut Effects Summary .txt")
                win.transitions_tab.projects_root = Path(temp) / "transitions"
                win.animations_tab.projects_root = Path(temp) / "animations"
                report = "Z BUILDER — CAPCUT EFFECTS SUMMARY\nnative_combo_animations_available=2\n"
                with (mock.patch("z_builder.ui.scan_effects_summary", return_value=report) as scan,
                      mock.patch("z_builder.ui.QFileDialog.getSaveFileName",
                                 return_value=(report_file, "Text files (*.txt)")),
                      mock.patch("z_builder.ui.QMessageBox.information") as info):
                    win.effects_summary_button.click()
                scan.assert_called_once_with(
                    Path(temp) / "transitions", Path(temp) / "animations")
                self.assertEqual(Path(report_file).read_text(encoding="utf-8"), report)
                self.assertEqual(info.call_count, 1)
                self.assertIsNone(win.plan)
                self.assertEqual(win.tabs.count(), 4)
            finally:
                win.close()

    def test_cancel_does_not_write_or_mutate(self):
        with (mock.patch("z_builder.transitions_tab.list_projects", return_value=[]),
              mock.patch("z_builder.transitions_tab.harvest_transitions", return_value=[]),
              mock.patch("z_builder.transitions_tab.capcut_running", return_value=False),
              mock.patch("z_builder.animations_tab.list_projects", return_value=[]),
              mock.patch("z_builder.animations_tab.harvest_animations", return_value=[]),
              mock.patch("z_builder.animations_tab.capcut_running", return_value=False)):
            win = Window()
        try:
            with (mock.patch("z_builder.ui.scan_effects_summary", return_value="example"),
                  mock.patch("z_builder.ui.QFileDialog.getSaveFileName",
                             return_value=("", "")),
                  mock.patch("pathlib.Path.write_text", side_effect=AssertionError("Must not write"))):
                win.save_effects_summary()
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
