"""Windows desktop UI regression tests for Add to Queue navigation/clear."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from edge_voice_studio.store import Store
from edge_voice_studio.window import StudioWindow


class QueueSubmitUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "jobs.db")
        self.store.set_setting("draft_script", "")
        self.stores = patch("edge_voice_studio.window.Store", return_value=self.store)
        self.skip_queue = patch.object(StudioWindow, "_start_queue")
        self.stores.start()
        self.start_mock = self.skip_queue.start()
        self.window = StudioWindow()
        self.window._show_page(0)

    def tearDown(self):
        self.window.close()
        self.skip_queue.stop()
        self.stores.stop()
        self.temp.cleanup()

    def test_success_clears_script_and_navigates_queue(self):
        text = "Testing saved narration for the queue."
        voice = self.window.selected_voice
        self.window.script.setPlainText(text)
        self.window.title_input.setText("New Story")
        self.window.rate_slider.setValue(7)
        self.window.enqueue_current()
        jobs = self.store.all_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["script"], text)
        self.assertEqual(jobs[0]["voice"], voice)
        self.assertEqual(jobs[0]["rate"], 7)
        self.assertEqual(jobs[0]["status"], "queued")
        self.assertEqual(self.window.script.toPlainText(), "")
        self.assertEqual(self.window.stack.currentIndex(), 2)
        self.assertTrue(self.window.nav_buttons[2].isChecked())
        self.assertEqual(self.window.selected_voice, voice)
        self.assertEqual(self.window.rate_slider.value(), 7)
        self.start_mock.assert_called()

    def test_rejected_submission_preserves_input_and_current_tab(self):
        self.window.script.setPlainText("   ")
        self.window._show_page(0)
        with patch.object(self.window, "_error") as error:
            self.window.enqueue_current()
        self.assertEqual(len(self.store.all_jobs()), 0)
        self.assertEqual(self.window.script.toPlainText(), "   ")
        self.assertEqual(self.window.stack.currentIndex(), 0)
        error.assert_called_once()
        self.start_mock.assert_not_called()

    def test_settings_allow_one_to_ten_with_saved_five_default(self):
        self.assertEqual(self.window.parallel_chunks.count(), 10)
        self.assertEqual(self.window.parallel_chunks.currentText(), "5")
        self.window.parallel_chunks.setCurrentText("10")
        self.window.save_settings()
        self.assertEqual(self.store.get_setting("parallel_chunks"), 10)


if __name__ == "__main__":
    unittest.main()
