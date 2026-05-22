@echo off
REM ============================================================
REM  GenosLauncher — Windows build script
REM  Produces:  dist\GenosLauncher\  (onedir exe)
REM  Optionally: installer_output\GenosLauncher-X.Y.Z-Setup.exe
REM
REM  Requirements:
REM    pip install pyinstaller
REM    Inno Setup 6 (optional, for installer)
REM ============================================================

setlocal EnableDelayedExpansion

set APP_NAME=GenosLauncher
set VERSION=0.2.0

echo.
echo  ===============================================
echo   %APP_NAME% v%VERSION% — Build Script
echo  ===============================================
echo.

REM ── Activate venv if present ───────────────────────────────────────────
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo  [OK] Virtual environment activated
) else (
    echo  ERROR: No venv found. Create one with: python -m venv venv
    exit /b 1
)

REM ── 1. Install / upgrade dependencies ──────────────────────────────────
echo [1/4] Installing dependencies...
if exist "requirements.lock" (
    echo  Using hash-pinned requirements.lock
    pip install --require-hashes -r requirements.lock --quiet
) else (
    echo  WARNING: requirements.lock not found, falling back to requirements.txt
    pip install -r requirements.txt --quiet
)
pip install pyinstaller --quiet
if errorlevel 1 (
    echo  ERROR: pip install failed. Check requirements.lock / requirements.txt.
    exit /b 1
)

REM ── 2. Clean previous builds ────────────────────────────────────────────
echo [2/4] Cleaning previous builds...
if exist "dist"  rmdir /s /q dist
if exist "build" rmdir /s /q build

REM ── 3. PyInstaller — onedir build (via spec file) ───────────────────────
echo [3/4] Running PyInstaller...
pyinstaller GenosLauncher.spec --noconfirm --clean
if errorlevel 1 (
    echo  ERROR: PyInstaller failed.
    exit /b 1
)
echo  PyInstaller finished. Output: dist\%APP_NAME%\

REM ── 4. Inno Setup installer (optional) ──────────────────────────────────
echo [4/4] Building installer...
set ISCC=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
)

if %ISCC%=="" (
    echo  Inno Setup not found — skipping installer.
    echo  Install from https://jrsoftware.org/isinfo.php to build .exe installers.
) else (
    mkdir installer_output 2>nul
    %ISCC% GenosLauncher.iss
    if errorlevel 1 (
        echo  WARNING: Inno Setup failed. The app build is still usable.
    ) else (
        echo  Installer: installer_output\%APP_NAME%-%VERSION%-Setup.exe
    )
)

REM ── Optional: Code signing (S-Y-012) ────────────────────────────────────
REM  Signing is strongly recommended for distribution. Unsigned executables
REM  will trigger Windows SmartScreen warnings on first run.
if /I "%GENOS_RELEASE%"=="1" (
    where signtool >nul 2>nul
    if errorlevel 1 (
        echo  ERROR: GENOS_RELEASE=1 requires signtool on PATH for code signing.
        exit /b 1
    )
    signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a "dist\%APP_NAME%\%APP_NAME%.exe"
    if errorlevel 1 exit /b 1
    if exist "installer_output\%APP_NAME%-%VERSION%-Setup.exe" (
        signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a "installer_output\%APP_NAME%-%VERSION%-Setup.exe"
        if errorlevel 1 exit /b 1
    )
)
REM
REM  To sign: obtain an EV or OV code-signing certificate (e.g. DigiCert,
REM  Sectigo) and run after build:
REM    signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ^
REM                  /a dist\GenosLauncher\GenosLauncher.exe
REM  Then re-sign the installer output as well.

REM ── Summary ──────────────────────────────────────────────────────────────
echo.
echo  ===============================================
echo   Build complete!
echo  ===============================================
echo.
echo   Application : dist\%APP_NAME%\%APP_NAME%.exe
if not %ISCC%=="" (
    echo   Installer   : installer_output\%APP_NAME%-%VERSION%-Setup.exe
)
echo.
echo   Run directly: dist\%APP_NAME%\%APP_NAME%.exe
echo.

endlocal
pause
