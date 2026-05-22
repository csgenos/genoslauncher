# GenosLauncher — Codebase Reference for Claude Code

This file documents the architecture, conventions, and invariants of the GenosLauncher codebase. Read it before making changes to understand the patterns in use.

---

## Running the App

```bash
# First time
python -m venv venv && venv/Scripts/activate   # Windows
source venv/bin/activate                        # macOS / Linux
pip install --require-hashes -r requirements.lock

# Every time
python src/main.py
```

There is no full test suite configured yet. Validate changes with `python -m compileall -q src`, `python -m pip_audit -r requirements.lock --disable-pip`, and by running the app directly.

---

## Architecture Overview

GenosLauncher is a PySide6 desktop application. The entry point is `src/main.py`, which:

1. Reads `config.json` and applies the saved theme (`apply_theme`).
2. Shows a splash screen.
3. On first run, opens `SetupWizard`; otherwise goes straight to `MainWindow`.

### Layer separation

```
src/
  core/          — business logic, no Qt imports (except QObject/Signal/QThread in workers)
  ui/            — Qt widgets; tabs are thin; they call core modules and display results
  _version.py    — single source of truth: __version__ = "0.2.0"
```

All background work uses the `QThread` + `QObject.moveToThread()` pattern — never `QThread.run()` subclassing. Workers emit signals; the UI connects to them.

---

## Key Files

### `src/_version.py`
Single line: `__version__ = "0.2.0"`. Every other file that needs the version imports from here. Update this when bumping the release.

### `src/core/config.py`
Singleton `config` object backed by `~/.local/share/GenosLauncher/config.json` (XDG on Linux, AppData on Windows). Use `config.get(key, default)` and `config.set(key, value)`. Path constants (`APP_DIR`, `LOGS_DIR`, `INSTANCES_DIR`) are defined here.

### `src/ui/styles.py`
Contains `COLORS` (the live dict), `_LIGHT_COLORS` and `_DARK_COLORS` snapshots, and `apply_theme(dark: bool)`. `apply_theme` mutates `COLORS` in-place and calls `app.setStyleSheet(get_stylesheet())`. Because `C = COLORS` is a reference to the same dict object, `paintEvent` callbacks that read `C[...]` at draw time see updated colors immediately; f-string inline styles baked in at widget-construction time do not update until the window is recreated.

### `src/core/auth.py`
PKCE OAuth 2.0 flow. Key public API:
- `auth_manager.start_login(on_browser_opened)` — opens the browser, runs a local HTTP server, exchanges the code, stores tokens.
- `auth_manager.is_logged_in`, `auth_manager.username`, `auth_manager.access_token`
- `auth_manager.load_stored()` / `auth_manager.refresh_async()` — called at startup.
- `auth_manager.list_ms_accounts()` / `auth_manager.switch_account(username)` / `auth_manager.add_account()` — multi-account support.
- Per-account storage key: `"ms_account_" + re.sub(r"[^a-z0-9]", "_", username.lower())`.
- Credential storage priority: `keyring` library → Fernet-encrypted fallback file in `APP_DIR`.

### `src/core/launcher.py`
- `get_available_versions()` / `get_installed_versions()` — version lists.
- `InstallWorker(version_id)` — downloads and installs a Minecraft version; emits `progress_changed`, `finished`.
- `LaunchWorker(version_id, username, parent, instance_id, server_ip, server_port)` — builds the MLL command and runs the process; emits `status_changed`, `process_started`, `process_ended`, `error`.
- Installed-versions cache with 30-second TTL to avoid repeated filesystem scans (`_get_installed_versions_cached`, `invalidate_installed_cache`).
- JVM arg builder (`_build_jvm_args`) deduplicates `-Xmx`/`-Xms` flags and sanitizes tokens (must start with `-`).

### `src/core/modrinth.py`
Modrinth API client. All requests are synchronous; callers must run them in worker threads. Key functions: `search_projects`, `get_project_versions`, `download_file` (with SHA-1/SHA-512 verification), `parse_mrpack`, `install_mrpack_mods`, `extract_mrpack_overrides`.

### `src/core/curseforge.py`
CurseForge API v1 client. Requires `config.get("curseforge_api_key")`. Returns normalized dicts with the same field names as Modrinth results (`id`, `title`, `description`, `author`, `downloads`, `icon_url`). `is_configured()` returns False when no key is set — callers should check this before searching and show a message if False.

### `src/core/instances.py`
Instance CRUD. Each instance is a dict with `id`, `name`, `mc_version`, `directory`, `type`, `source`, `jvm_args`. Stored as a JSON array in `config["instances"]`. Key functions: `list_instances`, `create_vanilla_instance`, `create_custom_instance`, `upsert_instance`, `clone_instance`, `remove_instance`, `import_prism_instances`.

### `src/core/updater.py`
Checks GitHub releases API and compares semver tags against `CURRENT_VERSION` (imported from `_version.py`). `check_async(callback)` runs on a daemon thread.

### `src/ui/main_window.py`
Root window. Instantiates all tabs, wires signals, runs `LaunchWorker`/`InstallWorker`. Tab switching is in `_switch_tab`. The servers tab adds `_on_server_launch_requested` which passes `server_ip`/`server_port` through to `_start_launch`.

