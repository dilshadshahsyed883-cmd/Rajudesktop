"""Integrate the existing batch Whisper SRT engine without its Tk UI.

No model or audio is bundled alongside the final EXE. Model weights are
downloaded to the standard user cache on first use, then reused.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from voice_to_srt_batch.voice_to_srt_studio.engine import (
    Cancelled, make_model, render_srt, save_atomic, transcribe_one,
)

MODEL = "small"
PRESET = "Recommended (3-4 sec)"
LANGUAGE = "English"


def transcribe_completed_voice(
    mp3: str | Path, model, should_cancel: Callable[[], bool],
    progress: Callable[[float], None] = lambda _: None,
) -> str:
    """Return 'done' or 'skipped', preserving an existing nonempty SRT."""
    source = Path(mp3)
    if not source.is_file() or source.stat().st_size == 0:
        raise FileNotFoundError(f"Completed MP3 is missing: {source}")
    dest = source.with_suffix(".srt")
    if dest.exists() and dest.stat().st_size:
        return "skipped"
    if should_cancel():
        raise Cancelled()
    cues = transcribe_one(model, source, PRESET, LANGUAGE, progress, should_cancel)
    if should_cancel():
        raise Cancelled()
    if not cues:
        raise ValueError("No speech timestamps detected; SRT not saved")
    save_atomic(dest, render_srt(cues))
    return "done"
