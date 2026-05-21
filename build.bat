@echo off
echo ============================================
echo   GenosLauncher - Windows Build Script
echo ============================================
echo.

:: Activate venv if it exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo [OK] Virtual environment activated
) else (
    echo [WARN] No venv found, using global Python
)

:: Install/upgrade PyInstaller
echo.
echo [*] Installing PyInstaller...
pip install pyinstaller --quiet

:: Clean previous builds
echo [*] Cleaning previous builds...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

:: Run PyInstaller
echo.
echo [*] Building GenosLauncher.exe ...
echo.

pyinstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "GenosLauncher" ^
    --icon "src/resources/icons/app_icon.ico" ^
    --add-data "src/resources;resources" ^
    --hidden-import PySide6.QtSvg ^
    --hidden-import PySide6.QtMultimedia ^
    --collect-all minecraft_launcher_lib ^
    src/main.py

echo.
if exist "dist\GenosLauncher.exe" (
    echo ============================================
    echo   BUILD SUCCESSFUL!
    echo   Output: dist\GenosLauncher.exe
    echo ============================================
) else (
    echo ============================================
    echo   BUILD FAILED - check output above
    echo ============================================
    exit /b 1
)

pause
