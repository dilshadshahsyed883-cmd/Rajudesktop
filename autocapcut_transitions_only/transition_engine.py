"""Independent CapCut native-transition editor. No media/timeline rebuilds.

All writes are to the selected CapCut project JSON and metadata, with recoverable
per-file backups. No third-party AutoCapCut source is included.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DRAFT_NAMES = ("draft_content.json", "draft_info.json")


def default_projects_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"


def read_json(path: Path) -> dict:
    val = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(val, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return val


def find_draft(project: Path) -> Path:
    for name in DRAFT_NAMES:
        p = project / name
        if p.is_file():
            return p
    raise FileNotFoundError(f"No CapCut draft JSON inside {project}")


def active_mirror(project: Path, draft_name: str) -> Path | None:
    p = project / "Timelines" / "project.json"
    if not p.exists():
        return None
    info = read_json(p)
    tids = info.get("timelines") or []
    main_id = info.get("main_timeline_id") or ((tids[0] or {}).get("id") if tids else None)
    if not isinstance(main_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", main_id):
        raise ValueError("Unsafe or missing main_timeline_id")
    mirror = project / "Timelines" / main_id / draft_name
    if not mirror.is_file():
        raise ValueError(f"Active CapCut timeline mirror missing: {mirror}")
    return mirror


def list_projects(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out = []
    for child in root.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            try:
                f = find_draft(child)
                out.append((f.stat().st_mtime_ns, child))
            except (OSError, FileNotFoundError):
                pass
    return [p for _, p in sorted(out, reverse=True)]


def capcut_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/NH"],
                           capture_output=True, text=True, timeout=6, check=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return bool(re.search(r"(^|\s)CapCut\.exe\s", r.stdout, re.IGNORECASE | re.MULTILINE))
    except (OSError, subprocess.TimeoutExpired):
        # Fail closed if the operating system cannot prove CapCut is closed.
        return True


def load_project(project: Path) -> tuple[dict, Path, list[Path], list[str]]:
    main = find_draft(project)
    mirror = active_mirror(project, main.name)
    warnings = []
    if mirror:
        source = read_json(mirror)  # Authoritative CapCut timeline on newer versions.
        if read_json(main) != source:
            warnings.append("Top-level draft differs from active nested timeline; using active nested timeline as source. Both files will be backed up.")
    else:
        source = read_json(main)
    return source, (mirror or main), [main] + ([mirror] if mirror else []), warnings


def harvest_transitions(root: Path, *, project: Path | None = None) -> list[dict]:
    by_id: dict[str, dict] = {}
    scoped = project is not None
    for project in ([project] if scoped else list_projects(root)):
        try:
            obj, _, _, _ = load_project(project)
            transitions = obj.get("materials", {}).get("transitions", [])
            linked = {ref for t in obj.get("tracks", []) if t.get("type") == "video"
                      for s in t.get("segments", []) for ref in s.get("extra_material_refs", [])}
            for t in transitions:
                if not isinstance(t, dict):
                    continue
                if scoped and t.get("id") not in linked:
                    continue
                effect = t.get("effect_id")
                if not isinstance(effect, str) or not effect:
                    continue
                if effect not in by_id:
                    by_id[effect] = {"effect_id": effect, "name": t.get("name") or "Transition",
                                      "category": t.get("category_name") or "", "template": copy.deepcopy(t),
                                      "from_project": project.name}
        except (ValueError, OSError, KeyError, TypeError):
            continue
    entries = sorted(by_id.values(), key=lambda t: (str(t["category"]).casefold(), str(t["name"]).casefold(), t["effect_id"]))
    seen: dict[str, int] = {}
    for item in entries:
        name = str(item["name"])
        key = name.casefold()
        seen[key] = seen.get(key, 0) + 1
        item["label"] = f"{name} #{seen[key]}" if seen[key] > 1 else name
    return entries


def clip_name(material: dict) -> str:
    path = str(material.get("path") or "").replace("\\", "/")
    return str(material.get("material_name") or path.rsplit("/", 1)[-1] or material.get("id") or "Unnamed")


def normalize_name(name: str) -> str:
    return re.sub(r"\.[a-z0-9]+$", "", str(name).replace("\\", "/").split("/")[-1].strip().casefold())


def cut_inventory(draft: dict) -> tuple[list[dict], list[str]]:
    """Only directly adjacent segments on the SAME visual track are eligible.

    No claims about applying cross-track transitions (e.g. photo lower layer to
    video on a different upper layer) without a CapCut compatibility sample.
    """
    videos = {m.get("id"): m for m in draft.get("materials", {}).get("videos", []) if isinstance(m, dict)}
    cuts, warnings = [], []
    for ti, track in enumerate(draft.get("tracks", [])):
        if not isinstance(track, dict) or track.get("type") != "video":
            continue
        segs = track.get("segments", [])
        if not isinstance(segs, list):
            warnings.append(f"Visual track {ti+1}: invalid segments, skipped")
            continue
        for si in range(len(segs) - 1):
            a, b = segs[si], segs[si+1]
            if not isinstance(a, dict) or not isinstance(b, dict):
                warnings.append(f"Track {ti+1}, cut {si+1}: invalid segment")
                continue
            at, bt = a.get("target_timerange") or {}, b.get("target_timerange") or {}
            try:
                end = int(at["start"]) + int(at["duration"])
                start = int(bt["start"])
            except (KeyError, TypeError, ValueError):
                warnings.append(f"Track {ti+1}, cut {si+1}: missing timeline range")
                continue
            if abs(end - start) > 1:  # CapCut stores microseconds.
                warnings.append(f"Track {ti+1}, cut {si+1}: gap/overlap, skipped (no safe same-track junction)")
                continue
            ma, mb = videos.get(a.get("material_id"), {}), videos.get(b.get("material_id"), {})
            cuts.append({"track_index": ti, "segment_index": si,
                         "track_id": track.get("id") or f"track-{ti+1}",
                         "after": clip_name(ma), "before": clip_name(mb),
                         "after_type": ma.get("type", "unknown"), "before_type": mb.get("type", "unknown"),
                         "source_id": a.get("id"), "cut_start": int(at["start"]), "cut_end": end})
    if not cuts:
        warnings.append("No eligible adjacent visual clips on the same track. No changes will be made.")
    return cuts, warnings


def parse_edit_file(text: str) -> dict:
    obj = json.loads(text.removeprefix("\ufeff"))
    if not isinstance(obj, dict) or not isinstance(obj.get("transitions"), list):
        raise ValueError('Edit file needs a JSON object with a "transitions" array')
    if obj.get("version", 1) != 1:
        raise ValueError("Only Edit File version 1 is supported")
    return obj


@dataclass
class Plan:
    chosen: dict[tuple[int, int], dict] = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    eligible: list[dict] = field(default_factory=list)

    @property
    def counts(self) -> dict:
        statuses = [r["status"] for r in self.rows]
        return {"will_apply": statuses.count("Will Apply"),
                "missing": statuses.count("Missing"), "skipped": statuses.count("Skipped"),
                "eligible_cuts": len(self.eligible)}


def _duration_to_us(value: Any) -> int:
    try:
        f = float(value)
    except (ValueError, TypeError):
        raise ValueError("Invalid transition duration")
    if not (0.1 <= f <= 10.0):
        raise ValueError("Transition duration must be between 0.1 and 10.0 seconds")
    return round(f * 1_000_000)


def plan_transitions(draft: dict, catalog: list[dict], mode: str = "none", ids: list[str] | None = None,
                     duration: float = 0.5, spec: dict | None = None, seed: int | None = None) -> Plan:
    cuts, warnings = cut_inventory(draft)
    p = Plan(warnings=warnings, eligible=cuts)
    by_id = {c["effect_id"]: c for c in catalog}
    ids = list(dict.fromkeys(i for i in (ids or []) if i in by_id))
    if mode not in {"none", "single", "mix"}:
        raise ValueError("Unknown transition mode")
    if mode != "none" and not ids:
        raise ValueError("Choose an available transition for Single or Random mix")
    dur = _duration_to_us(duration)
    rng = random.Random(seed)
    prior = None
    for cut in cuts:
        chosen_id = None
        if mode == "single":
            chosen_id = ids[0]
        elif mode == "mix":
            pool = [x for x in ids if x != prior] if len(ids) > 1 else ids
            chosen_id = rng.choice(pool)
            prior = chosen_id
        if chosen_id:
            key = cut["track_index"], cut["segment_index"]
            p.chosen[key] = {"effect_id": chosen_id, "durationUs": dur}
    if spec:
        if not isinstance(spec.get("transitions"), list):
            raise ValueError("Invalid edit file: missing transitions array")
        for rule in spec["transitions"]:
            if not isinstance(rule, dict) or not isinstance(rule.get("after"), str) or not isinstance(rule.get("transition"), str) or not rule["after"].strip() or not rule["transition"].strip():
                p.rows.append({"after": str(rule.get("after", "") if isinstance(rule, dict) else ""),
                               "transition": str(rule.get("transition", "") if isinstance(rule, dict) else ""),
                               "status": "Skipped", "reason": "Invalid rule: after and transition are required"})
                continue
            row = {"after": rule["after"], "transition": rule["transition"], "status": "Skipped", "reason": ""}
            matched = [c for c in catalog if str(c["name"]).casefold() == rule["transition"].casefold()]
            if rule.get("effect_id") is not None:
                matched = [c for c in matched if c["effect_id"] == str(rule["effect_id"])]
            if not matched:
                row.update(status="Missing", reason="Transition is not in saved CapCut projects. Add it in CapCut and refresh catalog.")
                p.rows.append(row)
                continue
            if len(matched) > 1:
                row.update(status="Skipped", reason="Duplicate transition names: add exact effect_id for safety")
                p.rows.append(row)
                continue
            matches = [c for c in cuts if normalize_name(c["after"]) == normalize_name(rule["after"])]
            if rule.get("track_id") is not None:
                matches = [c for c in matches if c["track_id"] == str(rule["track_id"])]
            if rule.get("track_index") is not None:
                matches = [c for c in matches if c["track_index"] == rule["track_index"]]
            if rule.get("segment_index") is not None:
                matches = [c for c in matches if c["segment_index"] == rule["segment_index"]]
            if not matches:
                row.update(status="Skipped", reason="Filename not found on an eligible same-track cut")
            elif len(matches) > 1:
                row.update(status="Skipped", reason="Filename repeated; specify track_index and segment_index")
            else:
                try:
                    use_duration = _duration_to_us(rule.get("duration", duration))
                except ValueError as e:
                    row.update(status="Skipped", reason=str(e))
                else:
                    cut = matches[0]
                    key = cut["track_index"], cut["segment_index"]
                    p.chosen[key] = {"effect_id": matched[0]["effect_id"], "durationUs": use_duration}
                    row.update(status="Will Apply", reason=f"Track {key[0]+1}, cut {key[1]+1}")
            p.rows.append(row)
    for cut in cuts:
        key = cut["track_index"], cut["segment_index"]
        if key in p.chosen:
            info = p.chosen[key]
            p.rows.append({"after": cut["after"], "transition": by_id[info["effect_id"]]["name"],
                           "status": "Selected", "reason": f"Track {key[0]+1}, cut {key[1]+1}: {info['durationUs']/1e6:g}s"})
    return p


def immutable_snapshot(draft: dict) -> str:
    """Hash of all unrelated project fields and all segment fields except transition refs."""
    original = copy.deepcopy(draft)
    old_ids = {m.get("id") for m in original.get("materials", {}).get("transitions", []) if isinstance(m, dict)}
    original.get("materials", {}).pop("transitions", None)
    for track in original.get("tracks", []):
        if not isinstance(track, dict):
            continue
        for seg in track.get("segments", []):
            if isinstance(seg, dict) and isinstance(seg.get("extra_material_refs"), list):
                seg["extra_material_refs"] = [r for r in seg["extra_material_refs"] if r not in old_ids]
    return hashlib.sha256(json.dumps(original, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def apply_plan(source: dict, catalog: list[dict], plan: Plan) -> tuple[dict, dict]:
    draft = copy.deepcopy(source)
    by_effect = {c["effect_id"]: c for c in catalog}
    mats = draft.setdefault("materials", {}).setdefault("transitions", [])
    old_by_id = {m["id"]: m for m in mats if isinstance(m, dict) and m.get("id")}
    changed, unchanged, retired = 0, 0, set()
    for (ti, si), setting in sorted(plan.chosen.items()):
        track = draft["tracks"][ti]
        seg = track["segments"][si]
        old_refs = seg.get("extra_material_refs") or []
        if not isinstance(old_refs, list):
            raise ValueError("Unexpected extra_material_refs schema")
        old_t = [old_by_id[r] for r in old_refs if r in old_by_id]
        eff = setting["effect_id"]
        dur = setting["durationUs"]
        if len(old_t) == 1 and old_t[0].get("effect_id") == eff and int(old_t[0].get("duration") or 0) == dur:
            unchanged += 1
            continue
        cat = by_effect.get(eff)
        if not cat:
            raise ValueError(f"Transition disappeared from catalog: {eff}")
        mat = copy.deepcopy(cat["template"])
        mat["id"] = str(uuid.uuid4()).upper()
        mat["duration"] = dur
        mats.append(mat)
        removed = {r for r in old_refs if r in old_by_id}
        retired.update(removed)
        seg["extra_material_refs"] = [r for r in old_refs if r not in removed] + [mat["id"]]
        changed += 1
    if retired:
        referenced = set()
        for tr in draft.get("tracks", []):
            for seg in tr.get("segments", []):
                referenced.update(seg.get("extra_material_refs") or [])
        mats[:] = [m for m in mats if m.get("id") not in retired or m.get("id") in referenced]
    if immutable_snapshot(draft) != immutable_snapshot(source):
        raise AssertionError("Safety invariant failed: non-transition data changed")
    return draft, {"changed": changed, "already_matching": unchanged,
                   "total_selected": len(plan.chosen)}


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".transition_only_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _metadata_updates(project: Path, duration: Any, now_us: int) -> dict[Path, bytes]:
    updates: dict[Path, bytes] = {}
    mp = project / "draft_meta_info.json"
    if mp.is_file():
        meta = read_json(mp)
        meta["tm_draft_modified"] = now_us
        if isinstance(duration, (int, float)):
            meta["tm_duration"] = round(duration)
        updates[mp] = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    rp = project.parent / "root_meta_info.json"
    if rp.is_file():
        root = read_json(rp)
        entries = root.get("all_draft_store") or []
        target = str(project.resolve()).replace("\\", "/").rstrip("/").casefold()
        hit = None
        for entry in entries:
            if str(entry.get("draft_fold_path") or "").replace("\\", "/").rstrip("/").casefold() == target:
                hit = entry
                break
        if hit is None:
            # Avoid modifying a different project that merely has the same name.
            same = [entry for entry in entries if entry.get("draft_name") == project.name]
            if len(same) == 1:
                hit = same[0]
        if hit is not None:
            hit["tm_draft_modified"] = now_us
            if isinstance(duration, (int, float)):
                hit["tm_duration"] = round(duration)
            updates[rp] = json.dumps(root, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return updates


def save_transitions(project: Path, catalog: list[dict], plan: Plan) -> dict:
    """Guarded, backed-up, best-effort transactional JSON-only write."""
    if capcut_running():
        raise RuntimeError("CapCut is running. Close CapCut before applying transitions.")
    if not plan.chosen:
        raise ValueError("No valid transition selections to apply")
    project = project.resolve()
    lock = project / ".autocapcut_transitions_only.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as e:
        raise RuntimeError("Another transitions-only operation may be running (lock exists)") from e
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"pid={os.getpid()}\n")
        source, _, drafts, warnings = load_project(project)
        actual_cuts, _ = cut_inventory(source)
        actual_by_key = {(c["track_index"], c["segment_index"]): c for c in actual_cuts}
        preview_by_key = {(c["track_index"], c["segment_index"]): c for c in plan.eligible}
        if not set(plan.chosen).issubset(actual_by_key):
            raise RuntimeError("Selected timeline changed after preview. Refresh and preview again.")
        for key in plan.chosen:
            old, now = preview_by_key.get(key), actual_by_key[key]
            if old is None or any(old.get(k) != now.get(k) for k in
                                  ("track_id", "source_id", "after", "before", "cut_start", "cut_end")):
                raise RuntimeError("Clip identity/timing changed after preview. Refresh and preview again.")
        output, stats = apply_plan(source, catalog, plan)
        if not stats["changed"]:
            return {**stats, "backup_dir": None, "warnings": warnings, "saved": False}
        updates = {p: json.dumps(output, ensure_ascii=False, separators=(",", ":")).encode("utf-8") for p in drafts}
        now_us = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        updates.update(_metadata_updates(project, output.get("duration"), now_us))
        original = {p: p.read_bytes() for p in updates}
        fingerprints = {p: _hash_bytes(data) for p, data in original.items()}
        backup_dir = project / ".transition_only_backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        backup_dir.mkdir(parents=True, exist_ok=False)
        manifests = []
        for i, (p, old) in enumerate(original.items()):
            copy_name = f"{i:02d}_{p.name}"
            (backup_dir / copy_name).write_bytes(old)
            manifests.append({"original": str(p), "backup": copy_name, "sha256": fingerprints[p]})
        (backup_dir / "manifest.json").write_text(json.dumps(manifests, indent=2), encoding="utf-8")
        if capcut_running():
            raise RuntimeError("CapCut opened during preparation. Aborted before writing")
        for p, expected in fingerprints.items():
            if _hash_bytes(p.read_bytes()) != expected:
                raise RuntimeError(f"File modified externally during preview: {p}")
        written: list[Path] = []
        try:
            for p, data in updates.items():
                _atomic_write(p, data)
                written.append(p)
            reloaded, _, _, _ = load_project(project)
            if reloaded != output or immutable_snapshot(reloaded) != immutable_snapshot(source):
                raise RuntimeError("Post-write verification failed; rolling back")
        except BaseException:
            for p in reversed(written):
                _atomic_write(p, original[p])
            raise
        return {**stats, "backup_dir": str(backup_dir), "warnings": warnings, "saved": True,
                "updated_files": [str(p) for p in updates]}
    finally:
        lock.unlink(missing_ok=True)
