"""Offscreen Windows/Qt checks for embedded image-only CapCut animations controls."""
import os
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from z_builder.animations_tab import CapcutAnimationsTab
from z_builder.capcut_controls_tab import CapcutControlsTab


def demo():
    return {
        "materials": {
            "videos": [
                {"id": "photo1", "type": "photo", "material_name": "first.jpg"},
                {"id": "movie1", "type": "video", "material_name": "clip.mp4"},
                {"id": "photo2", "type": "photo", "material_name": "second.png"},
            ],
            "material_animations": [],
            "transitions": [],
        },
        "tracks": [
            {"type": "video", "segments": [
                {"id": "p1", "material_id": "photo1", "target_timerange": {"start": 0, "duration": 2_500_000}, "extra_material_refs": []},
                {"id": "v1", "material_id": "movie1", "target_timerange": {"start": 2_500_000, "duration": 4_000_000}, "extra_material_refs": []},
                {"id": "p2", "material_id": "photo2", "target_timerange": {"start": 6_500_000, "duration": 1_700_000}, "extra_material_refs": []},
            ]},
        ],
    }


def catalog():
    return [
        {"effect_id": "native-a", "name": "Pendulum 1", "category": "Trending-3",
         "duration_us": 5_000_000, "path": "C:/fake/a",
         "template": {"id": "old", "type": "sticker_animation",
                      "animations": [{"id": "native-a", "resource_id": "native-a", "type": "group",
                                      "category_name": "Trending-3", "name": "Pendulum 1",
                                      "duration": 5_000_000}]}},
        {"effect_id": "native-b", "name": "Sway Out", "category": "Trending-3",
         "duration_us": 5_000_000, "path": "C:/fake/b",
         "template": {"id": "old2", "type": "sticker_animation",
                      "animations": [{"id": "native-b", "resource_id": "native-b", "type": "group",
                                      "category_name": "Trending-3", "name": "Sway Out",
                                      "duration": 5_000_000}]}},
    ]


class AnimationsPanelQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def panel(self):
        patches = [
            mock.patch("z_builder.animations_tab.list_projects", return_value=[Path("C:/drafts/demo")]),
            mock.patch("z_builder.animations_tab.harvest_animations", return_value=catalog()),
            mock.patch("z_builder.animations_tab.load_project", return_value=(demo(), [], [])),
            mock.patch("z_builder.animations_tab.resource_is_available", return_value=True),
            mock.patch("autocapcut_animations_only.animation_engine.resource_is_available", return_value=True),
            mock.patch("z_builder.animations_tab.capcut_running", return_value=False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        widget = CapcutAnimationsTab()
        self.addCleanup(widget.close)
        return widget

    def test_animation_panel_detects_only_images(self):
        w = self.panel()
        self.assertEqual(w.image_table.rowCount(), 2)
        self.assertEqual([x["name"] for x in w.images], ["first.jpg", "second.png"])
        self.assertEqual(w.catalog_table.rowCount(), 2)
        self.assertEqual(w.apply_button.text(), "Apply animations to selected images")

    def test_randomize_all_freezes_short_native_animation_preview(self):
        w = self.panel()
        w.randomize_all()
        self.assertEqual(w.mode.currentData(), "random_all")
        self.assertEqual(len(w.preview_rows), 2)
        self.assertEqual([r["applied_duration_us"] for r in w.preview_rows],
                         [2_500_000, 1_700_000])
        self.assertTrue(all(r["status"] == "Will Apply" for r in w.preview_rows))
        self.assertNotEqual(w.preview_rows[0]["effect_id"], w.preview_rows[1]["effect_id"])
        self.assertEqual(w.preview_project, Path("C:/drafts/demo"))

    def test_apply_uses_frozen_preview_and_never_calls_export(self):
        w = self.panel()
        w.randomize_all()
        frozen = w.preview_rows
        with (mock.patch("z_builder.animations_tab.save", return_value={
                  "saved": True, "changed": 2, "already_matching": 0, "backup_dir": "backup",
              }) as saved,
              mock.patch("z_builder.animations_tab.QMessageBox.question",
                         return_value=__import__("PySide6.QtWidgets", fromlist=["QMessageBox"]).QMessageBox.StandardButton.Yes),
              mock.patch("z_builder.animations_tab.QMessageBox.information"),
              mock.patch("z_builder.capcut.export_capcut", side_effect=AssertionError("No Scene Plan export"))):
            w.apply()
        self.assertEqual(saved.call_count, 1)
        self.assertIs(saved.call_args.args[3], frozen)
        self.assertEqual(w.preview_rows, [])

    def test_controls_parent_has_exact_three_subtabs(self):
        with (mock.patch("z_builder.transitions_tab.list_projects", return_value=[]),
              mock.patch("z_builder.transitions_tab.harvest_transitions", return_value=[]),
              mock.patch("z_builder.transitions_tab.capcut_running", return_value=False),
              mock.patch("z_builder.animations_tab.list_projects", return_value=[]),
              mock.patch("z_builder.animations_tab.harvest_animations", return_value=[]),
              mock.patch("z_builder.animations_tab.capcut_running", return_value=False)):
            p = CapcutControlsTab()
        self.addCleanup(p.close)
        self.assertEqual(p.sections.count(), 3)
        self.assertEqual([p.sections.tabText(i) for i in range(3)], ["Transitions", "Animations", "Scale"])


if __name__ == "__main__":
    unittest.main()
