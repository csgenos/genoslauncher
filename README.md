# GenosLauncher

A premium, open-source Minecraft launcher built with Python and PySide6. Designed to deliver a visual experience on par with Lunar Client and Feather Client.

## Features

- **Frameless custom window** with smooth window controls
- **Animated sidebar** navigation (Home, Instances, Mods, Accounts, Settings)
- **Premium dark UI** with cyan/purple accents and glassmorphic cards
- **Smooth animations** — hover glows, fade-ins, animated progress bars
- **Version browser** with card-based layout
- **Settings panel** — RAM slider, resolution, Java path configuration
- **Microsoft account** login (placeholder, ready for full OAuth integration)
- **Animated launch** sequence with progress tracking

## Requirements

- Python 3.11+
- Windows 10/11 (primary target), Linux/macOS supported

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

# 4. Run the launcher
python src/main.py
```

## Building a Windows Executable

```bash
# Install PyInstaller
pip install pyinstaller

# Run the build script
build.bat
```

The final `GenosLauncher.exe` will be in the `dist/` folder.

## Project Structure

```
GenosLauncher/
├── src/
│   ├── main.py                 # Entry point
│   ├── core/
│   │   ├── config.py           # Config management (JSON)
│   │   └── launcher.py         # Minecraft launch logic
│   ├── ui/
│   │   ├── main_window.py      # Root window
│   │   ├── titlebar.py         # Custom frameless title bar
│   │   ├── styles.py           # Master QSS stylesheet + color constants
│   │   ├── components/         # Reusable animated widgets
│   │   └── tabs/               # Individual content tabs
│   └── resources/
│       ├── icons/
│       ├── backgrounds/
│       └── fonts/
├── requirements.txt
├── build.bat
└── README.md
```

## License

MIT License — open source and free forever.
