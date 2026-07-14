@echo off
chcp 65001 >nul
title Spotify Master Tool - Installer
color 0A

echo.
echo  ==========================================
echo   Spotify Master Tool - Installation
echo  ==========================================
echo.

:: Check admin rights
net session >nul 2>&1
if errorlevel 1 (
    echo  [!] This installer needs Administrator rights.
    echo      Right-click Install.bat and choose Run as administrator.
    echo.
    pause
    exit /b 1
)

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo.
    echo  Install from: https://www.python.org/downloads/
    echo  Tick "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  Found: %%v
echo.

:: Choose install location
set "INSTALL_DIR=%LOCALAPPDATA%\SpotifyMasterTool"
echo  Default install location:
echo    %INSTALL_DIR%
echo.
set /p "CUSTOM_DIR=  Press Enter to accept, or type a new path: "
if not "%CUSTOM_DIR%"=="" set "INSTALL_DIR=%CUSTOM_DIR%"
echo.
echo  Installing to: %INSTALL_DIR%
echo.

:: Copy files
echo  [1/4] Copying files...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
xcopy /Y /Q "%~dp0*.py"      "%INSTALL_DIR%\" >nul
xcopy /Y /Q "%~dp0*.html"    "%INSTALL_DIR%\" >nul
xcopy /Y /Q "%~dp0*.md"      "%INSTALL_DIR%\" >nul
xcopy /Y /Q "%~dp0*.bat"     "%INSTALL_DIR%\" >nul
xcopy /Y /Q "%~dp0*.docx"    "%INSTALL_DIR%\" >nul 2>&1
echo  Files copied.

:: Install packages
echo  [2/4] Installing Python packages...
pip install flask flask-cors pyloudnorm soundfile scipy numpy matchering --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [WARNING] Some packages may not have installed correctly.
    echo  The tool will retry on first launch.
) else (
    echo  Packages installed.
)
echo.

:: Create launcher script in install dir
echo  [3/4] Creating launcher...
(
echo @echo off
echo title Spotify Master Tool
echo cd /d "%INSTALL_DIR%"
echo python "%INSTALL_DIR%\server.py"
echo pause
) > "%INSTALL_DIR%\SpotifyMasterTool.bat"

:: Create shortcuts using PowerShell
echo  [4/4] Creating shortcuts...

:: Desktop shortcut
set "DESKTOP=%USERPROFILE%\Desktop"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%DESKTOP%\Spotify Master Tool.lnk'); $s.TargetPath = '%INSTALL_DIR%\SpotifyMasterTool.bat'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Spotify Master Tool'; $s.Save()"
if exist "%DESKTOP%\Spotify Master Tool.lnk" (
    echo  Desktop shortcut: OK
) else (
    echo  Desktop shortcut: FAILED - see note below
)

:: Start Menu shortcut
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTMENU%\Spotify Master Tool.lnk'); $s.TargetPath = '%INSTALL_DIR%\SpotifyMasterTool.bat'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Spotify Master Tool'; $s.Save()"
if exist "%STARTMENU%\Spotify Master Tool.lnk" (
    echo  Start Menu entry: OK
) else (
    echo  Start Menu entry: FAILED - see note below
)

echo.
echo  ==========================================
echo   Installation complete!
echo  ==========================================
echo.
echo  You can now launch the tool from:
echo    - Desktop shortcut
echo    - Start Menu
echo    - %INSTALL_DIR%\SpotifyMasterTool.bat
echo.
echo  Note: If shortcuts show FAILED above, you can still
echo  launch the tool by double-clicking SpotifyMasterTool.bat
echo  in the install folder.
echo.
set /p "LAUNCH=  Launch the tool now? (Y/N): "
if /i "%LAUNCH%"=="Y" (
    start "" "%INSTALL_DIR%\SpotifyMasterTool.bat"
)
echo.
pause
