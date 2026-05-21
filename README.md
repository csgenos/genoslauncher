# GenosLauncher

A premium, open-source Minecraft launcher built with Python and PySide6.
Clean white/light premium aesthetic — no bloat, no subscriptions.

## Features

- **Frameless custom window** with smooth window controls and resize
- **Animated sidebar** navigation with account widget at the bottom
- **Microsoft Account sign-in** (PKCE OAuth2 — no client secret needed)
- **Offline accounts** for solo / LAN play
- **Modrinth modpack browser** with one-click `.mrpack` installation
- **Shaders & resource packs** management with drag-and-drop support
- **JVM performance presets** — Aikar's G1GC, Low Latency, ZGC, Fabric/Sodium
- **Version browser** — search, filter snapshots/legacy, install and launch
- **RAM slider**, resolution picker, Java auto-detection in Settings

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/csgenos/genoslauncher.git
cd genoslauncher

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python src/main.py
```

**Requirements:** Python 3.11+, Windows 10/11 (primary), Linux/macOS supported.

---

## Microsoft Account Setup (Azure App)

GenosLauncher uses the standard Microsoft OAuth 2.0 PKCE flow for authentication.
You must register a free Azure App to obtain a **Client ID**.

### Step-by-step (≈5 minutes)

1. Go to [portal.azure.com](https://portal.azure.com) and sign in.

2. Navigate to **Azure Active Directory → App registrations → New registration**.

3. Fill in:
   - **Name:** GenosLauncher (or anything you like)
   - **Supported account types:** *Accounts in any organizational directory and personal Microsoft accounts*
   - **Redirect URI:** select **Public client/native (mobile & desktop)** and enter:
     ```
     http://localhost:8090
     ```
   Click **Register**.

4. On the app's **Overview** page, copy the **Application (client) ID** (a UUID).

5. Go to **Authentication** → under *Advanced settings*, set  
   **Allow public client flows** = **Yes**. Click **Save**.

6. Go to **API permissions → Add a permission → APIs my organization uses**,  
   search for **Xbox Live**, and add:
   - `XboxLive.signin`
   - `offline_access`

7. In GenosLauncher, open **Settings → Microsoft Authentication** and paste your Client ID.

8. Go to the **Accounts** tab and click **Sign In**. A browser window will open.  
   Complete the Microsoft login, then return to the launcher.

> **Note:** The port in the redirect URI (`8090`) must match the  
> *OAuth Redirect Port* setting in GenosLauncher → Settings → Microsoft Authentication.  
> If you change the port there, update the Azure App redirect URI to match.

---

## Building a Windows Executable

### Prerequisites

```bash
pip install pyinstaller
```

Optionally install [Inno Setup 6](https://jrsoftware.org/isinfo.php) to generate a `.exe` installer.

### Build

```bat
build.bat
```

This will:
1. Install all Python dependencies.
2. Run `pyinstaller GenosLauncher.spec` (onedir mode — better PySide6 compatibility).
3. If Inno Setup is installed, build `installer_output\GenosLauncher-X.Y.Z-Setup.exe`.

Output locations:
| Artifact | Path |
|---|---|
| Application folder | `dist\GenosLauncher\` |
| Main executable | `dist\GenosLauncher\GenosLauncher.exe` |
| Windows installer | `installer_output\GenosLauncher-0.2.0-Setup.exe` |

### Manual PyInstaller command

```bash
pyinstaller GenosLauncher.spec --noconfirm --clean
```

---

## Project Structure

```
GenosLauncher/
├── src/
│   ├── main.py                      # Entry point
│   ├── core/
│   │   ├── auth.py                  # Microsoft auth (PKCE, keyring)
│   │   ├── config.py                # JSON config persistence
│   │   ├── java_manager.py          # Java detection + JVM presets
│   │   ├── launcher.py              # Minecraft install + launch workers
│   │   └── modrinth.py              # Modrinth REST API client
│   └── ui/
│       ├── login_dialog.py          # Microsoft login modal dialog
│       ├── main_window.py           # Root window + tab orchestration
│       ├── titlebar.py              # Custom frameless title bar
│       ├── styles.py                # Master QSS stylesheet + color tokens
│       ├── components/
│       │   ├── account_widget.py    # Sidebar account strip
│       │   ├── animated_button.py   # PrimaryButton, OutlineButton, LaunchButton
│       │   ├── clean_card.py        # Hoverable white card component
│       │   ├── progress_widget.py   # Launch progress bar panel
│       │   ├── sidebar.py           # Animated sidebar navigation
│       │   └── version_card.py      # Version browser card
│       └── tabs/
│           ├── accounts_tab.py      # Account management UI
│           ├── home_tab.py          # Hero + launch + news
│           ├── instances_tab.py     # Version browser + search
│           ├── modpacks_tab.py      # Modrinth modpack browser
│           ├── settings_tab.py      # RAM, JVM, Java, auth settings
│           └── shaders_tab.py       # Shader / resource pack management
├── GenosLauncher.spec               # PyInstaller spec (onedir)
├── GenosLauncher.iss                # Inno Setup installer script
├── build.bat                        # One-click Windows build
├── requirements.txt
└── README.md
```

---

## License

MIT License — open source and free forever.
