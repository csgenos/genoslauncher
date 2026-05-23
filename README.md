# GenosLauncher

Open-source Minecraft launcher built with Python + PySide6.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Download

Use the Windows installer from the [Releases page](https://github.com/csgenos/genoslauncher/releases).

## What It Does

- Launch Minecraft with Microsoft or offline accounts
- Manage isolated instances (create, clone, repair, validate, import/export)
- Browse/install mods and modpacks (Modrinth, optional CurseForge)
- Install shaders and resource packs
- Save and launch servers directly

## Quick Start (Source)

```bash
git clone https://github.com/csgenos/genoslauncher.git
cd genoslauncher

python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install --require-hashes -r requirements.lock
# or: pip install -r requirements.txt

python src/main.py
```

Requirements: Python `>=3.11,<3.13`

## Build (Windows)

```bat
build.bat
```

Outputs:

- `dist\GenosLauncher\GenosLauncher.exe`
- `installer_output\GenosLauncher-<version>-Setup.exe` (if Inno Setup is installed)
- `SHA256SUMS.txt`

## Notes

- Microsoft sign-in works out of the box (built-in client ID).
- CurseForge requires an API key in Settings.
- macOS public build flow is currently disabled.

## Windows Antivirus Warning

GenosLauncher is not yet code-signed. Windows Defender or other antivirus software may quarantine Qt DLL files during installation, causing a "No module named PySide6" error on startup.

**Fix:**

1. Open **Windows Security** → Virus & threat protection → Protection history
2. Find any quarantined items related to `GenosLauncher` and click **Restore**
3. Go to **Virus & threat protection settings** → Exclusions → Add an exclusion
4. Add the folder: `C:\Users\<YourUsername>\AppData\Local\GenosLauncher`
5. Reinstall from the [Releases page](https://github.com/csgenos/genoslauncher/releases)

This is a known limitation for unsigned open-source projects. Code signing is planned for a future release.

## Repo Layout

```text
src/main.py                 app entry point
src/core/                   auth, config, launcher, modrinth, instances
src/ui/                     Qt UI, tabs, dialogs, components
tests/                      unit and smoke tests
build.bat                   Windows build script
```

## License

MIT
