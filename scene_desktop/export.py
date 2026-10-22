"""FFmpeg-based CPU-safe MVP export; source assets are never modified."""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import threading
from typing import Callable

from .core import Project
from .media import ffmpeg_path

Progress = Callable[[int, str], None]


def _execute(args: list[str], stop: threading.Event | None) -> None:
    """Cancelable FFmpeg process with bounded error output; no shell execution."""
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
                raise RuntimeError("Export cancelled")
            try:
                _, stderr = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise RuntimeError((stderr or b"").decode("utf-8", "replace")[-2200:] or
                               f"FFmpeg failed with code {process.returncode}")
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def export_mp4(project: Project, output: str | Path,
               progress: Progress | None = None,
               stop: threading.Event | None = None) -> Path:
    """Render visual cuts then optionally mix full-length narration into an MP4.

    MVP boundary: per-clip original sound is NOT mixed; narration is the optional
    audio track. Transitions/LUTs and complex compositing are future milestones.
    """
    project.validate()
    if not project.clips:
        raise ValueError("Add clips before exporting")
    for clip in project.clips:
        if not Path(clip.path).is_file():
            raise FileNotFoundError(f"Missing source: {clip.path}")
    if project.narration and not Path(project.narration).is_file():
        raise FileNotFoundError(f"Missing narration: {project.narration}")
    target = Path(output).expanduser().resolve()
    if target.suffix.lower() != ".mp4":
        raise ValueError("Output must end in .mp4")
    if target.exists():
        raise FileExistsError(f"Use another output filename; existing export is preserved: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    exe = ffmpeg_path()
    vf = (f"scale={project.width}:{project.height}:force_original_aspect_ratio=decrease,"
          f"pad={project.width}:{project.height}:(ow-iw)/2:(oh-ih)/2,"
          f"setsar=1,fps={project.fps},format=yuv420p")
    with tempfile.TemporaryDirectory(prefix=".sds-render-", dir=target.parent) as scratch:
        root = Path(scratch)
        segments = []
        for index, clip in enumerate(project.clips):
            segment = root / f"clip_{index:05d}.mp4"
            span = f"{clip.duration_ms / 1000:.3f}"
            if clip.kind == "image":
                source_args = ["-loop", "1", "-framerate", str(project.fps), "-i", clip.path]
            else:
                source_args = ["-i", clip.path, "-ss", f"{clip.in_ms / 1000:.3f}"]
            cmd = ([exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"] +
                   source_args + ["-t", span, "-vf", vf, "-an", "-c:v", "libx264",
                   "-preset", "veryfast", "-crf", "23", "-movflags", "+faststart", str(segment)])
            _execute(cmd, stop)
            if not segment.is_file() or segment.stat().st_size < 1024:
                raise RuntimeError(f"Clip {index + 1}: FFmpeg produced no usable video")
            segments.append(segment)
            if progress:
                progress(round(5 + (index + 1) / len(project.clips) * 75),
                         f"Rendered {index + 1}/{len(project.clips)} clips")
        manifest = root / "join.txt"
        manifest.write_text("".join(f"file '{x.name}'\n" for x in segments), encoding="utf-8")
        joined = root / "joined.mp4"
        _execute([exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f",
                  "concat", "-safe", "0", "-i", str(manifest), "-c:v", "copy",
                  "-movflags", "+faststart", str(joined)], stop)
        result = joined
        if project.narration:
            narrated = root / "narrated.mp4"
            _execute([exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                      "-i", str(joined), "-i", project.narration, "-filter_complex",
                      "[1:a:0]apad[aout]", "-map", "0:v:0", "-map", "[aout]",
                      "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                      "-t", f"{project.duration_ms / 1000:.3f}",
                      "-movflags", "+faststart", str(narrated)], stop)
            result = narrated
        if stop and stop.is_set():
            raise RuntimeError("Export cancelled")
        if not result.exists() or result.stat().st_size < 1024:
            raise RuntimeError("Final MP4 validation failed")
        # Same filesystem staging then atomic publish; source originals never touched.
        shutil.move(str(result), str(target))
        if progress:
            progress(100, "MP4 export complete")
    return target
