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
    """Write word-timed cues with measured audio duration offsets."""
    entries: list[str] = []
    shift_ms = 0
    for words, duration_ms in chunks:
        group: list[dict] = []
        for item in words:
            try:
                word = str(item["text"]).strip()
                start = max(0, int(item["offset"]) // 10000)
                duration = max(1, int(item["duration"]) // 10000)
            except (KeyError, ValueError, TypeError):
                continue
            if not word:
                continue
            group.append({"text": word, "start": start, "end": start + duration})
            if len(group) >= 8 or word[-1] in ".!?":
                first, last = group[0], group[-1]
                entries.append(
                    f"{len(entries)+1}\n{srt_time(shift_ms+first['start'])} --> "
                    f"{srt_time(shift_ms+last['end'])}\n"
                    + " ".join(x["text"] for x in group) + "\n"
                )
                group = []
        if group:
            first, last = group[0], group[-1]
            entries.append(
                f"{len(entries)+1}\n{srt_time(shift_ms+first['start'])} --> "
                f"{srt_time(shift_ms+last['end'])}\n"
                + " ".join(x["text"] for x in group) + "\n"
            )
        shift_ms += duration_ms
    if entries:
        output.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return len(entries)
