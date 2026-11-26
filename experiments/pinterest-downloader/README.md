# Pinterest Video Downloader V5

Standalone experimental Windows Python application, archived unchanged from the V5 ZIP. Extract and run `START.bat`.

V3 successfully captured an HLS stream and saved an MP4 on the user's PC. V4 background navigation and automatic Pin attribution failed. V5 uses visible Chrome, reuses the persistent V3 browser profile, and offers manual stream selection if attribution fails. Login is required only if Pinterest requests it. V5 live automatic download is not yet verified.

Future integration target: existing Video Clip Cutter online-video input; mixed YouTube/Pinterest links, video-only download, existing FFmpeg cutting, queue and numbering. No production integration or dependency changes in this archive.

The ZIP contains app.py, test_app.py, START.bat, INSTALL_CHROMIUM.bat, requirements.txt, and README.txt. No browser profile, session data or downloaded media is included.
