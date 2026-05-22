"""
Java auto-detection and JVM preset definitions for GenosLauncher.

Detects installed JRE/JDK installations on Windows, macOS, and Linux.

Fix O-Y-005: Results are cached for _JAVA_CACHE_TTL seconds to avoid
repeated subprocess calls on every Settings tab open or launch.
"""

from __future__ import annotations

import os
import platform
import subprocess
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from .config import APP_DIR, config

# Minecraft version → minimum required Java major version
_NEWEST_KNOWN_JAVA = 21

JAVA_INSTALLS_DIR = APP_DIR / "java"

# Detection cache (O-Y-005)
_java_cache: Optional[list[dict]] = None
_java_cache_time: float = 0.0
_JAVA_CACHE_TTL: float = 60.0


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def get_java_version(java_executable: str) -> Optional[str]:
    """Run `java -version` and return the version string or None."""
    try:
        result = subprocess.run(
            [java_executable, "-version"],
            capture_output=True,
            text=True,
            timeout=3,
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
    valid.sort(key=lambda j: j["major"])
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
