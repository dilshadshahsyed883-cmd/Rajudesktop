@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 app.py
) else (
  python app.py
)
if errorlevel 1 (
  echo.
  echo App failed to start. Read the error above or:
  echo %LOCALAPPDATA%\CapCutIndependentRenderer\startup_error.txt
  pause
)
