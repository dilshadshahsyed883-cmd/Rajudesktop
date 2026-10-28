"""Fail CI if former Z Studio workspaces leak into the Video Editor build."""
from pathlib import Path
import json, sys

app = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'Z-Studio-Local/app'
html = (app / 'renderer/index.html').read_text('utf-8')
main = (app / 'main.js').read_text('utf-8')
js = (app / 'renderer/js/video-editor.js').read_text('utf-8')
assert html.count('<section class="screen active" id="video">') == 1
assert 'Z Studio Video Editor' in html
assert 'openVideoEditor()' in js and "addEventListener('DOMContentLoaded'" in js
assert "<div class=\"toasts\" id=\"toasts\">" in html
assert 'videoEditor.register' in main
assert "Z Studio Local" in main # keep existing video projects
assert 'persist:gemini' not in main and 'session:signOut' not in main
for name in ['chImage', 'chVideo', 'chVoice', 'zCanvasConfig', 'zLocalVoice', 'vToImage', 'vBack', 'zvTabDlg', 'signM']:
    assert name not in html, name
for file in ['renderer/js/voice-studio.js','renderer/js/app.js','renderer/js/prompts.js','renderer/css/voice.css','src/jobs.js','src/local-voice.js','src/signin-url.js']:
    assert not (app / file).exists(), file
for file in ['src/video-editor.js','src/capcut-draft.js','renderer/js/video-editor.js', 'renderer/js/ve-motion.js', 'renderer/js/ve-looks.js']:
    assert (app / file).is_file(), file
pkg = json.loads((app / 'package.json').read_text('utf-8'))
assert pkg['name'] == 'z-studio-video-editor'
print('Standalone Video Editor verified: no Image Editor, Voice Studio, Canvas or licensing UI')
