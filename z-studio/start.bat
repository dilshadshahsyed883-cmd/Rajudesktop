@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where py.exe >nul 2>nul
if not errorlevel 1 (
    py -3 assemble_source.py --extract
) else (
    python assemble_source.py --extract
)
if errorlevel 1 (
    echo ERROR: Unable to verify and assemble Z Studio source.
    pause
    exit /b 1
)
call "%~dp0Z-Studio-Local\start.bat"
