"""Deterministic, preview/export-shared creator effects for the Scene Desktop renderer.

These are parameterized color looks, not externally sourced .cube LUTs.
"""
from __future__ import annotations

# Twenty-three visually distinct built-in color looks. Key -> (brightness,
# contrast, saturation, red-shift, green-shift, blue-shift).
COLOR_LOOKS = {
    "neutral": (0, 1, 1, 0, 0, 0),
    "warm": (.025, 1.04, 1.07, .13, .02, -.12),
    "cool": (-.008, 1.07, .98, -.09, .015, .14),
    "teal_orange": (.005, 1.12, 1.15, .12, -.05, .14),
    "cinematic": (-.018, 1.21, .86, .05, -.04, .07),
    "vintage": (.035, .93, .79, .12, .04, -.12),
    "noir": (-.027, 1.33, 0, 0, 0, 0),
    "sunset": (.04, 1.1, 1.27, .18, -.03, -.18),
    "moonlight": (-.04, 1.16, .72, -.13, -.03, .19),
    "pastel": (.06, .84, .74, .09, .04, .05),
    "high_contrast": (-.025, 1.38, 1.1, 0, 0, 0),
    "soft_film": (.025, .89, .83, .06, -.01, -.03),
    "golden_hour": (.045, .99, 1.18, .22, .06, -.19),
    "winter": (-.025, 1.15, .72, -.1, .015, .19),
    "forest": (-.012, 1.11, 1.08, -.05, .17, -.09),
    "desert": (.028, 1.13, .94, .21, .025, -.17),
    "portrait": (.03, .94, 1.04, .07, -.015, .015),
    "bleach_bypass": (-.03, 1.3, .59, -.02, 0, .03),
    "dreamy": (.055, .87, .85, .065, .03, .075),
    "retro_tv": (-.012, 1.15, 1.19, .045, .095, -.1),
    "emerald": (-.017, 1.08, 1.08, -.08, .19, -.1),
    "magenta": (-.016, 1.07, 1.11, .13, -.12, .13),
    "sepia": (.025, 1.08, .50, .23, .02, -.25),
}

MOTIONS = {
    "none", "pan_left", "pan_right", "pan_up", "pan_down",
    "slow_push", "gentle_zoom", "ken_burns", "reframe_left", "reframe_right",
}
GRAINS = {"none", "film", "white", "black", "analog"}
TRANSITIONS = {"cut", "fade", "dissolve", "slide_left", "slide_right", "slide_up", "slide_down"}


def clamp(value, low, high):
    return max(low, min(high, float(value)))


def _move_expression(direction: str, frames: int) -> tuple[str, str]:
    # This uses FFmpeg crop x/y variables evaluated once per output frame.
    frac = f"(n/({frames}+n))"
    if direction in {"pan_left", "reframe_left"}:
        return f"(iw-ow)*(1-{frac})", "(ih-oh)/2"
    if direction in {"pan_right", "reframe_right"}:
        return f"(iw-ow)*{frac}", "(ih-oh)/2"
    if direction == "pan_up":
        return "(iw-ow)/2", f"(ih-oh)*(1-{frac})"
    if direction == "pan_down":
        return "(iw-ow)/2", f"(ih-oh)*{frac}"
    return "(iw-ow)/2", "(ih-oh)/2"


