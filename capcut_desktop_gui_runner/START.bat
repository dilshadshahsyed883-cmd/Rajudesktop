@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\python.exe" (
  echo Portable runtime missing. Download the Windows workflow ZIP, not the source archive.
  pause
  exit /b 2
)
if "%~1"=="" goto help
"runtime\python.exe" runner.py %*
exit /b %errorlevel%
:help
echo CapCut GUI Export - AGENT-ASSISTED portable toolkit
echo Read README.md and AGENT_EXPORT.md. Automatic overnight export is NOT available.
"runtime\python.exe" runner.py --help
pause
