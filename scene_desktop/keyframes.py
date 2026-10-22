"""Validated clip-local numeric keyframes and FFmpeg interpolation expressions.

Keyframe times are milliseconds relative to the trimmed timeline clip start.
Expressions are generated from numeric model values only, never arbitrary input.
"""
from __future__ import annotations
import math

LIMITS = {
    "zoom": (1.0, 3.0),
    "brightness": (-1.0, 1.0),
    "saturation": (0.0, 4.0),
}
MAX_FRAMES = 100


def validate_keyframes(data: dict, duration_ms: int) -> None:
    if not isinstance(data, dict) or set(data).difference(LIMITS):
        raise ValueError("Unsupported keyframe property")
    for property_name, entries in data.items():
        if not isinstance(entries, list) or len(entries) > MAX_FRAMES:
            raise ValueError("Expected at most 100 keyframes per property")
        previous = -1
        low, high = LIMITS[property_name]
        for key in entries:
            if not isinstance(key, dict) or set(key) != {"at_ms", "value"}:
                raise ValueError("Invalid keyframe record")
            at = key["at_ms"]
            val = key["value"]
            if not isinstance(at, int) or isinstance(at, bool) or not 0 <= at <= duration_ms:
                raise ValueError("Keyframe exceeds clip bounds")
            if at <= previous:
                raise ValueError("Keyframes must be sorted and unique")
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError("Keyframe value must be finite")
            if not low <= float(val) <= high:
                raise ValueError("Keyframe property is out of range")
            previous = at


def set_keyframe(data: dict, property_name: str, at_ms: int, value: float,
                 duration_ms: int) -> dict:
    updated = {k: [dict(x) for x in arr] for k, arr in data.items()}
    if property_name not in LIMITS:
        raise ValueError("Unsupported keyframe property")
    frames = [k for k in updated.get(property_name, []) if k["at_ms"] != at_ms]
    frames.append({"at_ms": int(at_ms), "value": float(value)})
    updated[property_name] = sorted(frames, key=lambda x: x["at_ms"])
    validate_keyframes(updated, duration_ms)
    return updated


def remove_keyframe(data: dict, property_name: str, at_ms: int) -> dict:
    updated = {k: [dict(x) for x in arr] for k, arr in data.items()}
    if property_name not in LIMITS:
        raise ValueError("Unsupported keyframe property")
    updated[property_name] = [x for x in updated.get(property_name, [])
                              if x["at_ms"] != at_ms]
    return updated


def value_at(entries: list[dict], time_ms: int, default: float) -> float:
    if not entries:
        return float(default)
    if time_ms <= entries[0]["at_ms"]:
        return float(entries[0]["value"])
    for left, right in zip(entries, entries[1:]):
        if time_ms <= right["at_ms"]:
            fraction = (time_ms-left["at_ms"])/(right["at_ms"]-left["at_ms"])
            return left["value"]+(right["value"]-left["value"])*fraction
    return float(entries[-1]["value"])


def ffmpeg_expression(entries: list[dict], default: float, fps: int,
                      offset_ms: int, variable: str = "n") -> str:
    """Piecewise linear on clip-local frame clock, continuous across cached chunks.

    The caller must quote the output as an FFmpeg expression; commas are
    backslash-escaped once for FFmpeg filtergraph parsing.
    """
    if not entries:
        return f"{default:.6f}"
    frame_clock = f"({variable}+{offset_ms*fps/1000:.6f})"
    points = [(at["at_ms"]*fps/1000.0, float(at["value"])) for at in entries]
    expr = f"{points[-1][1]:.6f}"
    for idx in range(len(points)-2, -1, -1):
        t0, v0 = points[idx]
        t1, v1 = points[idx+1]
        linear = f"({v0:.6f}+({v1-v0:.6f})*({frame_clock}-{t0:.6f})/{max(.001,t1-t0):.6f})"
        expr = f"if(lte({frame_clock},{t1:.6f}),{linear},{expr})"
    if points[0][0] > 0:
        expr = f"if(lte({frame_clock},{points[0][0]:.6f}),{points[0][1]:.6f},{expr})"
    return expr.replace(",", r"\,")
