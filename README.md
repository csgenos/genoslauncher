# GenosLauncher

A premium, open-source Minecraft launcher built with Python and PySide6.
Clean light theme (with optional dark mode), no bloat, no subscriptions.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Download

**End users:** grab the Windows installer from the [Releases page](https://github.com/csgenos/genoslauncher/releases).  
Run the installer and launch `GenosLauncher.exe` — no Python, no dependencies, nothing else to install.

**Run from source:** see [Quick Start](#quick-start) below.

---

## Features

### Core Launch
- Microsoft Account login via **OAuth 2.0 PKCE** — click Sign In, your browser opens, done. No Azure registration required.
- Offline accounts for solo and LAN play
- Per-instance Minecraft directories — instances are completely isolated
- Custom JVM arguments with per-preset deduplication and RAM slider (512 MB – 32 GB)
- Java auto-detection with version-aware selection (Java 8 / 16 / 17 / 21+)
- Close-on-launch mode, fullscreen toggle, and resolution presets

### Instances
- Install any vanilla Minecraft version (releases, snapshots, legacy)
- Create, clone, edit, repair, and remove instances
- Import from **MultiMC / Prism Launcher** instance directories
- Per-instance JVM overrides
- Forge and Fabric/Quilt loader support for modpacks

### Mods & Modpacks
- **Modrinth** mod and modpack browser with one-click install
- **CurseForge** mod and modpack browser (API key required — see Settings)
- `.mrpack` modpack installation with loader auto-detection
- Mod update checker — compares installed version against Modrinth's latest
- **Mod profile switching** — create named profiles to enable/disable mod sets per instance
- Download destinations are sanitized to prevent traversal via untrusted remote filenames
- Modrinth and CurseForge downloads validate file integrity where hash metadata is provided

### Server Browser
- Save favorite servers with name, IP, and port
- One-click TCP ping to show live server status
- **Play on Server** — launches Minecraft and connects directly via `--server`/`--port`

### Accounts
- Multiple Microsoft accounts — add, switch, and remove without losing your active session
- Skin viewer — fetches and displays your Minecraft face from the Mojang skin API
- Offline accounts with UUID3 generation (mirrors Minecraft's own algorithm)

### Instance Tools (⋯ menu)
- **Crash log viewer** — reads `crash-reports/` in-app; browse reports newest-first
- **Screenshot gallery** — thumbnail grid from `screenshots/`; double-click to open
- **World backup manager** — zip any save world, restore from backup, delete old backups
- Restore uses a staged extraction flow with path validation and rollback on failures

### Appearance & Settings
- **Dark mode** toggle — full palette swap applied live without a restart
- Shaders and resource packs browser
- Auto-update notification bar checks for new GitHub releases on startup

---

## Quick Start

```bash
git clone https://github.com/csgenos/genoslauncher.git
cd genoslauncher

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# Reproducible install (recommended)
pip install --require-hashes -r requirements.lock
# OR standard install
pip install -r requirements.txt

python src/main.py
```

**Requirements:** Python >=3.11,<3.13 · Windows 10/11 primary target · Linux and macOS supported where PySide6 is available.

---

## Microsoft Sign-In

GenosLauncher includes a built-in client ID — Microsoft sign-in works out of the box with no setup:

1. Open **Accounts** tab and click **Sign In**.
2. Your browser opens to Microsoft's login page.
3. Sign in with the Microsoft account linked to your Minecraft purchase.
4. Done — your account is stored securely and refreshed automatically.

> **Advanced / self-hosted builds:** If you want to use your own Azure App registration, set the `GENOS_AZURE_CLIENT_ID` environment variable or paste your client ID into **Settings → Microsoft Authentication — Client ID Override**. The built-in ID is used when neither is set.

---

## CurseForge Integration

1. Get a free API key at [console.curseforge.com](https://console.curseforge.com).
2. Open **Settings** in the launcher and paste the key into **CurseForge API Key**.
   The key is stored with the same keyring-first secret storage used for account credentials, with an encrypted local fallback if the OS keyring is unavailable.
3. The **Mods** and **Modpacks** tabs will show a source toggle (Modrinth | CurseForge).

---

## Building a Windows Executable

```bat
build.bat
```

Requires a virtual environment at `venv\`. For release builds set `GENOS_RELEASE=1`; this requires code signing and a detached signature for `SHA256SUMS.txt`.
The build script reads the version from `src/_version.py` and emits `SHA256SUMS.txt` for artifact verification.

| Artifact | Path |
|---|---|
| Application folder | `dist\GenosLauncher\` |
| Main executable | `dist\GenosLauncher\GenosLauncher.exe` |
| Windows installer | `installer_output\GenosLauncher-<version>-Setup.exe` |
| SHA256 checksums | `SHA256SUMS.txt` |

### Publishing a Release

Push a version tag to trigger the CI build and create a GitHub Release automatically:

```bash
git tag v0.2.0
git push origin v0.2.0
```

GitHub Actions builds the Windows installer, generates SHA256 checksums, and attaches everything to the release. The installer is then available on the Releases page for users to download.

> **Code signing:** Tagged release workflows require `GENOS_WINDOWS_SIGNING_CERT_BASE64` and `GENOS_WINDOWS_SIGNING_CERT_PASSWORD`. Unsigned official releases are not published.

Manual PyInstaller invocation:

```bash
pyinstaller GenosLauncher.spec --noconfirm --clean
```

---

## Project Structure

```text
src/
  _version.py               — single source of truth for version string
  main.py                   — entry point; splash screen, wizard, main window
  core/
    auth.py                 — PKCE OAuth, token storage (keyring + Fernet fallback)
    config.py               — persistent JSON config, path constants
    curseforge.py           — CurseForge API v1 client
    instances.py            — instance CRUD, Prism import
    java_manager.py         — Java auto-detection and JVM preset definitions
    launcher.py             — InstallWorker, LaunchWorker, version helpers
    modrinth.py             — Modrinth API client, .mrpack installer
    updater.py              — GitHub release auto-update check
  ui/
    styles.py               — COLORS dict, dark/light palettes, apply_theme()
    main_window.py          — root QMainWindow, tab routing, launch orchestration
    login_dialog.py         — PKCE browser login dialog
    setup_wizard.py         — first-run onboarding wizard
    titlebar.py             — custom frameless title bar
    components/
      sidebar.py            — animated sidebar navigation
      account_widget.py     — sidebar account status widget
      animated_button.py    — PrimaryButton, OutlineButton, LaunchButton
      version_card.py       — version install/launch card
      progress_widget.py    — launch progress panel
    dialogs/
      crash_dialog.py       — crash report viewer
      screenshot_dialog.py  — screenshot gallery
      backup_dialog.py      — world backup manager
    tabs/
      home_tab.py           — home screen with quick-play
      instances_tab.py      — version browser + instance manager
      mods_tab.py           — mod browser, profiles, update checker
      modpacks_tab.py       — modpack browser + installer
      shaders_tab.py        — shaders and resource packs
      servers_tab.py        — server browser and favorites
      accounts_tab.py       — account manager + skin viewer
      settings_tab.py       — all launcher settings
GenosLauncher.spec          — PyInstaller build spec
GenosLauncher.iss           — Inno Setup installer script
build.bat                   — Windows build script
requirements.txt            — direct dependencies
requirements.lock           — hash-pinned reproducible lock file
```

---

## License

MIT License. Open source and free forever.
