@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "APP_DIR=%~dp0app"
set "PORTABLE_NODE=%~dp0.runtime\node"

echo.
echo ===== Z Studio Local Launcher =====
if not exist "%APP_DIR%\package.json" (
  echo ERROR: App files are missing. Please extract the entire ZIP first.
  goto :error
)

rem Use an existing, working Node and npm when possible; otherwise download
rem official Node.js LTS to this app folder without admin rights or global PATH changes.
where node.exe >nul 2>nul
if errorlevel 1 goto :portable_node
where npm.cmd >nul 2>nul
if errorlevel 1 goto :portable_node
node --version >nul 2>nul
if errorlevel 1 goto :portable_node
call npm.cmd --version >nul 2>nul
if errorlevel 1 goto :portable_node
set "NPM_COMMAND=npm.cmd"
echo [1/3] Found installed Node.js and npm.
goto :install_app

:portable_node
if not exist "%PORTABLE_NODE%\node.exe" goto :bootstrap
if not exist "%PORTABLE_NODE%\npm.cmd" goto :bootstrap
goto :portable_ready

:bootstrap
echo [1/3] Node.js/npm missing. Downloading official portable Node.js LTS...
where py.exe >nul 2>nul
if errorlevel 1 goto :python_fallback
py -3 "%~dp0bootstrap_node.py"
if errorlevel 1 goto :node_failure
goto :portable_ready

:python_fallback
where python.exe >nul 2>nul
if errorlevel 1 goto :python_missing
python "%~dp0bootstrap_node.py"
if errorlevel 1 goto :node_failure
goto :portable_ready

:python_missing
echo ERROR: Python 3 is not on PATH, so the portable Node.js setup cannot run.
echo Install official Node.js LTS from https://nodejs.org/en/download
 goto :error

:node_failure
echo ERROR: Portable Node.js setup failed. Check internet access and retry.
echo Alternative: install Node.js LTS from https://nodejs.org/en/download
 goto :error

:portable_ready
set "PATH=%PORTABLE_NODE%;%PATH%"
set "NPM_COMMAND=%PORTABLE_NODE%\npm.cmd"
"%PORTABLE_NODE%\node.exe" --version
if errorlevel 1 goto :error

:install_app
cd /d "%APP_DIR%"
if not exist "node_modules\electron\cli.js" (
  echo [2/3] Installing required Electron dependency, first launch only...
  call "%NPM_COMMAND%" install --no-audit --no-fund
  if errorlevel 1 goto :npm_failure
) else (
  echo [2/3] Electron dependency already installed.
)

echo [3/3] Starting Z Studio...
call "%NPM_COMMAND%" start
if errorlevel 1 goto :app_failure
exit /b 0

:npm_failure
echo ERROR: Electron installation failed. Check internet, antivirus, and disk space.
goto :error

:app_failure
echo ERROR: Z Studio could not start. The message above contains the cause.
goto :error

:error
echo.
pause
exit /b 1
