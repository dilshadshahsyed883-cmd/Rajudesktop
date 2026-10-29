"""Build Windows ZIP with private embedded Python, leaving upstream source intact."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
PYTHON_URL = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip'


def main():
    if sys.platform != 'win32':
        raise ValueError('Portable build must run on Windows x64.')
    output = ROOT.parent / 'dist-native-cli'
    output.mkdir(exist_ok=True)
    stage = output / 'CapCut_Native_CLI_Export'
    if stage.exists():
        shutil.rmtree(stage)
    def ignored(directory, names):
        excluded = {'__pycache__', '.runtime', '.native-tools'}
        if Path(directory) == ROOT:
            excluded |= {'config.json', 'python', 'tools', 'logs', 'state'}
        return set(names) & excluded
    shutil.copytree(ROOT, stage, ignore=ignored)
    archive = output / 'python-embed.zip'
    urllib.request.urlretrieve(PYTHON_URL, archive)
    with archive.open('rb') as stream:
        python_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    with zipfile.ZipFile(archive) as z:
        z.extractall(stage / 'python')
    # Embedded Python honors only this explicit path; no system Python required.
    (stage / 'python/python311._pth').write_text('python311.zip\n.\nLib/site-packages\n..\nimport site\n')
    packages = stage / 'python/Lib/site-packages'
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--only-binary=:all:', '--no-compile',
                    '--target', str(packages), 'frida==17.23.3'], check=True)
    shutil.copyfile(stage / 'config.example.json', stage / 'config.json')
    env = dict(__import__('os').environ, REVERSE_CLI_REGISTRY=str(stage / 'registry.json'),
               REVERSE_CLI_STATE_DIR=str(stage / 'state'))
    python = stage / 'python/python.exe'
    subprocess.run([str(python), '-B', str(stage / 'runner.py'), 'integrity'], check=True, env=env)
    subprocess.run([str(python), '-B', '-c', 'import frida; print(frida.__version__)'], check=True, env=env)
    subprocess.run([str(python), '-B', str(stage / 'vendor/upstream/capcut-cli/capcut_agent.py'), 'capabilities'], check=True, env=env)
    subprocess.run([str(python), '-B', '-m', 'unittest', 'discover', '-s', str(stage / 'tests'), '-v'], check=True, env=env)
    # Actual launch path, controlled menu exit, no CapCut needed.
    subprocess.run([str(python), '-B', str(stage / 'runner.py'), 'menu'], input='3\n', text=True, check=True, env=env)
    probe = subprocess.run([str(python), '-B', str(stage / 'runner.py'), 'doctor'],
                            capture_output=True, text=True, env=env)
    if probe.returncode != 2 or 'CapCut' not in probe.stderr:
        raise ValueError('Missing CapCut packaged error test failed: ' + probe.stdout + probe.stderr)
    manifest = {'pythonUrl': PYTHON_URL, 'pythonSha256': python_hash, 'pythonVersion': '3.11.9',
                'fridaVersion': '17.23.3', 'nativeCapCutExport': 'NOT TESTED',
                'windowsPortableLaunch': 'PASS', 'upstreamCapabilities': 'PASS',
                'missingCapCutError': 'PASS', 'mediaTools': 'External hash-checked one-time setup'}
    (stage / 'BUILD_MANIFEST.json').write_text(json.dumps(manifest, indent=2))
    shutil.make_archive(str(output / 'CapCut_Native_CLI_Export'), 'zip', output, stage.name)
    final = output / 'CapCut_Native_CLI_Export.zip'
    (output / 'SHA256SUMS.txt').write_text(hashlib.sha256(final.read_bytes()).hexdigest() + '  ' + final.name + '\n')
    print(final)


if __name__ == '__main__':
    main()
