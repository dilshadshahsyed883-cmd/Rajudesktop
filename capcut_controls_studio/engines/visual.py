"""Extracted V2.1 Scale/Position/Blur engine (stdlib only).

Works on existing CapCut desktop draft JSON; does not rebuild/reorder timeline,
change media/audio/effects, or alter Z Builder. Test on duplicate projects first.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import uuid
from typing import Any

DRAFT_NAMES = ("draft_content.json", "draft_info.json")
BLURS = {"Off": 0.0, "Level 1 — Light": 0.0625, "Level 2 — Medium": 0.375,
         "Level 3 — Strong": 0.75, "Level 4 — Maximum": 1.0}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".heic"}


@dataclass(frozen=True)
class Options:
    canvas_blur: bool = True
    blur_strength: float = 0.375
    video_scale: bool = True
    video_scale_min: float = 115.0
    video_scale_max: float = 125.0
    video_position: bool = True
    video_y_min: float = -220.0
    video_y_max: float = -120.0
    video_x: float = 0.0
    image_scale: bool = True
    image_scale_min: float = 105.0
    image_scale_max: float = 110.0
    image_position: bool = True
    image_y_min: float = -50.0
    image_y_max: float = 0.0
    seed: int = 28
    invert_y: bool = False  # Experimental compatibility switch; no silent inversion

    def validate(self):
        if self.blur_strength not in set(BLURS.values()):
            raise ValueError("Choose a known native CapCut canvas blur level")
        for lo, hi, low, high, label in [
            (self.video_scale_min, self.video_scale_max, 25, 400, "Video scale"),
            (self.image_scale_min, self.image_scale_max, 25, 400, "Image scale"),
            (self.video_y_min, self.video_y_max, -2500, 2500, "Video Y"),
            (self.image_y_min, self.image_y_max, -2500, 2500, "Image Y")]:
            if not (low <= lo <= hi <= high):
                raise ValueError(f"{label} min/max invalid: {lo} to {hi}")
        if not -2500 <= self.video_x <= 2500:
            raise ValueError("Video X outside safe test range")


def default_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"


def _read_json(path: Path) -> dict:
    v = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(v, dict):
        raise ValueError(f"Invalid CapCut project structure: {path}")
    return v


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def capcut_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        p = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/NH"],
                           capture_output=True, text=True, timeout=7,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if p.returncode != 0:
            return True
        return bool(re.search(r"(^|\s)CapCut\.exe\s", p.stdout, re.I | re.M))
    except (OSError, subprocess.TimeoutExpired):
        return True  # fail closed


def _main_draft(project: Path) -> Path:
    for name in DRAFT_NAMES:
        f = project / name
        if f.is_file():
            return f
    raise FileNotFoundError("Select a CapCut project folder containing draft_content.json")


def _mirror(project: Path, name: str) -> Path | None:
    index = project / "Timelines" / "project.json"
    if not index.is_file():
        return None
    data = _read_json(index)
    entries = data.get("timelines") or []
    timeline_id = data.get("main_timeline_id") or (entries[0].get("id") if entries and isinstance(entries[0], dict) else None)
    if not isinstance(timeline_id, str) or not re.fullmatch(r"[\w-]+", timeline_id, re.ASCII):
        raise ValueError("Unsafe active timeline ID")
    f = project / "Timelines" / timeline_id / name
    if not f.is_file():
        raise ValueError("CapCut nested active timeline missing; refusing unsafe write")
    return f


def load_project(project: Path) -> tuple[dict, list[Path], list[str]]:
    project = project.resolve(strict=True)
    top = _main_draft(project)
    mirror = _mirror(project, top.name)
    paths = [top] + ([mirror] if mirror else [])
    warning = []
    source = _read_json(mirror or top)
    if mirror and _read_json(top) != source:
        warning.append("Top-level and active nested timeline differ; nested copy is authoritative and both will be synchronized")
    if not isinstance(source.get("tracks"), list) or not isinstance(source.get("materials"), dict):
        raise ValueError("Not a recognizable native CapCut timeline")
    return source, paths, warning


def list_projects(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out = []
    for child in root.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            try:
                f = _main_draft(child)
                out.append((f.stat().st_mtime_ns, child))
            except (OSError, FileNotFoundError):
                pass
    return [x for _, x in sorted(out, reverse=True)]


def _pixel_to_unit(v: float, full_canvas_size: float, invert: bool = False) -> float:
    """CapCut draft offsets are fractions of a half-canvas; UI pixel sign is experimental."""
    return round(((-1 if invert else 1) * 2 * v) / full_canvas_size, 7)


def _canvas_size(d: dict) -> tuple[int, int]:
    c = d.get("canvas_config") or {}
    w = c.get("width") or c.get("W")
    h = c.get("height") or c.get("H")
    if not isinstance(w, (int, float)) or not isinstance(h, (int, float)) or not (100 <= w <= 10000 and 100 <= h <= 10000):
        raise ValueError("Missing canvas width/height; cannot safely convert pixel positions")
    return int(w), int(h)


def _clip_type(material: dict) -> str | None:
    kind = str(material.get("type", "")).lower()
    if kind in ("photo", "image"):
        return "image"
    if kind == "video":
        return "video"
    path = str(material.get("path") or material.get("material_name") or "").lower()
    if Path(path).suffix in IMG_EXT:
        return "image"
    return None


def _rand_range(seed: int, clipid: str, control: str, lo: float, hi: float) -> float:
    # Stable per clip and control, independent from track position/selection order.
    key = hashlib.sha256(f"{seed}:{clipid}:{control}".encode()).hexdigest()
    return round(random.Random(int(key[:16], 16)).uniform(lo, hi), 2)


def _has_keyframes(seg: dict) -> bool:
    """Existing animated transforms are never silently flattened by this first test."""
    return bool(seg.get("common_keyframes") or seg.get("keyframe_refs"))


def _canvas_template(d: dict) -> dict:
    mats = d["materials"].get("canvases") or []
    for obj in mats:
        if isinstance(obj, dict) and obj.get("type") in ("canvas_color", "canvas_blur", "canvas_image"):
            template = copy.deepcopy(obj)
            template["id"] = str(uuid.uuid4()).upper()
            return template
    return {"id": str(uuid.uuid4()).upper(), "type": "canvas_color", "color": "", "blur": 0,
            "image": "", "album_image": "", "image_id": "", "image_name": "",
            "source_platform": 0, "team_id": ""}


def create_preview(original: dict, opts: Options) -> tuple[dict, list[dict], dict]:
    opts.validate()
    draft = copy.deepcopy(original)
    width, height = _canvas_size(draft)
    mats = draft["materials"]
    source_mats = {m["id"]: m for m in mats.get("videos", []) if isinstance(m, dict) and isinstance(m.get("id"), str)}
    canvases = mats.setdefault("canvases", [])
    if not isinstance(canvases, list):
        raise ValueError("Invalid materials.canvases structure")
    canvas_by_id = {m["id"]: m for m in canvases if isinstance(m, dict) and m.get("id")}
    output = []
    counts = {"videos": 0, "images": 0, "updated_visuals": 0, "blurred": 0,
              "transforms": 0, "animated_skipped": 0, "ineligible": 0}
    for ti, track in enumerate(draft["tracks"]):
        if not isinstance(track, dict) or track.get("type") != "video":
            continue
        for si, seg in enumerate(track.get("segments", [])):
            if not isinstance(seg, dict):
                continue
            mat = source_mats.get(seg.get("material_id"))
            kind = _clip_type(mat) if mat else None
            if kind is None or not isinstance(seg.get("clip"), dict):
                counts["ineligible"] += 1
                continue
            counts["videos" if kind == "video" else "images"] += 1
            clip = seg["clip"]
            animated = _has_keyframes(seg)
            flags = []
            details = {"track": ti + 1, "clip": si + 1, "kind": kind,
                       "name": Path(str(mat.get("material_name") or mat.get("path") or seg.get("id"))).name,
                       "scale": "unchanged", "x": "unchanged", "y": "unchanged", "blur": "unchanged", "status": ""}
            if opts.canvas_blur:
                refs = seg.get("extra_material_refs")
                if refs is None:
                    refs = []
                    seg["extra_material_refs"] = refs
                if not isinstance(refs, list):
                    raise ValueError("Non-list extra_material_refs in visual clip")
                found = [r for r in refs if r in canvas_by_id]
                if len(found) > 1:
                    raise ValueError("Multiple canvas material references found; unsafe to choose one")
                if found:
                    item = canvas_by_id[found[0]]
                    # Other clip refs to same canvas intentionally share background setting.
                else:
                    item = _canvas_template(draft)
                    canvases.append(item)
                    canvas_by_id[item["id"]] = item
                    refs.append(item["id"])
                item["type"] = "canvas_blur" if opts.blur_strength else "canvas_color"
                item["blur"] = opts.blur_strength
                if opts.blur_strength:
                    item["color"] = ""
                    item["image"] = ""
                details["blur"] = str(opts.blur_strength)
                counts["blurred"] += 1
                flags.append("blur")
            do_scale = opts.video_scale if kind == "video" else opts.image_scale
            do_pos = opts.video_position if kind == "video" else opts.image_position
            if (do_scale or do_pos) and animated:
                counts["animated_skipped"] += 1
                flags.append("animated: transforms skipped")
            elif do_scale or do_pos:
                if do_scale:
                    lo, hi = ((opts.video_scale_min, opts.video_scale_max) if kind == "video"
                              else (opts.image_scale_min, opts.image_scale_max))
                    val = _rand_range(opts.seed, str(seg.get("id", f"{ti}:{si}")), "scale", lo, hi) / 100
                    if not isinstance(clip.get("scale"), dict):
                        raise ValueError("Missing native clip.scale object")
                    clip["scale"]["x"] = clip["scale"]["y"] = round(val, 6)
                    if isinstance(seg.get("uniform_scale"), dict):
                        seg["uniform_scale"]["value"] = round(val, 6)
                    details["scale"] = f"{val*100:.2f}%"
                    flags.append("scale")
                if do_pos:
                    if not isinstance(clip.get("transform"), dict):
                        raise ValueError("Missing native clip.transform object")
                    lo, hi = ((opts.video_y_min, opts.video_y_max) if kind == "video"
                              else (opts.image_y_min, opts.image_y_max))
                    yy = _rand_range(opts.seed, str(seg.get("id", f"{ti}:{si}")), "position", lo, hi)
                    clip["transform"]["y"] = _pixel_to_unit(yy, height, opts.invert_y)
                    if kind == "video":
                        clip["transform"]["x"] = _pixel_to_unit(opts.video_x, width)
                        details["x"] = f"{opts.video_x:.0f}px"
                    details["y"] = f"{yy:.2f}px"
                    flags.append("position")
                counts["transforms"] += 1
            if flags:
                counts["updated_visuals"] += 1
            details["status"] = ", ".join(flags) or "No change"
            output.append(details)
    return draft, output, counts


def _atomic(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=".visual_controls_", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def project_fingerprint(paths: list[Path]) -> dict[str, str]:
    return {str(p.resolve()): _sha(p.read_bytes()) for p in paths}


def save_project(project: Path, opts: Options, expected: dict[str, str] | None = None) -> dict:
    if capcut_running():
        raise RuntimeError("Close CapCut completely before Apply")
    project = project.resolve(strict=True)
    lock = project / ".visual_controls_test.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(f"pid={os.getpid()}\n")
        source, drafts, warnings = load_project(project)
        if expected is not None and project_fingerprint(drafts) != expected:
            raise RuntimeError("Project changed since Preview; preview again before Apply")
        output, rows, counts = create_preview(source, opts)
        if output == source:
            return {"saved": False, "backup": "", "counts": counts, "warnings": warnings}
        changes: dict[Path, bytes] = {
            p: json.dumps(output, ensure_ascii=False, separators=(",", ":")).encode("utf8") for p in drafts
        }
        # Keep project modification time consistent for CapCut's list; preserve all other metadata.
        meta_path = project / "draft_meta_info.json"
        now_us = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        if meta_path.is_file():
            meta = _read_json(meta_path)
            meta["tm_draft_modified"] = now_us
            changes[meta_path] = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode("utf8")
        root_meta = project.parent / "root_meta_info.json"
        if root_meta.is_file():
            index = _read_json(root_meta)
            def normalized_path(raw: str) -> str:
                value = str(raw or "").replace("\\", "/").rstrip("/").casefold()
                # Some Windows tools return the extended-length path prefix.
                return value[4:] if value.startswith("//?/") else value

            normalized = normalized_path(str(project))
            entries = index.get("all_draft_store") or []
            if isinstance(entries, list):
                candidates = [ent for ent in entries if isinstance(ent, dict)]
                matches = [ent for ent in candidates if normalized_path(ent.get("draft_fold_path")) == normalized]
                if not matches:
                    # Unique project-folder-name fallback; never update a peer.
                    matches = [ent for ent in candidates if
                               normalized_path(ent.get("draft_fold_path")).split("/")[-1] == project.name.casefold()
                               or str(ent.get("draft_name") or "").casefold() == project.name.casefold()]
                if len(matches) == 1:
                    matches[0]["tm_draft_modified"] = now_us
                    changes[root_meta] = json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf8")
        originals = {p: p.read_bytes() for p in changes}
        hashes = {p: _sha(b) for p, b in originals.items()}
        backup = project / ".visual_controls_backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        backup.mkdir(parents=True, exist_ok=False)
        manifest = []
        for i, (path, raw) in enumerate(originals.items()):
            name = f"{i:02d}_{path.name}"
            (backup / name).write_bytes(raw)
            manifest.append({"original": str(path), "backup": name, "sha256": hashes[path]})
        (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf8")
        if capcut_running():
            raise RuntimeError("CapCut opened after preview; aborting")
        for path, expected_hash in hashes.items():
            if _sha(path.read_bytes()) != expected_hash:
                raise RuntimeError(f"Draft changed during backup: {path.name}")
        written = []
        try:
            for path, blob in changes.items():
                _atomic(path, blob)
                written.append(path)
            actual, _, _ = load_project(project)
            if actual != output:
                raise RuntimeError("Post-save verification mismatch; rolling back")
        except BaseException:
            for path in reversed(written):
                _atomic(path, originals[path])
            raise
        return {"saved": True, "backup": str(backup), "counts": counts, "warnings": warnings}
    finally:
        lock.unlink(missing_ok=True)

