"""
Modrinth API client for GenosLauncher.

Covers: search (modpacks, shaders, resource packs), version listing,
file download with progress callbacks, and .mrpack parsing.

All network calls are synchronous; callers should run them in worker threads.

Security fixes applied:
  S-Y-006: SHA1/SHA512 hash verification after every mod download;
           atomic temp-file-then-rename pattern
  B-Y-010: Zip-slip protection in extract_mrpack_overrides and install_mrpack_mods
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

import requests

BASE_URL   = "https://api.modrinth.com/v2"
USER_AGENT = "GenosLauncher/0.2.0 (github.com/csgenos/genoslauncher)"

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})
log = logging.getLogger(__name__)

_cache: dict[str, tuple[str, Any]] = {}
_cache_lock = threading.Lock()
_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
_MAX_ZIP_FILES = 5000
_MAX_ZIP_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 100


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ModrinthError(Exception):
    """Raised on any Modrinth API or network failure."""


# ---------------------------------------------------------------------------
# Low-level request helper
# ---------------------------------------------------------------------------

def _get(endpoint: str, params: dict | None = None, timeout: int = 15) -> Any:
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
# Data helpers
# ---------------------------------------------------------------------------

def _project_from_hit(hit: dict) -> dict:
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
    facets: list[list[str]] = [[f"project_type:{project_type}"]]
    if game_version:
        facets.append([f"versions:{game_version}"])
    if categories:
        facets.append([f"categories:{c}" for c in categories])

    params: dict[str, Any] = {
        "query":  query,
        "facets": json.dumps(facets),
        "limit":  limit,
        "offset": offset,
        "index":  "downloads",
    }
    data = _get("/search", params)
    hits = [_project_from_hit(h) for h in data.get("hits", [])]
    return hits, data.get("total_hits", len(hits))


def search_modpacks(query="", game_version="", limit=20, offset=0):
    return search_projects(query, "modpack", game_version, limit, offset)

def search_shaders(query="", game_version="", limit=20, offset=0):
    return search_projects(query, "shader", game_version, limit, offset)

def search_resource_packs(query="", game_version="", limit=20, offset=0):
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
# File download — atomic + hash verification (S-Y-006)
# ---------------------------------------------------------------------------

def download_file(
    url: str,
    dest_path: Path,
    on_progress: Callable[[int, int], None] | None = None,
    chunk_size: int = 65536,
    expected_sha1: str = "",
    expected_sha512: str = "",
    allow_unverified: bool = False,
) -> None:
    """
    Stream-download url → dest_path.

    Writes to a .tmp file, verifies SHA1/SHA512 if provided, then atomically
    renames to dest_path.  Cleans up on any error.

    Raises ModrinthError on network failure or hash mismatch.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ModrinthError(f"Refusing non-HTTPS download URL: {url}")
    if not allow_unverified and not (expected_sha1 or expected_sha512):
        raise ModrinthError(f"Refusing unverified download with no hash: {url}")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".download_tmp")

    sha1_h   = hashlib.sha1()   if expected_sha1   else None
    sha512_h = hashlib.sha512() if expected_sha512 else None

    try:
        with _session.get(url, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            if total > _MAX_DOWNLOAD_BYTES:
                raise ModrinthError(f"Download too large: {total} bytes")
            done  = 0
            with open(tmp_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    done += len(chunk)
                    if done > _MAX_DOWNLOAD_BYTES:
                        raise ModrinthError("Download exceeded maximum allowed size")
                    if sha1_h:   sha1_h.update(chunk)
                    if sha512_h: sha512_h.update(chunk)
                    if on_progress:
                        on_progress(done, total)

        if expected_sha1 and sha1_h and sha1_h.hexdigest() != expected_sha1:
            tmp_path.unlink(missing_ok=True)
            raise ModrinthError(
                f"SHA1 mismatch for {dest_path.name}: "
                f"got {sha1_h.hexdigest()}, expected {expected_sha1}"
            )
        if expected_sha512 and sha512_h and sha512_h.hexdigest() != expected_sha512:
            tmp_path.unlink(missing_ok=True)
            raise ModrinthError(
                f"SHA512 mismatch for {dest_path.name}: "
                f"got {sha512_h.hexdigest()}, expected {expected_sha512}"
            )

        tmp_path.replace(dest_path)

    except requests.RequestException as exc:
        tmp_path.unlink(missing_ok=True)
        raise ModrinthError(f"Download failed: {exc}") from exc
    except ModrinthError:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise ModrinthError(f"Unexpected error downloading {url}: {exc}") from exc


def download_icon(icon_url: str, cache_dir: Path) -> Optional[Path]:
    """Download a project icon to disk; return cached path or None on error."""
    if not icon_url:
        return None
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", icon_url.split("/")[-1])
    dest = cache_dir / safe
    if dest.exists():
        return dest
    try:
        download_file(icon_url, dest, allow_unverified=True)
        return dest
    except ModrinthError:
        return None


# ---------------------------------------------------------------------------
# .mrpack parsing and installation
# ---------------------------------------------------------------------------

MRPACK_MAGIC = "modrinth.index.json"


def parse_mrpack(mrpack_path: Path) -> dict:
    """Open a .mrpack ZIP and return the parsed modrinth.index.json dict."""
    if not zipfile.is_zipfile(mrpack_path):
        raise ModrinthError(f"Not a valid .mrpack file: {mrpack_path}")
    with zipfile.ZipFile(mrpack_path) as zf:
        _validate_zip_limits(zf)
        if MRPACK_MAGIC not in zf.namelist():
            raise ModrinthError("Missing modrinth.index.json inside .mrpack")
        return json.loads(zf.read(MRPACK_MAGIC))


def _validate_zip_limits(zf: zipfile.ZipFile) -> None:
    infos = zf.infolist()
    if len(infos) > _MAX_ZIP_FILES:
        raise ModrinthError("Archive contains too many files")
    total = 0
    for info in infos:
        total += info.file_size
        if total > _MAX_ZIP_UNCOMPRESSED_BYTES:
            raise ModrinthError("Archive uncompressed size is too large")
        if info.compress_size and info.file_size / max(info.compress_size, 1) > _MAX_ZIP_COMPRESSION_RATIO:
            raise ModrinthError(f"Suspicious compression ratio for {info.filename}")


def _safe_path(base_dir: Path, relative: str) -> Optional[Path]:
    """
    Resolve relative inside base_dir and return the result only if it stays
    within base_dir (zip-slip protection — B-Y-010).
    """
    try:
        target = (base_dir / relative).resolve()
        target.relative_to(base_dir.resolve())
        return target
    except (OSError, ValueError) as exc:
        log.warning("Rejected unsafe archive path %r: %s", relative, exc.__class__.__name__)
    return None


def extract_mrpack_overrides(mrpack_path: Path, dest_dir: Path) -> None:
    """Extract the overrides/ folder from a .mrpack into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(mrpack_path) as zf:
        _validate_zip_limits(zf)
        for member in zf.namelist():
            if not member.startswith("overrides/") or member.endswith("/"):
                continue
            relative = member[len("overrides/"):]
            target = _safe_path(dest_dir, relative)
            if target is None:
                log.warning("Skipping unsafe path in overrides: %s", member)
                continue
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
    Verifies SHA1/SHA512 hashes from the index (S-Y-006).
    Skips paths that would escape mods_dir (B-Y-010).

    on_progress(current_file, total_files, filename)
    """
    files = index.get("files", [])
    mods_dir.mkdir(parents=True, exist_ok=True)

    for i, file_entry in enumerate(files):
        raw_path = file_entry.get("path", "").lstrip("/")

        # Strip any traversal components before taking just the filename
        parts = [p for p in Path(raw_path).parts if p not in (".", "..")]
        if not parts:
            continue
        filename = Path(*parts).name
        dest = _safe_path(mods_dir, filename)
        if dest is None:
            log.warning("Skipping unsafe mod path: %s", raw_path)
            continue

        if on_progress:
            on_progress(i + 1, len(files), filename)

        if dest.exists():
            continue

        hashes = file_entry.get("hashes", {})
        sha1   = hashes.get("sha1", "")
        sha512 = hashes.get("sha512", "")

        urls: list[str] = file_entry.get("downloads", [])
        downloaded = False
        for url in urls:
            try:
                download_file(url, dest, expected_sha1=sha1, expected_sha512=sha512)
                downloaded = True
                break
            except ModrinthError:
                continue

        if not downloaded:
            log.warning("Could not download %s", filename)
