# GenosLauncher

Open-source Minecraft launcher built with Python + PySide6.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Download

Use the Windows installer from the [Releases page](https://github.com/csgenos/genoslauncher/releases).
Linux users can grab the AppImage or Flatpak from the same page.

## Features

### Launching
- Microsoft account login (PKCE OAuth 2.0, no setup required)
- Offline account support
- Multi-account management with per-account avatars and "last used" timestamps
- "Continue" quick-launch chip on the home screen resumes the last session instantly
- Close launcher on launch option

### Instances
- Create vanilla, Fabric, Forge, NeoForge, and Quilt instances
- Clone, rename, repair, and validate instances
- Import from Prism Launcher
- Per-instance disk usage display
- Bulk actions: Validate All, Repair All, Export All
- Per-instance JVM args and RAM allocation
- JVM performance presets (Aikar's Flags, ZGC, Low Latency)

### Mods
- Browse and install mods from Modrinth and CurseForge (no API key required)
- Automatic dependency resolution — required deps are offered for install alongside the mod
- Conflict detection — warns when duplicate mod IDs are present in an instance
- Mod update checker with one-click or bulk "Update All"
- Per-update rollback — auto-backup before each update, restore with one click
- Per-instance mod profiles — switch between named sets of enabled mods
- Mod metadata index for reliable update tracking

### Modpacks
- Install Modrinth modpacks (.mrpack) including full loader + mod download
- Install CurseForge modpacks (.zip)
- Export any instance as a redistributable .mrpack
- Install history log per instance with retry on failure

### Shaders & Resource Packs
- Drag-and-drop shader/resource pack installation
- Iris installer with duplicate-instance protection
- Compatibility badges showing supported MC versions before install
- Shader management per instance

### Servers
- Save and launch servers directly from the launcher
- Live ping with latency (ms) display
- Hostname and port validation on add

### Java
- Automatic Java download and version management (Eclipse Temurin)
- Manual Java path override with "Test" button to verify the binary
- Keyring backend diagnostics in Settings

### Settings & Diagnostics
- Light and dark themes
- Crash report viewer with copy-to-clipboard and in-report search
- Screenshot gallery with multi-select, export, and storage size display
- World backup and restore with multi-select and storage tracking
- Keyring status panel showing active credential storage backend

---

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

- Microsoft sign-in and CurseForge browsing both work out of the box — no API keys needed.
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
