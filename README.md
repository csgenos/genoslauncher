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
- Import from Prism Launcher — one-click 3-page migration wizard with auto-detection
- Per-instance disk usage display
- Bulk actions: Validate All, Repair All, Export All
- Per-instance JVM args, RAM allocation, and Java path override
- JVM performance presets (Aikar's Flags, ZGC, Low Latency)
- Per-instance health score with issue breakdown and reclaimable storage estimate
- Built-in optimizer for safe cleanup and repair tasks

### Mods
- Browse and install mods from Modrinth and CurseForge (no API key required)
- Automatic dependency resolution — required deps offered for install alongside the mod
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
- Smart Discovery panel — recommends modpacks based on your installed instances' MC version and loader
- Modpack update checker with one-click in-place update, staging, and rollback safety
- Update policy: manual, notify, or auto-on-launch

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
- Auto-selection prefers the newest compatible installed Java

### Cloud Sync & Backup
- Local-first instance backup to any directory (Dropbox, OneDrive, NAS, or any local path — no cloud account required)
- Push and pull individual instances; keep last 5 backups per instance
- "Sync All" pushes every instance modified since last sync
- Auto-sync before each launch (optional)
- Restore any previous backup from a timestamped menu

### Crash Diagnostics
- Smart crash signature analysis with severity-ranked suggestions
- One-click fix actions from crash reports (increase RAM, repair instance, clear logs)
- One-click modpack update action when a crash suggests an outdated pack

### Settings & Diagnostics
- Light and dark themes
- Performance Advisor — analyses RAM allocation and JVM preset against system memory; gives plain-English recommendations
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
- Cloud Sync works with any directory you can write to; no third-party account is required.
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
src/core/                   auth, config, launcher, modrinth, instances, cloud_sync
src/ui/                     Qt UI, tabs, dialogs, components
tests/                      unit and smoke tests
build.bat                   Windows build script
```

## License

MIT
