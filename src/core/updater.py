"""Auto-update checker — compares the running version against the latest GitHub release."""

from __future__ import annotations

import re
import threading
from typing import Callable, Optional

import requests

REPO            = "csgenos/genoslauncher"
CURRENT_VERSION = "0.2.0"
_API_URL        = f"https://api.github.com/repos/{REPO}/releases/latest"


def _parse_semver(tag: str) -> tuple[int, ...]:
    parts = re.split(r"[.\-]", tag.lstrip("vV"))
    result: list[int] = []
    for p in parts:
        if p.isdigit():
            result.append(int(p))
        else:
            break
    return tuple(result) or (0,)


def check_for_update(timeout: int = 8) -> Optional[dict]:
    """
    Query GitHub releases for a version newer than CURRENT_VERSION.
    Returns {version, url, notes} if one exists, else None.
    Drafts and pre-releases are ignored.
    """
    try:
        resp = requests.get(
            _API_URL,
            timeout=timeout,
            headers={"User-Agent": f"GenosLauncher/{CURRENT_VERSION}"},
        )
        if not resp.ok:
            return None
        data = resp.json()
        tag = data.get("tag_name", "")
        if not tag or data.get("draft") or data.get("prerelease"):
            return None
        if _parse_semver(tag) > _parse_semver(CURRENT_VERSION):
            return {
                "version": tag,
                "url":     data.get("html_url", ""),
                "notes":   (data.get("body") or "")[:400],
            }
    except Exception:
        pass
    return None


def check_async(callback: Callable[[Optional[dict]], None]) -> None:
    """Run check_for_update on a daemon thread; invoke callback(result) when done."""
    threading.Thread(target=lambda: callback(check_for_update()), daemon=True).start()
