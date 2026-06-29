@echo off
setlocal

set "BUILD_CMD="

py -m PyInstaller --version >nul 2>&1
if not errorlevel 1 set "BUILD_CMD=py -m PyInstaller"

if not defined BUILD_CMD (
    python -m PyInstaller --version >nul 2>&1
    if not errorlevel 1 set "BUILD_CMD=python -m PyInstaller"
)

if not defined BUILD_CMD (
    echo.
    echo [ERROR] PyInstaller is not available.
    echo Install dependencies with: pip install -r requirements.txt
    pause
    exit /b 1
)

%BUILD_CMD% -y --clean --onefile --noconsole --exclude-module PySide6 --name TgIosNotifier desktop_app.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo [OK] Build completed. File: dist\TgIosNotifier.exe
pause

endlocal
