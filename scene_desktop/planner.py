"""Script-to-scene director and media matching, fully local and explainable.

This is a deterministic offline scene planner. It does not pretend that it runs a
generative AI model; model-backed optional planning can be added behind this API.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import math
import re
from uuid import uuid4

from .timeline import StudioProject
from .library import MediaLibrary

_STOPWORDS = set("""the a an of is are and or it its they them for in on to with from by that this
as at he she him her about what who which how when why while so then but were was his
have has had been will would can could should after before their they into not just
mein hai aur ke ki ka ko se per yeh woh k is ko ek sy all then""".split())


def keywords(sentence: str, limit: int = 8) -> list[str]:
    """Find meaningful tokens for local catalog search; no external search calls."""
    words = re.findall(r"[\w]+", sentence.casefold())
    seen = set()
    result = []
    for word in words:
        if len(word) < 3 or word in _STOPWORDS or word.isdigit() or word in seen:
            continue
        seen.add(word)
        result.append(word)
    return result[:limit]


def split_script(script: str) -> list[str]:
    normalized = script.replace("\r", "\n").strip()
    if not normalized:
        return []
    paragraphs = [x.strip() for x in re.split(r"\n+", normalized) if x.strip()]
    sentences = []
    for line in paragraphs:
        sentences.extend(x.strip() for x in re.split(r"(?<=[.!?])\s+", line) if x.strip())
    return sentences


@dataclass
class Scene:
    text: str
    start_ms: int
    duration_ms: int
    keywords: list[str]
    id: str = field(default_factory=lambda: uuid4().hex)
    media_id: str = ""
    media_path: str = ""
    media_kind: str = ""
    approved: bool = False
    locked: bool = False
    match_reason: str = ""

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


def create_scene_plan(script: str, narration_duration_ms: int = 0,
                      min_duration_ms: int = 1800, max_duration_ms: int = 8000) -> list[Scene]:
    lines = split_script(script)
    if not lines:
        return []
    # Without speech timestamps, allocate a weighted estimate, not claimed as
    # word-accurate transcription. Durations are owner-editable on the timeline.
    weights = [max(1, len(x.split())) for x in lines]
    total = max(narration_duration_ms, len(lines)*min_duration_ms) if narration_duration_ms else sum(
        min(max_duration_ms, max(min_duration_ms, round(w/2.2*1000))) for w in weights
    )
    duration_weights = [max(min_duration_ms, min(max_duration_ms, round(total*w/sum(weights)))) for w in weights]
    # Last scene absorbs the fitting remainder when feasible.
    if narration_duration_ms and len(lines)>0:
        residual = total-sum(duration_weights)
        duration_weights[-1] = max(min_duration_ms, duration_weights[-1]+residual)
    cursor = 0
    scenes = []
    for text, dur in zip(lines, duration_weights):
        scenes.append(Scene(text=text, start_ms=cursor, duration_ms=dur, keywords=keywords(text)))
        cursor += dur
    return scenes


def match_media(scenes: list[Scene], library: MediaLibrary, mode: str = "local_first",
                allow_reuse: bool = False) -> list[Scene]:
    """Approved assets first; candidate assets never silently assumed approved."""
    if mode not in {"local_first", "video_only", "image_only", "alternate", "local_only"}:
        raise ValueError("Unknown media selection policy")
    media = library.list(status="approved")
    used = set()
    for idx, scene in enumerate(scenes):
        if scene.locked:
            continue
        options = []
        desired = "video" if idx%2==0 else "image"
        for item in media:
            if item["missing"] or (not allow_reuse and item["id"] in used):
                continue
            if mode == "video_only" and item["kind"] != "video":
                continue
            if mode == "image_only" and item["kind"] != "image":
                continue
            haystack = " ".join([item["name"]] + item["tags"]).casefold()
            word_matches = [k for k in scene.keywords if k in haystack]
            score = 10*len(word_matches)
            if mode == "alternate" and item["kind"] == desired:
                score += 3
            if item["kind"] == "video":
                score += 1
            options.append((score, item["name"].casefold(), item, word_matches))
        if not options:
            scene.media_id = scene.media_path = scene.media_kind = ""
            scene.approved = False
            scene.match_reason = "No eligible approved local asset; no external fallback was used"
            continue
        options.sort(key=lambda row: (-row[0], row[1]))
        score, _, chosen, tokens = options[0]
        scene.media_id, scene.media_path, scene.media_kind = chosen["id"], chosen["path"], chosen["kind"]
        scene.approved = True
        scene.match_reason = "matched: " + ",".join(tokens) if tokens else "approved local media; weak keyword match"
        used.add(chosen["id"])
    return scenes


def append_scenes(project: StudioProject, scenes: list[Scene], track_id: str = "v1") -> int:
    """Insert approved visuals into the timeline, preserving existing edits."""
    count = 0
    for scene in scenes:
        if not scene.approved or not scene.media_path:
            continue
        entry = project.add(scene.media_path, scene.media_kind, track_id, scene.duration_ms,
                            start_ms=scene.start_ms)
        count += 1
    project.scenes = [asdict(x) for x in scenes]
    return count
