# Voice → SRT Studio — Batch Edition

An independent Windows desktop app with a single-file workflow plus multiple-voice batch processing. The existing Edge Voice Studio remains unchanged.

## Start

Unzip to a folder and double-click `start.bat`. Python 3.10–3.12 recommended. The launcher creates a `.venv` inside the app folder and installs `faster-whisper` on first run. First transcription downloads the selected model; when already cached, it can run offline. CPU transcription time depends on file length and model size. No `.exe` or online speech service is required.

## Use

1. Click **Add audio files** (select any number) or **Add folder** (add all supported voices in a folder). Selecting just one file runs the same single-voice workflow.
2. Choose output setting: **Same folders as voices**, or **Choose output folder**. Each input `name.mp3` creates `name.srt`.
3. Choose speech model (`small` default), language (`English` default) and subtitle duration (`Recommended 3-4 sec` default).
4. Click **Generate batch SRT**. All items run **sequentially**, reusing the model. See each file's progress, generated path, and errors.
5. **Cancel** stops after the current transcription returns control. **Retry incomplete** requeues failed, skipped, or cancelled items; **Open output folder** opens output location. No source audio is modified.

Default policy **Skip existing SRT** protects earlier files. Select **Overwrite existing SRT** to replace them; writes are atomic. With a common output folder, different voices that have the same filename stem will collide; the second is skipped by default.

Word-level timestamps are taken from the model, not arbitrarily divided by a timer. The selected duration is a *target*: silence, phrase boundaries, or a long word can create shorter/longer cues. The model transcribes audible speech; recognition quality varies with recording and language.

## Constraints

- Only runs one transcription at a time to limit memory use on typical Windows laptops.
- The selected Whisper model downloads automatically once and stays in the locally cached model location, which may be under the Windows user profile. The app's virtual environment remains inside the app folder.
- Supported input extensions: MP3, WAV, M4A, FLAC, AAC, OGG, OPUS, WMA, MP4, MKV, MOV, WEBM (depending on decoder support).
- Requires internet for first-time model setup; cached models may work offline afterwards.

## Developer tests

`python -m unittest discover -s tests -v` (these tests do not need the model installed).
