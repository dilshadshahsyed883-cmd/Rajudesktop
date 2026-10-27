"""Prepare checked-in Z Studio source for a self-contained Windows EXE build."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
APP = ROOT / "Z-Studio-Local" / "app"
assert APP.is_dir(), "Run z-studio/assemble_source.py --extract first"

mainfile = APP / "main.js"
main = mainfile.read_text('utf-8')
needle = "const path = require('path');\nconst fs = require('fs');"
marker = "app.setPath('userData', path.join(app.getPath('appData'), 'Z Studio Local'));"
if marker not in main:
    assert main.count(needle) == 1, "Unknown main.js layout; refusing unsafe patch"
    main = main.replace(needle, needle + "\n// Keep this edition's settings independent from the original Z Studio installation.\n" + marker, 1)
    mainfile.write_text(main, 'utf-8')

pfile = APP / "package.json"
pkg = json.loads(pfile.read_text('utf-8'))
pkg['name'] = 'z-studio-local'
pkg['productName'] = 'Z Studio Local'
pkg['version'] = '5.43.3-local.2'
pkg['build'] = {
  'appId': 'online.scenebuilder.zstudio.local',
  'productName': 'Z Studio Local',
  'artifactName': 'Z-Studio-Local-${version}-${arch}-${os}.${ext}',
  'directories': {'output': '../../../dist/z-studio-local'},
  'asar': False,
  'files': ['**/*','!**/node_modules/.cache/**'],
  'win': {'icon': 'renderer/assets/icon.ico', 'target': [{'target':'nsis','arch':['x64']}, {'target':'portable','arch':['x64']}]},
  'nsis': {'artifactName': 'Z-Studio-Local-Setup-${version}-${arch}.${ext}', 'oneClick': False, 'allowToChangeInstallationDirectory': True, 'createDesktopShortcut': True, 'createStartMenuShortcut': True},
  'portable': {'artifactName': 'Z-Studio-Local-Portable-${version}-${arch}.${ext}'},
  'publish': None
}
pfile.write_text(json.dumps(pkg,indent=2)+'\n','utf-8')
print('Prepared Windows EXE build:',APP)