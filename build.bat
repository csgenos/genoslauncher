@echo off
REM ============================================================
REM  GenosLauncher — Windows build script
REM  Produces:  dist\GenosLauncher\  (onedir exe)
REM  Optionally: installer_output\GenosLauncher-X.Y.Z-Setup.exe
REM
REM  Requirements:
REM    pip install -r requirements-build.txt
REM    Inno Setup 6 (optional, for installer)
REM ============================================================

setlocal EnableDelayedExpansion

set APP_NAME=GenosLauncher
for /f "usebackq delims=" %%V in (`python -c "import pathlib,re; print(re.search(r'__version__\\s*=\\s*[\"\"'']([^\"\"'']+)', pathlib.Path('src/_version.py').read_text()).group(1))"`) do set VERSION=%%V
if not defined VERSION (
    echo ERROR: Could not read version from src\_version.py.
    exit /b 1
)

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
pip install -r requirements-build.txt --quiet
if errorlevel 1 (
    echo  ERROR: pip install failed. Check requirements.lock / requirements.txt.
    exit /b 1
)

REM Client IDs are read at runtime from GENOS_AZURE_CLIENT_ID, user settings,
REM or the built-in public client ID. The build never mutates source files.

REM ── 3. Clean previous builds ────────────────────────────────────────────
echo [3/4] Cleaning previous builds...
if exist "dist"  rmdir /s /q dist
if exist "build" rmdir /s /q build

REM ── 4. PyInstaller ──────────────────────────────────────────────────────
echo [4/4] Running PyInstaller...
pyinstaller GenosLauncher.spec --noconfirm --clean
if errorlevel 1 (
    echo  ERROR: PyInstaller failed.
    exit /b 1
)
echo  PyInstaller finished. Output: dist\%APP_NAME%\

REM ── 5. Inno Setup installer (optional) ──────────────────────────────────
echo [5/4] Building installer...
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
    %ISCC% /DAppVersion=%VERSION% GenosLauncher.iss
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

echo Generating SHA256 checksums...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$items=@('dist\%APP_NAME%\%APP_NAME%.exe'); $installer='installer_output\%APP_NAME%-%VERSION%-Setup.exe'; if (Test-Path $installer) { $items += $installer }; $items | Where-Object { Test-Path $_ } | Get-FileHash -Algorithm SHA256 | ForEach-Object { '{0}  {1}' -f $_.Hash.ToLowerInvariant(), (Split-Path $_.Path -Leaf) } | Set-Content -Encoding ASCII 'SHA256SUMS.txt'"
if errorlevel 1 (
    echo  WARNING: Failed to generate SHA256SUMS.txt.
) else (
    echo  Checksums: SHA256SUMS.txt
)
if /I "%GENOS_RELEASE%"=="1" (
    where gpg >nul 2>nul
    if errorlevel 1 (
        echo  ERROR: GENOS_RELEASE=1 requires gpg on PATH to sign SHA256SUMS.txt.
        exit /b 1
    )
    gpg --batch --yes --armor --detach-sign SHA256SUMS.txt
    if errorlevel 1 exit /b 1
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
