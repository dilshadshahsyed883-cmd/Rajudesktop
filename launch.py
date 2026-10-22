"""Scene Desktop Studio's packaged Windows launcher and read-only diagnostics."""
from __future__ import annotations
import sys


def main():
    if "--check-whisper-runtime" in sys.argv:
        # Import backend/runtime libraries inside the packaged EXE, not merely
        # on the CI Python host. Never downloads any model or handles user media.
        from faster_whisper import WhisperModel
        import ctranslate2
        import av
        import tokenizers
        if not all([WhisperModel,ctranslate2,av,tokenizers]):
            return 3
        return 0
    from scene_desktop.app import main as start_gui
    return start_gui()


if __name__ == "__main__":
    raise SystemExit(main())
