"""CurseForge API v1 client — mods and modpacks search/install."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import requests

from .config import config

log = logging.getLogger(__name__)

_BASE = "https://api.curseforge.com/v1"
_GAME_ID = 432   # Minecraft game ID in CurseForge

# CurseForge class IDs
_CLASS_MOD      = 6
_CLASS_MODPACK  = 4471


class CurseForgeError(Exception):
    pass


def _key() -> str:
    return config.get("curseforge_api_key", "")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "x-api-key": _key(),
        "Accept": "application/json",
    })
    return s


def is_configured() -> bool:
    return bool(_key())


def search(
    query: str,
    class_id: int = _CLASS_MOD,
    game_version: str = "",
    page_size: int = 20,
    index: int = 0,
) -> tuple[list[dict], int]:
    """Search CurseForge mods or modpacks. Returns (hits, total_count)."""
    if not _key():
        raise CurseForgeError("No CurseForge API key configured. Add one in Settings.")
    params: dict = {
        "gameId":    _GAME_ID,
        "classId":   class_id,
        "searchFilter": query,
        "pageSize":  page_size,
        "index":     index,
        "sortField": 2,   # 2 = Popularity
        "sortOrder": "desc",
    }
    if game_version:
        params["gameVersion"] = game_version
    try:
        resp = _session().get(f"{_BASE}/mods/search", params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        hits_raw = data.get("data", [])
        pagination = data.get("pagination", {})
        total = pagination.get("totalCount", len(hits_raw))
        hits = [_normalize(h) for h in hits_raw]
        return hits, total
    except CurseForgeError:
        raise
    except requests.RequestException as exc:
        raise CurseForgeError(f"CurseForge request failed: {exc}") from exc


def search_mods(query: str, game_version: str = "", page_size: int = 20) -> tuple[list[dict], int]:
    return search(query, _CLASS_MOD, game_version, page_size)


def search_modpacks(query: str, game_version: str = "", page_size: int = 20) -> tuple[list[dict], int]:
    return search(query, _CLASS_MODPACK, game_version, page_size)


def get_download_url(mod_id: int, file_id: int) -> str:
    """Return the CDN download URL for a specific mod file."""
    try:
        resp = _session().get(f"{_BASE}/mods/{mod_id}/files/{file_id}/download-url", timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", "")
    except requests.RequestException as exc:
        raise CurseForgeError(f"Could not fetch download URL: {exc}") from exc


def get_mod_files(mod_id: int, game_version: str = "") -> list[dict]:
    params: dict = {"gameVersion": game_version} if game_version else {}
    try:
        resp = _session().get(f"{_BASE}/mods/{mod_id}/files", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except requests.RequestException as exc:
        raise CurseForgeError(f"Could not fetch mod files: {exc}") from exc


def download_file(url: str, dest: Path, on_progress=None) -> None:
    """Download a file to dest path with optional progress callback(done, total)."""
    try:
        resp = _session().get(url, stream=True, timeout=60)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        done = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)
                    done += len(chunk)
                    if on_progress and total:
                        on_progress(done, total)
        tmp.replace(dest)
    except requests.RequestException as exc:
        raise CurseForgeError(f"Download failed: {exc}") from exc


def _normalize(raw: dict) -> dict:
    """Normalize CurseForge project dict to match Modrinth field names."""
    logo = (raw.get("logo") or {}).get("url", "")
    authors = raw.get("authors", [])
    author = authors[0]["name"] if authors else "Unknown"
    latest_files = raw.get("latestFiles", [])
    categories = [c.get("name", "") for c in raw.get("categories", [])]
    return {
        "id":           raw.get("id", 0),
        "title":        raw.get("name", ""),
        "description":  raw.get("summary", ""),
        "author":       author,
        "downloads":    raw.get("downloadCount", 0),
        "icon_url":     logo,
        "categories":   categories,
        "source":       "curseforge",
        "cf_id":        raw.get("id", 0),
        "latest_files": latest_files,
    }
