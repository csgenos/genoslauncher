# GenosLauncher — Installation Guide

This guide covers installing GenosLauncher from source on Windows, macOS, and Linux.
No prior Python experience needed — follow each step in order.

---

## Requirements

| Requirement | Minimum | Notes |
|---|---|---|
| Python | 3.11+ | 3.12 recommended |
| Git | Any recent | For cloning |
| Java | 8, 17, or 21 | For running Minecraft — the launcher auto-detects |
| OS | Windows 10/11 | Linux and macOS also work |

---

## Windows — Step-by-Step

### 1. Install Python

1. Go to <https://www.python.org/downloads/>
2. Click the yellow **Download Python** button.
3. Open the installer.
4. **Check "Add python.exe to PATH"** — this is important.
5. Click **Install Now** and wait for it to finish.

Verify:

```bat
python --version
```

Expected output: `Python 3.11.x` or newer.

### 2. Install Git

1. Go to <https://git-scm.com/download/win>
2. Download and run the installer.
3. Click **Next** through all screens using the defaults.
4. Click **Finish**.

Verify:

```bat
git --version
```

### 3. Download GenosLauncher

Open **Command Prompt** (`Windows + R`, type `cmd`, press Enter):

```bat
cd %USERPROFILE%\Desktop
git clone https://github.com/csgenos/genoslauncher.git
cd genoslauncher
```

### 4. Create a Virtual Environment

```bat
python -m venv venv
venv\Scripts\activate
```

You should see `(venv)` at the start of the prompt.

### 5. Install Dependencies

**Recommended — reproducible install with verified hashes:**

```bat
pip install --require-hashes -r requirements.lock
```

**Alternative — standard install:**

```bat
pip install -r requirements.txt
```

### 6. Run the Launcher

```bat
python src/main.py
```

The first time you run it, a setup wizard will open to configure your data folder, RAM, and Java.

### 7. Launching Again Later

```bat
cd %USERPROFILE%\Desktop\genoslauncher
venv\Scripts\activate
python src/main.py
```

---

## macOS — Step-by-Step

### 1. Install Homebrew (if not already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2. Install Python and Git

```bash
brew install python git
```

### 3. Clone and Set Up

```bash
cd ~/Desktop
git clone https://github.com/csgenos/genoslauncher.git
cd genoslauncher
python3 -m venv venv
source venv/bin/activate
pip install --require-hashes -r requirements.lock
python src/main.py
```

---

## Linux — Step-by-Step

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv git
cd ~/Desktop
git clone https://github.com/csgenos/genoslauncher.git
cd genoslauncher
python3.11 -m venv venv
source venv/bin/activate
pip install --require-hashes -r requirements.lock
python src/main.py
```

> **Headless servers:** GenosLauncher requires a display (X11 or Wayland). It is a desktop application and cannot run headlessly.

---

## Optional Configuration

### Microsoft Account (Online Play)

Online multiplayer requires a Microsoft account linked to Minecraft. GenosLauncher uses OAuth 2.0 PKCE — when you click **Sign In**, your browser opens automatically and you log in there. No code copy-paste needed.

To enable sign-in you need a free **Azure App registration**. Full setup instructions are in [`README.md`](README.md#microsoft-account-setup). The short version:

1. Register an app at [portal.azure.com](https://portal.azure.com).
2. Add `http://localhost` as a **Mobile and desktop** redirect URI.
3. Enable public client flows.
4. Set the **Application (client) ID** in the launcher's Settings tab.

You can still use **offline accounts** for solo play without any Azure setup.

### CurseForge Integration

The launcher supports searching and installing mods and modpacks from CurseForge in addition to Modrinth. To enable it:

1. Get a free API key at [console.curseforge.com](https://console.curseforge.com).
2. Open **Settings** in the launcher.
3. Paste the key into the **CurseForge API Key** field.

The Mods and Modpacks tabs will then show a source toggle (Modrinth | CurseForge).

### Java

GenosLauncher auto-detects installed Java versions. For best results:

- **Minecraft 1.17+** requires Java 17 or newer.
- **Minecraft 1.21+** works best with Java 21.
- **Legacy versions (1.12 and older)** require Java 8.

Install multiple Java versions and the launcher will pick the right one automatically.
If auto-detection fails, set a path manually in **Settings → Java**.

---

## Building a Standalone Executable (Windows only)

After completing the standard install:

```bat
build.bat
```

Output:

| File | Location |
|---|---|
| Portable folder | `dist\GenosLauncher\` |
| Executable | `dist\GenosLauncher\GenosLauncher.exe` |
| Installer | `installer_output\GenosLauncher-0.2.0-Setup.exe` |

Requirements for the build: `venv\Scripts\activate.bat` must work, PyInstaller is installed via `requirements.txt`, and Inno Setup 6 must be installed for the installer (optional).

---

## Troubleshooting

### `python` is not recognized

Python was not added to PATH. Reinstall Python and check **Add python.exe to PATH** on the first screen of the installer.

### `git` is not recognized

Git was not installed, or the terminal was opened before installation. Restart Command Prompt after installing Git.

### `pip install` fails with hash mismatch

The lock file may be for a different platform. Fall back to:

```bat
pip install -r requirements.txt
```

Then regenerate the lock file with pip-compile if needed.

### PySide6 import error on Linux

Install the system Qt libraries:

```bash
sudo apt install libgl1 libglib2.0-0 libxcb-cursor0
```

### The window opens but is blank

Check that your graphics drivers support OpenGL. Try setting:

```bash
export QT_QUICK_BACKEND=software
python src/main.py
```

### Minecraft won't launch / "Java not found"

Go to **Settings → Java** and either:
- Let auto-detect re-scan (it lists found installations in a dropdown), or
- Click **Browse** and point to your `java.exe` / `java` binary directly.

### Startup crash log

If the launcher crashes before the window appears, a log is written to:

```text
%APPDATA%\GenosLauncher\logs\startup-crash.log   (Windows)
~/.local/share/GenosLauncher/logs/startup-crash.log   (Linux)
~/Library/Application Support/GenosLauncher/logs/startup-crash.log   (macOS)
```

Open that file to see the full traceback.
