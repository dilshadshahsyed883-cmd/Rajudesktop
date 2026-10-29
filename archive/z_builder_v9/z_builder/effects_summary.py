"""Text summary of native effects already discovered in local CapCut drafts.

Read-only; does not read or write CapCut project media. The generated TXT is
intended as input to ChatGPT when planning future Scene Plan effect decisions.
"""
from __future__ import annotations

import json
from pathlib import Path

from autocapcut_animations_only.animation_engine import (
    harvest_animations, resource_is_available,
)
from autocapcut_transitions_only.transition_engine import harvest_transitions


def _quote(value: object) -> str:
    # JSON quoting makes punctuation and multi-language preset names unambiguous.
    return json.dumps(str(value or ""), ensure_ascii=False)


def render_effects_summary(
    animations: list[dict], transitions: list[dict], *, different_folders: bool = False,
) -> str:
    """Produce a deterministic, path-free summary suitable for AI input.

    Animation entries are verified against the current machine's resource cache
    by the caller via entry['cache_available']; transition entries represent
    saved draft materials (transition cache presence has not been verified).
    """
    available = sorted(
        (a for a in animations if a.get("cache_available") is True),
        key=lambda a: (str(a.get("name", "")).casefold(), str(a.get("effect_id", ""))),
    )
    missing = sorted(
        (a for a in animations if not a.get("cache_available")),
        key=lambda a: (str(a.get("name", "")).casefold(), str(a.get("effect_id", ""))),
    )
    transitions_sorted = sorted(
        transitions,
        key=lambda a: (str(a.get("category", "")).casefold(),
                       str(a.get("name", "")).casefold(),
                       str(a.get("effect_id", ""))),
    )
    out = [
        "Z BUILDER — CAPCUT EFFECTS SUMMARY",
        "Format: effects_summary_v1",
        "Source: native materials already stored in saved CapCut projects on this PC",
        "Purpose: give this TXT + Media Summary + SRT + Master Scene Plan prompt to ChatGPT.",
        "This report is read-only. No media, draft files or presets were modified.",
        "No PC file paths, account details or local cache directories are included.",
        "",
        "[COUNTS]",
        f"native_combo_animations_available={len(available)}",
        f"native_combo_animations_missing_cache={len(missing)}",
        f"transitions_detected_in_saved_drafts={len(transitions_sorted)}",
        "transition_resource_cache_verified=no",
        f"catalogs_scanned_from_different_folders={'yes' if different_folders else 'no'}",
        "",
        "[AVAILABLE_NATIVE_COMBO_ANIMATIONS]",
        "Scope: Video > Animation > Combo > Trending; ONLY images/photos, NEVER video clips.",
        "Every animation below was used on a photo in a saved CapCut project and its cached resource path exists on this PC.",
        "A cached path does not guarantee compatibility with every image duration or CapCut version.",
    ]
    if not available:
        out.append("(none; use a Trending Combo animation on a photo in CapCut, save and refresh)")
    for a in available:
        duration = int(a.get("duration_us") or 0)
        out.append(
            f"- name={_quote(a.get('name'))} | effect_id={_quote(a.get('effect_id'))}"
            f" | category={_quote(a.get('category'))} | duration_seconds={duration / 1_000_000:g}"
            " | cache=available | apply_to=images_only"
        )
    out.extend(["", "[DETECTED_TRANSITIONS]"])
    out.extend([
        "Native transition materials found in saved CapCut drafts.",
        "Only eligible adjacent cuts on the same visual track are supported by the current transition engine.",
        "The source scanner does not independently verify transition resource-cache availability.",
        "A detected transition still needs CapCut version/resource and cut compatibility validation.",
    ])
    if not transitions_sorted:
        out.append("(none; apply a transition in CapCut, save and refresh)")
    for t in transitions_sorted:
        out.append(
            f"- name={_quote(t.get('name'))} | effect_id={_quote(t.get('effect_id'))}"
            f" | category={_quote(t.get('category'))}"
            " | status=saved_draft_material | cache=not_independently_verified"
        )
    out.extend(["", "[MISSING_NATIVE_COMBO_ANIMATIONS]"])
    out.append("Listed for reference only; DO NOT select these until locally available.")
    if not missing:
        out.append("(none)")
    for a in missing:
        out.append(
            f"- name={_quote(a.get('name'))} | effect_id={_quote(a.get('effect_id'))}"
            " | cache=missing | selectable=no"
        )
    out.extend([
        "",
        "[CHATGPT_SCENE_PLAN_RULES]",
        "1. Use exact native effect names and effect_id values from this TXT; never invent preset names or IDs.",
        "2. Combo animations apply only to image shots; video shots must have no native Combo animation.",
        "3. Use only entries in AVAILABLE_NATIVE_COMBO_ANIMATIONS; do not use MISSING entries.",
        "4. Z Builder v9 uses one visual track: transitions may connect adjacent image-image, image-video, video-image or video-video clips; never cross CapCut part boundaries.",
        "5. Preserve SRT-aligned shot timings, exact media filenames, 5–7 minute part boundaries and the single chronological image/video visual track.",
        "6. A 5-second native animation may need to fit a shorter image duration without changing that image's duration.",
        "7. When effect resources or cut compatibility are uncertain, report a warning; do not silently substitute another effect.",
        "8. For duplicate effect names, use effect_id to disambiguate.",
        "9. Z Builder v9 accepts combo= and transition_after= in timed Scene Plan rows and applies compatible native effects to its single-track CapCut draft.",
        "10. Use combo_default=random_saved and transition_default=random_saved above shot rows for defaults; use combo=none or transition_after=none on a shot to opt out. Reference exact names or id:<effect ID> for overrides.",
        "",
        "[NATIVE_EFFECT_TIMED_SCENE_PLAN_EXAMPLE]",
        "name=My CapCut Project",
        "combo_default=random_saved",
        "transition_default=random_saved",
        "combo_seed=42",
        "transition_seed=43",
        "transition_duration=0.5",
        "00:00.000 --> 00:02.500 | image | First.jpg | combo=random_saved | transition_after=id:<real transition ID for eligible same-track cut>",
        "00:02.500 --> 00:05.500 | image | Second.jpg | combo=id:<real native animation ID>",
        "00:05.500 --> 00:09.500 | video | Video1.mp4 | in=0 | transition_after=none",
        "Only add explicit transitions where the next shot is adjacent on the same single visual track in the SAME CapCut part; image-video and video-image are eligible.",
        "Do not invent file names, timings or effect IDs: example rows above are illustrative only.",
        "",
    ])
    return "\n".join(out)


def scan_effects_summary(transitions_root: str | Path, animations_root: str | Path) -> str:
    """Scan both UI-configured CapCut project roots, without mutating them."""
    transition_path = Path(transitions_root).expanduser()
    animation_path = Path(animations_root).expanduser()
    if not transition_path.is_dir() and not animation_path.is_dir():
        raise FileNotFoundError(
            "CapCut project folders are unavailable. Set a valid folder in "
            "CapCut Controls > Transitions or Animations, then try again."
        )
    transitions = harvest_transitions(transition_path) if transition_path.is_dir() else []
    animations = harvest_animations(animation_path, trending_only=True) if animation_path.is_dir() else []
    annotated = [
        {**a, "cache_available": bool(resource_is_available(a))}
        for a in animations
    ]
    return render_effects_summary(
        annotated, transitions,
        different_folders=transition_path.resolve() != animation_path.resolve(),
    )
