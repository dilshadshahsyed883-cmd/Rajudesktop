$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$out = Join-Path $root 'build/CapCut_Desktop_GUI_Export'
New-Item -ItemType Directory -Force $out | Out-Null
Copy-Item "$root/runner.py","$root/START.bat","$root/*.md","$root/requirements.txt","$root/PROVENANCE.json" $out
Copy-Item "$root/upstream" $out -Recurse -Force
$runtime = Join-Path $out 'runtime'
New-Item -ItemType Directory -Force $runtime | Out-Null
$pythonZip = Join-Path $root 'build/python-3.12.10-embed-amd64.zip'
Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' -OutFile $pythonZip
Expand-Archive $pythonZip $runtime -Force
Set-Content -Path "$runtime/python312._pth" -Encoding ascii -Value @('python312.zip','.','..','Lib/site-packages','import site')
python -m pip install --only-binary=:all: --target "$runtime/Lib/site-packages" -r "$root/requirements.txt"
if ($LASTEXITCODE -ne 0) { throw 'Portable dependencies failed' }
# Dependency dist-info licenses and CPython LICENSE.txt are retained in runtime.
& "$runtime/python.exe" "$out/runner.py" self-test
if ($LASTEXITCODE -ne 0) { throw 'Portable startup failed' }
& "$runtime/python.exe" "$out/upstream/scripts/cc.py" --help
if ($LASTEXITCODE -ne 0) { throw 'Original command help failed' }
& "$runtime/python.exe" "$out/runner.py" cc version
if ($LASTEXITCODE -ne 0) { throw 'Original version detection failed' }
& "$runtime/python.exe" "$out/runner.py" cc windows
if ($LASTEXITCODE -ne 0) { throw 'Original windows smoke failed' }
& "$out/START.bat" --help
if ($LASTEXITCODE -ne 0) { throw 'BAT launcher smoke failed' }
@{startup='PASS'; dependencies='PASS'; original_commands='PASS'; capcut_installed='NOT TESTED'; real_capcut_export='NOT TESTED'; unattended_batch='NOT TESTED'; python_archive_sha256=(Get-FileHash $pythonZip -Algorithm SHA256).Hash} | ConvertTo-Json | Set-Content "$out/WINDOWS_SMOKE.json"
$zip = Join-Path $root 'build/CapCut_Desktop_GUI_Export.zip'
Compress-Archive -Path "$out/*" -DestinationPath $zip -Force
Get-FileHash $zip -Algorithm SHA256 | Format-List
