@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Installing CapCut Native Export dependencies...
  py -3 -m venv .venv
  if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m capcut_native_export
if errorlevel 1 goto :failed
exit /b 0
:failed
echo.
echo ERROR: app could not start. See error above.
pause
exit /b 1
