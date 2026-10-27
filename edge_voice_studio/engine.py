"""Online Edge synthesis, crash-resumable chunks, MP3/WAV and timed SRT."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable

from .core import english_voice, safe_title, settings_hash, split_script, write_srt
from .store import Store


class RenderStopped(Exception):
    pass


def ffmpeg_path() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def audio_duration_ms(path: Path) -> int:
    from mutagen.mp3 import MP3
    return int(MP3(path).info.length * 1000)


def concat_mp3(parts: list[Path], output: Path, executable: str | None = None) -> None:
    if not parts:
        raise ValueError("Cannot merge an empty narration")
    binary = executable or ffmpeg_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        manifest = Path(tmp) / "parts.ffconcat"
        lines = ["ffconcat version 1.0"]
        for p in parts:
            if not p.is_file() or p.stat().st_size == 0:
                raise RuntimeError(f"Empty voice segment: {p.name}")
            safe_path = str(p.resolve()).replace("\\", "/").replace("'", "'\\''")
            lines.append("file '" + safe_path + "'")
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        candidate = Path(tmp) / "final.mp3"
        result = subprocess.run(
            [binary, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", str(manifest),
             "-c:a", "copy", str(candidate)],
            capture_output=True, text=True, timeout=3600)
        if result.returncode or not candidate.is_file() or candidate.stat().st_size == 0:
            raise RuntimeError("Audio merge failed: " + result.stderr[-800:])
        os.replace(candidate, output)


def to_wav(mp3: Path, wav: Path, executable: str | None = None) -> None:
    binary = executable or ffmpeg_path()
    tmp = wav.with_suffix(".partial.wav")
    try:
        result = subprocess.run(
            [binary, "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(mp3), "-vn", "-c:a", "pcm_s16le", str(tmp)],
            capture_output=True, text=True, timeout=3600)
        if result.returncode or not tmp.is_file() or not tmp.stat().st_size:
            raise RuntimeError("WAV conversion failed: " + result.stderr[-800:])
        os.replace(tmp, wav)
    finally:
        tmp.unlink(missing_ok=True)


async def list_english_voices() -> list[dict]:
    import edge_tts
    available = await edge_tts.list_voices()
    filtered = []
    for row in available:
        name = row.get("ShortName", "")
        if english_voice(name) and str(row.get("Locale", "")).lower().startswith("en-"):
            filtered.append({
                "name": name, "gender": row.get("Gender", ""),
                "locale": row.get("Locale", ""),
                "display": name.split("-")[-1].removesuffix("Neural"),
            })
    return sorted(filtered, key=lambda v: (v["locale"], v["display"]))


async def synthesize_chunk(text: str, voice: str, rate: int, pitch: int,
                           volume: int, target: Path,
                           stopped: Callable[[], bool] = lambda: False) -> list[dict]:
    """Write a .part file and atomically promote it only when stream is complete."""
    import edge_tts
    part = target.with_suffix(".partial.mp3")
    boundaries: list[dict] = []
    communicate = edge_tts.Communicate(
        text, voice=voice, rate=f"{rate:+d}%", pitch=f"{pitch:+d}Hz",
        volume=f"{volume:+d}%")
    try:
        with part.open("wb") as f:
            async for event in communicate.stream():
                if stopped():
                    raise RenderStopped("Narration paused")
                if event.get("type") == "audio":
                    f.write(event["data"])
                elif event.get("type") == "WordBoundary":
                    boundaries.append({
                        "text": event.get("text", ""),
                        "offset": event.get("offset", 0),
                        "duration": event.get("duration", 0),
                    })
        if not part.is_file() or part.stat().st_size == 0:
            raise RuntimeError("Voice service returned empty audio")
        os.replace(part, target)
        return boundaries
    finally:
        part.unlink(missing_ok=True)


async def render_job(store: Store, job_id: str, output_dir: Path, cache_dir: Path,
                     stopped: Callable[[], bool] = lambda: False,
                     progress: Callable[[int, int], None] = lambda a, b: None,
                     synthesis=synthesize_chunk) -> Path:
    job = store.get(job_id)
    if job["status"] not in {"queued", "processing"}:
        raise RenderStopped("Job not queued")
    chunks = split_script(job["script"])
    signature = settings_hash(job["script"], job["voice"], job["rate"],
                              job["pitch"], job["volume"])
    work = Path(cache_dir) / (job_id + "-" + signature[:10])
    work.mkdir(parents=True, exist_ok=True)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    store.update(job_id, status="processing", error="")
    parts: list[Path] = []
    subtitle_parts: list[tuple[list[dict], int]] = []
    try:
        for index, text in enumerate(chunks):
            if stopped() or store.get(job_id)["status"] != "processing":
                raise RenderStopped("Job paused or cancelled")
            audio = work / f"{index:05}.mp3"
            timings = work / f"{index:05}.json"
            # Old / interrupted caches may contain audio without usable timing
            # events. Regenerate those chunks rather than exporting a fake SRT.
            try:
                cached_words = json.loads(timings.read_text(encoding="utf-8"))
                has_timings = isinstance(cached_words, list) and bool(cached_words)
            except (OSError, ValueError, TypeError):
                has_timings = False
            if (not audio.is_file() or audio.stat().st_size == 0
                    or not has_timings):
                audio.unlink(missing_ok=True)
                timings.unlink(missing_ok=True)
                last_exc = None
                for attempt in range(3):
                    if stopped() or store.get(job_id)["status"] != "processing":
                        raise RenderStopped("Job paused or cancelled")
                    try:
                        words = await synthesis(
                            text, job["voice"], job["rate"], job["pitch"],
                            job["volume"], audio, stopped)
                        if not words:
                            raise RuntimeError(
                                "Edge TTS returned no word timings; accurate SRT unavailable")
                        timings.write_text(json.dumps(words), encoding="utf-8")
                        last_exc = None
                        break
                    except RenderStopped:
                        raise
                    except Exception as exc:
                        audio.unlink(missing_ok=True)
                        last_exc = exc
                        if attempt != 2:
                            await asyncio.sleep(min(6.0, 0.8 * 2 ** attempt))
                if last_exc is not None:
                    raise RuntimeError(f"Chunk {index+1}/{len(chunks)}: {last_exc}")
            try:
                words = json.loads(timings.read_text(encoding="utf-8")) if timings.exists() else []
            except (OSError, ValueError):
                words = []
            parts.append(audio)
            subtitle_parts.append((words, audio_duration_ms(audio)))
            store.update(job_id, completed=index + 1)
            progress(index + 1, len(chunks))

        if stopped() or store.get(job_id)["status"] != "processing":
            raise RenderStopped("Job paused or cancelled")
        # Reserve matching filenames without overwriting another job's exports.
        stem = safe_title(job["title"])
        destination = output_dir / (stem + ".mp3")
        suffix = 2
        while destination.exists() or destination.with_suffix(".srt").exists():
            destination = output_dir / f"{stem} ({suffix}).mp3"
            suffix += 1

        # Both files must be valid before either appears in the output folder.
        with tempfile.TemporaryDirectory(prefix=".edge-tts-", dir=output_dir) as tmp:
            staged_mp3 = Path(tmp) / "voice.mp3"
            staged_srt = Path(tmp) / "voice.srt"
            concat_mp3(parts, staged_mp3)
            count = write_srt(subtitle_parts, staged_srt)
            if count == 0 or staged_srt.stat().st_size == 0:
                raise RuntimeError("Synchronized SRT could not be generated")
            if stopped() or store.get(job_id)["status"] != "processing":
                raise RenderStopped("Job paused or cancelled")
            os.replace(staged_mp3, destination)
            try:
                os.replace(staged_srt, destination.with_suffix(".srt"))
            except Exception:
                destination.unlink(missing_ok=True)
                raise
        store.update(job_id, status="done", completed=len(chunks), output=str(destination))
        return destination
    except RenderStopped:
        if store.get(job_id)["status"] == "processing":
            store.update(job_id, status="paused")
        raise
    except Exception as exc:
        store.update(job_id, status="failed", error=str(exc)[:2000])
        raise


async def generate_preview(text: str, voice: str, rate: int, pitch: int,
                           volume: int, target: Path) -> Path:
    if not text.strip():
        raise ValueError("Enter a script to preview")
    if not english_voice(voice):
        raise ValueError("Choose an English voice")
    target.parent.mkdir(parents=True, exist_ok=True)
    await synthesize_chunk(" ".join(text.split())[:480], voice, rate, pitch, volume, target)
    return target
