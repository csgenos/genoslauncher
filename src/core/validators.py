"""Shared validation helpers for untrusted user and remote metadata."""

from __future__ import annotations

import re
from pathlib import Path

OFFLINE_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
VERSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}$")
_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._ +()\[\]:-]+")


def normalize_offline_username(value: str) -> str:
    """Return a valid offline username or an empty string."""
    candidate = str(value or "").strip()
    if OFFLINE_USERNAME_RE.fullmatch(candidate):
        return candidate
    return ""


def validate_offline_username(value: str) -> str:
    """Return a valid offline username or raise ValueError."""
    candidate = normalize_offline_username(value)
    if not candidate:
        raise ValueError("Offline usernames must be 3-16 letters, numbers, or underscores.")
    return candidate


def validate_version_id(value: str) -> str:
    """Validate a Minecraft version id before it is used in a local path."""
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("Minecraft version id is required.")
    if "/" in candidate or "\\" in candidate:
        raise ValueError(f"Unsafe Minecraft version id: {value!r}")
    if candidate in {".", ".."} or Path(candidate).is_absolute():
        raise ValueError(f"Unsafe Minecraft version id: {value!r}")
    if ".." in candidate.split(":"):
        raise ValueError(f"Unsafe Minecraft version id: {value!r}")
    if not VERSION_ID_RE.fullmatch(candidate):
        raise ValueError(f"Unsafe Minecraft version id: {value!r}")
    return candidate


def safe_path_segment(value: str, fallback: str = "item", max_length: int = 96) -> str:
    """Return a filesystem-safe single path segment."""
    raw = str(value or "").strip()
    safe = _SAFE_SEGMENT_RE.sub("_", raw).replace("/", "_").replace("\\", "_")
    safe = safe.strip(" .")
    if not safe or safe in {".", ".."}:
        safe = fallback
    return safe[:max(1, max_length)]
