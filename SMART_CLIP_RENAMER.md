# Smart Clip Renamer — Raju Desktop

Standalone offline Windows desktop app. Existing Scene Desktop Studio, Clip Cutter, Edge Voice Studio and SML Desktop are untouched.

## How to use

1. Keep the best clips from different batches and collect them into one folder.
2. Run SmartClipRenamer.exe. Select the folder, enter a keyword like Alexa and pick the output location.
3. Click Preview Smart Order. The table shows original names and new names such as Alexa 1.mp4, Alexa 2.mp4, etc.
4. Click Create Renamed Clips. The app creates a unique output job folder containing byte-for-byte copies in the new order. Originals are NOT renamed or deleted.
5. Click Open Output.

Filename series such as Alexander 1.mp4, Alexander_2.mp4 and Alexander-5.mkv are recognized. Original consecutively numbered siblings are separated whenever possible. Impossible cases are reported as warnings in the preview.

Only video files directly in the selected folder are scanned. Extensions supported: MP4, MOV, MKV, AVI, WEBM, M4V, WMV, TS. Files are copied without transcoding, with original extensions preserved. Existing output is never overwritten. Cancellation deletes only the new incomplete job folder.

## Developer launch and tests

Python 3.11+:

    python launch_smart_clip_renamer.py
    python -m unittest discover -s tests -p test_smart_clip_renamer.py -v

Windows portable EXE is built by GitHub Actions workflow Smart Clip Renamer - Windows Portable. Download the SmartClipRenamer-Windows artifact from a successful run, unzip it and double-click SmartClipRenamer.exe. No Python or FFmpeg installation needed on Windows.

No automatic installation, network access, or VPS changes.
