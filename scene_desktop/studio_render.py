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
from .effects import visual_filters, overlay_position
from .word_captions import ass_for_section
from .chunk_pipeline import plan_chunks, ChunkStore

Progress = Callable[[int, str], None]


def execute(args: list[str], stop: threading.Event | None = None, cwd: Path | None = None):
    """Cancelable external render process; never run a shell command."""
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=cwd)
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
            lut = record.get("effects", {}).get("lut_file")
            if lut:
                file = Path(lut)
                if not file.is_file():
                    raise FileNotFoundError(f"Missing color LUT file: {file}")
                stat_lut = file.stat()
                record["lut_stat"] = (stat_lut.st_size,stat_lut.st_mtime_ns)
        result.append(record)
    return result


def section_key(project: StudioProject, items: list[Item], start_ms: int, end_ms: int,
                width: int, height: int, fps: int) -> str:
    payload = {
        "engine": 5,
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
    return sorted(items, key=lambda i: (rank[i.track_id], i.start_ms, i.id))


def _caption_items(project: StudioProject, start_ms: int, end_ms: int) -> list[Item]:
    captions = {t.id for t in project.tracks if t.kind == "captions" and t.visible}
    return [i for i in project.items if i.track_id in captions and i.kind == "text" and
            i.start_ms < end_ms and i.end_ms > start_ms]


def _audio_items(project: StudioProject) -> list[Item]:
    audible = {t.id for t in project.tracks if t.kind in AUDIO_TRACKS and not t.muted}
    explicit = [i for i in project.items if i.track_id in audible and i.kind == "audio"]
    # Optional original video sound. The visual track determines its timing;
    # silent video files must keep this opt-in setting disabled.
    for item in project.items:
        if item.kind == "video" and item.effects.get("source_audio") and not project.track(item.track_id).muted:
            explicit.append(Item(asset=item.asset, kind="audio", track_id="voice",
                                 start_ms=item.start_ms, in_ms=item.in_ms,
                                 out_ms=item.out_ms, volume=item.volume,
                                 fade_in_ms=item.fade_in_ms, fade_out_ms=item.fade_out_ms))
    return explicit


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
    elapsed = max(0., (relative_start - item.start_ms)/1000)
    chain = visual_filters(item.effects, width, height, fps, duration, elapsed,
                           keyframes=item.keyframes)
    if item.transition_in in {"fade", "dissolve"} and item.transition_ms:
        passed = max(0, relative_start - item.start_ms)
        if passed < item.transition_ms:
            # The next section begins at a source-time edit boundary. Alpha
            # fades start on the incoming clip; never substitute a generic fade.
            length = item.transition_ms/1000
            chain.append(f"fade=t=in:st=0:d={length:.4f}:alpha={1 if item.transition_in=='dissolve' else 0}")
    if item.fade_in_ms and relative_start == item.start_ms:
        chain.append(f"fade=t=in:st=0:d={item.fade_in_ms/1000:.4f}:alpha=1")
    if item.fade_out_ms:
        fade_start = item.end_ms - item.fade_out_ms
        if relative_start <= fade_start < relative_end:
            chain.append(f"fade=t=out:st={(fade_start-relative_start)/1000:.4f}:d={item.fade_out_ms/1000:.4f}:alpha=1")
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
                 stop: threading.Event | None, frames: int | None = None) -> None:
    frame_total = frames if frames is not None else max(1, round((end_ms-start_ms)*fps/1000))
    duration = frame_total / fps
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
        lut_file = str(item.effects.get("lut_file") or "")
        if lut_file:
            selected = Path(lut_file)
            if (not selected.is_file() or selected.suffix.lower() != ".cube"
                    or selected.stat().st_size > 50*1024*1024):
                raise ValueError(f"Invalid/missing .cube LUT: {selected}")
            key = hashlib.sha256((str(selected.resolve())+str(selected.stat().st_mtime_ns)).encode()).hexdigest()[:18]
            local_name = f"scene_lut_{key}.cube"
            local_path = output.parent / local_name
            if not local_path.is_file():
                shutil.copyfile(selected, local_path)
            filter_text = filter_text.replace(
                "format=yuva420p",f"format=rgb24,lut3d=file={local_name}:interp=tetrahedral,format=yuva420p",1)
        graph.append(f"[{number}:v]{filter_text}[{label}]")
        target = f"base{number}"
        x_pos, y_pos = overlay_position(item.transition_in, item.transition_ms/1000,
                                         max(0, start_ms-item.start_ms)/1000)
        graph.append(f"[{base}][{label}]overlay=x='{x_pos}':y='{y_pos}':"
                     f"eval=frame:shortest=1:eof_action=pass:format=auto[{target}]")
        base = target
    regular = [x for x in captions if not x.caption_style.get("karaoke_words")]
    for number, item in enumerate(regular):
        # Ordinary caption text uses FFmpeg drawtext.
        text = _text_for_filter(item.text)
        size = max(18, min(100, int(item.caption_style.get("font_size", 38))))
        color = str(item.caption_style.get("color", "white"))
        if not all(x.isalnum() or x in "#@" for x in color):
            color = "white"
        target = f"cap{number}"
        graph.append(f"[{base}]drawtext=text='{text}':fontcolor={color}:fontsize={size}:"
                     f"x=(w-text_w)/2:y=h-text_h-50:box=1:boxcolor=black@0.45[{target}]")
        base = target
    karaoke = [x for x in captions if x.caption_style.get("karaoke_words")]
    if karaoke:
        ass_path = output.parent / f"scene_karaoke_{start_ms}_{end_ms}.ass"
        ass_path.write_text(ass_for_section(karaoke, start_ms,end_ms,width,height),
                            encoding="utf-8")
        graph.append(f"[{base}]ass=filename={ass_path.name}[karaoke]")
        base = "karaoke"
    args += ["-filter_complex", ";".join(graph),
             "-map", f"[{base}]", "-an", "-frames:v", str(frame_total),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    execute(args, stop, cwd=output.parent)
    if not output.is_file() or output.stat().st_size < 1000:
        raise RuntimeError("Render section is missing/empty")


def _mix_audio(project: StudioProject, destination: Path,
               stop: threading.Event | None,
               window: tuple[int,int] | None = None) -> Path | None:
    """Mix narration, SFX and music, including a short preview audio window."""
    first, last = window if window else (0, project.duration_ms)
    items = [i for i in _audio_items(project) if i.start_ms < last and i.end_ms > first]
    if not items:
        return None
    exe = ffmpeg_path()
    args = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    filters = []
    for index, item in enumerate(items):
        if not Path(item.asset).is_file():
            raise FileNotFoundError(item.asset)
        actual_start = max(item.start_ms, first)
        actual_end = min(item.end_ms, last)
        seek = (item.in_ms + actual_start - item.start_ms) / 1000
        span = (actual_end - actual_start) / 1000
        args += ["-ss", f"{seek:.5f}", "-t", f"{span:.5f}", "-i", item.asset]
        chain = [f"[{index}:a:0]asetpts=PTS-STARTPTS",
                 "aformat=sample_rates=48000:channel_layouts=stereo",
                 f"volume={item.volume:.4f}"]
        # Fades are applied relative to the source clip's timeline start/end.
        if item.fade_in_ms and actual_start == item.start_ms:
            chain.append(f"afade=t=in:st=0:d={item.fade_in_ms/1000:.4f}")
        fade_at = item.end_ms - item.fade_out_ms
        if item.fade_out_ms and actual_start <= fade_at < actual_end:
            chain.append(f"afade=t=out:st={(fade_at-actual_start)/1000:.4f}:d={item.fade_out_ms/1000:.4f}")
        chain.append(f"adelay={actual_start-first}:all=1[a{index}]")
        filters.append(",".join(chain))
    refs = "".join(f"[a{i}]" for i in range(len(items)))
    filters.append(f"{refs}amix=inputs={len(items)}:duration=longest:normalize=0,"
                   f"apad=whole_dur={(last-first)/1000:.4f},"
                   f"atrim=duration={(last-first)/1000:.4f}[mixed]")
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



def prune_render_cache(cache_dir: str | Path, maximum_bytes: int = 2 * 1024**3,
                       protected: tuple[Path, ...] = ()) -> int:
    """Remove only old, cache-owned section MP4 files; never user source assets."""
    root = Path(cache_dir)
    if not root.is_dir():
        return 0
    files = sorted(
        (f for f in root.glob("*.mp4") if f.is_file() and not f.is_symlink()),
        key=lambda f: f.stat().st_mtime,
    )
    protected_names = {str(p.resolve()) for p in protected}
    total = sum(p.stat().st_size for p in files)
    deleted = 0
    for path in files:
        if total <= maximum_bytes:
            break
        if str(path.resolve()) in protected_names:
            continue
        size = path.stat().st_size
        path.unlink()
        total -= size
        deleted += 1
    return deleted


def verify_scratch_room(output: Path, reserve_bytes: int = 512 * 1024**2) -> None:
    if shutil.disk_usage(output.parent).free < reserve_bytes:
        raise RuntimeError("Insufficient free disk for rendering: keep at least 512 MiB free")


def render(project: StudioProject, dest: str | Path, *,
           cache_dir: str | Path | None = None, preview: bool = False,
           window: tuple[int, int] | None = None,
           preview_side: int = 540, max_chunk_ms: int = 5000,
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
    verify_scratch_room(output)
    start_ms, end_ms = window if window else (0, project.duration_ms)
    start_ms = max(0, int(start_ms))
    end_ms = min(project.duration_ms, int(end_ms))
    if end_ms - start_ms < 100:
        raise ValueError("Preview/export range too short")
    width, height = project.width, project.height
    if preview:
        if preview_side not in (360, 540, 720, 960):
            raise ValueError("Preview size must be 360, 540, 720 or 960")
        scale = min(1, preview_side / max(width, height))
        width = max(2, round(width * scale / 2) * 2)
        height = max(2, round(height * scale / 2) * 2)
    fps = project.fps
    all_parts = plan_chunks(project, start_ms, end_ms, max_ms=max_chunk_ms)
    if not all_parts:
        raise ValueError("No visible timeline range")
    with tempfile.TemporaryDirectory(prefix=".scene-work-", dir=output.parent) as scratch:
        root = Path(scratch)
        persistent = Path(cache_dir).expanduser() if cache_dir else root / "segments"
        store = ChunkStore(persistent)
        plans = []
        for part in all_parts:
            relevant = (_visual_items(project, part.start_ms, part.end_ms)
                        + _caption_items(project, part.start_ms, part.end_ms))
            signature = section_key(project, relevant, part.start_ms,
                                    part.end_ms, width, height, fps)
            plans.append((part, signature))
        signatures = [key for _, key in plans]
        verified = []
        if cache_dir and not preview:
            store.checkpoint(output, signatures, verified, "rendering")
        chunks = []
        for index, (part, key) in enumerate(plans):
            if stop and stop.is_set():
                raise RuntimeError("Render cancelled; committed chunks retained for resume")
            if store.valid(key, part):
                section = store.section_path(key)
                reused = True
            else:
                staging = root / f"{index:04d}.mp4"
                _one_section(project, part.start_ms, part.end_ms, staging,
                             width, height, fps, stop, frames=part.frames)
                section = store.commit(key, part, staging)
                reused = False
            chunks.append(section)
            verified.append(key)
            if cache_dir and not preview:
                store.checkpoint(output, signatures, verified, "rendering")
            if progress:
                progress(5 + int((index + 1) / len(plans) * 75),
                         f"Chunk {index+1}/{len(plans)}: {'reused' if reused else 'rendered'} "
                         f"({len(verified)}/{len(signatures)} saved for restart)")
        joined = root / "visual.mp4"
        _concat(chunks, joined, stop)
        result = joined
        if _audio_items(project):
            audio = root / "mixed.m4a"
            audio_result = _mix_audio(project, audio, stop, (start_ms, end_ms))
            if audio_result:
                narrated = root / "full.mp4"
                execute([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin",
                         "-y", "-i", str(joined), "-i", str(audio),
                         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
                         "-t", f"{sum(part.frames for part in all_parts)/fps:.6f}",
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
        if cache_dir and not preview:
            store.checkpoint(output, signatures, verified, "complete")
        if cache_dir:
            prune_render_cache(persistent, protected=tuple(chunks))
        if progress:
            progress(100, "Video exported successfully")
        return output
