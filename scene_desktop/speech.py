"""Local CPU Whisper transcription with word-level timing, no external audio upload.

A model can be downloaded only when the operator explicitly authorizes it.
The application bundles the faster-whisper runtime, but model weights are
stored separately in the user's own Desktop Studio application-data folder.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

MODELS={"tiny","base","small"}
MAX_WORDS=20000


def transcribe_local(audio_path: str | Path, model_name: str,
                     models_dir: str | Path, allow_download: bool = False,
                     progress: Callable[[str],None] | None = None) -> dict:
    file=Path(audio_path).expanduser()
    if not file.is_file():
        raise FileNotFoundError(f"Missing audio file: {file}")
    if model_name not in MODELS:
        raise ValueError("Select tiny, base or small Whisper model")
    root=Path(models_dir).expanduser()
    root.mkdir(parents=True,exist_ok=True)
    if progress:
        progress("Loading offline Whisper CPU model; first approved download may be large")
    try:
        from faster_whisper import WhisperModel
    except (ImportError,OSError) as exc:
        raise RuntimeError("Windows Whisper runtime not bundled in this build") from exc
    try:
        model=WhisperModel(model_name,device="cpu",compute_type="int8",
                           download_root=str(root),local_files_only=not allow_download,
                           cpu_threads=4,num_workers=1)
    except Exception as exc:
        raise RuntimeError(
            "Model is unavailable locally. Choose Download once in the app to "
            "authorize model weights, or import Whisper word JSON."
        ) from exc
    if progress:
        progress("Analyzing narration; speech recognition runs locally on CPU")
    segments,info=model.transcribe(str(file),beam_size=3,
                                   vad_filter=True,word_timestamps=True,
                                   condition_on_previous_text=False)
    rows=[]
    for segment in segments:
        for word in (segment.words or []):
            if word.start is None or word.end is None or not word.word.strip():
                continue
            if word.end <= word.start:
                continue
            rows.append({"word":word.word.strip(),
                         "start":round(float(word.start),3),
                         "end":round(float(word.end),3)})
            if len(rows)>MAX_WORDS:
                raise ValueError("Narration exceeds 20,000 recognized words")
    if not rows:
        raise ValueError("No words found in the selected voice-over")
    return {"words":rows,
            "language":str(getattr(info,"language","unknown")),
            "model":model_name,
            "engine":"faster-whisper / CTranslate2 (local CPU)",
            "source":str(file.resolve())}
