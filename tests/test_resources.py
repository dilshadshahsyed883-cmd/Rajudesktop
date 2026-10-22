import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scene_desktop.resources import probe


class ResourceTests(unittest.TestCase):
    def test_readonly_hardware_report(self):
        with tempfile.TemporaryDirectory() as root:
            with patch("scene_desktop.resources.platform.system", return_value="Linux"):
                report = probe(Path(root))
            self.assertGreater(report["disk_total_gib"], 0)
            self.assertGreaterEqual(report["disk_free_gib"], 0)
            self.assertIn("ffmpeg_encoders_present", report)
            self.assertFalse(report["gpu_acceleration_verified"])
            self.assertIsNone(report["ram_total_gib"])


if __name__ == "__main__":
    unittest.main()
