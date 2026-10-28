"""Standalone Voice to SRT Studio Batch launcher, including frozen EXE smoke check."""
from __future__ import annotations

import sys


def main() -> None:
    if "--self-test" in sys.argv:
        # Exercise frozen dependency imports without creating a GUI or downloading a model.
        from faster_whisper import WhisperModel  # noqa: F401
        import ctranslate2  # noqa: F401
        import av  # noqa: F401
        from voice_to_srt_studio.engine import Word, build_cues, render_srt
        cues = build_cues([Word(" Hello", 0.0, 1.1), Word(" world", 1.1, 2.9)])
        assert len(cues) == 1
        assert "Hello world" in render_srt(cues)
        return
    from voice_to_srt_studio.app import main as app_main
    app_main()


if __name__ == "__main__":
    main()
