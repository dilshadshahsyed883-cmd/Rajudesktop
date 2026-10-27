@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_CMD=python"
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"
%PYTHON_CMD% -c "import PySide6, imageio_ffmpeg" >nul 2>nul
if errorlevel 1 (
    echo Installing the Python dependencies for Scene Builder Desktop...
    %PYTHON_CMD% -m pip install --user -r requirements.txt
    if errorlevel 1 goto install_failed
)
%PYTHON_CMD% launch_scene_builder_desktop.py
if errorlevel 1 goto launch_failed
exit /b 0
:install_failed
echo Dependency installation failed. Check Python 3.11+ and internet access.
pause
exit /b 1
:launch_failed
echo Scene Builder Desktop did not start. See the error message above.
pause
exit /b 1
