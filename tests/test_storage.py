"""Resource and cache regression: app-owned files only, originals untouched."""
from pathlib import Path
import os
import tempfile
import time
import unittest

from scene_desktop.studio_render import prune_render_cache, verify_scratch_room


class StorageTests(unittest.TestCase):
    def test_bounded_render_cache_never_deletes_inputs(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            cache = root / "render-cache"
            cache.mkdir()
            source = root / "user-input.mp4"
            source.write_bytes(b"DO_NOT_DELETE")
            stale = cache / "stale.mp4"
            newer = cache / "newer.mp4"
            stale.write_bytes(b"A"*128)
            newer.write_bytes(b"B"*128)
            os.utime(stale, (100, 100))
            self.assertEqual(prune_render_cache(cache, maximum_bytes=130,
                                               protected=(newer,)), 1)
            self.assertFalse(stale.exists())
            self.assertTrue(newer.exists())
            self.assertEqual(source.read_bytes(), b"DO_NOT_DELETE")
            verify_scratch_room(root / "output.mp4",reserve_bytes=1)


if __name__ == "__main__":
    unittest.main()
