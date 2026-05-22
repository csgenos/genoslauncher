#!/usr/bin/env bash
set -euo pipefail

# Basic macOS build script for GenosLauncher.
# Produces:
#   dist/GenosLauncher.app
#   dist/GenosLauncher.dmg

APP_NAME="GenosLauncher"
VERSION="$(python - <<'PY'
import pathlib, re
text = pathlib.Path("src/_version.py").read_text(encoding="utf-8")
m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
print(m.group(1) if m else "0.0.0")
PY
)"

echo "Building ${APP_NAME} ${VERSION} for macOS..."

python -m pip install -r requirements.txt
python -m pip install pyinstaller

rm -rf build dist

pyinstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "${APP_NAME}" \
  --icon "assets/icon.ico" \
  src/main.py

APP_PATH="dist/${APP_NAME}.app"
if [[ ! -d "${APP_PATH}" ]]; then
  echo "App bundle not found at ${APP_PATH}"
  exit 1
fi

DMG_PATH="dist/${APP_NAME}-${VERSION}.dmg"
rm -f "${DMG_PATH}"

hdiutil create \
  -volname "${APP_NAME}" \
  -srcfolder "${APP_PATH}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}"

echo "Done:"
echo "  ${APP_PATH}"
echo "  ${DMG_PATH}"
