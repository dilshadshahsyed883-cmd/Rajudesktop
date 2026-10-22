"""Import Whisper-compatible word timestamps as editable synchronized karaoke captions.

Word timestamp JSON may be flat [{'word','start','end'}], {'words':[]}
or Whisper {'segments':[{'words':[],...}, ...]}. Times are seconds.
No network requests or model calls are performed by this importer.
"""
from __future__ import annotations
from pathlib import Path
import json
import math

from .timeline import StudioProject

MAX_WORDS = 20000


def _parse_words(payload: object) -> list[dict]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("words"), list):
        rows = payload["words"]
    elif isinstance(payload, dict) and isinstance(payload.get("segments"), list):
        rows = []
        for segment in payload["segments"]:
            if not isinstance(segment, dict) or not isinstance(segment.get("words"), list):
                raise ValueError("Whisper JSON requires word timestamps in each segment")
            rows.extend(segment["words"])
    else:
        raise ValueError("Expected Whisper word-level JSON, not transcript-only text")
    if not 1 <= len(rows) <= MAX_WORDS:
        raise ValueError("Expected 1–20,000 recognized words")
    result = []
    last_start = -1
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid word")
        word = str(row.get("word") or row.get("text") or "").strip()
        if not word or len(word) > 100:
            raise ValueError("Missing or oversized word")
        try:
            start, end = float(row["start"]),float(row["end"])
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError("Each word needs numeric start/end seconds") from exc
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ValueError("Invalid word time range")
        if start < last_start:
            raise ValueError("Words must be sorted by speech time")
        if end-start < 0.01 or end-start > 20:
            raise ValueError("Invalid word duration")
        start_ms, end_ms = round(start*1000),round(end*1000)
        result.append({"word":word,"start_ms":start_ms,"end_ms":end_ms})
        last_start = start
    return result


def grouped_words(words: list[dict], max_words: int = 7,
                  max_span_ms: int = 3800, gap_ms: int = 650) -> list[list[dict]]:
    groups, current = [], []
    for word in words:
        if current and (len(current) >= max_words or
                        word["start_ms"]-current[0]["start_ms"] > max_span_ms or
                        word["start_ms"]-current[-1]["end_ms"] > gap_ms):
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    return groups


def import_word_json(project: StudioProject, path: str | Path) -> int:
    source = Path(path)
    if source.stat().st_size > 3*1024*1024:
        raise ValueError("Word transcript JSON exceeds 3 MB")
    words = _parse_words(json.loads(source.read_text(encoding="utf-8-sig")))
    groups = grouped_words(words)
    if not project.track("captions").locked is False:
        raise ValueError("Captions track is locked")
    # Validate the payload completely before mutating a project.
    for group in groups:
        start, end = group[0]["start_ms"], max(x["end_ms"] for x in group)
        if end-start < 100:
            raise ValueError("Caption phrase is shorter than 100ms")
    for group in groups:
        start, end = group[0]["start_ms"], max(x["end_ms"] for x in group)
        item = project.add("","text","captions",end-start,
                           start_ms=start,text=" ".join(x["word"] for x in group))
        item.caption_style = {
            "font_size":38,
            "karaoke_words":[{"word":x["word"],"start_ms":x["start_ms"]-start,
                              "end_ms":x["end_ms"]-start} for x in group],
        }
    project.validate()
    return len(groups)


def ass_seconds(ms: int) -> str:
    cs=max(0,round(ms/10))
    hours,remainder=divmod(cs,360000)
    minutes,remainder=divmod(remainder,6000)
    seconds,centis=divmod(remainder,100)
    return f"{hours}:{minutes:02}:{seconds:02}.{centis:02}"


def _ass_text(text: str) -> str:
    # Data is literal subtitle text; escape any ASS override syntax.
    return (text.replace("\\", "＼").replace("{", "｛").replace("}", "｝")
            .replace("\r", " ").replace("\n", " "))


def ass_for_section(items, start_ms: int, end_ms: int, width: int, height: int) -> str:
    header=(
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,38,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,3,1,2,20,20,35,1\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events=[]
    for item in items:
        if not isinstance(item.caption_style.get("karaoke_words"),list):
            continue
        words = item.caption_style["karaoke_words"]
        elapsed = max(0,start_ms-item.start_ms)
        # ASS karaoke \k is a centisecond count; already-spoken words use k0.
        parts=[]
        for index,word in enumerate(words):
            wstart=int(word["start_ms"])
            next_start=(int(words[index+1]["start_ms"]) if index+1<len(words)
                        else int(word["end_ms"]))
            length=max(0,next_start-max(elapsed,wstart))
            parts.append(r"{\k"+str(round(length/10))+"}"+_ass_text(str(word["word"]))+" ")
        ev_start=max(item.start_ms,start_ms)-start_ms
        ev_end=min(item.end_ms,end_ms)-start_ms
        if ev_end > ev_start and parts:
            events.append("Dialogue: 0,"+ass_seconds(ev_start)+","+ass_seconds(ev_end)+
                          ",Default,,0,0,0,,"+"".join(parts).rstrip())
    return header+"\n".join(events)+"\n"
