@echo off
setlocal
cd /d "%~dp0"
"python\python.exe" -B setup_media_tools.py
set "setup_exit=%errorlevel%"
pause
exit /b %setup_exit%
