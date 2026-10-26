"""Safe, image-byte-preserving bulk renames. Standard library only."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import re
import shutil
import tempfile
import uuid

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}

@dataclass(frozen=True)
class Rename:
    source: Path
    target: Path
    size: int
    mtime_ns: int

def natural_key(path):
    return tuple((0, int(v)) if v.isdigit() else (1, v.casefold()) for v in re.split(r"(\d+)", path.name))

def scan_folder(folder, recursive=False):
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError("Select an existing folder.")
    files = folder.rglob("*") if recursive else folder.iterdir()
    return sorted((p for p in files if p.is_file() and not p.is_symlink() and p.suffix.lower() in EXTENSIONS),
                  key=lambda p: (natural_key(p), str(p).casefold()))

def valid_keyword(raw):
    word = raw.strip()
    if not word or word in (".", "..") or BAD.search(word) or word.endswith("."):
        raise ValueError("Enter a valid filename keyword, e.g. Alexa.")
    if len(word) > 100 or word.upper() in RESERVED:
        raise ValueError("Keyword is too long or reserved by Windows.")
    return word

def key(path):
    return str(path.absolute()).casefold()

def make_plan(files, keyword, start, output=None, in_place=False):
    keyword = valid_keyword(keyword)
    if type(start) is not int or start < 1:
        raise ValueError("Starting number must be a positive whole number.")
    if not files:
        raise ValueError("Select at least one image.")
    if not in_place and output is None:
        raise ValueError("Select an output folder.")
    output = Path(output).expanduser().resolve() if output is not None else None
    seen_sources, seen_targets, plan = set(), set(), []
    for number, file in enumerate(files, start=start):
        src = Path(file).expanduser().resolve()
        if not src.is_file() or src.is_symlink() or src.suffix.lower() not in EXTENSIONS:
            raise ValueError(f"Unsupported or missing image: {src}")
        if key(src) in seen_sources:
            raise ValueError(f"Image selected twice: {src.name}")
        seen_sources.add(key(src))
        target = (src.parent if in_place else output) / f"{keyword} {number}{src.suffix}"
        if len(target.name) > 240:
            raise ValueError("Resulting filename too long.")
        if key(target) in seen_targets:
            raise ValueError(f"Duplicate output name: {target.name}")
        seen_targets.add(key(target))
        stat = src.stat()
        plan.append(Rename(src, target, stat.st_size, stat.st_mtime_ns))
    check_plan(plan, in_place)
    return plan

def check_plan(plan, in_place):
    source_names = {key(x.source) for x in plan} if in_place else set()
    listing = {}
    for item in plan:
        if not item.source.is_file():
            raise FileNotFoundError(str(item.source))
        stat = item.source.stat()
        if stat.st_size != item.size or stat.st_mtime_ns != item.mtime_ns:
            raise RuntimeError(f"Image changed since preview: {item.source.name}")
        parent = item.target.parent
        if parent.is_file():
            raise ValueError(f"Output is a file: {parent}")
        if parent not in listing:
            listing[parent] = {x.name.casefold() for x in parent.iterdir()} if parent.is_dir() else set()
        if item.target.name.casefold() in listing[parent] and key(item.target) not in source_names:
            raise FileExistsError(f"Will not overwrite existing image: {item.target}")

def execute(plan, in_place=False, progress=None):
    check_plan(plan, in_place)
    if not in_place:
        created = []
        try:
            for number, item in enumerate(plan, 1):
                item.target.parent.mkdir(parents=True, exist_ok=True)
                with item.source.open("rb") as source, item.target.open("xb") as dest:
                    created.append(item.target)
                    shutil.copyfileobj(source, dest, 1024 * 1024)
                    dest.flush()
                    os.fsync(dest.fileno())
                shutil.copystat(item.source, item.target)
                if progress:
                    progress(number, len(plan))
            return len(created)
        except Exception:
            for dest in reversed(created):
                dest.unlink(missing_ok=True)
            raise
    staged, completed = [], []
    try:
        for item in plan:
            temp = item.source.parent / (".image-renamer-" + uuid.uuid4().hex + ".tmp")
            os.rename(item.source, temp)
            staged.append((item, temp))
        for number, (item, temp) in enumerate(staged, 1):
            if item.target.exists():
                raise FileExistsError(f"Target appeared during rename: {item.target}")
            os.rename(temp, item.target)
            completed.append((item, temp))
            if progress:
                progress(number, len(plan))
        return len(completed)
    except Exception:
        for item, temp in reversed(completed):
            if item.target.exists() and not temp.exists():
                os.rename(item.target, temp)
        for item, temp in reversed(staged):
            if temp.exists() and not item.source.exists():
                os.rename(temp, item.source)
        raise

def save_history(location, plan):
    location = Path(location)
    location.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"version": 1, "entries": [
        {"source": str(p.source), "target": str(p.target), "size": p.size, "mtime_ns": p.mtime_ns}
        for p in plan]}, indent=2)
    fd, temp = tempfile.mkstemp(dir=location.parent, prefix="image-renamer-history-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(body)
        os.replace(temp, location)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def undo_last(location, progress=None):
    location = Path(location)
    history = json.loads(location.read_text(encoding="utf-8"))
    if history.get("version") != 1 or not history.get("entries"):
        raise ValueError("No valid operation to undo.")
    plan = [Rename(Path(p["target"]), Path(p["source"]), p["size"], p["mtime_ns"])
            for p in history["entries"]]
    count = execute(plan, True, progress=progress)
    location.unlink(missing_ok=True)
    return count
