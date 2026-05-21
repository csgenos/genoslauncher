"""
Java auto-detection and download manager for GenosLauncher.

Detects installed JRE/JDK installations on Windows, macOS, and Linux.
Can download the correct Adoptium (Eclipse Temurin) JRE for a given
Minecraft version automatically.
"""

from __future__ import annotations

import os
import platform
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from .config import APP_DIR, config

# Minecraft version → minimum required Java major version
MC_JAVA_REQUIREMENTS: dict[str, int] = {
    "1.21": 21,
    "1.20": 21,
    "1.19": 17,
    "1.18": 17,
    "1.17": 16,
    "1.16": 8,
    "1.15": 8,
    "1.14": 8,
    "1.13": 8,
    "1.12": 8,
    "1.8":  8,
}

# Where GenosLauncher installs its own JREs
JAVA_INSTALLS_DIR = APP_DIR / "java"


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def get_java_version(java_executable: str) -> Optional[str]:
    """
    Run `java -version` and return the version string (e.g. '21.0.3') or None.
    """
    try:
        result = subprocess.run(
            [java_executable, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stderr or result.stdout
        # Typical: `openjdk version "21.0.3" 2024-04-16`
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
        # Old 1.8-style versioning
        if first == "1":
            return int(version_str.split(".")[1])
        return int(first)
    except (ValueError, IndexError):
        return 0


def required_java_for_mc(mc_version: str) -> int:
    """Return the minimum Java major version needed for a Minecraft version."""
    # Match on major.minor prefix
    for prefix in sorted(MC_JAVA_REQUIREMENTS.keys(), reverse=True):
        if mc_version.startswith(prefix):
            return MC_JAVA_REQUIREMENTS[prefix]
    return 8  # safe default


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _candidate_paths() -> list[Path]:
    """Return a list of candidate Java executable paths for the current OS."""
    system = platform.system()
    candidates: list[Path] = []

    # 1. Value from config
    configured = config.get("java_path", "")
    if configured:
        candidates.append(Path(configured))

    # 2. GenosLauncher-managed installs
    if JAVA_INSTALLS_DIR.exists():
        for entry in JAVA_INSTALLS_DIR.iterdir():
            if entry.is_dir():
                if system == "Windows":
                    candidates.append(entry / "bin" / "javaw.exe")
                    candidates.append(entry / "bin" / "java.exe")
                else:
                    candidates.append(entry / "bin" / "java")

    # 3. System PATH
    java_in_path = shutil.which("java") or shutil.which("javaw")
    if java_in_path:
        candidates.append(Path(java_in_path))

    # 4. Well-known installation directories
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

    else:  # Linux
        for prefix in ["/usr/lib/jvm", "/usr/local/lib/jvm", "/opt/java", "/opt/jdk"]:
            p = Path(prefix)
            if p.exists():
                for child in sorted(p.iterdir(), reverse=True):
                    candidates.append(child / "bin" / "java")

    return candidates


def find_java_installations() -> list[dict]:
    """
    Return a list of detected Java installations as dicts:
    {"path": str, "version": str, "major": int}
    """
    seen: set[str] = set()
    results: list[dict] = []

    for candidate in _candidate_paths():
        exe = str(candidate)
        if exe in seen or not candidate.exists():
            continue
        seen.add(exe)

        version = get_java_version(exe)
        if version:
            results.append({
                "path":    exe,
                "version": version,
                "major":   get_java_major(version),
            })

    return results


def find_best_java(required_major: int = 21) -> Optional[str]:
    """
    Return the path to the best available Java executable for the given
    minimum major version, or None if none is found.

    Prefers exact required version over higher versions.
    """
    installs = find_java_installations()
    valid = [j for j in installs if j["major"] >= required_major]
    if not valid:
        return None
    # Prefer closest to required (not excessively new)
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
    """Return the JVM args string for a named preset, or '' if not found."""
    return JVM_PRESETS.get(preset_key, {}).get("args", "")
