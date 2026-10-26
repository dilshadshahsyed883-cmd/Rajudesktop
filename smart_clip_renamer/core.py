"""Deterministic smart-shuffle planner and safe, byte-for-byte video copier."""
from __future__ import annotations

import hashlib
import os
import random
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Callable

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".ts"})
NUMBERED = re.compile(r"^(?P<stem>.+?)[\s._-]+(?P<number>\d+)$")
INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


class RenamerError(Exception):
    """Invalid selection, unsafe destination or failed processing."""


class Cancelled(RenamerError):
    """User stopped a copy; only this job's output is discarded."""


@dataclass(frozen=True)
class Clip:
    path: Path
    series: str | None
    number: int | None


@dataclass(frozen=True)
class PlanItem:
    original: Path
    renamed: str
    series: str | None
    original_number: int | None


@dataclass(frozen=True)
class RenamePlan:
    source: Path
    destination: Path
    keyword: str
    items: tuple[PlanItem, ...]
    remaining_adjacent_pairs: int


def clean_keyword(keyword: str) -> str:
    value = keyword.strip()
    if (not value or len(value) > 80 or INVALID_NAME.search(value)
            or value.endswith((".", " "))
            or value.split(".")[0].upper() in RESERVED):
        raise RenamerError("Enter a valid output keyword (1-80 characters, no Windows-forbidden symbols).")
    return value


def _series_and_number(path: Path) -> tuple[str | None, int | None]:
    match = NUMBERED.fullmatch(path.stem.strip())
    if not match:
        return None, None
    series = re.sub(r"[\s._-]+", " ", match.group("stem").strip()).casefold()
    return (series, int(match.group("number"))) if series else (None, None)


def scan_clips(folder: Path) -> list[Clip]:
    if not folder.is_dir():
        raise RenamerError("Choose an existing folder with video clips.")
    try:
        paths = [p for p in folder.iterdir()
                 if p.is_file() and not p.is_symlink() and p.suffix.casefold() in VIDEO_EXTENSIONS]
    except OSError as exc:
        raise RenamerError(f"Cannot read source folder: {exc}") from exc
    paths.sort(key=lambda p: (p.name.casefold(), p.name))
    if not paths:
        raise RenamerError("No supported video clips found in this folder (only top-level files are scanned).")
    result = []
    for path in paths:
        series, number = _series_and_number(path)
        result.append(Clip(path, series, number))
    return result


def _consecutive(a: Clip, b: Clip) -> bool:
    return (a.series is not None and a.series == b.series and
            a.number is not None and b.number is not None and
            abs(a.number - b.number) == 1)


def _score(order: list[Clip]) -> int:
    """Adjacency is overwhelmingly more important than cosmetic distance."""
    score = 0
    for i, clip in enumerate(order):
        for distance, weight in ((1, 10000), (2, 20), (3, 3)):
            if i >= distance and _consecutive(order[i - distance], clip):
                score += weight
    return score


def smart_order(clips: list[Clip]) -> list[Clip]:
    """Avoid original sequential siblings; deterministic, with exact search on small sets.

    Some input sets have no possible zero-conflict permutation (e.g. just 1, 2).
    Caller displays any remaining violations instead of claiming impossible success.
    """
    if len(clips) < 2:
        return list(clips)
    n = len(clips)

    if n <= 11:
        @lru_cache(maxsize=None)
        def search(used: int, last: int) -> tuple[int, ...] | None:
            if used == (1 << n) - 1:
                return ()
            remaining = [i for i in range(n) if not (used >> i) & 1]
            remaining.sort(key=lambda i: (
                -sum(_consecutive(clips[i], clips[j]) for j in remaining if j != i),
                clips[i].series or "", clips[i].number if clips[i].number is not None else -1,
                clips[i].path.name.casefold()))
            for i in remaining:
                if last >= 0 and _consecutive(clips[last], clips[i]):
                    continue
                suffix = search(used | (1 << i), i)
                if suffix is not None:
                    return (i,) + suffix
            return None

        exact = search(0, -1)
        if exact is not None:
            return [clips[i] for i in exact]

    seed = int.from_bytes(hashlib.sha256(
        "\n".join(str(c.path.name) for c in clips).encode("utf-8")).digest()[:8], "big")
    best: list[Clip] | None = None
    best_score = float("inf")
    rounds = 64 if n <= 75 else 18 if n <= 400 else 6
    for attempt in range(rounds):
        rng = random.Random(seed + attempt)
        remaining = list(clips)
        result: list[Clip] = []
        while remaining:
            sample = remaining if n <= 400 else rng.sample(remaining, min(100, len(remaining)))
            pick = min(sample, key=lambda c: (
                10000 if result and _consecutive(result[-1], c) else 0,
                20 if len(result) > 1 and _consecutive(result[-2], c) else 0,
                3 if len(result) > 2 and _consecutive(result[-3], c) else 0,
                -sum(_consecutive(c, r) for r in sample if r is not c) * 0.4,
                rng.random() * 6,
            ))
            result.append(pick)
            remaining.remove(pick)
        cost = _score(result)
        if cost < best_score:
            best, best_score = result, cost
        if cost == 0:
            break
    assert best is not None
    return best


def create_plan(source: Path, output_root: Path, keyword: str) -> RenamePlan:
    keyword = clean_keyword(keyword)
    source = source.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    clips = smart_order(scan_clips(source))
    tag = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    destination = output_root / f"{keyword}_{tag}"
    if destination.exists():
        raise RenamerError("Generated output folder already exists. Please preview again.")
    items = tuple(PlanItem(c.path, f"{keyword} {i}{c.path.suffix}", c.series, c.number)
                  for i, c in enumerate(clips, start=1))
    conflicts = sum(_consecutive(a, b) for a, b in zip(clips, clips[1:]))
    return RenamePlan(source, destination, keyword, items, conflicts)


def execute_plan(plan: RenamePlan, cancel=None,
                 progress: Callable[[int, int, str], None] | None = None) -> Path:
    """Copy originals into a unique new folder; never move, rename or delete input.

    If cancelled or a copy fails, only the newly-created job folder is cleaned.
    The originals and all pre-existing destination data remain untouched.
    """
    created = False
    try:
        plan.destination.parent.mkdir(parents=True, exist_ok=True)
        plan.destination.mkdir(exist_ok=False)
        created = True
        for index, item in enumerate(plan.items, start=1):
            if cancel is not None and cancel.is_set():
                raise Cancelled("Copy cancelled. Original files remain untouched.")
            target = plan.destination / item.renamed
            partial = plan.destination / (item.renamed + ".partial")
            with item.original.open("rb") as src, partial.open("xb") as dst:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled("Copy cancelled. Original files remain untouched.")
                    data = src.read(1024 * 1024)
                    if not data:
                        break
                    dst.write(data)
            os.replace(partial, target)
            if progress:
                progress(index, len(plan.items), item.renamed)
        return plan.destination
    except Exception:
        if created:
            shutil.rmtree(plan.destination)
        raise
