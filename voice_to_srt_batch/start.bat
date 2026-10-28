@echo off
setlocal
cd /d "%~dp0"
set "PYEXE=python"
where py >nul 2>&1 && set "PYEXE=py -3"
if not exist ".venv\Scripts\python.exe" (
  echo Preparing local Python environment on first launch...
  %PYEXE% -m venv .venv
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -c "import faster_whisper" >nul 2>&1
if errorlevel 1 (
  echo Installing speech dependencies once...
  ".venv\Scripts\python.exe" -m pip install -r requirements-voice-to-srt.txt
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" launch_voice_to_srt.py
if errorlevel 1 goto :error
exit /b 0
:error
echo.
echo Startup failed. Check the error above.
pause
exit /b 1
