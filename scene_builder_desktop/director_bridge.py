"""Director V25 preflight and explicitly limited offline rough-cut adapter.

Full Director instructions must never be silently ignored. Only compatible
cut-based plans can generate an editable local draft for manual inspection.
This is deliberately separate from the production Scene Builder renderer.
"""
from __future__ import annotations

from pathlib import Path

from scene_desktop.core import Project
from scene_desktop.media import duration_ms

from .director_v25 import DirectorSpecError, parse_v25, preflight_v25
from .director_v25_execution import compile_v25


def inspect_plan(text: str, catalog, selected_mode: str) -> dict:
    result = preflight_v25(text, catalog.list(limit=100000),
                          selected_mode, True)
    issues = list(result["errors"])
    if issues:
        return {**result, "desktop_rough_cut_ready": False,
                "desktop_blockers": issues}
    try:
        parsed = parse_v25(text)
        doc = parsed["sections"]
    except DirectorSpecError as exc:
        return {**result, "desktop_rough_cut_ready": False,
                "desktop_blockers": [str(exc)]}

    unsupported = []
    for section, field in [
        ("CAPTIONS", "captions_enabled"),
        ("LOOK", "lut_enabled"),
        ("AUDIO", "music_enabled"),
        ("INTRO", "intro_enabled"),
    ]:
        if doc[section].get(field, "").lower() == "true":
            unsupported.append(f"[{section}].{field}: rendering is not yet supported on desktop")
    if doc["OUTPUT"].get("resolution") not in {"720p", "1080p"}:
        unsupported.append("[OUTPUT].resolution: desktop export supports 720p/1080p")
    if doc["OUTPUT"].get("aspect_ratio") not in {"16:9", "9:16"}:
        unsupported.append("[OUTPUT].aspect_ratio: unsupported in desktop export")
    if doc["OUTPUT"].get("fps") not in {"24", "25", "30", "60"}:
        unsupported.append("[OUTPUT].fps: unsupported in desktop export")
    if doc["AUDIO"].get("voice_volume_percent", "100") != "100":
        unsupported.append("[AUDIO].voice_volume_percent: desktop narration level is fixed to 100%")
    if doc["TIMING"].get("narration_start") != "auto":
        unsupported.append("[TIMING].narration_start: manual synchronization unavailable")

    for section in parsed["scene_shots"]:
        shot = doc[section]
        for field in ("motion", "animation", "effect"):
            value = shot.get(field, "none")
            if value not in {"", "none"}:
                unsupported.append(f"[{section}].{field}={value}: not supported in rough-cut export")
        if shot.get("transition_out", "none") not in {"", "none", "hard_cut"}:
            unsupported.append(f"[{section}].transition_out: only hard cuts are supported")
    for assigned in result["resolved_assets"]:
        if assigned["source"] != "scene_media_library":
            unsupported.append(f"[{assigned['shot']}]: Pexels fallback cannot be rendered offline")
    return {**result, "desktop_rough_cut_ready": not unsupported,
            "desktop_blockers": unsupported}


def build_rough_cut(text: str, catalog, selected_mode: str) -> Project:
    report = inspect_plan(text, catalog, selected_mode)
    if not report["desktop_rough_cut_ready"]:
        raise DirectorSpecError("Rough-cut blocked:\n" +
                                "\n".join(report["desktop_blockers"][:30]))
    doc = parse_v25(text)["sections"]
    compiled = compile_v25(
        text, catalog, source_mode=selected_mode, library_enabled=True,
        selected_preset=doc["PROJECT"]["base_preset"], capabilities={},
    )
    settings = compiled["settings"]
    project = Project(name=doc["PROJECT"]["name"], width=settings["width"],
                      height=settings["height"], fps=settings["fps"])
    maximum_ms = min(3000, round(
        float(doc["TIMING"].get("max_semantic_beat_seconds", "3") or "3") * 1000
    ))
    if maximum_ms < 100:
        raise DirectorSpecError("Shot duration below desktop minimum")
    for row in compiled["scenes"]:
        media_id = row["director_v25_media_asset_id"]
        if row["director_v25_media_source"] != "scene_media_library":
            raise DirectorSpecError("Nonlocal shot cannot be rendered offline")
        path, stored = catalog.file(media_id)
        if not stored["approved"] or stored["original_name"] != row["director_v25_media_filename"]:
            raise DirectorSpecError("Media changed after preflight: " + media_id)
        source_ms = duration_ms(str(path))
        clip = project.add_media(str(path), source_ms)
        clip.trim(0, min(source_ms, maximum_ms))
    project.validate()
    return project
