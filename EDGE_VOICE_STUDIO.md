# Edge Voice Studio - Auto SRT integrated Windows executable

Canonical source: `edge_voice_studio/` on `main`. The existing
`voice_to_srt_batch/voice_to_srt_studio/engine.py` is reused directly
without running the separate Tk batch SRT application.

## Single EXE / one control

The standard EdgeVoiceStudio application contains one persistent checkbox in
the left navigation: **Auto SRT after MP3 (3-4 sec)**. It applies to both the
single script **Add to Queue** and **Batch Studio** multi-TXT submission.
The checkbox state is persisted as a preference and copied to each job on
submission; changing it later does not alter existing queue jobs.

- Unchecked: create MP3 only.
- Checked: complete and save MP3, then automatically enqueue its audio for
  Whisper `small` / English / `Recommended (3-4 sec)` word-aligned SRT.
- The SRT worker is separate from voice synthesis; the next queued voice
  continues while subtitle transcription runs.
- Output paths always share one parent and base name:
  `VideoName-<job-id>.mp3` and `VideoName-<job-id>.srt`.
- An existing nonempty SRT is preserved rather than overwritten.
- Subtitle transcription errors leave the completed MP3 safe and visible.
  Select a completed job and choose **Resume / Retry** to retry subtitles.
- Queued SRT and speech jobs survive restart; interrupted SRT jobs become pending.
- A failed model download marks affected pending jobs failed; retry from queue
  after network/model issues are resolved.
- Existing completed older jobs are not silently re-transcribed on upgrade.

SRT cues target 3-4 seconds, respecting real spoken word boundaries and pauses;
unusual phrases/silences may produce a shorter/longer cue.

## Distribution

GitHub Actions workflow `.github/workflows/edge-voice.yml` runs Windows unit
tests, native GUI smoke test, `--onefile` PyInstaller compilation and a **frozen
EXE speech-engine import smoke test**. On a successful push to main, it publishes
a GitHub Release containing **EdgeVoiceStudio.exe** directly and a checksum.
The executable does **not** need an adjacent `_internal` directory. Do not
ship a `--onedir` bundle or ask users to start a separate SRT app.

This is a self-contained Windows binary for Python application dependencies;
the Whisper `small` model is downloaded once on first SRT use into the normal
Windows user cache, NOT an EXE-adjacent internal folder. The packed program
temporarily extracts its runtime to Windows temporary storage when launched.
Edge TTS synthesis requires a network connection.

The old VoiceToSRTStudioBatch executable remains a separate standalone utility
with its original code and Windows build workflow untouched.

## Developer/test

```powershell
python -m pip install -r requirements-edge-voice.txt
python -m unittest discover -s tests -p "test_edge_voice*.py" -v
cd voice_to_srt_batch && python -m unittest discover -s tests -v && cd ..
python launch_edge_voice.py --self-test
python launch_edge_voice.py
```

SQLite lives in normal application data. Output folder and cache folder remain
configurable, independent of the bundled EXE. No VPS or existing CapCut/Z Builder
configuration is changed.
