"""Shared clip geometry and bounded live-preview budgeting.

GPU live-preview performs OpenGL-backed *compositing*, not GPU video decode.
This pure module is used by Windows CI and the on-device benchmark.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sin, pi

from .effects import COLOR_LOOKS, clamp
from .keyframes import value_at

SOFTWARE_GL_MARKERS = ("llvmpipe", "softpipe", "swiftshader", "gdi generic",
                       "microsoft basic render driver", "software rasterizer",
                       "software renderer", "mesa offscreen")
PREVIEW_MAX_SIDE = 1280
MAX_CACHE_BYTES = 96 * 1024**2
MAX_PARALLEL_DECODERS = 3


def classify_gl_renderer(renderer: str, vendor: str = "") -> str:
    if not renderer:
        return "unknown"
    details = f"{renderer} {vendor}".lower()
    return "software" if any(marker in details for marker in SOFTWARE_GL_MARKERS) else "hardware-candidate"


def clip_property(item, prop: str, at_ms: int, default: float) -> float:
    time_ms = max(0, min(item.duration_ms, at_ms - item.start_ms))
    return float(value_at(item.keyframes.get(prop, []), time_ms,
                          item.effects.get(prop, default)))


@dataclass(frozen=True)
class LayerPlacement:
    zoom: float
    opacity: float
    translate_x: float
    translate_y: float
    rotation: float
    mirror: bool
    brightness: float
    contrast: float
    saturation: float


def placement_for(item, at_ms: int, width: int, height: int) -> LayerPlacement:
    """Map timeline to a composition, using the same named motion primitives.

    Texture composition is immediate; some high-end FFmpeg effects (noise,
    .cube LUTs, complex filters) remain in accurate FFmpeg preview/export.
    """
    elapsed = max(0, min(item.duration_ms, at_ms-item.start_ms))
    portion = elapsed / max(1, item.duration_ms)
    effects = item.effects
    motion = effects.get("motion", "none")
    zoom = clamp(clip_property(item, "zoom", at_ms, 1.0), .5, 3)
    dx = dy = 0.0
    displacement = .12 * min(width, height)
    if motion in ("pan_left", "reframe_left"):
        dx = displacement*(1-2*portion)
        zoom = max(1.14, zoom)
    elif motion in ("pan_right", "reframe_right"):
        dx = displacement*(2*portion-1)
        zoom = max(1.14, zoom)
    elif motion == "pan_up":
        dy = displacement*(1-2*portion)
        zoom = max(1.14, zoom)
    elif motion == "pan_down":
        dy = displacement*(2*portion-1)
        zoom = max(1.14, zoom)
    elif motion in ("slow_push", "gentle_zoom", "ken_burns") and not item.keyframes.get("zoom"):
        zoom = max(zoom, 1.0 + portion*(.10 if motion == "gentle_zoom" else .28))
    fade = 1.0
    if item.transition_ms and item.transition_in in ("fade", "dissolve"):
        fade = min(1., elapsed / item.transition_ms)
    if item.fade_in_ms:
        fade = min(fade, elapsed / item.fade_in_ms)
    if item.fade_out_ms:
        fade = min(fade, (item.duration_ms-elapsed)/item.fade_out_ms)
    opacity = clamp(effects.get("opacity", 1.) * fade, 0, 1)
    if item.transition_ms and elapsed < item.transition_ms:
        progress = elapsed / item.transition_ms
        if item.transition_in == "slide_left":
            dx += width*(1-progress)
        elif item.transition_in == "slide_right":
            dx -= width*(1-progress)
        elif item.transition_in == "slide_up":
            dy += height*(1-progress)
        elif item.transition_in == "slide_down":
            dy -= height*(1-progress)
    look = COLOR_LOOKS.get(effects.get("look", "neutral"), COLOR_LOOKS["neutral"])
    look_strength = clamp(effects.get("look_intensity", 100), 0, 100)/100
    brightness = clip_property(item, "brightness", at_ms, 0) + look[0]*look_strength
    saturation = clip_property(item, "saturation", at_ms, 1) + (look[2]-1)*look_strength
    contrast = clamp(effects.get("contrast", 1), 0, 3)+(look[1]-1)*look_strength
    return LayerPlacement(zoom, opacity, dx, dy, clamp(effects.get("rotate", 0), -360, 360),
                          bool(effects.get("mirror", False)), brightness,
                          contrast, saturation)


def active_layers(project, at_ms: int) -> list:
    """Visual background -> overlay ordering; hidden tracks excluded."""
    available = {t.id: idx for idx,t in enumerate(project.tracks)
                 if t.kind in {"video", "overlay", "image"} and t.visible}
    return sorted(
        (item for item in project.items if item.track_id in available
         and item.kind in {"video","image"} and item.start_ms <= at_ms < item.end_ms),
        key=lambda item:(available[item.track_id],item.start_ms,item.id)
    )


def active_captions(project, at_ms: int) -> list:
    visible = {t.id for t in project.tracks if t.kind == "captions" and t.visible}
    return sorted(
        (item for item in project.items if item.kind == "text" and
         item.track_id in visible and item.start_ms <= at_ms < item.end_ms),
        key=lambda item:(item.start_ms,item.id)
    )


def cache_size(image) -> int:
    return max(0, int(image.width())*int(image.height())*4)


def percentile_95(values: list[float]) -> float:
    """Nearest-rank p95; explicit empty samples are unmeasured."""
    if not values:
        return 0.0
    ordered=sorted(values)
    return float(ordered[max(0, __import__("math").ceil(.95*len(ordered))-1)])
