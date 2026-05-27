"""
Java auto-detection and JVM preset definitions for GenosLauncher.

Detects installed JRE/JDK installations on Windows, macOS, and Linux.

Fix O-Y-005: Results are cached for _JAVA_CACHE_TTL seconds to avoid
repeated subprocess calls on every Settings tab open or launch.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from .config import APP_DIR, config

# Minecraft version → minimum required Java major version
_NEWEST_KNOWN_JAVA = 21

JAVA_INSTALLS_DIR = APP_DIR / "java"
_ADOPTIUM_ALLOWED_HOSTS = frozenset({"adoptium.net", "github.com", "objects.githubusercontent.com"})

# Detection cache (O-Y-005)
_java_cache: Optional[list[dict]] = None
_java_cache_time: float = 0.0
_JAVA_CACHE_TTL: float = 60.0


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def _windows_no_window_kwargs() -> dict:
    if platform.system() != "Windows":
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    kwargs: dict = {"startupinfo": startup}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs

def get_java_version(java_executable: str) -> Optional[str]:
    """Run `java -version` and return the version string or None."""
    try:
        result = subprocess.run(
            [java_executable, "-version"],
            capture_output=True,
            text=True,
            timeout=3,
            **_windows_no_window_kwargs(),
        )
        output = result.stderr or result.stdout
        for line in output.splitlines():
            if "version" in line.lower():
                parts = line.split('"')
                if len(parts) >= 2:
                    return parts[1]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_java_major(version_str: str) -> int:
    """Parse major version number from a Java version string."""
    try:
        first = version_str.split(".")[0]
        if first == "1":
            return int(version_str.split(".")[1])
        return int(first)
    except (ValueError, IndexError):
        return 0


def required_java_for_mc(mc_version: str) -> int:
    """Return the minimum Java major version needed for a Minecraft version."""
    version = str(mc_version or "").strip()
    if version.startswith(("fabric-loader-", "quilt-loader-")):
        version = version.rsplit("-", 1)[-1]
    if "-forge-" in version:
        version = version.split("-forge-", 1)[0]
    parts = version.split(".")
    try:
        if parts[0] != "1":
            return _NEWEST_KNOWN_JAVA
        minor = int(parts[1])
        patch = int(parts[2].split("-")[0]) if len(parts) > 2 and parts[2] else 0
    except (IndexError, ValueError):
        return _NEWEST_KNOWN_JAVA

    if minor >= 21:
        return 21
    if minor == 20:
        return 21 if patch >= 5 else 17
    if minor in (18, 19):
        return 17
    if minor == 17:
        return 16
    return 8


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _candidate_paths() -> list[Path]:
    """Return candidate Java executable paths for the current OS."""
    system = platform.system()
    candidates: list[Path] = []

    configured = config.get("java_path", "")
    if configured:
        candidates.append(Path(configured))

    if JAVA_INSTALLS_DIR.exists():
        for entry in JAVA_INSTALLS_DIR.iterdir():
            if entry.is_dir():
                if system == "Windows":
                    candidates.append(entry / "bin" / "javaw.exe")
                    candidates.append(entry / "bin" / "java.exe")
                else:
                    candidates.append(entry / "bin" / "java")

    java_in_path = shutil.which("java") or shutil.which("javaw")
    if java_in_path:
        candidates.append(Path(java_in_path))

    if system == "Windows":
        search_roots = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")),
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")),
        ]
        for root in search_roots:
            for vendor_dir in ("Java", "Eclipse Adoptium", "Microsoft", "Azul", "BellSoft"):
                vendor_path = root / vendor_dir
                if vendor_path.exists():
                    for child in sorted(vendor_path.iterdir(), reverse=True):
                        candidates.append(child / "bin" / "javaw.exe")
                        candidates.append(child / "bin" / "java.exe")

    elif system == "Darwin":
        java_home_base = Path("/Library/Java/JavaVirtualMachines")
        if java_home_base.exists():
            for jdk in sorted(java_home_base.iterdir(), reverse=True):
                candidates.append(jdk / "Contents" / "Home" / "bin" / "java")

    else:
        for prefix in ["/usr/lib/jvm", "/usr/local/lib/jvm", "/opt/java", "/opt/jdk"]:
            p = Path(prefix)
            if p.exists():
                for child in sorted(p.iterdir(), reverse=True):
                    candidates.append(child / "bin" / "java")

    return candidates


def find_java_installations(force_refresh: bool = False) -> list[dict]:
    """
    Return detected Java installations as dicts: {path, version, major}.
    Results are cached for _JAVA_CACHE_TTL seconds (O-Y-005).
    Pass force_refresh=True to bypass the cache.
    """
    global _java_cache, _java_cache_time
    now = time.monotonic()
    if (
        not force_refresh
        and _java_cache is not None
        and (now - _java_cache_time) < _JAVA_CACHE_TTL
    ):
        return _java_cache

    seen: set[str] = set()
    results: list[dict] = []

    candidates = []
    for candidate in _candidate_paths():
        exe = str(candidate)
        if exe in seen or not candidate.exists():
            continue
        seen.add(exe)
        candidates.append((candidate, exe))

    def probe(item: tuple[Path, str]) -> Optional[dict]:
        _candidate, exe = item
        version = get_java_version(exe)
        if version:
            return {
                "path":    exe,
                "version": version,
                "major":   get_java_major(version),
            }
        return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(probe, item) for item in candidates]
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                results.append(result)

    _java_cache = results
    _java_cache_time = now
    return results


def find_best_java(required_major: int = 21) -> Optional[str]:
    """Return the path to the best available Java for the given minimum major version."""
    installs = find_java_installations()
    valid = [j for j in installs if j["major"] >= required_major]
    if not valid:
        return None
    # Prefer the newest compatible major to reduce edge-case incompatibilities.
    valid.sort(key=lambda j: j["major"], reverse=True)
    return valid[0]["path"]


# ---------------------------------------------------------------------------
# JVM preset definitions
# ---------------------------------------------------------------------------

JVM_PRESETS: dict[str, dict] = {
    "performance": {
        "name":        "Performance (Aikar's Flags)",
        "short":       "Performance",
        "description": "Proven GC flags by Aikar. Best for most players — reduces GC stutter significantly.",
        "args": (
            "-XX:+UseG1GC "
            "-XX:+ParallelRefProcEnabled "
            "-XX:MaxGCPauseMillis=200 "
            "-XX:+UnlockExperimentalVMOptions "
            "-XX:+DisableExplicitGC "
            "-XX:+AlwaysPreTouch "
            "-XX:G1NewSizePercent=30 "
            "-XX:G1MaxNewSizePercent=40 "
            "-XX:G1HeapRegionSize=8M "
            "-XX:G1ReservePercent=20 "
            "-XX:G1HeapWastePercent=5 "
            "-XX:G1MixedGCCountTarget=4 "
            "-XX:InitiatingHeapOccupancyPercent=15 "
            "-XX:G1MixedGCLiveThresholdPercent=90 "
            "-XX:G1RSetUpdatingPauseTimePercent=5 "
            "-XX:SurvivorRatio=32 "
            "-XX:+PerfDisableSharedMem "
            "-XX:MaxTenuringThreshold=1"
        ),
        "java_min": 8,
    },
    "low_latency": {
        "name":        "Low Latency",
        "short":       "Low Latency",
        "description": "Minimizes GC pauses at the cost of some throughput. Best for competitive PvP.",
        "args": (
            "-XX:+UseG1GC "
            "-XX:MaxGCPauseMillis=50 "
            "-XX:+ParallelRefProcEnabled "
            "-XX:G1HeapRegionSize=16M "
            "-XX:G1NewSizePercent=20 "
            "-XX:G1MaxNewSizePercent=30 "
            "-Xss2M "
            "-XX:+DisableExplicitGC"
        ),
        "java_min": 8,
    },
    "zgc": {
        "name":        "ZGC (Java 21+)",
        "short":       "ZGC",
        "description": "Ultra-low pause garbage collector. Requires Java 21+. Near-zero GC stutter.",
        "args": (
            "-XX:+UseZGC "
            "-XX:+ZGenerational "
            "-XX:+UnlockExperimentalVMOptions "
            "-XX:SoftMaxHeapSize=4G "
            "-XX:+DisableExplicitGC"
        ),
        "java_min": 21,
    },
    "sodium": {
        "name":        "Fabric / Sodium Optimized",
        "short":       "Fabric",
        "description": "Tuned for Fabric loader with Sodium + Iris. Balances GC with rendering workload.",
        "args": (
            "-XX:+UseG1GC "
            "-XX:+ParallelRefProcEnabled "
            "-XX:MaxGCPauseMillis=200 "
            "-XX:+UnlockExperimentalVMOptions "
            "-XX:+DisableExplicitGC "
            "-XX:+AlwaysPreTouch "
            "-XX:G1NewSizePercent=30 "
            "-XX:G1MaxNewSizePercent=40 "
            "-XX:G1HeapRegionSize=8M "
            "-Dfabric.log.disableAnsi=false"
        ),
        "java_min": 17,
    },
}


def get_preset_args(preset_key: str) -> str:
    return JVM_PRESETS.get(preset_key, {}).get("args", "")


# ---------------------------------------------------------------------------
# Adoptium (Eclipse Temurin) auto-downloader
# ---------------------------------------------------------------------------

ADOPTIUM_API = "https://api.adoptium.net/v3"
_JAVA_MAJOR_VERSIONS = [8, 11, 17, 21]


def _adoptium_platform() -> tuple[str, str]:
    """Return (os_name, arch) in Adoptium API format."""
    system = platform.system()
    machine = platform.machine().lower()
    os_map = {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}
    arch_map = {
        "x86_64": "x64", "amd64": "x64",
        "aarch64": "aarch64", "arm64": "aarch64",
        "x86": "x32",
    }
    return os_map.get(system, "linux"), arch_map.get(machine, "x64")


def list_adoptium_releases(major: int) -> list[dict]:
    """Fetch available Eclipse Temurin JDK releases for given major and current platform."""
    import requests
    os_name, arch = _adoptium_platform()
    try:
        from .._version import __version__ as _v
    except Exception:
        _v = "0"
    try:
        resp = requests.get(
            f"{ADOPTIUM_API}/assets/latest/{major}/hotspot",
            params={"os": os_name, "architecture": arch, "image_type": "jdk"},
            headers={"User-Agent": f"GenosLauncher/{_v}"},
            timeout=15,
        )
        if not resp.ok:
            return []
        return resp.json()
    except Exception:
        return []


def download_java(
    major: int,
    on_progress: Optional[Callable[[int, int], None]] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """
    Download and extract Eclipse Temurin JDK for the given major version.

    Extracts into JAVA_INSTALLS_DIR/<major>/. Returns the java executable path
    on success, or None on failure. Verifies SHA256 checksum from Adoptium metadata.
    """
    import requests

    def _s(msg: str) -> None:
        if on_status:
            on_status(msg)

    releases = list_adoptium_releases(major)
    if not releases:
        _s(f"No Java {major} release found for this platform.")
        return None

    binary = releases[0].get("binary", {})
    package = binary.get("package", {})
    url = package.get("link", "")
    checksum = package.get("checksum", "").lower()

    if not url:
        _s("No download URL in release metadata.")
        return None
    if not checksum:
        _s("Release metadata did not include SHA256 checksum.")
        return None

    _parsed_url = urllib.parse.urlparse(url)
    _hostname = (_parsed_url.hostname or "").lower()
    if _parsed_url.scheme != "https" or not any(
        _hostname == h or _hostname.endswith(f".{h}")
        for h in _ADOPTIUM_ALLOWED_HOSTS
    ):
        _s("Unexpected download URL from Adoptium API — aborting for security.")
        return None

    dest_dir = JAVA_INSTALLS_DIR / str(major)
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_name = Path(urllib.parse.urlparse(url).path).name
    archive_path = dest_dir / archive_name

    _s(f"Downloading Java {major}…")
    try:
        try:
            from .._version import __version__ as _v
        except Exception:
            _v = "0"
        resp = requests.get(
            url, stream=True, timeout=120,
            headers={"User-Agent": f"GenosLauncher/{_v}"},
        )
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        with open(archive_path, "wb") as fh:
            for chunk in resp.iter_content(65536):
                if chunk:
                    fh.write(chunk)
                    done += len(chunk)
                    if on_progress:
                        on_progress(done, total)
    except Exception as exc:
        archive_path.unlink(missing_ok=True)
        _s(f"Download failed: {exc}")
        return None

    _s("Verifying download…")
    sha256 = hashlib.sha256()
    with open(archive_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha256.update(chunk)
    if sha256.hexdigest() != checksum:
        archive_path.unlink(missing_ok=True)
        _s("SHA256 mismatch — download corrupted.")
        return None

    _s(f"Extracting Java {major}…")
    extract_dir = dest_dir / "extracted"
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        _extract_dir_resolved = extract_dir.resolve()
        if archive_name.endswith((".tar.gz", ".tar")):
            with tarfile.open(archive_path) as tf:
                for member in tf.getmembers():
                    if member.issym() or member.islnk() or (
                        not member.isreg() and not member.isdir()
                    ):
                        continue
                    target = (extract_dir / member.name).resolve()
                    try:
                        target.relative_to(_extract_dir_resolved)
                    except ValueError:
                        continue
                    tf.extract(member, extract_dir, set_attrs=False)
        elif archive_name.endswith(".zip"):
            with zipfile.ZipFile(archive_path) as zf:
                for member in zf.infolist():
                    target = (extract_dir / member.filename).resolve()
                    try:
                        target.relative_to(_extract_dir_resolved)
                    except ValueError:
                        continue
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
        else:
            _s(f"Unsupported archive type: {archive_name}")
            return None
    except Exception as exc:
        _s(f"Extraction failed: {exc}")
        return None
    finally:
        archive_path.unlink(missing_ok=True)

    java_exe = "java.exe" if platform.system() == "Windows" else "java"
    for candidate in sorted(extract_dir.rglob(f"bin/{java_exe}")):
        if candidate.is_file():
            global _java_cache, _java_cache_time
            _java_cache = None
            _java_cache_time = 0.0
            _s(f"Java {major} installed.")
            return str(candidate)

    _s("Could not find java binary in extracted archive.")
    return None


def remove_java_installation(major: int) -> bool:
    """Delete a managed Java installation from JAVA_INSTALLS_DIR."""
    target = JAVA_INSTALLS_DIR / str(major)
    if not target.exists():
        return False
    shutil.rmtree(target, ignore_errors=True)
    global _java_cache, _java_cache_time
    _java_cache = None
    _java_cache_time = 0.0
    return True
