"""Conservative native CapCut effect/filter track detection and timeline-length editor.

Only existing, unambiguous, *dedicated* effect/filter tracks are changed. Scene
materials remain intact; segment-attached/animated/multi-segment tracks are
reported but NEVER promoted or stretched speculatively.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_US = 12 * 60 * 60 * 1_000_000


@dataclass(frozen=True)
class Target:
    end_us: int
    source: str
    audio_end_us: int
    visual_end_us: int

    @property
    def label(self) -> str:
        return f"{self.end_us / 1_000_000:.3f}s ({self.source})"


def _end_us(seg: dict) -> int | None:
    timerange = seg.get("target_timerange")
    if not isinstance(timerange, dict):
        return None
    start, duration = timerange.get("start"), timerange.get("duration")
    # bool subclasses int; accept only integer microseconds in native CapCut.
    if type(start) is not int or type(duration) is not int or start < 0 or duration <= 0:
        return None
    end = start + duration
    return end if 0 < end <= MAX_US else None


def find_target(draft: dict) -> Target:
    """Audio segment endpoint (preferred), otherwise visual endpoint.

    Never trust draft.duration alone: it is sometimes stale or represents a
    different max-track duration. Never extend any media to fill the endpoint.
    """
    audio_end = visual_end = 0
    for track in draft.get("tracks", []):
        if not isinstance(track, dict):
            continue
        kind = track.get("type")
        if kind not in ("audio", "video", "image"):
            continue
        for seg in track.get("segments", []):
            if not isinstance(seg, dict):
                continue
            end = _end_us(seg)
            if end is None:
                continue
            if kind == "audio":
                audio_end = max(audio_end, end)
            else:
                visual_end = max(visual_end, end)
    duration = audio_end or visual_end
    if duration <= 0:
        return Target(0, "none (no valid audio/visual segments)", audio_end, visual_end)
    return Target(duration, "audio timeline endpoint" if audio_end else "visual timeline fallback", audio_end, visual_end)


def _kind(track_kind: str, material: dict) -> str | None:
    # Do not guess from category_name: it is a human-facing name, not a discriminator.
    mtype = str(material.get("type") or "").casefold()
    expected = {"filter": "filter", "effect": "video_effect"}.get(track_kind)
    if mtype == expected or (not mtype and expected):
        return track_kind
    return None


def inspect(draft: dict, *, apply_filters: bool = True, apply_effects: bool = True,
            stretch: bool = True) -> tuple[list[dict], Target]:
    """Mutate duration only if stretch=True. Return all discovered FX rows.

    - One existing segment per dedicated track, no conflicting overlaps.
    - Global or track-type material scope only, never targeted to a single clip.
    - Native source_timerange is resized only for start=0 range.
    - Original material, ids, other tracks, visual/audio trim values untouched.
    """
    target = find_target(draft)
    materials = draft.get("materials") or {}
    material_list = materials.get("video_effects") or []
    if not isinstance(material_list, list):
        raise ValueError("Invalid CapCut materials.video_effects array")
    by_id: dict[str, dict] = {}
    duplicate_ids: set[str] = set()
    for m in material_list:
        if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"]:
            if m["id"] in by_id:
                duplicate_ids.add(m["id"])
            by_id[m["id"]] = m
    rows = []
    used_by_fx_tracks = set()
    for ti, track in enumerate(draft.get("tracks", [])):
        if not isinstance(track, dict) or track.get("type") not in ("filter", "effect"):
            continue
        tk = track["type"]
        segments = track.get("segments")
        if not isinstance(segments, list):
            raise ValueError(f"Invalid {tk} track segments array")
        for si, seg in enumerate(segments):
            if not isinstance(seg, dict):
                continue
            mid = seg.get("material_id")
            used_by_fx_tracks.add(mid)
            mat = by_id.get(mid)
            tr = seg.get("target_timerange") or {}
            start = tr.get("start") if isinstance(tr, dict) else None
            old_duration = tr.get("duration") if isinstance(tr, dict) else None
            row = {"track": ti + 1, "segment": si + 1, "kind": tk.title(),
                   "name": (str((mat or {}).get("name") or (mat or {}).get("effect_name") or (mat or {}).get("effect_id") or mid or "unknown")),
                   "current": f"{start / 1e6:.3f}+{old_duration / 1e6:.3f}s" if type(start) is int and type(old_duration) is int else "unknown",
                   "target": f"0+{target.end_us / 1e6:.3f}s" if target.end_us else "unknown",
                   "scope": str((mat or {}).get("apply_target_type", "unspecified")),
                   "status": "", "material_id": mid}
            reason = ""
            if not mat:
                reason = "Unknown effect material; skipped"
            elif mid in duplicate_ids:
                reason = "Duplicate material ID; skipped"
            elif _kind(tk, mat) is None:
                reason = "Track/material type conflict; skipped"
            elif not isinstance(seg.get("id"), str) or not seg["id"]:
                reason = "Missing native segment ID; skipped"
            elif len(segments) != 1:
                reason = "Multiple segments on same FX track; skipped to avoid overlap"
            elif seg.get("common_keyframes") or seg.get("keyframe_refs"):
                reason = "Animated FX segment; skipped to preserve keyframes"
            elif mat.get("apply_target_type") not in (None, 1, 2):
                reason = "Segment-scoped/unknown target; skipped"
            elif mat.get("apply_target_type") == 1 and mat.get("apply_target_track_type") not in (None, 0):
                reason = "Nonvisual target-track scope; skipped"
            elif not isinstance(tr, dict) or type(start) is not int or type(old_duration) is not int or start < 0 or old_duration <= 0 or _end_us(seg) is None:
                reason = "Invalid timerange; skipped"
            elif target.end_us <= 0:
                reason = "Missing audio and visual timeline endpoint"
            elif isinstance(seg.get("source_timerange"), dict) and (
                type(seg["source_timerange"].get("start")) is not int or seg["source_timerange"]["start"] != 0 or
                type(seg["source_timerange"].get("duration")) is not int or seg["source_timerange"]["duration"] <= 0
            ):
                reason = "Nonzero/invalid FX source timerange; skipped"
            elif (tk == "filter" and not apply_filters) or (tk == "effect" and not apply_effects):
                reason = "Disabled by checkbox"
            elif start == 0 and old_duration == target.end_us and (
                not isinstance(seg.get("source_timerange"), dict) or seg["source_timerange"]["duration"] == target.end_us
            ):
                reason = "Already full length"
            if reason:
                row["status"] = reason
            else:
                row["status"] = "Will extend" if stretch else "Eligible — preview only"
                if stretch:
                    seg["target_timerange"]["start"] = 0
                    seg["target_timerange"]["duration"] = target.end_us
                    if isinstance(seg.get("source_timerange"), dict):
                        seg["source_timerange"]["duration"] = target.end_us
            rows.append(row)
    # Additional detection only: local segment-attached effects cannot be extended
    # without changing their per-clip ownership/scope, so never silently promote.
    attached_seen = set()
    for ti, track in enumerate(draft.get("tracks", [])):
        if not isinstance(track, dict) or track.get("type") not in ("video", "image"):
            continue
        for si, seg in enumerate(track.get("segments", [])):
            if not isinstance(seg, dict):
                continue
            refs = seg.get("extra_material_refs") or []
            if not isinstance(refs, list):
                continue
            for mid in refs:
                if mid not in by_id or mid in attached_seen:
                    continue
                attached_seen.add(mid)
                mat = by_id[mid]
                mtype = str(mat.get("type") or "").casefold()
                kind = "Filter" if mtype == "filter" else "Effect" if mtype == "video_effect" else "Unknown"
                rows.append({"track": ti + 1, "segment": si + 1, "kind": kind,
                             "name": str(mat.get("name") or mat.get("effect_name") or mat.get("effect_id") or mid),
                             "current": "attached to clip", "target": "—",
                             "scope": "segment attachment", "status": "Detected only — clip-scoped, not stretched",
                             "material_id": mid})
    # Report cached/unattached native materials, but never fabricate a new
    # timeline track or silently turn them into active effects.
    observed = used_by_fx_tracks | attached_seen
    for mid, mat in by_id.items():
        if mid in observed:
            continue
        mtype = str(mat.get("type") or "").casefold()
        if mtype not in ("filter", "video_effect"):
            continue
        rows.append({"track": "—", "segment": "—", "kind": "Filter" if mtype == "filter" else "Effect",
                     "name": str(mat.get("name") or mat.get("effect_name") or mat.get("effect_id") or mid),
                     "current": "material only", "target": "—", "scope": "unreferenced",
                     "status": "Detected cache only — not applied to any timeline track",
                     "material_id": mid})
    return rows, target

