"""Entry point for source launch and frozen Windows EXE."""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path


def self_test():
    from short_studio.core import Store, RenderOptions, ffmpeg_exe
    with tempfile.TemporaryDirectory() as folder:
        store = Store(folder)
        store.create_folder("Test")
        first = store.reserve_names("Test", 2)
        second = Store(folder).reserve_names("Test", 1)
        assert first[0].name.startswith("Test 001_")
        assert first[1].name.startswith("Test 002_")
        assert second[0].name.startswith("Test 003_")
        assert RenderOptions().validate() is None
        assert Path(ffmpeg_exe()).is_file()
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    from short_studio.ui import main
    main()
