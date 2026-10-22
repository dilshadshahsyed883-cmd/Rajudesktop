"""Pure-Python project and timeline model; source media is always non-destructive."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PROJECT_VERSION = 1
MIN_CLIP_MS = 100


def classify(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in VIDEO_EXTS:
        return "video"
    if suffix in IMAGE_EXTS:
        return "image"
    raise ValueError(f"Unsupported image/video format: {suffix or 'missing extension'}")


@dataclass
class Clip:
    path: str
    kind: str
    source_duration_ms: int
    in_ms: int
    out_ms: int
    id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def duration_ms(self) -> int:
        return self.out_ms - self.in_ms

    def validate(self) -> None:
        if self.kind != classify(self.path):
            raise ValueError("Clip type and file extension do not match")
        if not self.id or self.source_duration_ms < MIN_CLIP_MS:
            raise ValueError("Invalid clip ID or duration")
        if self.in_ms < 0 or self.out_ms > self.source_duration_ms:
            raise ValueError("Trim outside source duration")
        if self.duration_ms < MIN_CLIP_MS:
            raise ValueError("Clip duration must be at least 100 milliseconds")

    def trim(self, start_ms: int, end_ms: int) -> None:
        previous = (self.in_ms, self.out_ms)
        self.in_ms, self.out_ms = int(start_ms), int(end_ms)
        try:
            self.validate()
        except ValueError:
            self.in_ms, self.out_ms = previous
            raise


@dataclass
class Project:
    name: str = "Untitled Project"
    clips: list[Clip] = field(default_factory=list)
    narration: str = ""
    width: int = 1920
    height: int = 1080
    fps: int = 30
    version: int = PROJECT_VERSION

    @property
    def duration_ms(self) -> int:
        return sum(c.duration_ms for c in self.clips)

    def validate(self) -> None:
        if self.version != PROJECT_VERSION:
            raise ValueError(f"Unsupported project version: {self.version}")
        if (self.width, self.height) not in {(1920, 1080), (1080, 1920), (1280, 720), (720, 1280)}:
            raise ValueError("Output must be 1080p or 720p, landscape or portrait")
        if self.fps not in {24, 25, 30, 60}:
            raise ValueError("Unsupported output FPS")
        seen = set()
        for c in self.clips:
            c.validate()
            if c.id in seen:
                raise ValueError("Duplicate timeline clip ID")
            seen.add(c.id)

    def add_media(self, path: str, duration_ms: int) -> Clip:
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(str(p))
        kind = classify(str(p))
        duration_ms = int(duration_ms)
        clip = Clip(str(p), kind, duration_ms, 0, duration_ms)
        clip.validate()
        self.clips.append(clip)
        return clip

    def clip_by_id(self, clip_id: str) -> Clip:
        return next(c for c in self.clips if c.id == clip_id)

    def reorder(self, clip_ids: list[str]) -> None:
        if len(clip_ids) != len(self.clips) or set(clip_ids) != {c.id for c in self.clips}:
            raise ValueError("Reorder must contain each existing clip exactly once")
        lookup = {c.id: c for c in self.clips}
        self.clips = [lookup[i] for i in clip_ids]

    def split(self, index: int, source_at_ms: int) -> tuple[Clip, Clip]:
        clip = self.clips[index]
        if not clip.in_ms + MIN_CLIP_MS <= source_at_ms <= clip.out_ms - MIN_CLIP_MS:
            raise ValueError("Split point is too close to the clip boundary")
        right = Clip(clip.path, clip.kind, clip.source_duration_ms, int(source_at_ms), clip.out_ms)
        clip.trim(clip.in_ms, source_at_ms)
        self.clips.insert(index + 1, right)
        return clip, right

    def locate(self, global_ms: int) -> tuple[int, int]:
        if not self.clips:
            raise ValueError("The timeline is empty")
        t = max(0, min(int(global_ms), max(self.duration_ms - 1, 0)))
        for i, c in enumerate(self.clips):
            if t < c.duration_ms:
                return i, t
            t -= c.duration_ms
        return len(self.clips) - 1, self.clips[-1].duration_ms - 1

    def start_of(self, index: int) -> int:
        return sum(c.duration_ms for c in self.clips[:index])

    def to_dict(self) -> dict:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        if not isinstance(data, dict) or data.get("version") != PROJECT_VERSION:
            raise ValueError("Unknown or malformed project version")
        if not isinstance(data.get("clips"), list):
            raise ValueError("Project is missing clips")
        obj = cls(
            name=str(data.get("name", "Untitled Project")),
            clips=[Clip(**c) for c in data["clips"]],
            narration=str(data.get("narration", "")),
            width=int(data.get("width", 1920)),
            height=int(data.get("height", 1080)),
            fps=int(data.get("fps", 30)),
            version=data["version"],
        )
        obj.validate()
        return obj


def save_project(project: Project, path: str | Path) -> None:
    """Atomically save editable manifest; never write over original media."""
    dest = Path(path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(project.to_dict(), ensure_ascii=False, indent=2) + "\n"
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=dest.parent,
                                         prefix=".sds-save-", suffix=".tmp", delete=False) as f:
            name = f.name
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, dest)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def load_project(path: str | Path) -> Project:
    with open(path, "r", encoding="utf-8") as f:
        return Project.from_dict(json.load(f))
