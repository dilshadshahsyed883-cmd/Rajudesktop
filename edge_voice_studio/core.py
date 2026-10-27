"""Pure helpers for reliable long narration and subtitle formatting."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

MAX_CHUNK = 2600
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_script(text: str, limit: int = MAX_CHUNK) -> list[str]:
    if limit < 40:
        raise ValueError("Chunk limit must be at least 40")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("Enter narration text first")
    chunks: list[str] = []
    buf = ""

    def push(segment: str) -> None:
        nonlocal buf
        segment = segment.strip()
        if not segment:
            return
        if buf and len(buf) + 1 + len(segment) > limit:
            chunks.append(buf)
            buf = ""
        if len(segment) <= limit:
            buf = (buf + " " + segment).strip()
            return
        words = re.findall(r"\S+", segment)
        for word in words:
            if len(word) > limit:
                if buf:
                    chunks.append(buf)
                    buf = ""
                for start in range(0, len(word), limit):
                    part = word[start:start + limit]
                    if len(part) == limit:
                        chunks.append(part)
                    else:
                        buf = part
            else:
                if buf and len(buf) + 1 + len(word) > limit:
                    chunks.append(buf)
                    buf = ""
                buf = (buf + " " + word).strip()

    for paragraph in re.split(r"\n\s*\n|\n", text):
        for sentence in SENTENCE_END.split(paragraph.strip()):
            push(sentence)
    if buf:
        chunks.append(buf)
    return chunks


def english_voice(voice: str) -> bool:
    return bool(re.fullmatch(r"en-[A-Za-z]{2,4}-[A-Za-z0-9]+Neural", voice))


def safe_title(title: str) -> str:
    name = re.sub(r"[^\w .-]+", "_", title, flags=re.UNICODE).strip(" ._")
    return name[:75] or "Narration"


def settings_hash(script: str, voice: str, rate: int, pitch: int, volume: int) -> str:
    raw = "\x1f".join((script, voice, str(rate), str(pitch), str(volume)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def srt_time(ms: int) -> str:
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(chunks: list[tuple[list[dict], int]], output: Path) -> int:
    """Create captions of roughly 3–4 seconds using Edge's actual word timestamps.

    Word offsets are relative to the beginning of each synthesized MP3 chunk;
    measured MP3 lengths locate each chunk on the final concatenated timeline.
    Short final phrases and long pauses may necessarily yield shorter cues.
    Missing timing metadata is an error, never an empty or guessed SRT.
    """
    words: list[dict] = []
    shift_ms = 0
    for events, duration_ms in chunks:
        duration_ms = max(0, int(duration_ms))
        if duration_ms <= 0:
            raise ValueError("Cannot synchronize subtitles with an empty audio chunk")
        chunk_words = []
        for item in events:
            try:
                word = str(item["text"]).strip()
                start = max(0, int(item["offset"]) // 10000)
                length = max(1, int(item["duration"]) // 10000)
            except (KeyError, ValueError, TypeError):
                continue
            if not word or start >= duration_ms:
                continue
            end = min(duration_ms, start + length)
            chunk_words.append({"text": word, "start": shift_ms + start,
                                "end": shift_ms + end})
        if not chunk_words:
            raise ValueError(
                "Edge TTS did not provide word timings for a voice chunk; "
                "accurate synchronized SRT cannot be generated")
        words.extend(sorted(chunk_words, key=lambda item: item["start"]))
        shift_ms += duration_ms

    if not words:
        raise ValueError("Cannot generate subtitles without spoken words")

    groups: list[list[dict]] = []
    current: list[dict] = []

    def flush() -> None:
        nonlocal current
        if current:
            groups.append(current)
            current = []

    for index, word in enumerate(words):
        if current:
            gap = word["start"] - current[-1]["end"]
            proposed_ms = word["end"] - current[0]["start"]
            # Do not hold captions through a conspicuous silence, or exceed
            # four seconds just to squeeze in another spoken word.
            if gap >= 1200 or (proposed_ms > 4000 and
                               current[-1]["end"] - current[0]["start"] >= 1200):
                flush()
        current.append(word)
        elapsed = current[-1]["end"] - current[0]["start"]
        upcoming = words[index + 1] if index + 1 < len(words) else None
        next_too_late = upcoming is None or (
            upcoming["end"] - current[0]["start"] > 4000
            or upcoming["start"] - current[-1]["end"] >= 1200)
        if elapsed >= 3000 and (next_too_late or word["text"].endswith((".", "!", "?"))):
            flush()
    flush()

    # Avoid a one-word tail if the preceding cue can accommodate it without
    # crossing a large pause. Preserve precise spoken starts/ends.
    if len(groups) >= 2:
        previous, last = groups[-2], groups[-1]
        last_ms = last[-1]["end"] - last[0]["start"]
        joined_ms = last[-1]["end"] - previous[0]["start"]
        gap = last[0]["start"] - previous[-1]["end"]
        if last_ms < 1800 and joined_ms <= 4200 and gap < 700:
            previous.extend(last)
            groups.pop()

    entries = []
    for index, group in enumerate(groups, 1):
        text = " ".join(part["text"] for part in group)
        text = re.sub(r"\\s+([,.!?;:])", r"\\1", text)
        entries.append(
            f"{index}\\n{srt_time(group[0]['start'])} --> "
            f"{srt_time(group[-1]['end'])}\\n{text}\\n"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\\n".join(entries) + "\\n", encoding="utf-8")
    return len(entries)
