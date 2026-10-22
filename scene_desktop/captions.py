"""Import and export manually editable subtitle/caption tracks in SRT format."""
from __future__ import annotations
from pathlib import Path
import re

from .timeline import StudioProject


_TIME = re.compile(r"(\d{2,}):(\d{2}):(\d{2})[,\.](\d{3})")


def to_ms(token: str) -> int:
    match = _TIME.fullmatch(token.strip())
    if not match:
        raise ValueError(f"Invalid subtitle time: {token}")
    h, m, s, ms = map(int, match.groups())
    if m >= 60 or s >= 60:
        raise ValueError("Subtitle time is out of range")
    return ((h*60+m)*60+s)*1000 + ms


def from_ms(value: int) -> str:
    value = max(0, value)
    h, remain = divmod(value, 3600000)
    m, remain = divmod(remain, 60000)
    s, ms = divmod(remain, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def parse_srt(text: str) -> list[tuple[int, int, str]]:
    result = []
    source = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    for block in re.split(r"\n\s*\n", source):
        lines = [x.rstrip() for x in block.split("\n") if x.strip()]
        if len(lines) < 2:
            continue
        position = 1 if lines[0].strip().isdigit() else 0
        if position >= len(lines):
            continue
        match = re.fullmatch(r"\s*(\S+)\s*-->\s*(\S+)(?:\s+.*)?", lines[position])
        if not match:
            continue
        start, end = to_ms(match.group(1)), to_ms(match.group(2))
        body = "\n".join(lines[position+1:]).strip()
        if body and end-start >= 100:
            result.append((start,end,body))
    return result


def import_srt(project: StudioProject, path: str | Path, track_id: str = "captions") -> int:
    text = Path(path).read_text(encoding="utf-8-sig")
    segments = parse_srt(text)
    if not segments:
        raise ValueError("No valid captions found")
    for start,end,caption in segments:
        project.add("", "text", track_id, end-start, start_ms=start, text=caption)
    return len(segments)


def export_srt(project: StudioProject, dest: str | Path) -> Path:
    captions = sorted((i for i in project.items if i.kind=="text"), key=lambda i:(i.start_ms,i.id))
    output = Path(dest)
    if output.exists():
        raise FileExistsError(str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(
        f"{idx}\n{from_ms(i.start_ms)} --> {from_ms(i.end_ms)}\n{i.text}\n"
        for idx,i in enumerate(captions,start=1)
    ),encoding="utf-8")
    return output
