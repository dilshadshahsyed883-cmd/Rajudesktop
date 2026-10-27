@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (set "PYTHON=py -3") else (set "PYTHON=python")
%PYTHON% -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  echo Installing Z Builder Python dependencies...
  %PYTHON% -m pip install -r requirements-z-builder.txt || (pause & exit /b 1)
)
where node >nul 2>nul
if errorlevel 1 (
  if not exist ".runtime\node\node.exe" (
    echo Setting up official verified portable Node.js for CapCut...
    %PYTHON% z_builder\bootstrap_node.py
  )
)
%PYTHON% launch_z_builder.py
if errorlevel 1 pause
