@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".capcut-demo-venv\Scripts\python.exe" (
    py -3 -m venv .capcut-demo-venv
    if errorlevel 1 goto fail
)
".capcut-demo-venv\Scripts\python.exe" -m pip install -r capcut_auto_export_evidence\requirements.txt
if errorlevel 1 goto fail
".capcut-demo-venv\Scripts\python.exe" -m capcut_auto_export_evidence.app
if errorlevel 1 goto fail
exit /b 0
:fail
echo Source demo start failed; see error above.
pause
exit /b 1
