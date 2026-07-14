@echo off
chcp 65001 >nul
title Spotify Master Tool
color 0A

echo.
echo  ==========================================
echo   Spotify Master Tool
echo  ==========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo  Install from: https://www.python.org/downloads/
    echo  Tick "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo  Checking packages...
python -c "import flask" >nul 2>&1
if errorlevel 1 goto install
python -c "import flask_cors" >nul 2>&1
if errorlevel 1 goto install
python -c "import pyloudnorm" >nul 2>&1
if errorlevel 1 goto install
python -c "import soundfile" >nul 2>&1
if errorlevel 1 goto install
python -c "import scipy" >nul 2>&1
if errorlevel 1 goto install
python -c "import numpy" >nul 2>&1
if errorlevel 1 goto install
python -c "import matchering" >nul 2>&1
if errorlevel 1 goto install
goto launch

:install
echo  Installing packages (first run only)...
pip install flask flask-cors pyloudnorm soundfile scipy numpy matchering --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo  [ERROR] Package install failed.
    echo  Try right-clicking Launch.bat and choosing Run as Administrator.
    echo.
    pause
    exit /b 1
)

:launch
echo  Starting server...
echo  Browser will open automatically at http://localhost:5051
echo  Close this window to stop the tool.
echo.
python "%~dp0server.py"
pause
