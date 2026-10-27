"""Convert the archived Z Studio source into a genuine video-only Electron desktop app.

This runs after checked-in archive extraction. The archive itself is kept as immutable
source input; only Video Editor modules are copied into the distributable application.
"""
from __future__ import annotations
import json
from pathlib import Path
import re

VIDEO_START = '<section class="screen" id="video">'
VIDEO_END = '<script src="js/prompts.js"></script>'
VIDEO_SCRIPTS = (
    'transitions-data.js', 'looks-data.js', 'effects-data.js',
    'motion-data.js', 'stickers-data.js', 'captions-data.js',
    'video-editor.js', 've-looks.js', 've-motion.js',
)

MAIN = r'''// Z Studio Video Editor — independent offline desktop entry point.
// Image generation, Canvas, vendor licensing, account login and Voice Studio
// deliberately do not exist in this edition.
const { app, BrowserWindow, ipcMain, dialog, shell, nativeImage } = require('electron');
const path = require('path');
const videoEditor = require('./src/video-editor');
let win = null;
const send = (channel, payload) => {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
};

app.whenReady().then(() => {
  // Preserve existing local video project records when upgrading from Z Studio Local.
  app.setPath('userData', path.join(app.getPath('appData'), 'Z Studio Local'));
  videoEditor.register({ ipcMain, app, dialog, shell, BrowserWindow, nativeImage, send });
  win = new BrowserWindow({
    width: 1440, height: 900, minWidth: 880, minHeight: 600,
    title: 'Z Studio Video Editor', backgroundColor: '#090a1a',
    autoHideMenuBar: true,
    icon: path.join(__dirname, 'renderer', 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true, sandbox: false, nodeIntegration: false,
      webviewTag: false, devTools: !app.isPackaged
    }
  });
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', event => event.preventDefault());
});

app.on('window-all-closed', () => app.quit());
'''

# Exact fragment present in archived video renderer; fail closed if source changes.
OLD_NAV = """  $('videoBtn') && ($('videoBtn').onclick = async () => { if (window.zsAccess && window.zsAccess.video === false) { toastV('The Video Editor is not included in your license. Contact us on WhatsApp to add it.'); if (window.zsShowChooser) window.zsShowChooser(); return; } show('video'); await checkFf(); await loadSfxLib(); if (hi < 0) { await openLastProject(); } zoomFit(); renderAll(); renderCapPresets(); renderBin(); });
  $('vToImage').onclick = async () => { if (playing) togglePlay(); try { await saveNow(); } catch (_) {} if (window.zsOpenImage) window.zsOpenImage(); };

  $('vBack').onclick = () => { if (playing) togglePlay(); if (window.zsShowChooser) window.zsShowChooser(); else show('studio'); };
"""
NEW_NAV = """  // One workspace, no license or editor chooser, launch straight into Video Editor.
  async function openVideoEditor() {
    show('video');
    await checkFf();
    await loadSfxLib();
    if (hi < 0) await openLastProject();
    zoomFit(); renderAll(); renderCapPresets(); renderBin();
  }
"""

def transform(app: Path) -> None:
    app = Path(app)
    assert app.is_dir(), f'Application directory missing: {app}'
    index = app / 'renderer/index.html'
    html = index.read_text(encoding='utf-8')
    if VIDEO_START in html:
        assert VIDEO_END in html, 'Video screen boundary not found'
        body = html[html.index(VIDEO_START):html.index(VIDEO_END)]
        # Remove navigation into separate Image/Voice workspaces (audio track stays).
        body, n1 = re.subn(r'\s*<button[^>]*id="vBack"[^>]*>.*?</button>', '', body)
        body, n2 = re.subn(r'\s*<button[^>]*id="vToImage"[^>]*>.*?</button>', '', body)
        assert (n1, n2) == (1, 1), f'Video navigation mismatch: {n1} {n2}'
        body = body.replace(VIDEO_START, '<section class="screen active" id="video">', 1)
        sources = '\n'.join('<script src="js/' + s + '"></script>' for s in VIDEO_SCRIPTS)
        html = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' file: data: blob:; img-src 'self' file: data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Z Studio Video Editor</title>
<link rel="stylesheet" href="css/app.css"><link rel="stylesheet" href="css/video-editor.css">
</head><body>
''' + body + '''\n<div class="toasts" id="toasts"></div>\n''' + sources + '''\n</body></html>\n'''
        index.write_text(html, encoding='utf-8')
    else:
        assert '<section class="screen active" id="video">' in html, 'Unexpected video-only HTML layout'
    jsfile = app / 'renderer/js/video-editor.js'
    js = jsfile.read_text(encoding='utf-8')
    if OLD_NAV in js:
        js = js.replace(OLD_NAV, NEW_NAV, 1)
        suffix = '  window.addEventListener(\'resize\', () => { if ($(\'video\') && $(\'video\').classList.contains(\'active\')) renderRuler(); });\n})();'
        assert suffix in js, 'Unable to locate renderer startup point'
        js = js.replace(suffix, suffix.replace('})();', "  window.addEventListener('DOMContentLoaded', () => { openVideoEditor().catch(error => toastV('Video Editor failed to open: ' + String(error.message || error), 12000)); });\n})();"), 1)
        jsfile.write_text(js, encoding='utf-8')
    else:
        assert 'openVideoEditor()' in js, 'Unexpected renderer navigation layout'
    (app / 'main.js').write_text(MAIN, encoding='utf-8')

    # Delete all former image generation, account, Canvas and separate Voice Studio modules.
    remove_files = [
      'config.json', 'src/jobs.js', 'src/signin-url.js', 'src/local-voice.js',
      'src/license.js', 'src/ai33.js', 'src/license-public.pem',
      'src/oauth.js', 'src/updater.js', 'src/voice-ipc.js',
      'renderer/js/app.js', 'renderer/js/prompts.js', 'renderer/js/voice-studio.js',
      'renderer/css/voice.css',
    ]
    for p in remove_files:
        (app / p).unlink(missing_ok=True)

    pkgpath = app / 'package.json'
    pkg = json.loads(pkgpath.read_text(encoding='utf-8'))
    pkg.update(name='z-studio-video-editor', productName='Z Studio Video Editor',
               description='Standalone video editor: timeline, media, effects, captions and CapCut export. No Image or Voice Studio.',
               version='5.43.3-video.1')
    pkg.pop('build', None)
    pkgpath.write_text(json.dumps(pkg, indent=2) + '\n', encoding='utf-8')
    # Strong validation: only the video module + its dependencies remain in source.
    assert not any((app / p).exists() for p in remove_files)
    assert set(s.name for s in (app / 'renderer/js').glob('*.js')) == set(VIDEO_SCRIPTS)
    assert 'zCanvasConfig' not in index.read_text(encoding='utf-8')
    assert 'chImage' not in index.read_text(encoding='utf-8')
    assert 'zvTabDlg' not in index.read_text(encoding='utf-8')
    assert 'videoEditor.register' in (app / 'main.js').read_text(encoding='utf-8')
    print('Video-only transformation complete:', app)

if __name__ == '__main__':
    import sys
    transform(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / 'Z-Studio-Local/app')
