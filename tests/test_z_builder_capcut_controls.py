"""V6.2 CapCut controls expose only Transitions + Scale."""
import os
import unittest
from unittest import mock
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from z_builder.capcut_controls_tab import CapcutControlsTab
from z_builder.transitions_tab import CapcutTransitionsTab
from z_builder.scale_tab import CapcutScaleTab

class CapcutControlsV62QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def panel(self):
        with (mock.patch("z_builder.capcut_controls_tab.list_projects", return_value=[]),
              mock.patch("z_builder.transitions_tab.list_projects", return_value=[]),
              mock.patch("z_builder.transitions_tab.harvest_transitions", return_value=[]),
              mock.patch("z_builder.transitions_tab.capcut_running", return_value=False)):
            panel = CapcutControlsTab()
        panel.timer.stop()
        self.addCleanup(panel.close)
        return panel

    def test_two_subtabs_no_animation_editor(self):
        p=self.panel()
        self.assertEqual([p.sections.tabText(i) for i in range(p.sections.count())],["Transitions","Scale"])
        self.assertEqual(p.panels,[p.transitions_tab,p.scale_tab])
        self.assertIs(p.sections.widget(0),p.transitions_tab)
        self.assertIs(p.sections.widget(1),p.scale_tab)
        self.assertIsInstance(p.transitions_tab,CapcutTransitionsTab)
        self.assertIsInstance(p.scale_tab,CapcutScaleTab)
        self.assertFalse(hasattr(p,"animations_tab"))

    def test_scale_engine_defaults_without_effect_extensions(self):
        opts=self.panel().scale_tab.options()
        self.assertEqual((opts.video_scale_min,opts.video_scale_max),(150,170))
        self.assertEqual((opts.image_scale_min,opts.image_scale_max),(105,110))
        self.assertFalse(opts.extend_filters)
        self.assertFalse(opts.extend_effects)

if __name__=="__main__":
    unittest.main()
