@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1 && (py -3 assemble_source.py --extract) || (python assemble_source.py --extract)
if errorlevel 1 (
 echo Failed to verify or unpack the Z Studio source.
 pause
 exit /b 1
)
call "Z-Studio-Local\start.bat"
