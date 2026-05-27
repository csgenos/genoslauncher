# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for GenosLauncher — onedir mode.
# Build: pyinstaller GenosLauncher.spec

import importlib.util
import os
import re
import sys
from pathlib import Path

block_cipher = None

# ---------------------------------------------------------------------------
# Read version — single source of truth is src/_version.py
# ---------------------------------------------------------------------------
_ver_text = Path("src/_version.py").read_text(encoding="utf-8")
_ver_match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', _ver_text)
if not _ver_match:
    raise RuntimeError("Could not read __version__ from src/_version.py")
_VERSION = _ver_match.group(1)
_ver_parts = [int(x) for x in re.split(r"[.\-]", _VERSION) if x.isdigit()]
_ver_parts = (_ver_parts + [0, 0, 0, 0])[:4]  # pad to 4 ints

_PUBLISHER = "GenosLauncher Contributors"

# ---------------------------------------------------------------------------
# Generate file_version_info.txt for PyInstaller EXE version resource.
# This embeds company/product/version metadata into the EXE so signtool
# can read it and authenticode signatures display the correct publisher.
# ---------------------------------------------------------------------------
Path("file_version_info.txt").write_text(
    f"""\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({_ver_parts[0]}, {_ver_parts[1]}, {_ver_parts[2]}, {_ver_parts[3]}),
    prodvers=({_ver_parts[0]}, {_ver_parts[1]}, {_ver_parts[2]}, {_ver_parts[3]}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'{_PUBLISHER}'),
         StringStruct(u'FileDescription', u'GenosLauncher Minecraft Launcher'),
         StringStruct(u'FileVersion', u'{_VERSION}.0'),
         StringStruct(u'InternalName', u'GenosLauncher'),
         StringStruct(u'LegalCopyright', u'Copyright 2025 {_PUBLISHER}'),
         StringStruct(u'OriginalFilename', u'GenosLauncher.exe'),
         StringStruct(u'ProductName', u'GenosLauncher'),
         StringStruct(u'ProductVersion', u'{_VERSION}.0')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [0x0409, 1200])])
  ]
)
""",
    encoding="utf-8",
)

# ---------------------------------------------------------------------------
# Build-time secret injection
# ---------------------------------------------------------------------------
_CF_KEY = os.environ.get("CURSEFORGE_API_KEY", "")
_RUNTIME_HOOKS = []
if _CF_KEY:
    _hook_path = Path("_genos_cf_key_hook.py")
    _hook_path.write_text(
        f"import os\nos.environ.setdefault('GENOS_CURSEFORGE_API_KEY', {_CF_KEY!r})\n"
    )
    _RUNTIME_HOOKS = [str(_hook_path)]

# ---------------------------------------------------------------------------
# Explicit package collection via find_spec.
#
# PyInstaller's auto-detection and collect_all() both silently omit C-extension
# packages on this CI environment. Using importlib to locate each installed
# package directory and copying it wholesale into DATAS guarantees the full
# package lands in _internal/ regardless of PyInstaller's hook behaviour.
#
# Confirmed missing from previous builds (absent folders in _internal/):
#   - PySide6      (Qt DLLs, .pyd bindings, plugins)
#   - cryptography (Rust-compiled bindings + OpenSSL)
#   - psutil       (_psutil_windows.pyd)
# ---------------------------------------------------------------------------

def _pkg_dir(name):
    spec = importlib.util.find_spec(name)
    if spec is None:
        import site
        raise RuntimeError(
            f"{name} not found in sys.path.\n"
            f"site-packages dirs: {site.getsitepackages()}\n"
            f"Likely cause: requirements.lock is missing the Windows wheel hash for {name}. "
            f"Re-run pip-compile on Windows or add the win_amd64 hash manually."
        )
    if spec.submodule_search_locations:
        return list(spec.submodule_search_locations)[0]
    return os.path.dirname(spec.origin)


_pyside6_dir      = _pkg_dir("PySide6")
_cryptography_dir = _pkg_dir("cryptography")
_psutil_dir       = _pkg_dir("psutil")

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------
HIDDEN_IMPORTS = [
    "PySide6.QtSvg",
    "PySide6.QtXml",
    "PySide6.QtNetwork",
    "PySide6.QtPrintSupport",
    "PySide6.QtGui",
    "minecraft_launcher_lib.install",
    "minecraft_launcher_lib.command",
    "minecraft_launcher_lib.utils",
    "minecraft_launcher_lib.microsoft_account",
    "minecraft_launcher_lib.natives",
    "minecraft_launcher_lib.runtime",
    "minecraft_launcher_lib.forge",
    "minecraft_launcher_lib.fabric",
    "minecraft_launcher_lib.quilt",
    "minecraft_launcher_lib.mod_loader",
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.fail",
    "keyring.backends.null",
    "cryptography.fernet",
    "cryptography.hazmat.primitives.hashes",
    "cryptography.hazmat.primitives.kdf.pbkdf2",
    "requests",
    "urllib3",
    "charset_normalizer",
    "certifi",
    "idna",
    "pkg_resources",
    "setuptools",
    "backports",
    "backports.tarfile",
    "jaraco.context",
    "setuptools._vendor.jaraco.context",
    "setuptools._vendor.jaraco.text",
]

# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------
DATAS = [
    ("src",             "src"),
    (_pyside6_dir,      "PySide6"),
    (_cryptography_dir, "cryptography"),
    (_psutil_dir,       "psutil"),
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
    runtime_hooks=_RUNTIME_HOOKS,
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
    console=False,
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
