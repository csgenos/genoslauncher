# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for GenosLauncher — onedir mode.
# Build: pyinstaller GenosLauncher.spec

import sys
from pathlib import Path

block_cipher = None

# ---------------------------------------------------------------------------
# Hidden imports needed by PySide6 + minecraft-launcher-lib + keyring
# ---------------------------------------------------------------------------
HIDDEN_IMPORTS = [
    # PySide6 plugins loaded at runtime
    "PySide6.QtSvg",
    "PySide6.QtXml",
    "PySide6.QtNetwork",
    "PySide6.QtPrintSupport",

    # minecraft-launcher-lib sub-modules
    "minecraft_launcher_lib.install",
    "minecraft_launcher_lib.command",
    "minecraft_launcher_lib.utils",
    "minecraft_launcher_lib.microsoft_account",
    "minecraft_launcher_lib.natives",
    "minecraft_launcher_lib.runtime",
    "minecraft_launcher_lib.forge",
    "minecraft_launcher_lib.fabric",
    "minecraft_launcher_lib.quilt",

    # keyring backends — include the ones most likely present on Windows
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.fail",
    "keyring.backends.null",

    # requests / urllib3
    "requests",
    "urllib3",
    "charset_normalizer",
    "certifi",
    "idna",
]

# ---------------------------------------------------------------------------
# Data files bundled into the distribution
# ---------------------------------------------------------------------------
DATAS = [
    ("src", "src"),
]
if Path("assets").exists():
    DATAS.append(("assets", "assets"))

a = Analysis(
    ["src/main.py"],
    pathex=["."],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "_pytest",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GenosLauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # no console window
    windowed=True,
    icon="assets/icon.ico" if Path("assets/icon.ico").exists() else None,
    version="file_version_info.txt" if Path("file_version_info.txt").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GenosLauncher",
)
