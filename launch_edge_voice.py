"""Launch Edge Voice Studio, with frozen dependency smoke test support."""
from __future__ import annotations

import sys


def self_test() -> None:
    # Fail a Windows EXE build if hidden speech dependencies were omitted.
    from faster_whisper import WhisperModel  # noqa: F401
    import ctranslate2  # noqa: F401
    import av  # noqa: F401
    from voice_to_srt_batch.voice_to_srt_studio.engine import (
        Word, build_cues, render_srt,
    )
    cues = build_cues([Word(" Hello", 0, 1.5), Word(" world", 1.5, 3.7)])
    assert len(cues) == 1 and "Hello world" in render_srt(cues)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        from edge_voice_studio.window import main
        raise SystemExit(main())
