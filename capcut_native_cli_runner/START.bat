@echo off
setlocal
cd /d "%~dp0"
if not exist "python\python.exe" (
  echo Portable Python missing. Download the Windows Actions artifact ZIP and extract it fully.
  pause
  exit /b 2
)
if not exist config.json copy /y config.example.json config.json >nul
"python\python.exe" -B runner.py %*
set "runner_exit=%errorlevel%"
if not "%runner_exit%"=="0" echo Operation failed. Read the error above; do not blindly retry exports.
pause
exit /b %runner_exit%
