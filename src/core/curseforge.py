"""CurseForge API v1 client — mods and modpacks search/install."""

from __future__ import annotations

import logging
import hashlib
import ipaddress
import tempfile
import urllib.parse
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import config

log = logging.getLogger(__name__)

_BASE = "https://api.curseforge.com/v1"
_GAME_ID = 432   # Minecraft game ID in CurseForge

# CurseForge class IDs
_CLASS_MOD      = 6
_CLASS_MODPACK  = 4471
_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
_ALLOWED_DOWNLOAD_HOST_SUFFIXES = (
    "curseforge.com",
    "forgecdn.net",
    "overwolf.com",
)
_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})
_SESSION.mount(
    "https://",
    HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.4, status_forcelist=(429, 500, 502, 503, 504))),
)


class CurseForgeError(Exception):
    pass


def _key() -> str:
    return config.get("curseforge_api_key", "")


def _session() -> requests.Session:
    return _SESSION


def _headers() -> dict[str, str]:
    return {"x-api-key": _key()}


def _is_blocked_host(hostname: str) -> bool:
    host = hostname.strip().lower().strip("[]")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
    except ValueError:
        return False


def _validate_download_url(url: str, allow_external_hosts: bool = False) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https":
        raise CurseForgeError(f"Refusing non-HTTPS download URL: {url}")
    hostname = parsed.hostname or ""
    if not hostname or _is_blocked_host(hostname):
        raise CurseForgeError(f"Refusing blocked download host: {hostname or url}")
    if not allow_external_hosts and not any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in _ALLOWED_DOWNLOAD_HOST_SUFFIXES
    ):
        raise CurseForgeError(f"Refusing unapproved download host: {hostname}")


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
        resp = _session().get(f"{_BASE}/mods/search", params=params, headers=_headers(), timeout=12)
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
        resp = _session().get(
            f"{_BASE}/mods/{mod_id}/files/{file_id}/download-url",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("data", "")
    except requests.RequestException as exc:
        raise CurseForgeError(f"Could not fetch download URL: {exc}") from exc


def get_mod_files(mod_id: int, game_version: str = "") -> list[dict]:
    params: dict = {"gameVersion": game_version} if game_version else {}
    try:
        resp = _session().get(f"{_BASE}/mods/{mod_id}/files", params=params, headers=_headers(), timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except requests.RequestException as exc:
        raise CurseForgeError(f"Could not fetch mod files: {exc}") from exc


def hashes_for_file(file_info: dict) -> tuple[str, str]:
    """Return (sha1, sha512) from CurseForge file metadata when available."""
    sha1 = ""
    sha512 = ""
    for item in file_info.get("hashes", []) or []:
        algo = str(item.get("algo", "")).lower()
        value = str(item.get("value", "")).strip()
        if algo in {"1", "sha1"}:
            sha1 = value
        elif algo in {"sha512", "512"}:
            sha512 = value
    return sha1, sha512


def download_file(
    url: str,
    dest: Path,
    on_progress=None,
    expected_sha1: str = "",
    expected_sha512: str = "",
    allow_unverified: bool = False,
    max_bytes: int = _MAX_DOWNLOAD_BYTES,
) -> None:
    """Download a CurseForge file with HTTPS, size, and hash protections."""
    _validate_download_url(url, allow_external_hosts=allow_unverified)
    expected_sha1 = expected_sha1.strip().lower()
    expected_sha512 = expected_sha512.strip().lower()
    if not allow_unverified and not (expected_sha1 or expected_sha512):
        raise CurseForgeError(f"Refusing unverified download with no hash: {url}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    sha1_h = hashlib.sha1(usedforsecurity=False) if expected_sha1 else None
    sha512_h = hashlib.sha512() if expected_sha512 else None

    try:
        resp = _session().get(url, stream=True, headers=_headers(), timeout=60)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        if total > max_bytes:
            raise CurseForgeError(f"Download too large: {total} bytes")
        done = 0
        with tempfile.NamedTemporaryFile(delete=False, dir=dest.parent, suffix=".download_tmp") as fh:
            tmp_path = Path(fh.name)
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)
                    done += len(chunk)
                    if done > max_bytes:
                        raise CurseForgeError("Download exceeded maximum allowed size")
                    if sha1_h:
                        sha1_h.update(chunk)
                    if sha512_h:
                        sha512_h.update(chunk)
                    if on_progress and total:
                        on_progress(done, total)
        if expected_sha1 and sha1_h and sha1_h.hexdigest() != expected_sha1:
            raise CurseForgeError(f"SHA1 mismatch for {dest.name}")
        if expected_sha512 and sha512_h and sha512_h.hexdigest() != expected_sha512:
            raise CurseForgeError(f"SHA512 mismatch for {dest.name}")
        tmp_path.replace(dest)
    except requests.RequestException as exc:
        raise CurseForgeError(f"Download failed: {exc}") from exc
    except Exception:
        raise
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


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
