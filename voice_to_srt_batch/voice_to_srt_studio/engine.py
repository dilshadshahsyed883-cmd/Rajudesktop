"""Testable, UI-independent, offline-capable transcription engine."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import tempfile
from typing import Callable, Iterable, Sequence

AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".wma", ".mp4", ".mkv", ".mov", ".webm"})
PRESETS = {"Short (2-3 sec)": (2.0, 3.0), "Recommended (3-4 sec)": (3.0, 4.0), "Long (4-6 sec)": (4.0, 6.0)}
LANGUAGES = {"Auto detect": None, "English": "en", "Urdu": "ur", "Hindi": "hi"}
MODELS = ("tiny", "base", "small", "medium")

class Cancelled(Exception):
    """Raised when the user stops a queued job."""

@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float

@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def to_srt_time(seconds: float) -> str:
    ms = max(0, round(float(seconds) * 1000))
    h, remain = divmod(ms, 3_600_000)
    m, remain = divmod(remain, 60_000)
    s, ms = divmod(remain, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_cues(words: Sequence[Word], min_seconds: float = 3.0, max_seconds: float = 4.0, max_chars: int = 90) -> list[Cue]:
    """Group aligned Whisper words without manufacturing equal-spaced timings.

    The maximum is a soft limit only when a single aligned word is longer.
    Pauses and line length can produce shorter cues for readable subtitles.
    """
    if not (0 < min_seconds <= max_seconds):
        raise ValueError("Invalid subtitle duration range")
    ordered = sorted((w for w in words if clean_text(w.text)), key=lambda w: (w.start, w.end))
    cues: list[Cue] = []
    pending: list[Word] = []

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        start = max(0., pending[0].start)
        end = max(start + 0.001, max(w.end for w in pending))
        # Overlap is possible in the model's raw word alignment.
        if cues:
            start = max(start, cues[-1].end)
            end = max(end, start + 0.001)
        text = clean_text("".join(w.text if w.text.startswith((" ", "'", "’")) else " " + w.text for w in pending))
        if text:
            cues.append(Cue(start, end, text))
        pending = []

    for w in ordered:
        start = max(0., float(w.start))
        end = max(start + 0.001, float(w.end))
        candidate = Word(w.text, start, end)
        if pending:
            duration = end - pending[0].start
            gap = start - pending[-1].end
            chars = len(clean_text(" ".join(x.text for x in pending + [candidate])))
            if duration > max_seconds or gap >= 0.75 or chars > max_chars:
                flush()
        pending.append(candidate)
        if pending:
            duration = pending[-1].end - pending[0].start
            ends_sentence = pending[-1].text.rstrip().endswith((".", "?", "!", "۔", "؟"))
            if duration >= min_seconds and ends_sentence:
                flush()
    flush()
    return cues


def render_srt(cues: Iterable[Cue]) -> str:
    blocks = []
    for i, cue in enumerate(cues, 1):
        blocks.append(f"{i}\n{to_srt_time(cue.start)} --> {to_srt_time(cue.end)}\n{cue.text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def output_path(source: Path, output_dir: Path | None) -> Path:
    return (output_dir if output_dir is not None else source.parent) / (source.stem + ".srt")


def save_atomic(destination: Path, text: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".srt-", suffix=".tmp", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)
        os.replace(tmp_name, destination)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def make_model(name: str):
    """Loads model once per queue. First run downloads model; later runs use local cache."""
    if name not in MODELS:
        raise ValueError(f"Unsupported model: {name}")
    from faster_whisper import WhisperModel  # Imported lazily for fast GUI startup/tests.
    return WhisperModel(name, device="cpu", compute_type="int8")


def transcribe_one(
    model,
    source: Path,
    preset: str,
    language: str,
    progress: Callable[[float], None],
    should_cancel: Callable[[], bool],
) -> list[Cue]:
    if preset not in PRESETS or language not in LANGUAGES:
        raise ValueError("Invalid transcription settings")
    if should_cancel():
        raise Cancelled()
    segments, info = model.transcribe(
        str(source), language=LANGUAGES[language], beam_size=5,
        word_timestamps=True, vad_filter=True, condition_on_previous_text=False,
    )
    duration = float(getattr(info, "duration", 0) or 0)
    words: list[Word] = []
    for segment in segments:
        if should_cancel():
            raise Cancelled()
        aligned_words = getattr(segment, "words", None) or []
        if aligned_words:
            for w in aligned_words:
                token = str(getattr(w, "word", "") or "")
                if not clean_text(token):
                    continue
                start = float(getattr(w, "start", getattr(segment, "start", 0)) or 0)
                end = float(getattr(w, "end", getattr(segment, "end", start)) or start)
                words.append(Word(token, start, end))
        else:
            # Use segment's original speech timestamps if word alignment is unavailable.
            text = clean_text(str(getattr(segment, "text", "") or ""))
            if text:
                words.append(Word(text, float(segment.start), float(segment.end)))
        if duration:
            progress(min(0.99, max(0.0, float(segment.end) / duration)))
    if should_cancel():
        raise Cancelled()
    progress(1.0)
    lo, hi = PRESETS[preset]
    return build_cues(words, lo, hi)


def unique_valid_sources(paths: Iterable[str | Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        p = Path(path).expanduser()
        if p.suffix.lower() not in AUDIO_EXTENSIONS or not p.is_file():
            continue
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def collect_folder(folder: Path, recursive: bool = False) -> list[Path]:
    if not folder.is_dir():
        return []
    items = folder.rglob("*") if recursive else folder.iterdir()
    return unique_valid_sources(sorted((p for p in items if p.is_file()), key=lambda p: str(p).lower()))
