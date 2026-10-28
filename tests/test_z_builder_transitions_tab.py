"""Regression checks for native CapCut Transitions editor embedded in Z Builder CapCut Controls."""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from z_builder.transitions_tab import CapcutTransitionsTab, EXAMPLE_EDIT_FILE
from z_builder.capcut_controls_tab import CapcutControlsTab
from autocapcut_transitions_only.transition_engine import parse_edit_file


class CapcutTransitionsQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self):
        patches = [
            mock.patch("z_builder.transitions_tab.list_projects", return_value=[]),
            mock.patch("z_builder.transitions_tab.harvest_transitions", return_value=[]),
            mock.patch("z_builder.transitions_tab.capcut_running", return_value=False),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        panel = CapcutTransitionsTab()
        self.addCleanup(panel.close)
        return panel

    def test_transitions_panel_has_complete_independent_workflow(self):
        panel = self._panel()
        self.assertEqual(panel.sections.count(), 3)
        self.assertEqual([panel.sections.tabText(i) for i in range(3)],
                         ["Transitions", "Edit file", "Preview / Log"])
        self.assertEqual(panel.mode.currentData(), "none")
        self.assertEqual(panel.apply_button.text(), "Apply transitions only")
        self.assertTrue(panel.project_combo.count() == 0)
        self.assertIn("transitions", EXAMPLE_EDIT_FILE)
        self.assertEqual(parse_edit_file(EXAMPLE_EDIT_FILE)["version"], 1)

    def test_fourth_tab_is_embedded_in_main_z_builder_window(self):
        from z_builder.ui import Window
        with (mock.patch("z_builder.transitions_tab.list_projects", return_value=[]),
              mock.patch("z_builder.transitions_tab.harvest_transitions", return_value=[]),
              mock.patch("z_builder.transitions_tab.capcut_running", return_value=False),
              mock.patch("z_builder.animations_tab.list_projects", return_value=[]),
              mock.patch("z_builder.animations_tab.harvest_animations", return_value=[]),
              mock.patch("z_builder.animations_tab.capcut_running", return_value=False)):
            win = Window()
        try:
            self.assertEqual(win.tabs.count(), 4)
            self.assertEqual(win.tabs.tabText(0), "1  Input — Scene Plan + Voice")
            self.assertEqual(win.tabs.tabText(1), "2  Media Selection + Timeline")
            self.assertEqual(win.tabs.tabText(2), "3  Open in CapCut")
            self.assertEqual(win.tabs.tabText(3), "4  CapCut Controls")
            self.assertIsInstance(win.tabs.widget(3), CapcutControlsTab)
            self.assertEqual([win.capcut_controls_tab.sections.tabText(i) for i in range(2)],
                             ["Transitions", "Animations"])
            self.assertIsInstance(win.transitions_tab, CapcutTransitionsTab)
            self.assertIs(win.transitions_tab, win.capcut_controls_tab.transitions_tab)
            self.assertIsNot(win.tabs.widget(3), win.tabs.widget(2))
        finally:
            win.close()

    def test_tab_does_not_invoke_scene_plan_export(self):
        panel = self._panel()
        with mock.patch("z_builder.capcut.export_capcut", side_effect=AssertionError("must not export")):
            self.assertFalse(panel.validate()) if panel.selected_project() else self.assertIsNone(panel.selected_project())
            panel.clear_edit()
            panel.copy_example()
            self.assertIsNone(panel.preview_project)


if __name__ == "__main__":
    unittest.main()
