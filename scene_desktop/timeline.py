"""Multitrack non-destructive timeline and revision-safe project persistence.

Time units are integer milliseconds. The timeline model never touches source files.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from pathlib import Path
import copy
import json
import os
import tempfile
import uuid

VERSION = 2
VISUAL_TRACKS = {"video", "overlay", "image"}
AUDIO_TRACKS = {"narration", "music", "sfx", "audio"}
KINDS = {"video", "image", "audio", "text"}
EFFECTS = {"zoom", "mirror", "brightness", "contrast", "saturation", "grain", "opacity", "rotate", "blur", "speed"}
TRANSITIONS = {"cut", "fade", "dissolve"}
MIN_DURATION_MS = 100


def fresh_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Track:
    id: str
    name: str
    kind: str
    locked: bool = False
    muted: bool = False
    visible: bool = True

    def validate(self) -> None:
        if not self.id or self.kind not in VISUAL_TRACKS | AUDIO_TRACKS | {"captions"}:
            raise ValueError("Invalid track")


@dataclass
class Item:
    asset: str
    kind: str
    track_id: str
    start_ms: int
    in_ms: int
    out_ms: int
    id: str = field(default_factory=fresh_id)
    effects: dict = field(default_factory=dict)
    transition_in: str = "cut"
    transition_ms: int = 0
    volume: float = 1.0
    fade_in_ms: int = 0
    fade_out_ms: int = 0
    text: str = ""
    caption_style: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        return self.out_ms - self.in_ms

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms

    def validate(self) -> None:
        if self.kind not in KINDS or not self.track_id or not self.id:
            raise ValueError("Invalid timeline item")
        if self.start_ms < 0 or self.in_ms < 0 or self.duration_ms < MIN_DURATION_MS:
            raise ValueError("Timeline positions/duration invalid")
        if self.transition_in not in TRANSITIONS or self.transition_ms < 0 or self.transition_ms > self.duration_ms:
            raise ValueError("Invalid transition")
        if not 0 <= self.volume <= 4 or self.fade_in_ms < 0 or self.fade_out_ms < 0:
            raise ValueError("Invalid audio settings")
        if self.kind != "text" and not self.asset:
            raise ValueError("Item requires a media source")
        if not isinstance(self.effects, dict) or set(self.effects).difference(EFFECTS):
            raise ValueError("Unsupported effect")
        if self.fade_in_ms + self.fade_out_ms > self.duration_ms * 2:
            raise ValueError("Fade exceeds item duration")


@dataclass
class StudioProject:
    title: str = "Untitled"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    tracks: list[Track] = field(default_factory=lambda: [
        Track("v1", "Main Video", "video"),
        Track("v2", "Video Overlay", "overlay"),
        Track("captions", "Captions", "captions"),
        Track("voice", "Narration", "narration"),
        Track("music", "Background Music", "music"),
        Track("sfx", "Sound Effects", "sfx"),
    ])
    items: list[Item] = field(default_factory=list)
    scenes: list[dict] = field(default_factory=list)
    version: int = VERSION
    revision: int = 0
    media_db: str = ""

    @property
    def duration_ms(self) -> int:
        return max((i.end_ms for i in self.items), default=0)

    def validate(self) -> None:
        if self.version != VERSION:
            raise ValueError("Unsupported project schema")
        if not self.title or self.width % 2 or self.height % 2 or not 240 <= self.width <= 7680 or not 240 <= self.height <= 7680:
            raise ValueError("Invalid project dimensions or name")
        if self.fps not in {24, 25, 30, 50, 60}:
            raise ValueError("Unsupported FPS")
        ids = set()
        for track in self.tracks:
            track.validate()
            if track.id in ids:
                raise ValueError("Duplicate track")
            ids.add(track.id)
        item_ids = set()
        for item in self.items:
            item.validate()
            if item.id in item_ids or item.track_id not in ids:
                raise ValueError("Duplicate item or unknown track")
            item_ids.add(item.id)
            tr = self.track(item.track_id)
            if item.kind in {"video", "image"} and tr.kind not in VISUAL_TRACKS:
                raise ValueError("Visual item on nonvisual track")
            if item.kind == "audio" and tr.kind not in AUDIO_TRACKS:
                raise ValueError("Audio item on nonaudio track")
            if item.kind == "text" and tr.kind != "captions":
                raise ValueError("Caption on noncaption track")

    def track(self, track_id: str) -> Track:
        return next(t for t in self.tracks if t.id == track_id)

    def item(self, item_id: str) -> Item:
        return next(i for i in self.items if i.id == item_id)

    def add(self, asset: str, kind: str, track_id: str, duration_ms: int,
            start_ms: int | None = None, text: str = "") -> Item:
        tr = self.track(track_id)
        if tr.locked:
            raise ValueError("Track is locked")
        if start_ms is None:
            start_ms = max((i.end_ms for i in self.items if i.track_id == track_id), default=0)
        entry = Item(str(asset), kind, track_id, int(start_ms), 0, int(duration_ms), text=text)
        entry.validate()
        self.items.append(entry)
        self.validate()
        self.revision += 1
        return entry

    def move(self, item_id: str, track_id: str, start_ms: int) -> None:
        item = self.item(item_id)
        source = self.track(item.track_id)
        dest = self.track(track_id)
        if source.locked or dest.locked:
            raise ValueError("Track is locked")
        old = (item.track_id, item.start_ms)
        item.track_id, item.start_ms = track_id, int(start_ms)
        try:
            self.validate()
        except ValueError:
            item.track_id, item.start_ms = old
            raise
        self.revision += 1

    def trim(self, item_id: str, in_ms: int, out_ms: int) -> None:
        item = self.item(item_id)
        if self.track(item.track_id).locked:
            raise ValueError("Track is locked")
        prev = item.in_ms, item.out_ms
        item.in_ms, item.out_ms = int(in_ms), int(out_ms)
        try:
            self.validate()
        except ValueError:
            item.in_ms, item.out_ms = prev
            raise
        self.revision += 1

    def split(self, item_id: str, timeline_ms: int) -> Item:
        left = self.item(item_id)
        if self.track(left.track_id).locked:
            raise ValueError("Track is locked")
        offset = timeline_ms - left.start_ms
        if offset < MIN_DURATION_MS or offset > left.duration_ms - MIN_DURATION_MS:
            raise ValueError("Split is too close to item boundary")
        right = copy.deepcopy(left)
        right.id = fresh_id()
        right.start_ms = timeline_ms
        right.in_ms = left.in_ms + offset
        right.transition_in, right.transition_ms = "cut", 0
        left.out_ms = right.in_ms
        self.items.append(right)
        self.validate()
        self.revision += 1
        return right

    def remove(self, item_id: str) -> None:
        item = self.item(item_id)
        if self.track(item.track_id).locked:
            raise ValueError("Track is locked")
        self.items.remove(item)
        self.revision += 1

    def replace_asset(self, item_id: str, new_path: str) -> None:
        item = self.item(item_id)
        if self.track(item.track_id).locked:
            raise ValueError("Track is locked")
        if not Path(new_path).is_file():
            raise FileNotFoundError(new_path)
        item.asset = str(Path(new_path).resolve())
        self.revision += 1

    def to_dict(self) -> dict:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StudioProject":
        if not isinstance(data, dict) or data.get("version") != VERSION:
            raise ValueError("Not a supported Scene Desktop project")
        allowed = {k for k in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in allowed}
        clean["tracks"] = [Track(**x) for x in clean.get("tracks", [])]
        clean["items"] = [Item(**x) for x in clean.get("items", [])]
        p = cls(**clean)
        p.validate()
        return p


def save(project: StudioProject, dest: str | Path) -> None:
    dest = Path(dest).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(project.to_dict(), ensure_ascii=False, indent=2) + "\n"
    temp = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=dest.parent,
                                         prefix=".scene-save-", suffix=".tmp", delete=False) as f:
            temp = f.name
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, dest)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def load(path: str | Path) -> StudioProject:
    with open(path, encoding="utf-8") as f:
        return StudioProject.from_dict(json.load(f))


class EditHistory:
    """Bounded snapshot-based undo/redo. No original media written or modified."""
    def __init__(self, project: StudioProject, max_steps: int = 50):
        self.project = project
        self.max_steps = max_steps
        self.back: list[dict] = []
        self.forward: list[dict] = []

    def checkpoint(self):
        self.back.append(copy.deepcopy(self.project.to_dict()))
        self.back = self.back[-self.max_steps:]
        self.forward.clear()

    def undo(self) -> StudioProject:
        if not self.back:
            return self.project
        self.forward.append(self.project.to_dict())
        self.project = StudioProject.from_dict(self.back.pop())
        return self.project

    def redo(self) -> StudioProject:
        if not self.forward:
            return self.project
        self.back.append(self.project.to_dict())
        self.project = StudioProject.from_dict(self.forward.pop())
        return self.project
