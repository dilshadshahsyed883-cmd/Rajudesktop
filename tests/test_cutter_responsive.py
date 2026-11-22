"""Real Tk layout regression checks for Smart Media Manager's batch cutter.

Runs on Windows CI with a display; does not start downloads or media work.
"""
import tkinter as tk
import unittest

from smart_media_manager.app import SmartMediaManager
from smart_media_manager.cutter_queue_ui import BatchCutterTab


class ResponsiveCutterTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = SmartMediaManager()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.root.update()
        self.cutter = next(
            tab for tab in self.root.tabs if isinstance(tab, BatchCutterTab)
        )

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    def resize(self, width, height):
        self.root.geometry(f"{width}x{height}")
        self.root.update_idletasks()
        self.root.update()
        self.root.update_idletasks()

    def assert_footer_visible(self):
        parent_bottom = self.cutter.winfo_rooty() + self.cutter.winfo_height()
        for widget in (self.cutter.run_button, self.cutter.cancel_button,
                       self.cutter.retry_button, self.cutter.remove_button,
                       self.cutter.clear_button, self.cutter.progress_bar):
            self.assertEqual(widget.winfo_manager(), "grid")
            self.assertLessEqual(
                widget.winfo_rooty() + widget.winfo_height(), parent_bottom + 2,
                f"{widget} is clipped below the visible tab",
            )
        self.assertGreater(self.cutter.tree.winfo_height(), 28)

    def test_wide_medium_and_narrow_reflow(self):
        for width, height, expected in (
            (1260, 900, "wide"),
            (960, 700, "medium"),
            (720, 600, "narrow"),
        ):
            with self.subTest(size=(width, height)):
                self.resize(width, height)
                self.assertEqual(self.cutter._layout_mode, expected)
                left = self.cutter._input_left.grid_info()
                right = self.cutter._input_right.grid_info()
                if expected == "narrow":
                    self.assertNotEqual(left["row"], right["row"])
                else:
                    self.assertEqual(left["row"], right["row"])
                self.assert_footer_visible()

    def test_vertical_scroll_and_compact_action_grid(self):
        self.resize(660, 540)
        self.assertIn(self.cutter._layout_mode, ("narrow", "tiny"))
        self.assert_footer_visible()
        self.assertLess(
            self.cutter._upper_canvas.winfo_height(),
            self.cutter._upper_body.winfo_reqheight(),
        )
        self.assertTrue(self.cutter.tree["xscrollcommand"])
        self.assertNotEqual(
            self.cutter.run_button.grid_info()["row"],
            self.cutter.clear_button.grid_info()["row"],
        )

    def test_source_controls_and_queue_are_still_available(self):
        self.resize(720, 600)
        self.assertIsInstance(self.cutter.links, tk.Text)
        self.assertEqual(str(self.cutter.quality_select["state"]), "readonly")
        self.assertTrue(self.cutter.run_button["command"])
        self.assertTrue(self.cutter.pc_button["command"])
        self.assert_footer_visible()


if __name__ == "__main__":
    unittest.main()
