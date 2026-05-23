# GenosLauncher

Open-source Minecraft launcher built with Python + PySide6.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Download:** Windows installer · Linux AppImage · Flatpak — all on the [Releases page](https://github.com/csgenos/genoslauncher/releases).

---

GenosLauncher is a full-featured Minecraft launcher designed to replace tools like Prism — including a one-click migration wizard to import from it. Sign in with Microsoft or play offline, manage isolated instances, browse mods and modpacks, and get back into the game fast. The "Continue" chip on the home screen resumes your last session in one click.

## Instances

Every version runs in its own isolated environment. You can create vanilla, Fabric, Forge, NeoForge, or Quilt instances side-by-side, each with its own RAM allocation, JVM args, Java path, and mod set. Bulk actions (Validate All, Repair All, Export All) apply across your whole library at once.

A **health scorer** analyses each instance for broken files, orphaned data, and wasted disk space, then gives you a one-click optimizer to clean up safely. Per-instance disk usage is shown inline in the list.

**Importing from Prism Launcher** is a guided 3-step wizard: it auto-detects your Prism data directory, shows a checklist of every instance it found (with MC version), and imports the ones you select in the background.

## Mods & Modpacks

Browse and install from **Modrinth** and **CurseForge** — no API key needed for either. When you install a mod, required dependencies are resolved automatically and offered alongside it. A conflict detector warns you when duplicate mod IDs are present. The update checker scans every tracked mod and lets you update individually or all at once; each update creates an auto-backup so you can roll back with one click. **Mod profiles** let you switch between named sets of enabled mods per instance without moving files manually.

Modpack installs handle the full chain: downloads the `.mrpack` or CurseForge `.zip`, installs the right Minecraft base and loader version, fetches every mod, and extracts overrides. Every install is logged with a retry button if something fails. Installed modpacks can be checked for updates and updated in-place with staging and automatic rollback if the update breaks anything. The update policy (manual / notify / auto-on-launch) is configurable per-launcher and runs at startup even if you never open the Modpacks tab.

**Smart Discovery** sits above the search bar as a collapsible panel. It looks at which MC versions and loaders you actually use, scores candidate modpacks against that profile, and surfaces up to 6 recommendations as browsable cards — no account or tracking required.

## Cloud Sync & Backup

Instance backup works with any directory you can write to — a Dropbox folder, a NAS mount, an external drive, anything. No cloud account is required. You can push and pull individual instances on demand, or run "Sync All" to push every instance that has changed since the last sync. Each instance keeps its last 5 snapshots; restoring any of them is a single menu pick. An optional auto-sync runs before every launch so your backup is always current.

## Crash Diagnostics & Performance

When a crash happens, the **crash analyser** reads the report, identifies the most likely causes by signature, ranks them by severity, and presents one-click fix actions — increase RAM, repair the instance, clear logs, or update the modpack if that's what the crash points to.

The **Performance Advisor** in Settings reads your actual system memory, current RAM allocation, and JVM preset, then gives plain-English recommendations: whether your allocation is too low for modern versions, too high relative to physical RAM, or whether a different GC preset would suit your hardware better.

## Shaders, Servers & Java

Shaders and resource packs install by drag-and-drop. The Iris installer is built in with duplicate-instance protection, and each shader card shows a compatibility badge listing supported MC versions before you commit to installing.

Saved servers show live ping with latency in milliseconds. Hostname and port are validated on add.

Java is managed automatically via Eclipse Temurin — the right version is downloaded and selected for each instance. You can override the path manually with a "Test" button that verifies the binary on the spot.

---

## Quick Start (Source)

```bash
git clone https://github.com/csgenos/genoslauncher.git
cd genoslauncher

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install --require-hashes -r requirements.lock
python src/main.py
```

Requires Python `>=3.11,<3.13`.

## Build (Windows)

```bat
build.bat
```

Produces `dist\GenosLauncher\GenosLauncher.exe`, an Inno Setup installer, and `SHA256SUMS.txt`.

## Notes

- Microsoft sign-in and CurseForge browsing work out of the box — no configuration needed.
- Cloud Sync requires no third-party account; any writable directory works.
- macOS builds are currently disabled.
- GenosLauncher is not yet code-signed. If Windows Defender quarantines Qt DLLs on install, restore them from Protection History, add `%LOCALAPPDATA%\GenosLauncher` as an exclusion, and reinstall.

## License

MIT
