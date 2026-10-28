# Z Studio Video Editor — Windows only

This `z-studio` branch now delivers **only the standalone Video Editor**. The
image-generation app, Google Canvas URL configurator, separate Voice Studio,
activation/login, and their backend modules are absent from generated builds.
The video editor retains its independent media bin, audio/voiceover **track**,
preview, timeline, effects, captions, project autosave, MP4 export, and CapCut
draft export. Importing voiceover files is **not** Voice Studio and remains available.

## Windows EXE

Download the **Z-Studio-Video-Editor-Windows-EXEs** artifact from the successful
GitHub Actions Windows build. It includes a Windows installer and portable EXE.
Neither Python nor Node is needed on the end-user computer. On first video export,
FFmpeg may need a one-time installation through the app, or selection of an
existing ffmpeg.exe.

## Editable source

`python z-studio/assemble_source.py --extract` verifies the historical base ZIP
and converts it to the isolated video-only source (preserving the original
checksum-based audit trail). `z-studio/start.bat` then runs the resulting source
on Windows, with a portable Node bootstrap if needed.

The installer uses a separate application ID and the same **Z Studio Local**
project-data directory to preserve existing saved video projects. An existing
installation is not automatically uninstalled; the new Video Editor works
independently.

## Validation

CI verifies missing modules, direct launch wiring, all JavaScript syntax, and
Windows installer/portable executable packaging. End-user render tests still
require opening the Windows app and a real FFmpeg engine. Third-party notices
and bundled media dependencies must retain their applicable license terms.
