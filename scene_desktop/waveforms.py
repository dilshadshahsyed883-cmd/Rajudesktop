"""Cache-only waveform previews for narration/music/SFX timeline clips."""
from __future__ import annotations
from pathlib import Path
import hashlib
import subprocess

from .media import ffmpeg_path


def waveform_path(source: str | Path, cache_dir: str | Path) -> Path:
    path=Path(source)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    stat=path.stat()
    token=f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    name=hashlib.sha256(token.encode("utf-8")).hexdigest()[:28] + ".png"
    return Path(cache_dir) / name


def generate_waveform(source: str | Path, cache_dir: str | Path,
                      width: int = 640, height: int = 72) -> Path:
    if not 160 <= width <= 2048 or not 32 <= height <= 256:
        raise ValueError("Waveform display dimensions out of range")
    output=waveform_path(source,cache_dir)
    if output.is_file() and output.stat().st_size>64:
        return output
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=output.with_suffix(".temp.png")
    cmd=[ffmpeg_path(),"-hide_banner","-loglevel","error","-nostdin","-y",
         "-t","240","-i",str(Path(source).resolve()),
         "-filter_complex",
         f"aformat=channel_layouts=mono,showwavespic=s={width}x{height}:colors=cyan",
         "-frames:v","1",str(stage)]
    try:
        subprocess.run(cmd,check=True,timeout=75,capture_output=True)
        if not stage.is_file() or stage.stat().st_size<64:
            raise RuntimeError("FFmpeg waveform output missing")
        stage.replace(output)
    finally:
        stage.unlink(missing_ok=True)
    return output
