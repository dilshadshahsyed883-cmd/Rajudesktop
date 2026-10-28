"""Prepare a Windows installer and portable EXE for the standalone Video Editor."""
from pathlib import Path
import json
from transform_video_only import transform

ROOT = Path(__file__).resolve().parent
APP = ROOT / "Z-Studio-Local" / "app"
assert APP.is_dir(), "Run z-studio/assemble_source.py --extract first"
transform(APP)  # Idempotent. Never package legacy Image/Voice/Canvas modules.
pfile = APP / 'package.json'
pkg = json.loads(pfile.read_text(encoding='utf-8'))
pkg['name'] = 'z-studio-video-editor'
pkg['productName'] = 'Z Studio Video Editor'
pkg['version'] = '5.43.3-video.1'
pkg['build'] = {
  'appId': 'online.scenebuilder.zstudio.video',
  'productName': 'Z Studio Video Editor',
  'directories': {'output': '../../../dist/z-studio-video-editor'},
  'asar': True,
  'files': ['**/*', '!**/node_modules/.cache/**'],
  'win': {'icon': 'renderer/assets/icon.ico', 'target': [{'target': 'nsis', 'arch': ['x64']}, {'target': 'portable', 'arch': ['x64']}]},
  'nsis': {'artifactName': 'Z-Studio-Video-Editor-Setup-${version}-${arch}.${ext}', 'oneClick': False, 'allowToChangeInstallationDirectory': True, 'createDesktopShortcut': True, 'createStartMenuShortcut': True},
  'portable': {'artifactName': 'Z-Studio-Video-Editor-Portable-${version}-${arch}.${ext}'},
  'publish': None
}
pfile.write_text(json.dumps(pkg, indent=2)+'\n', encoding='utf-8')
print('Prepared video-only Windows EXE build:', APP)