### `src/ui/tabs/mods_tab.py`
- Source toggle: Modrinth or CurseForge (via `_source_combo`).
- Mod profile switching: `_load_profiles` / `_save_profiles` / `_switch_profile` helpers work with `<instance_dir>/mod_profiles.json`. Switching moves `.jar` files between `mods/` and `.disabled_mods/`.
- Mod metadata index: `<instance_dir>/mods_index.json` tracks installed mods for update checking.
- `ModUpdateWorker` queries Modrinth for newer versions of every tracked mod.

### `src/ui/dialogs/`
Three standalone dialogs opened from the instances tab's ⋯ context menu:
- `CrashReportDialog` — reads `crash-reports/*.txt`, shows in a `QPlainTextEdit`.
- `ScreenshotGalleryDialog` — loads `screenshots/*.png` thumbnails async via `_ThumbLoader`.
- `WorldBackupDialog` — zips `saves/<world>/` to `APP_DIR/backups/<instance_id>/`, lists and restores backups.

### `src/ui/tabs/servers_tab.py`
Saved servers in `config["servers"]` as `[{name, ip, port}]`. `ServerRow._ping()` does a TCP connect on a daemon thread. `ServersTab.server_launch_requested` signal is connected to `MainWindow._on_server_launch_requested`.

### `src/ui/tabs/accounts_tab.py`
`SkinWidget` fetches the Mojang UUID → profile → skin PNG → crops the 8×8 face tile at position (8,8) → scales to 56px. Only meaningful for online accounts; offline accounts show a placeholder. The widget is hidden when logged out.

---

## UI Conventions

- **Colors:** Always use `C["key"]` (which is `COLORS["key"]`). Never hardcode hex values except in `_LIGHT_COLORS` / `_DARK_COLORS` definitions in `styles.py`.
- **Fonts:** Use size tokens from `FONT` dict (`FONT["xs"]`, `FONT["sm"]`, etc.).
- **Buttons:** Use `PrimaryButton` (dark, CTA) and `OutlineButton` (ghost) from `animated_button.py`.
- **Inline styles:** f-strings baked at widget construction. They do not reflect theme changes after creation. Use `paintEvent` or QSS rules for theme-reactive rendering.
- **Background work:** Always use `QThread` + `moveToThread`. Emit signals from worker threads; never touch Qt widgets from a non-UI thread. Use `QTimer.singleShot(0, lambda: ...)` for thread-safe UI callbacks from daemon threads.

---

## Config Keys (selected)

| Key | Type | Description |
|---|---|---|
| `minecraft_dir` | str | Default MC directory |
| `instances` | list | Instance dicts |
| `selected_instance_id` | str | Active instance |
| `last_account` | str | Active account username |
| `offline_accounts` | list[str] | Offline usernames |
| `ms_usernames` | list[str] | Saved MS account usernames |
| `active_ms_username` | str | Currently logged-in MS username |
| `servers` | list | `[{name, ip, port}]` |
| `ram_mb` | int | Allocated RAM |
| `jvm_preset` | str | `performance` / `low_latency` / `zgc` / `fabric` |
| `jvm_args` | str | Extra JVM flags |
| `java_path` | str | Manual Java path override |
| `dark_mode` | bool | Theme preference |
| `curseforge_api_key` | str | CurseForge API key |
| `close_on_launch` | bool | Hide launcher when MC starts |
| `show_snapshots` | bool | Include snapshot versions |
| `show_old_versions` | bool | Include alpha/beta versions |
| `first_run` | bool | False after wizard completes |
| `window_width` / `window_height` | int | Persisted window size |

---

## Adding a New Tab

1. Create `src/ui/tabs/<name>_tab.py` with a `class <Name>Tab(QWidget)`.
2. Add `("<key>", "<icon>", "<Label>")` to `Sidebar.NAV_ITEMS` in `sidebar.py`.
3. Instantiate the tab and add it to `self._tabs` dict in `MainWindow._build_ui`.
4. The tab will appear in the sidebar and be stacked into the content area automatically.

## Adding a New Core Module

1. Create `src/core/<name>.py`.
2. Import it in the relevant tab or worker using a relative import (`from ...core import <name>`).
3. All network calls must be synchronous. Wrap in a `QObject` worker + `QThread` before calling from UI code.

---

## Security Notes

- **`--accessToken`** in the Minecraft launch command is visible in `/proc/<pid>/cmdline` on Linux and Task Manager on Windows. This is a known limitation of the MLL-based launch approach (documented in `SECURITY.md`).
- Tokens are stored per-account in the system keyring where available. A Fernet-encrypted file in `APP_DIR` is used as a fallback.
- The CurseForge API key is stored in `config.json` in plaintext. Treat it like a password.
- All mod downloads from Modrinth are verified with SHA-1 and SHA-512 hashes.
- CurseForge downloads enforce HTTPS, maximum size caps, temporary-file atomic replace, and hash verification when metadata provides hashes.
- Backup restore validates archive entries, applies extraction limits, blocks traversal, and restores via staged swap with rollback on failure.

---

## Release Process

1. Update `src/_version.py` — change `__version__`.
2. Update `GenosLauncher.iss` — change `AppVersion`.
3. Update `build.bat` — change `set VERSION=`.
4. Tag the commit: `git tag v0.x.0`.
5. Push the tag — GitHub Actions builds and attaches the release artifacts.
6. The in-app updater compares the tag against `CURRENT_VERSION` on next launch.

Release workflow now requires code-signing secrets for tag releases, signs artifacts in CI when configured, and publishes SHA256 checksum files with release artifacts.
