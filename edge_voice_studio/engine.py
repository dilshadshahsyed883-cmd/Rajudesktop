"""Online Edge synthesis, crash-resumable chunks, MP3/WAV and timed SRT."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Callable

from .core import MAX_CHUNK, english_voice, safe_title, settings_hash, split_script
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


# Online Edge streaming can stall without raising. Keep the deadline conservative
# for long 2,600-character chunks; never leave a request running indefinitely.
SYNTH_TIMEOUT_SECONDS = 240.0


def edge_stream_count(configured: int | None = None) -> int:
    """Clamp the PC setting to 1–20 online requests; default to ten."""
    try:
        choice = configured if configured is not None else os.environ.get("EDGE_VOICE_STREAMS", "10")
        return max(1, min(20, int(choice)))
    except (TypeError, ValueError):
        return 10


async def render_job(store: Store, job_id: str, output_dir: Path, cache_dir: Path,
                     stopped: Callable[[], bool] = lambda: False,
                     progress: Callable[[int, int], None] = lambda a, b: None,
                     synthesis=synthesize_chunk,
                     parallel_chunks: int | None = None) -> Path:
    job = store.get(job_id)
    if job["status"] not in {"queued", "processing"}:
        raise RenderStopped("Job not queued")
    # Immutable per-job value keeps chunk boundaries stable after changing Settings.
    chunks = split_script(job["script"], limit=int(job.get("chunk_size", MAX_CHUNK)))
    signature = settings_hash(job["script"], job["voice"], job["rate"],
                              job["pitch"], job["volume"])
    work = Path(cache_dir) / (job_id + "-" + signature[:10])
    work.mkdir(parents=True, exist_ok=True)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    store.update(job_id, status="processing", error="")

    # Query SQLite at most twice per second, even when the stream emits many
    # audio events. Stop callbacks remain responsive without a DB hit per frame.
    state_check = [0.0, False]

    def interrupted() -> bool:
        if stopped():
            return True
        now = time.monotonic()
        if now - state_check[0] >= 0.5:
            state_check[0] = now
            state_check[1] = store.get(job_id)["status"] != "processing"
        return state_check[1]

    def metric(event: str, index: int, seconds: float, attempt: int = 0) -> None:
        # No narration text, network payloads or credentials in diagnostics.
        try:
            with (work / "performance.log").open("a", encoding="utf-8") as log:
                log.write(
                    f"{time.time():.0f} chunk={index+1}/{len(chunks)} "
                    f"event={event} attempt={attempt} seconds={seconds:.2f}\n")
        except OSError:
            pass  # Metrics must never affect a completed voice.

    async def render_chunk(index: int, text: str) -> int:
        if interrupted():
            raise RenderStopped("Job paused or cancelled")
        audio = work / f"{index:05}.mp3"
        timings = work / f"{index:05}.json"
        if audio.is_file() and audio.stat().st_size > 0 and timings.is_file():
            metric("cached", index, 0)
            return index

        audio.unlink(missing_ok=True)
        timings.unlink(missing_ok=True)
        last_exc: Exception | None = None
        for attempt in range(3):
            if interrupted():
                raise RenderStopped("Job paused or cancelled")
            started = time.monotonic()
            try:
                words = await asyncio.wait_for(
                    synthesis(text, job["voice"], job["rate"], job["pitch"],
                              job["volume"], audio, interrupted),
                    timeout=SYNTH_TIMEOUT_SECONDS)
                if interrupted():
                    raise RenderStopped("Job paused or cancelled")
                timings.write_text(json.dumps(words), encoding="utf-8")
                metric("success", index, time.monotonic() - started, attempt + 1)
                return index
            except RenderStopped:
                raise
            except Exception as exc:
                audio.unlink(missing_ok=True)
                timings.unlink(missing_ok=True)
                last_exc = exc
                metric("timeout" if isinstance(exc, TimeoutError) else
                       "error_" + type(exc).__name__, index,
                       time.monotonic() - started, attempt + 1)
                if attempt < 2:
                    # Small backoff to avoid hammering Edge if it is throttling.
                    await asyncio.sleep((1.5, 3.0)[attempt])

        raise RuntimeError(
            f"Chunk {index+1}/{len(chunks)} failed after 3 attempts: "
            f"{type(last_exc).__name__}")

    parts: list[Path] = []
    completed: set[int] = set()
    contiguous = 0
    streams = edge_stream_count(parallel_chunks)
    try:
        # Rolling window: immediately replace whichever request finishes first.
        # Always keep <= streams requests running; avoid batch-wide barriers.
        pending: set[asyncio.Task[int]] = set()
        next_index = 0

        def fill_slots() -> None:
            nonlocal next_index
            while next_index < len(chunks) and len(pending) < streams:
                if interrupted():
                    raise RenderStopped("Job paused or cancelled")
                pending.add(asyncio.create_task(
                    render_chunk(next_index, chunks[next_index])))
                next_index += 1

        try:
            fill_slots()
            while pending:
                if interrupted():
                    raise RenderStopped("Job paused or cancelled")
                finished, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED)

                # Consume all finished tasks, including concurrent failures,
                # before scheduling any replacements.
                outcomes = await asyncio.gather(*finished, return_exceptions=True)
                failures = [value for value in outcomes if isinstance(value, BaseException)]
                if failures:
                    raise failures[0]
                for index in outcomes:
                    completed.add(index)
                    while contiguous in completed:
                        parts.append(work / f"{contiguous:05}.mp3")
                        contiguous += 1
                        store.update(job_id, completed=contiguous)
                        progress(contiguous, len(chunks))
                        if interrupted():
                            raise RenderStopped("Job paused or cancelled")
                fill_slots()
        finally:
            # On failure, pause, cancel or shutdown never leave orphan requests.
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        if interrupted():
            raise RenderStopped("Job paused or cancelled")
        stem = safe_title(job["title"]) + "-" + job_id[:8]
        destination = output_dir / (stem + ".mp3")
        concat_mp3(parts, destination)
        # Auto SRT stays on its own queue after the verified MP3 is committed.
        store.complete_voice(job_id, str(destination), len(chunks))
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
