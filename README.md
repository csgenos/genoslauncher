# GenosLauncher

A premium, open-source Minecraft launcher built with Python and PySide6.
Clean white/light aesthetic, no bloat, no subscriptions.

## Features

- Frameless custom window with smooth window controls and resize
- Animated sidebar navigation with account widget at the bottom
- Microsoft Account sign-in with OAuth2 PKCE
- Offline accounts for solo and LAN play
- Modrinth modpack browser with `.mrpack` installation
- Shaders and resource packs management with drag-and-drop support
- JVM performance presets for G1GC, ZGC, and Fabric/Sodium
- Version browser with search, snapshots, legacy versions, install, and launch
- RAM slider, resolution picker, and Java auto-detection

## Quick Start

```bash
git clone https://github.com/csgenos/genoslauncher.git
cd genoslauncher

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
python src/main.py
```

Requirements: Python 3.11+ and Windows 10/11 primary. Linux and macOS are supported where platform dependencies are available.

## Microsoft Account Setup

GenosLauncher uses the standard Microsoft OAuth 2.0 PKCE flow for authentication. Register a public Azure app to obtain a client ID.

1. Go to [portal.azure.com](https://portal.azure.com) and sign in.
2. Navigate to Azure Active Directory > App registrations > New registration.
3. Use "Accounts in any organizational directory and personal Microsoft accounts".
4. Add a Public client/native redirect URI:

```text
http://localhost:8090
```

5. Copy the Application (client) ID.
6. In Authentication, enable public client flows.
7. Add the Xbox Live permissions `XboxLive.signin` and `offline_access`.
8. In GenosLauncher, open Settings > Microsoft Authentication and paste the client ID.
9. Open Accounts and click Sign In.

If you change the OAuth redirect port in Settings, update the Azure redirect URI to match.

## Building a Windows Executable

```bat
build.bat
```

The build script requires `venv\Scripts\activate.bat`; create a virtual environment first. For release builds, set `GENOS_RELEASE=1` and ensure `signtool` plus a valid signing certificate are available.

Output locations:

| Artifact | Path |
|---|---|
| Application folder | `dist\GenosLauncher\` |
| Main executable | `dist\GenosLauncher\GenosLauncher.exe` |
| Windows installer | `installer_output\GenosLauncher-0.2.0-Setup.exe` |

Manual PyInstaller command:

```bash
pyinstaller GenosLauncher.spec --noconfirm --clean
```

## Project Structure

```text
src/
  main.py
  core/
    auth.py
    config.py
    java_manager.py
    launcher.py
    modrinth.py
  ui/
    login_dialog.py
    main_window.py
    titlebar.py
    styles.py
    components/
    tabs/
GenosLauncher.spec
GenosLauncher.iss
build.bat
requirements.txt
```

## License

MIT License. Open source and free forever.
