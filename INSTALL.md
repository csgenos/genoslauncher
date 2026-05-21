# GenosLauncher Install Guide

This guide is written for Windows 10/11 and goes one tiny step at a time.

## What You Need

- A Windows computer
- Internet
- Python 3.11 or newer
- Git

## Step 1: Install Python

1. Open this page: <https://www.python.org/downloads/>
2. Click the yellow **Download Python** button.
3. Open the downloaded installer.
4. Check the box that says **Add python.exe to PATH**.
5. Click **Install Now**.
6. Wait until it finishes.
7. Click **Close**.

Check it worked:

1. Press `Windows + R`.
2. Type `cmd`.
3. Press `Enter`.
4. Type this and press `Enter`:

```bat
python --version
```

You should see something like:

```text
Python 3.11.x
```

## Step 2: Install Git

1. Open this page: <https://git-scm.com/download/win>
2. Download Git for Windows.
3. Open the installer.
4. Click **Next** through the installer using the default choices.
5. Click **Install**.
6. Click **Finish**.

Check it worked:

```bat
git --version
```

You should see something like:

```text
git version 2.x.x
```

## Step 3: Download GenosLauncher

In Command Prompt, run:

```bat
cd %USERPROFILE%\Desktop
git clone https://github.com/csgenos/genoslauncher.git
cd genoslauncher
```

You now have the launcher code on your Desktop.

## Step 4: Make a Safe Python Folder

Run:

```bat
python -m venv venv
venv\Scripts\activate
```

You should now see `(venv)` at the start of the command line.

## Step 5: Install the Launcher Parts

Run:

```bat
pip install -r requirements.txt
```

This may take a few minutes. That is normal.

## Step 6: Start GenosLauncher

Run:

```bat
python src/main.py
```

The GenosLauncher window should open.

## Step 7: Next Time You Want to Open It

Open Command Prompt and run:

```bat
cd %USERPROFILE%\Desktop\genoslauncher
venv\Scripts\activate
python src/main.py
```

## Optional: Sign In With Microsoft

You can use offline accounts without Microsoft sign-in.

For Microsoft sign-in, follow the Microsoft Account Setup section in `README.md`. You need an Azure App client ID before the sign-in button will work.

## If Something Goes Wrong

### `python` is not recognized

Python was not added to PATH. Reinstall Python and check **Add python.exe to PATH**.

### `git` is not recognized

Git was not installed correctly. Reinstall Git for Windows.

### `pip install` fails

Try:

```bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### The window does not open

Make sure you are inside the project folder and the virtual environment is active:

```bat
cd %USERPROFILE%\Desktop\genoslauncher
venv\Scripts\activate
python src/main.py
```

## Build an EXE Later

Only do this after the normal launcher works:

```bat
build.bat
```

The EXE will be in:

```text
dist\GenosLauncher\GenosLauncher.exe
```
