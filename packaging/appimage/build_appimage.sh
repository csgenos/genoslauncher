#!/bin/bash
# Build an AppImage for GenosLauncher (Linux x86_64 / aarch64).
# Requires: pyinstaller, appimagetool (from https://github.com/AppImage/AppImageKit)
#
# Usage:  bash packaging/appimage/build_appimage.sh [--arch aarch64]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ARCH="${ARCH:-x86_64}"

# Parse flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        --arch) ARCH="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

cd "${REPO_ROOT}"

# ── 1. Build with PyInstaller ─────────────────────────────────────────────────
echo "==> Building with PyInstaller…"
pyinstaller GenosLauncher.spec --clean --noconfirm

# ── 2. Create AppDir layout ───────────────────────────────────────────────────
APPDIR="${REPO_ROOT}/AppDir"
rm -rf "${APPDIR}"
mkdir -p \
    "${APPDIR}/usr/bin" \
    "${APPDIR}/usr/share/applications" \
    "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

# Copy frozen executable + dependencies
cp -r "${REPO_ROOT}/dist/GenosLauncher/." "${APPDIR}/usr/bin/"

# AppRun, desktop entry, icon
cp "${SCRIPT_DIR}/AppRun" "${APPDIR}/AppRun"
chmod +x "${APPDIR}/AppRun"
cp "${SCRIPT_DIR}/GenosLauncher.desktop" "${APPDIR}/GenosLauncher.desktop"
cp "${SCRIPT_DIR}/GenosLauncher.desktop" "${APPDIR}/usr/share/applications/"

# Icon (use a 256×256 PNG from the repo, or create a placeholder)
if [[ -f "${REPO_ROOT}/assets/icon_256.png" ]]; then
    cp "${REPO_ROOT}/assets/icon_256.png" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/genoslauncher.png"
    cp "${REPO_ROOT}/assets/icon_256.png" "${APPDIR}/genoslauncher.png"
else
    # Minimal placeholder so appimagetool doesn't complain
    python3 -c "
from PIL import Image
img = Image.new('RGBA', (256, 256), (17, 24, 39, 255))
img.save('${APPDIR}/genoslauncher.png')
import shutil
shutil.copy('${APPDIR}/genoslauncher.png', '${APPDIR}/usr/share/icons/hicolor/256x256/apps/genoslauncher.png')
" 2>/dev/null || touch "${APPDIR}/genoslauncher.png"
fi

# ── 3. Run appimagetool ───────────────────────────────────────────────────────
APPIMAGETOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
APPIMAGETOOL="${REPO_ROOT}/appimagetool"

if [[ ! -x "${APPIMAGETOOL}" ]]; then
    echo "==> Downloading appimagetool for ${ARCH}…"
    curl -L --retry 3 -o "${APPIMAGETOOL}" "${APPIMAGETOOL_URL}"
    chmod +x "${APPIMAGETOOL}"
fi

VERSION="$(python3 -c "import re, pathlib; print(re.search(r'__version__\s*=\s*[\"\'](.*?)[\"\']\s*$', pathlib.Path('src/_version.py').read_text(), re.M).group(1))")"
OUTPUT_NAME="GenosLauncher-${VERSION}-linux-${ARCH}.AppImage"

echo "==> Creating ${OUTPUT_NAME}…"
ARCH="${ARCH}" "${APPIMAGETOOL}" "${APPDIR}" "${OUTPUT_NAME}"

# ── 4. SHA256 checksum ────────────────────────────────────────────────────────
sha256sum "${OUTPUT_NAME}" > "${OUTPUT_NAME}.sha256"
echo "==> Done: ${OUTPUT_NAME}"
echo "==> SHA256: $(cat "${OUTPUT_NAME}.sha256")"