def visual_filters(effects: dict, width: int, height: int, fps: int, duration: float,
                   section_elapsed: float = 0) -> list[str]:
    """Return FFmpeg filter expressions for a section of one video/image.

    Section elapsed is in seconds from clip start; use it for motion continuity.
    Never build a shell string.
    """
    effect = effects or {}
    motion = str(effect.get("motion", "none"))
    if motion not in MOTIONS:
        raise ValueError("Unknown image/video motion")
    look = str(effect.get("look", "neutral"))
    if look not in COLOR_LOOKS:
        raise ValueError("Unknown color look")
    grain_kind = str(effect.get("grain_style", "film"))
    if grain_kind not in GRAINS:
        raise ValueError("Unknown noise style")
    zoom = clamp(effect.get("zoom", 1), .5, 3)
    frame_count = max(1, round((duration + section_elapsed) * fps))
    frames_elapsed = max(0, round(section_elapsed * fps))
    chain = ["setpts=PTS-STARTPTS", f"fps={fps}",
             f"scale={width}:{height}:force_original_aspect_ratio=increase",
             f"crop={width}:{height}", "setsar=1"]

    if motion != "none" or zoom != 1:
        overscan = max(zoom, 1.16 if motion != "none" else zoom)
        # Zooms below 100% use a black canvas instead of invalid negative crop.
        if overscan < 1:
            chain += [
                f"scale=trunc(iw*{overscan:.5f}/2)*2:trunc(ih*{overscan:.5f}/2)*2",
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            ]
        else:
            chain.append(f"scale=trunc(iw*{overscan:.5f}/2)*2:trunc(ih*{overscan:.5f}/2)*2")
            if motion in {"slow_push", "gentle_zoom", "ken_burns"}:
                # Continuous zoompan expressions; on counts rendered frames.
                start_z = clamp(1.001 + frames_elapsed * .00055, 1, 1.29)
                rate = .00055 if motion != "gentle_zoom" else .00025
                chain.append(
                    f"zoompan=z='min(zoom+{rate:.6f}\\,1.30)':"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d=1:s={width}x{height}:fps={fps}"
                )
            else:
                x, y = _move_expression(motion, frame_count)
                chain.append(f"crop={width}:{height}:x='{x}':y='{y}'")
    if effect.get("mirror"):
        chain.append("hflip")
    degrees = clamp(effect.get("rotate", 0), -360, 360)
    if degrees:
        chain.append(f"rotate={degrees:.3f}*PI/180:c=black")
    raw = COLOR_LOOKS[look]
    strength = clamp(effect.get("look_intensity", 100), 0, 100) / 100
    lum = clamp(effect.get("brightness", 0), -1, 1) + raw[0]*strength
    contrast = clamp(effect.get("contrast", 1), 0, 3) + (raw[1]-1)*strength
    saturation = clamp(effect.get("saturation", 1), 0, 4) + (raw[2]-1)*strength
    chain.append(f"eq=brightness={clamp(lum,-1,1):.5f}:contrast={clamp(contrast,0,3):.5f}:saturation={clamp(saturation,0,4):.5f}")
    if strength and any(raw[3:]):
        r, g, b = (clamp(v*strength, -.5,.5) for v in raw[3:])
        chain.append(f"colorbalance=rs={r:.5f}:gs={g:.5f}:bs={b:.5f}")
    blur = clamp(effect.get("blur", 0), 0, 20)
    if blur:
        chain.append(f"gblur=sigma={blur:.2f}")
    noise = round(clamp(effect.get("grain", 0), 0, 40))
    if noise and grain_kind != "none":
        if grain_kind == "black":
            chain.append("eq=brightness=-0.025")
        if grain_kind == "white":
            chain.append("eq=brightness=0.025")
        if grain_kind == "analog":
            chain.append("format=yuv420p")
        chain.append(f"noise=alls={noise}:allf=t+u")
    chain.append("format=yuva420p")
    alpha = clamp(effect.get("opacity", 1), 0, 1)
    if alpha < 1:
        chain.append(f"colorchannelmixer=aa={alpha:.5f}")
    return chain


def transition_alpha(name: str, elapsed: float, duration_seconds: float) -> float:
    if name == "cut" or duration_seconds <= 0:
        return 1.
    return clamp(elapsed/duration_seconds, 0, 1)


def overlay_position(transition: str, duration_sec: float, elapsed_sec: float) -> tuple[str,str]:
    """FFmpeg overlay x/y expressions for real slide transitions."""
    if transition not in TRANSITIONS:
        raise ValueError("Unknown transition")
    if transition not in {"slide_left","slide_right","slide_up","slide_down"}:
        return "0", "0"
    ratio = f"max(0\\,1-(t+{elapsed_sec:.6f})/{max(.001,duration_sec):.6f})"
    if transition == "slide_left":
        return f"W*{ratio}", "0"
    if transition == "slide_right":
        return f"-W*{ratio}", "0"
    if transition == "slide_up":
        return "0", f"H*{ratio}"
    return "0", f"-H*{ratio}"
