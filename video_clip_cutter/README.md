# Video Clip Cutter V1 (independent Windows app)

Select a local video, enter a **required** output filename, select an **adjustable clip duration** (default 4 seconds) and press **Start Processing**. Produces `Name 1.mp4`, `Name 2.mp4`, etc. The last short segment is kept.

- Default output: Windows **Documents/ProcessedClips**, including redirected Documents folders.
- Change destination in app; last folder and duration are remembered.
- Offline, original video never edited or deleted; audio included, resolution preserved.
- Processing progress and cancel button; completed clips stay on cancellation.
- Existing output names are never overwritten. Choose a different filename/folder if a name is already used.
- FFmpeg and FFprobe included in Windows distribution, no Python installation needed.

## Download / run

Get the built `VideoClipCutter-Windows.zip` from the latest **Video Clip Cutter** GitHub release, extract, and open `VideoClipCutter.exe`. Keep the `_internal` folder next to the EXE. No installation needed.

## Development

Python 3.11+ (Tkinter ships with Python), FFmpeg & FFprobe in PATH:

```sh
python launch_video_clip_cutter.py
python -m unittest discover -s tests -p 'test_video_clip_cutter.py' -v
```

## Windows build

GitHub Actions runs test/build using a Windows runner and downloads the official gyan.dev FFmpeg essentials distribution, including `ffmpeg.exe` and `ffprobe.exe`. PyInstaller generates an offline one-folder executable and Windows ZIP. Push changes in `video_clip_cutter/**`, `launch_video_clip_cutter.py`, or workflow file to main to trigger the action and publish a release. The ZIP includes the tools. Do not distribute only the bare EXE.
