"""Regression test for Tkinter's reserved widget _options(cnf, kw) method.

The V2 standalone executable crashed before displaying its window because
VisualApp._options(self) shadowed tkinter.Misc._options(self, cnf, kw).
"""
from __future__ import annotations

import inspect
from pathlib import Path
import sys
import tkinter as tk
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import VisualApp
from engine import Options


class GUIStartupTests(unittest.TestCase):
    def test_tkinter_reserved_widget_option_method_is_inherited(self):
        # This runs on Linux CI without needing a display, catching the exact
        # startup bug in all builds, including frozen Windows packaging.
        self.assertIs(VisualApp._options, tk.Misc._options)
        self.assertEqual(inspect.signature(VisualApp._options),
                         inspect.signature(tk.Misc._options))
        self.assertTrue(callable(VisualApp._build_edit_options))

    @unittest.skipUnless(sys.platform == "win32", "Windows GUI smoke")
    def test_real_window_initializes_and_edit_options_work(self):
        app = VisualApp()
        try:
            app.withdraw()
            app.update_idletasks()
            self.assertTrue(app.winfo_exists())
            self.assertIsInstance(app._build_edit_options(), Options)
            self.assertTrue(hasattr(app, "fx_tree"))
            self.assertTrue(hasattr(app, "apply_btn"))
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
