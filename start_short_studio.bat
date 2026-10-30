@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 is required. To avoid installing Python, use ShortStudio.exe.
  pause
  exit /b 1
)
python -m pip install -r short_studio\requirements.txt
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)
python launch_short_studio.py
if errorlevel 1 pause
