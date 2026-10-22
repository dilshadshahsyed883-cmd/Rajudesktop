"""Timeline renderer: layered visuals, audio tracks, captions, preview proxies and cache.

Only cache-owned intermediate files are written; imported originals are read-only.
This is an FFmpeg-backed editor (not the old Scene generation pipeline).
"""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
from typing import Callable

from .media import ffmpeg_path
from .timeline import StudioProject, Item, VISUAL_TRACKS, AUDIO_TRACKS

Progress = Callable[[int, str], None]


def execute(args: list[str], stop: threading.Event | None = None):
    """Cancelable external render process; never run a shell command."""
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        while True:
            if stop and stop.is_set():
                process.terminate()
                try:
                    process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                raise RuntimeError("Render cancelled")
            try:
                _, error = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise RuntimeError(
                "FFmpeg: " + (error or b"").decode("utf-8", errors="replace")[-3000:]
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def dependencies(items: list[Item]) -> list:
    result = []
    for item in items:
        record = asdict(item)
        if item.kind != "text":
            source = Path(item.asset)
            if not source.is_file():
                raise FileNotFoundError(f"Missing project media: {source}")
            stat = source.stat()
            record["source_size"] = stat.st_size
            record["source_mtime_ns"] = stat.st_mtime_ns
        result.append(record)
    return result


def section_key(project: StudioProject, items: list[Item], start_ms: int, end_ms: int,
                width: int, height: int, fps: int) -> str:
    payload = {
        "engine": 2,
        "dims": [width, height, fps],
        "section": [start_ms, end_ms],
        "items": dependencies(items),
        "tracks": [asdict(t) for t in project.tracks if t.id in {i.track_id for i in items}],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _visual_items(project: StudioProject, start_ms: int, end_ms: int) -> list[Item]:
    track_ids = {t.id for t in project.tracks if t.kind in VISUAL_TRACKS and t.visible}
    items = [i for i in project.items if i.track_id in track_ids and
             i.kind in {"image", "video"} and i.start_ms < end_ms and i.end_ms > start_ms]
    rank = {t.id: idx for idx, t in enumerate(project.tracks)}
    # Earlier tracks appear on top, but within one track the latest started clip wins.
    return sorted(items, key=lambda i: (-rank[i.track_id], i.start_ms, i.id))


def _caption_items(project: StudioProject, start_ms: int, end_ms: int) -> list[Item]:
    captions = {t.id for t in project.tracks if t.kind == "captions" and t.visible}
    return [i for i in project.items if i.track_id in captions and i.kind == "text" and
            i.start_ms < end_ms and i.end_ms > start_ms]


def _audio_items(project: StudioProject) -> list[Item]:
    audible = {t.id for t in project.tracks if t.kind in AUDIO_TRACKS and not t.muted}
    return [i for i in project.items if i.track_id in audible and i.kind == "audio"]


def _sections(project: StudioProject, start_ms: int, end_ms: int, max_ms: int = 4500) -> list[tuple[int, int]]:
    bounds = {start_ms, end_ms}
    for entry in project.items:
        if entry.kind in {"video", "image", "text"}:
            for value in (entry.start_ms, entry.end_ms):
                if start_ms < value < end_ms:
                    bounds.add(value)
    anchors = sorted(bounds)
    output = []
    for left, right in zip(anchors, anchors[1:]):
        while left < right:
            nxt = min(right, left + max_ms)
            if nxt-left >= 25:
                output.append((left, nxt))
            left = nxt
    return output


def _video_filter(item: Item, width: int, height: int, fps: int, duration: float,
                  relative_start: int, relative_end: int) -> str:
    effect = item.effects
    zoom = min(3, max(0.5, float(effect.get("zoom", 1))))
    chain = [
        "setpts=PTS-STARTPTS",
        f"fps={fps}",
        f"scale={width}:{height}:force_original_aspect_ratio=decrease",
        f"scale=trunc(iw*{zoom:.4f}/2)*2:trunc(ih*{zoom:.4f}/2)*2",
        f"crop=w='min(iw,{width})':h='min(ih,{height})'",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "setsar=1",
    ]
    if bool(effect.get("mirror", False)):
        chain.append("hflip")
    if float(effect.get("rotate", 0)):
        angle = max(-360, min(360, float(effect["rotate"])))
        chain.append(f"rotate={angle:.4f}*PI/180:c=black")
    brightness = max(-1, min(1, float(effect.get("brightness", 0))))
    contrast = max(0, min(3, float(effect.get("contrast", 1))))
    saturation = max(0, min(4, float(effect.get("saturation", 1))))
    chain.append(f"eq=brightness={brightness:.4f}:contrast={contrast:.4f}:saturation={saturation:.4f}")
    grain = max(0, min(40, int(effect.get("grain", 0))))
    if grain:
        chain.append(f"noise=alls={grain}:allf=t+u")
    chain += ["format=yuva420p"]
    opacity = max(0, min(1, float(effect.get("opacity", 1))))
    if opacity < 1:
        chain.append(f"colorchannelmixer=aa={opacity:.4f}")
    # Actual overlap transition: fade in the incoming layer over the previous clip.
    if item.transition_in != "cut" and item.transition_ms:
        boundary = item.start_ms + item.transition_ms
        if relative_start < boundary:
            # section starts at or after clip start; fade continues across boundaries
            passed = max(0, relative_start - item.start_ms)
            remaining = min(relative_end, boundary) - relative_start
            if passed == 0 and remaining > 0:
                chain.append(f"fade=t=in:st=0:d={max(0.001,item.transition_ms/1000):.4f}:alpha=1")
    if item.fade_in_ms and relative_start == item.start_ms:
        chain.append(f"fade=t=in:st=0:d={item.fade_in_ms/1000:.4f}:alpha=1")
    if item.fade_out_ms:
        start_fade = item.end_ms - item.fade_out_ms
        if relative_start <= start_fade < relative_end:
            chain.append(f"fade=t=out:st={(start_fade-relative_start)/1000:.4f}:d={item.fade_out_ms/1000:.4f}:alpha=1")
    chain.append(f"trim=duration={duration:.4f}")
    return ",".join(chain)


def _text_for_filter(value: str) -> str:
    # Filtergraph expression escaping (no shell); simple captions only.
    return (value.replace("\\", "\\\\\\\\").replace(":", "\\:")
            .replace("'", "\\'").replace("%", "\\%")
            .replace(",", "\\,").replace("[", "\\[")
            .replace("]", "\\]").replace("\n", " "))


def _one_section(project: StudioProject, start_ms: int, end_ms: int, output: Path,
                 width: int, height: int, fps: int,
                 stop: threading.Event | None) -> None:
    duration = (end_ms - start_ms) / 1000
    video = _visual_items(project, start_ms, end_ms)
    captions = _caption_items(project, start_ms, end_ms)
    args = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i",
            f"color=c=black:s={width}x{height}:r={fps}:d={duration:.6f}"]
    graph = ["[0:v]format=yuv420p[base0]"]
    base = "base0"
    for number, item in enumerate(video, start=1):
        trim_at = max(start_ms, item.start_ms)
        trim_end = min(end_ms, item.end_ms)
        offset = item.in_ms + trim_at - item.start_ms
        if item.kind == "image":
            args += ["-loop", "1", "-framerate", str(fps), "-i", item.asset]
        else:
            args += ["-ss", f"{offset/1000:.6f}", "-i", item.asset]
        label = f"v{number}"
        filter_text = _video_filter(item, width, height, fps, duration,
                                    start_ms, end_ms)
        graph.append(f"[{number}:v]{filter_text}[{label}]")
        target = f"base{number}"
        graph.append(f"[{base}][{label}]overlay=0:0:shortest=1:eof_action=pass:format=auto[{target}]")
        base = target
    for number, item in enumerate(captions):
        # Each section starts at an edit boundary, so only active captions
        # appear in this section. Handles native FFmpeg libfreetype.
        text = _text_for_filter(item.text)
        size = max(18, min(100, int(item.caption_style.get("font_size", 38))))
        color = str(item.caption_style.get("color", "white"))
        if not all(x.isalnum() or x in "#@" for x in color):
            color = "white"
        target = f"cap{number}"
        graph.append(f"[{base}]drawtext=text='{text}':fontcolor={color}:fontsize={size}:"
                     f"x=(w-text_w)/2:y=h-text_h-50:box=1:boxcolor=black@0.45[{target}]")
        base = target
    args += ["-filter_complex", ";".join(graph),
             "-map", f"[{base}]", "-an", "-t", f"{duration:.6f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    execute(args, stop)
    if not output.is_file() or output.stat().st_size < 1000:
        raise RuntimeError("Render section is missing/empty")


def _mix_audio(project: StudioProject, destination: Path,
               stop: threading.Event | None) -> Path | None:
    items = _audio_items(project)
    if not items:
        return None
    exe = ffmpeg_path()
    args = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    filters = []
    for index, item in enumerate(items):
        if not Path(item.asset).is_file():
            raise FileNotFoundError(item.asset)
        args += ["-i", item.asset]
        filters.append(f"[{index}:a:0]atrim=start={item.in_ms/1000:.4f}:"
                       f"end={item.out_ms/1000:.4f},asetpts=PTS-STARTPTS,"
                       f"aformat=sample_rates=48000:channel_layouts=stereo,"
                       f"volume={item.volume:.4f},"
                       f"adelay={item.start_ms}:all=1[a{index}]")
    refs = "".join(f"[a{i}]" for i in range(len(items)))
    filters.append(f"{refs}amix=inputs={len(items)}:duration=longest:normalize=0,"
                   f"atrim=duration={project.duration_ms/1000:.4f}[mixed]")
    args += ["-filter_complex", ";".join(filters), "-map", "[mixed]",
             "-c:a", "aac", "-b:a", "192k", str(destination)]
    execute(args, stop)
    return destination


def _concat(files: list[Path], output: Path, stop: threading.Event | None):
    manifest = output.with_suffix(".txt")
    # Each file is an internal predictable cache file, not user-provided path.
    manifest.write_text("".join("file '" + x.resolve().as_posix().replace("'", "'\\''") + "'\n"
                                for x in files), encoding="utf-8")
    try:
        execute([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                 "-f", "concat", "-safe", "0", "-i", str(manifest),
                 "-c:v", "copy", "-an", "-movflags", "+faststart", str(output)], stop)
    finally:
        manifest.unlink(missing_ok=True)


def render(project: StudioProject, dest: str | Path, *,
           cache_dir: str | Path | None = None, preview: bool = False,
           window: tuple[int, int] | None = None,
           progress: Progress | None = None,
           stop: threading.Event | None = None) -> Path:
    """Render new output. Reuse unchanged sections based on content/input fingerprints.

    For previews, output is a short low-resolution composition. For exports,
    full timeline is reassembled; compatible sections can be reused.
    """
    project.validate()
    if project.duration_ms < 100:
        raise ValueError("Timeline is empty")
    output = Path(dest).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"An output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    start_ms, end_ms = window if window else (0, project.duration_ms)
    start_ms = max(0, int(start_ms))
    end_ms = min(project.duration_ms, int(end_ms))
    if end_ms - start_ms < 100:
        raise ValueError("Preview/export range too short")
    width, height = project.width, project.height
    if preview:
        scale = min(1, 540 / max(width, height))
        width = max(2, round(width * scale / 2) * 2)
        height = max(2, round(height * scale / 2) * 2)
    fps = project.fps
    all_parts = _sections(project, start_ms, end_ms)
    if not all_parts:
        raise ValueError("No visible timeline range")
    with tempfile.TemporaryDirectory(prefix=".scene-work-", dir=output.parent) as scratch:
        root = Path(scratch)
        persistent = Path(cache_dir).expanduser() if cache_dir else root / "segments"
        persistent.mkdir(parents=True, exist_ok=True)
        chunks = []
        for index, (left, right) in enumerate(all_parts):
            relevant = _visual_items(project, left, right) + _caption_items(project, left, right)
            key = section_key(project, relevant, left, right, width, height, fps)
            section = persistent / (key + ".mp4")
            if not section.exists() or section.stat().st_size < 1000:
                staging = root / f"{index:04d}.mp4"
                _one_section(project, left, right, staging, width, height, fps, stop)
                if section.exists():
                    section.unlink()
                shutil.copyfile(staging, section)
            chunks.append(section)
            if progress:
                progress(5 + int((index+1)/len(all_parts)*75),
                         f"Rendering {index+1}/{len(all_parts)} (cached where possible)")
        joined = root / "visual.mp4"
        _concat(chunks, joined, stop)
        result = joined
        if not preview and _audio_items(project):
            audio = root / "mixed.m4a"
            _mix_audio(project, audio, stop)
            narrated = root / "full.mp4"
            execute([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin",
                     "-y", "-i", str(joined), "-i", str(audio),
                     "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
                     "-t", f"{project.duration_ms/1000:.4f}",
                     "-movflags", "+faststart", str(narrated)], stop)
            result = narrated
        if stop and stop.is_set():
            raise RuntimeError("Render cancelled")
        if not result.is_file() or result.stat().st_size < 1000:
            raise RuntimeError("Final render missing")
        # Intermediate file is on output filesystem, so os.replace is atomic.
        published = root / "publish.mp4"
        shutil.copyfile(result, published)
        os.replace(published, output)
        if progress:
            progress(100, "Video exported successfully")
        return output
