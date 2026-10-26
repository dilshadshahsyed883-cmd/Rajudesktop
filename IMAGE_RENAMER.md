# Image Renamer V1 — standalone Windows desktop app

Rename photos to Alexa 1.jpg, Alexa 2.png, Alexa 3.webp (or any keyword), with adjustable starting number.

Features:
- Choose an image folder, optionally include subfolders, or select individual images.
- Live preview, natural ordering (IMG_2 before IMG_10), automatic numbering.
- Default: copy renamed images to Documents/Renamed Images; choose any other output folder.
- Original files stay untouched and image data is never re-encoded.
- Optional in-place rename with confirmation and guarded Undo Last Rename.
- Detect case-insensitive filename conflicts; do not overwrite other files.
- JPG/JPEG, PNG, WEBP, BMP, GIF and TIF/TIFF; progress indicator; open output folder.
- Fully offline, no accounts, cloud, network, or dependency on other Rajudesktop apps.

Windows owner instructions:
1. Download ImageRenamer-Windows-x64.zip from the Image Renamer V1 GitHub Release.
2. Extract ZIP into a folder such as D:\Apps\ImageRenamer.
3. Double-click ImageRenamer.exe. Python installation is not required.
4. Select your images, enter keyword, preview, then click Rename All Images.

Developer instructions (Python 3.11 or later with Tkinter):

    python launch_image_renamer.py
    python -m unittest discover -s tests -p "test_image_renamer.py" -v

The dedicated GitHub Actions workflow runs tests and builds a Windows executable ZIP and SHA256 checksum. A successful main-branch build publishes the permanent release. Other desktop applications are not modified.
