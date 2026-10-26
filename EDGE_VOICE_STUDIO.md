# Edge Voice Studio V1 — Windows app

A native PySide6 Kokoro-inspired English Edge TTS voiceover app built alongside,
not inside, Scene Desktop Studio. The original video editor and media files stay unchanged.

## Features

- Live English neural voice browser (locale/gender/search), with cached voice choices.
- Starred favorites, speed/pitch/volume presets, script drafts, dark/light theme.
- TXT scripts and multi-file batch import.
- SQLite queued narration jobs with restart recovery.
- Long-script sentence-aware chunks and resumable MP3 segment generation.
- Bounded network retries, pause, cancel and resume.
- Finished MP3, optional word-timed SRT when available, background WAV conversion.
- Audio preview and library player, independent output/cache folder locations.
- Scripts, favorites, outputs and queue stay local to the Windows PC.

## Developer launch

Use Python 3.11 or newer:

    python -m pip install -r requirements-edge-voice.txt
    python launch_edge_voice.py

The existing Scene Desktop Studio continues to use:

    python launch.py

## Storage and recovery

SQLite data is stored under the Windows application data directory; output MP3/WAV
and chunk cache are stored in the configurable folders. Choose a folder on the D
drive in Settings if C drive space is limited. Completed segments remain in cache
so jobs can recover after interruption. Removing a queue row never deletes
a generated audio file or any Scene editor media.

The Microsoft Edge voice endpoint is online and is not under this application's
control. Upstream rate limits, protocol changes and network problems may interrupt
speech synthesis. Timing-based subtitle export depends on word-boundary events.

## Tests and releases

    python -m unittest discover -s tests -p "test_edge_voice*.py" -v

Windows CI runs offline tests and a GUI startup smoke test. EdgeVoiceStudio EXE
packaging is manual via workflow dispatch, not part of ordinary commits or PRs.
A manually triggered release provides a Windows portable ZIP and SHA-256 checksums.

No VPS deployment, background uploader, cloning, or access to the existing editor.


## Windows ZIP V1.1 — Screenshot colors and output destination

- Native navy header, pale-blue sidebar, white panels and bright-blue action buttons.
- Theme defaults to **Navy Light**; the previous Dark option remains available.
- Generated MP3s and matching SRT/WAV files default to the Windows Documents directory
  (normally Documents\EdgeVoiceStudio). The Documents location is resolved by Windows,
  so OneDrive-redirected Documents folders are also respected.
- Settings -> Output folder -> Browse -> Save Settings changes this destination.
  The selection persists after closing/reopening and future updates.
- Until Save Settings is pressed, browsing/editing the output field does not affect
  queued job destination.
- Settings -> Restore Documents Default -> Save Settings restores the default.
- Cache defaults to the application data directory, separate from user outputs.
- The release ZIP includes the Windows executable and bundled Python dependencies;
  no separate Python installation is required on the user's PC.
