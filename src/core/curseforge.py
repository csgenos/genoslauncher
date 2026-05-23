"""CurseForge API v1 client — mods and modpacks search/install."""

from __future__ import annotations

import json
import logging
import hashlib
import ipaddress
import os
import socket
import tempfile
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import APP_DIR
from .secure_store import get_secret

log = logging.getLogger(__name__)

_BASE = "https://api.curseforge.com/v1"
_GAME_ID = 432   # Minecraft game ID in CurseForge

# CurseForge class IDs
_CLASS_MOD      = 6
_CLASS_MODPACK  = 4471
_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
_MAX_ZIP_FILES = 5000
_MAX_ZIP_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 100
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

# ---------------------------------------------------------------------------
# Built-in API key (baked in at build time via CI secret CURSEFORGE_API_KEY)
# Priority: GENOS_CURSEFORGE_API_KEY env var (set by runtime hook in frozen
#           build) -> user-supplied key stored in the secure store
# ---------------------------------------------------------------------------
_BUILTIN_CF_KEY: str = os.environ.get("GENOS_CURSEFORGE_API_KEY", "")


class CurseForgeError(Exception):
    pass


def _key() -> str:
    """Return the best available CurseForge API key."""
    return (
        _BUILTIN_CF_KEY
        or get_secret(APP_DIR, "curseforge_api_key")
    )


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
        return not ip.is_global
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True
    for info in infos:
        addr = info[4][0]
        try:
            if not ipaddress.ip_address(addr).is_global:
                return True
        except ValueError:
            return True
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


def _open_validated_download(url: str, allow_external_hosts: bool, timeout: int = 60) -> requests.Response:
    current_url = url
    for _ in range(6):
        _validate_download_url(current_url, allow_external_hosts=allow_external_hosts)
        resp = _session().get(current_url, stream=True, timeout=timeout, allow_redirects=False)
        if 300 <= resp.status_code < 400:
            location = resp.headers.get("Location", "")
            resp.close()
            if not location:
                raise CurseForgeError(f"Download redirect missing Location header: {current_url}")
            current_url = urllib.parse.urljoin(current_url, location)
            continue
        return resp
    raise CurseForgeError(f"Too many redirects while downloading: {url}")


def is_configured() -> bool:
    """Return True if any API key source is available."""
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

    resp: requests.Response | None = None
    try:
        resp = _open_validated_download(url, allow_external_hosts=allow_unverified, timeout=60)
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
        if resp is not None:
            resp.close()
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


# ---------------------------------------------------------------------------
# Zip validation helpers
# ---------------------------------------------------------------------------

def _validate_zip_limits(zf: zipfile.ZipFile) -> None:
    infos = zf.infolist()
    if len(infos) > _MAX_ZIP_FILES:
        raise CurseForgeError("Archive contains too many files")
    total = 0
    for info in infos:
        total += info.file_size
        if total > _MAX_ZIP_UNCOMPRESSED_BYTES:
            raise CurseForgeError("Archive uncompressed size is too large")
        if info.compress_size and info.file_size / max(info.compress_size, 1) > _MAX_ZIP_COMPRESSION_RATIO:
            raise CurseForgeError(f"Suspicious compression ratio for {info.filename}")


def _safe_path(base_dir: Path, relative: str) -> Optional[Path]:
    """Resolve relative inside base_dir and return only if it stays within base_dir."""
    try:
        target = (base_dir / relative).resolve()
        target.relative_to(base_dir.resolve())
        return target
    except (OSError, ValueError) as exc:
        log.warning("Rejected unsafe archive path %r: %s", relative, exc.__class__.__name__)
    return None


# ---------------------------------------------------------------------------
# CurseForge modpack (.zip) support
# ---------------------------------------------------------------------------

def parse_cf_modpack(zip_path: Path) -> dict:
    """Parse a CurseForge modpack zip. Returns manifest dict."""
    if not zipfile.is_zipfile(zip_path):
        raise CurseForgeError(f"Not a valid CurseForge modpack zip: {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        _validate_zip_limits(zf)
        if "manifest.json" not in zf.namelist():
            raise CurseForgeError("Missing manifest.json inside CurseForge modpack zip")
        manifest = json.loads(zf.read("manifest.json"))
    if not isinstance(manifest, dict):
        raise CurseForgeError("manifest.json is not a JSON object")
    mc_info = manifest.get("minecraft", {})
    if not mc_info.get("version"):
        raise CurseForgeError("manifest.json missing minecraft.version")
    return manifest


def install_cf_modpack_mods(
    manifest: dict,
    instance_dir: Path,
    on_progress=None,
) -> list[str]:
    """Download all mods listed in the CurseForge modpack manifest.

    Returns a list of failed project IDs.
    """
    files = manifest.get("files", [])
    mods_dir = instance_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    for i, file_entry in enumerate(files):
        project_id = file_entry.get("projectID")
        file_id = file_entry.get("fileID")
        required = file_entry.get("required", True)

        if not project_id or not file_id:
            log.warning("Skipping modpack entry missing projectID or fileID: %s", file_entry)
            continue

        if on_progress:
            on_progress(i + 1, len(files), str(project_id))

        try:
            url = get_download_url(int(project_id), int(file_id))
            if not url:
                raise CurseForgeError(f"No download URL for project {project_id}, file {file_id}")
            # Fetch file metadata for hash verification
            files_data = get_mod_files(int(project_id))
            file_meta = next((f for f in files_data if str(f.get("id", "")) == str(file_id)), {})
            sha1, sha512 = hashes_for_file(file_meta)
            filename = file_meta.get("fileName") or f"{project_id}-{file_id}.jar"
            from .modrinth import safe_filename
            filename = safe_filename(filename)
            dest = mods_dir / filename
            download_file(
                url, dest,
                expected_sha1=sha1,
                expected_sha512=sha512,
                allow_unverified=(not sha1 and not sha512),
            )
        except Exception as exc:
            log.warning("Failed to download CF modpack mod %s/%s: %s", project_id, file_id, exc)
            if required:
                failures.append(str(project_id))

    return failures


def extract_cf_overrides(zip_path: Path, dest_dir: Path) -> None:
    """Extract overrides/ from CurseForge modpack zip into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    with zipfile.ZipFile(zip_path) as zf:
        _validate_zip_limits(zf)
        for member in zf.namelist():
            if not member.startswith("overrides/") or member.endswith("/"):
                continue
            relative = member[len("overrides/"):]
            target = _safe_path(dest_dir, relative)
            if target is None:
                raise CurseForgeError(f"Unsafe override path in archive: {member}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
