<p align="center">
  <img src="assets/genoslauncherlogo.png" alt="GenosLauncher" width="120" />
</p>

# GenosLauncher

Open-source Minecraft launcher built with Python + PySide6.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Download:** Windows installer · Linux AppImage · Flatpak — all on the [Releases page](https://github.com/csgenos/genoslauncher/releases).

---

GenosLauncher is a full-featured Minecraft launcher designed to replace tools like Prism — including a one-click migration wizard to import from it. Sign in with a Microsoft account that owns Minecraft: Java Edition, manage isolated instances, browse mods and modpacks, and get back into the game fast. After successful ownership verification, local play remains available for seven days when Microsoft services cannot be reached. The "Continue" chip on the home screen resumes your last session in one click.

## UI and UX

GenosLauncher now uses a dedicated app-style shell with a centered top navigation, compact account controls, and a cleaner content stage so it feels like a desktop launcher instead of a website-style layout.

Discord Rich Presence is built in with application ID `1524019146030055444`. When Discord Desktop is running, GenosLauncher can show whether you are browsing the launcher, launching Minecraft, or playing an instance. Presence intentionally omits Microsoft account names and server IP addresses.

Install actions across major tabs were hardened for reliability:
- Modpack install cards now keep state in sync across search results and recommendations.
- Duplicate install clicks are blocked while an install is already running.
- Buttons recover to a usable state after fetch or install errors instead of getting stuck disabled.

## Instances

Every version runs in its own isolated environment. You can create vanilla, Fabric, Forge, NeoForge, or Quilt instances side-by-side, each with its own RAM allocation, JVM args, Java path, and mod set. Bulk actions (Validate All, Repair All, Export All) apply across your whole library at once.

A **health scorer** analyses each instance for broken files, orphaned data, and wasted disk space, then gives you a one-click optimizer to clean up safely. Per-instance disk usage is shown inline in the list.

**Importing from Prism Launcher** is a guided 3-step wizard: it auto-detects your Prism data directory, shows a checklist of every instance it found (with MC version), and imports the ones you select in the background.

## Mods & Modpacks

Browse and install from **Modrinth** and **CurseForge** — no API key needed for either. When you install a mod, required dependencies are resolved automatically and offered alongside it. A conflict detector warns you when duplicate mod IDs are present. The update checker scans every tracked mod and lets you update individually or all at once; each update creates an auto-backup so you can roll back with one click. **Mod profiles** let you switch between named sets of enabled mods per instance without moving files manually.

Modpack installs handle the full chain: downloads the `.mrpack` or CurseForge `.zip`, installs the right Minecraft base and loader version, fetches every mod, and extracts overrides. Every install is logged with a retry button if something fails. Installed modpacks can be checked for updates and updated in-place with staging and automatic rollback if the update breaks anything. The update policy (manual / notify / auto-on-launch) is configurable per-launcher and runs at startup even if you never open the Modpacks tab.

**Smart Discovery** sits above the search bar as a collapsible panel. It looks at which MC versions and loaders you actually use, scores candidate modpacks against that profile, and surfaces up to 6 recommendations as browsable cards — no account or tracking required.

Both Modpacks and Shaders use live Minecraft release lists for their version selectors, so newly released versions can appear without waiting for a manual hardcoded update.

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

Requires Python `>=3.11,<3.13`, a virtual environment with dependencies installed, and [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```bat
build.bat
```

The script runs PyInstaller in **onedir mode**, producing a `dist\GenosLauncher\` folder containing `GenosLauncher.exe` and a `_internal\` directory with all bundled libraries (PySide6, cryptography, psutil, etc.). Inno Setup then packages that folder into a single `installer_output\GenosLauncher-X.Y.Z-Setup.exe` that installs per-user into `%LocalAppData%` with no UAC prompt required.

To build the installer manually:

```bat
pyinstaller GenosLauncher.spec --clean --noconfirm
iscc /DAppVersion=0.2.1 GenosLauncher.iss
```

SHA256 checksums are written to `SHA256SUMS.txt` and published alongside each release for verification.

## Notes

- CurseForge browsing works out of the box.
- Discord Rich Presence uses the local Discord Desktop IPC connection. Upload `assets/glauncherlogo.png` to the Discord Developer Portal for application `1524019146030055444` with the asset key `glauncherlogo` so the logo appears in activity cards.
- Microsoft sign-in requires a valid Azure public client ID (set in Settings → Microsoft Authentication or `GENOS_AZURE_CLIENT_ID`).
- Every launch requires a Microsoft account with verified Minecraft: Java Edition ownership. There are no local username profiles.
- Successful sign-in or silent ownership refresh starts a rolling 168-hour offline grace period. Explicitly rejected or revoked credentials still require immediate sign-in.
- Microsoft auth now ignores deprecated legacy client ID overrides by default (including `00000000402b5328`) to avoid `unauthorized_client` login failures.
- Microsoft auth also blocks known first-party IDs (for example `04f0c124-f2bc-4f59-8241-bf6df9866bbd`) that cause consent failures in custom launchers.
- Advanced users can still allow legacy 16-character client IDs with `GENOS_ALLOW_LEGACY_AZURE_CLIENT_ID=1`.
- Microsoft sign-in now prefers PKCE browser callback flow by default. Device-code flow remains available for custom client IDs when explicitly enabled.
- Cloud Sync requires no third-party account; any writable directory works.
- Linux package builds include `backports.tarfile` so Flatpak runtime startup does not fail on missing `backports` module imports.
- macOS builds are currently disabled.

## Windows SmartScreen

When you run the installer for the first time, Windows SmartScreen may show a blue **"Windows protected your PC"** dialog. This happens because GenosLauncher is a new open-source project and is building its download reputation with Microsoft.

**This is expected and safe to bypass:**

1. Click **More info** (below the warning text)
2. Click **Run anyway**

SmartScreen reputation is earned by download count — the more people install GenosLauncher, the sooner this dialog disappears for everyone. If you trust the project, clicking "Run anyway" directly helps.

You can verify the download is genuine by checking the SHA256 checksum published on the [Releases page](https://github.com/csgenos/genoslauncher/releases) against the file you downloaded.

## Antivirus Troubleshooting (Windows)

Some antivirus software — including Windows Defender — may quarantine bundled Qt DLLs (PySide6) during or after installation, causing a **"No module named 'PySide6'"** startup error.

### Fix for Windows Security (Defender)

**Step 1 — Restore the quarantined files**

1. Open **Windows Security** → **Virus & threat protection**
2. Click **Protection history**
3. Find any recent detections related to `GenosLauncher` or `PySide6`, select them, and click **Restore**

**Step 2 — Add an exclusion folder**

1. In **Windows Security** → **Virus & threat protection**, scroll to **Virus & threat protection settings** and click **Manage settings**
2. Scroll to **Exclusions** → click **Add or remove exclusions**
3. Click **+ Add an exclusion** → **Folder**
4. Enter the path shown in the error dialog (typically `C:\Users\<YourName>\AppData\Local\GenosLauncher`) and click **Select Folder**

**Step 3 — Reinstall**

Run the GenosLauncher installer again with the exclusion in place.

> If you use a third-party antivirus (Malwarebytes, Norton, Kaspersky, etc.) the steps are similar — look for a **Quarantine** or **Protection History** section to restore files, and an **Exclusions** or **Whitelist** section to add the folder path.

## License

MIT
