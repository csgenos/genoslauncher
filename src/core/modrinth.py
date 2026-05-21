"""
Modrinth API client for GenosLauncher.

Covers: search (modpacks, shaders, resource packs), version listing,
file download with progress callbacks, and .mrpack parsing.

All network calls are synchronous; callers should run them in worker threads.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

import requests

BASE_URL = "https://api.modrinth.com/v2"
USER_AGENT = "GenosLauncher/0.2.0 (github.com/csgenos/genoslauncher)"

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})

# Simple in-memory cache (key → (etag, data))
_cache: dict[str, tuple[str, Any]] = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Low-level request helper
# ---------------------------------------------------------------------------

def _get(endpoint: str, params: dict | None = None, timeout: int = 15) -> Any:
    """GET request with ETag caching. Returns parsed JSON."""
    url = f"{BASE_URL}{endpoint}"
    cache_key = url + str(sorted((params or {}).items()))

    headers: dict[str, str] = {}
    with _cache_lock:
        if cache_key in _cache:
            etag, cached_data = _cache[cache_key]
            headers["If-None-Match"] = etag

    try:
        resp = _session.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise ModrinthError(f"Network error: {exc}") from exc

    if resp.status_code == 304:
        with _cache_lock:
            return _cache[cache_key][1]

    if not resp.ok:
        raise ModrinthError(f"Modrinth API error {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    etag = resp.headers.get("ETag", "")
    if etag:
        with _cache_lock:
            _cache[cache_key] = (etag, data)
    return data


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ModrinthError(Exception):
    """Raised on any Modrinth API or network failure."""


# ---------------------------------------------------------------------------
# Data classes (simple dicts — no dataclass to keep deps minimal)
# ---------------------------------------------------------------------------

def _project_from_hit(hit: dict) -> dict:
    """Normalise a search hit into a standard project dict."""
    return {
        "id":           hit.get("project_id", ""),
        "slug":         hit.get("slug", ""),
        "title":        hit.get("title", "Unknown"),
        "description":  hit.get("description", ""),
        "author":       hit.get("author", "Unknown"),
        "icon_url":     hit.get("icon_url", ""),
        "downloads":    hit.get("downloads", 0),
        "follows":      hit.get("follows", 0),
        "categories":   hit.get("categories", []),
        "versions":     hit.get("versions", []),
        "project_type": hit.get("project_type", ""),
        "date_modified":hit.get("date_modified", ""),
        "color":        hit.get("color"),
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_projects(
    query: str = "",
    project_type: str = "modpack",
    game_version: str = "",
    limit: int = 20,
    offset: int = 0,
    categories: list[str] | None = None,
) -> tuple[list[dict], int]:
    """
    Search Modrinth projects.

    project_type: "modpack" | "shader" | "resourcepack" | "mod"

    Returns (hits, total_hits).
    """
    facets: list[list[str]] = [[f"project_type:{project_type}"]]
    if game_version:
        facets.append([f"versions:{game_version}"])
    if categories:
        facets.append([f"categories:{c}" for c in categories])

    params: dict[str, Any] = {
        "query":   query,
        "facets":  json.dumps(facets),
        "limit":   limit,
        "offset":  offset,
        "index":   "downloads",
    }

    data = _get("/search", params)
    hits = [_project_from_hit(h) for h in data.get("hits", [])]
    return hits, data.get("total_hits", len(hits))


def search_modpacks(query: str = "", game_version: str = "", limit: int = 20, offset: int = 0):
    return search_projects(query, "modpack", game_version, limit, offset)

def search_shaders(query: str = "", game_version: str = "", limit: int = 20, offset: int = 0):
    return search_projects(query, "shader", game_version, limit, offset)

def search_resource_packs(query: str = "", game_version: str = "", limit: int = 20, offset: int = 0):
    return search_projects(query, "resourcepack", game_version, limit, offset)


# ---------------------------------------------------------------------------
# Project & version details
# ---------------------------------------------------------------------------

def get_project(project_id_or_slug: str) -> dict:
    return _get(f"/project/{project_id_or_slug}")


def get_project_versions(
    project_id_or_slug: str,
    game_versions: list[str] | None = None,
    loaders: list[str] | None = None,
) -> list[dict]:
    params: dict[str, Any] = {}
    if game_versions:
        params["game_versions"] = json.dumps(game_versions)
    if loaders:
        params["loaders"] = json.dumps(loaders)
    return _get(f"/project/{project_id_or_slug}/version", params)


def get_version(version_id: str) -> dict:
    return _get(f"/version/{version_id}")


# ---------------------------------------------------------------------------
# File download
# ---------------------------------------------------------------------------

def download_file(
    url: str,
    dest_path: Path,
    on_progress: Callable[[int, int], None] | None = None,
    chunk_size: int = 65536,
) -> None:
    """
    Stream-download url → dest_path.

    on_progress(bytes_downloaded, total_bytes) called periodically.
    Raises ModrinthError on failure.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _session.get(url, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            with open(dest_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        fh.write(chunk)
                        done += len(chunk)
                        if on_progress:
                            on_progress(done, total)
    except requests.RequestException as exc:
        raise ModrinthError(f"Download failed: {exc}") from exc


def download_icon(icon_url: str, cache_dir: Path) -> Optional[Path]:
    """Download a project icon to disk; return cached path or None on error."""
    if not icon_url:
        return None
    # Derive a safe filename from the URL
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", icon_url.split("/")[-1])
    dest = cache_dir / safe
    if dest.exists():
        return dest
    try:
        download_file(icon_url, dest)
        return dest
    except ModrinthError:
        return None


# ---------------------------------------------------------------------------
# .mrpack parsing and installation
# ---------------------------------------------------------------------------

MRPACK_MAGIC = "modrinth.index.json"


def parse_mrpack(mrpack_path: Path) -> dict:
    """
    Open a .mrpack file (ZIP) and return the parsed modrinth.index.json dict.

    Raises ModrinthError if the file is invalid.
    """
    if not zipfile.is_zipfile(mrpack_path):
        raise ModrinthError(f"Not a valid .mrpack file: {mrpack_path}")
    with zipfile.ZipFile(mrpack_path) as zf:
        if MRPACK_MAGIC not in zf.namelist():
            raise ModrinthError("Missing modrinth.index.json inside .mrpack")
        return json.loads(zf.read(MRPACK_MAGIC))


def extract_mrpack_overrides(mrpack_path: Path, dest_dir: Path) -> None:
    """
    Extract the overrides/ folder from a .mrpack into dest_dir.
    These are config files, options.txt, etc. bundled with the pack.
    """
    with zipfile.ZipFile(mrpack_path) as zf:
        for member in zf.namelist():
            if member.startswith("overrides/") and not member.endswith("/"):
                relative = member[len("overrides/"):]
                target = dest_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)


def install_mrpack_mods(
    index: dict,
    mods_dir: Path,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> None:
    """
    Download all mod files listed in the mrpack index into mods_dir.

    on_progress(current_file, total_files, filename)
    """
    files = index.get("files", [])
    mods_dir.mkdir(parents=True, exist_ok=True)

    for i, file_entry in enumerate(files):
        path_parts = file_entry.get("path", "").lstrip("/")
        filename = Path(path_parts).name
        dest = mods_dir / filename

        if on_progress:
            on_progress(i + 1, len(files), filename)

        if dest.exists():
            continue

        # Try each download URL in order
        urls: list[str] = file_entry.get("downloads", [])
        downloaded = False
        for url in urls:
            try:
                download_file(url, dest)
                downloaded = True
                break
            except ModrinthError:
                continue

        if not downloaded:
            print(f"[Modrinth] Warning: could not download {filename}")
