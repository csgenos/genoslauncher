"""Secret storage and atomic file helpers."""

from __future__ import annotations

import json
import logging
import os
import platform
import secrets
import subprocess
from pathlib import Path
from typing import Any

try:
    import keyring
except ImportError:  # pragma: no cover - optional dependency
    keyring = None  # type: ignore[assignment]

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:  # pragma: no cover - optional dependency
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment]
    PBKDF2HMAC = None  # type: ignore[assignment]
    hashes = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

SERVICE_NAME = "GenosLauncher"
_FALLBACK_FILE = ".secrets_store"
_FALLBACK_KEY_FILE = ".secrets_key"
_FALLBACK_SALT_FILE = ".secrets_salt"


def _restrict_file(path: Path) -> None:
    """Best-effort owner-only permissions on supported platforms."""
    try:
        if platform.system() == "Windows":
            username = os.environ.get("USERNAME") or os.getlogin()
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                shell=False,
            )
        else:
            os.chmod(path, 0o600)
    except Exception:
        log.debug("Unable to harden permissions for %s", path, exc_info=True)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically replace path with data and restrict file permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with open(tmp, "xb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        _restrict_file(tmp)
        os.replace(tmp, path)
        _restrict_file(path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def secure_delete(path: Path) -> None:
    """Best-effort deletion for local credential fallback files."""
    try:
        if not path.exists() or not path.is_file():
            return
        size = path.stat().st_size
        with open(path, "r+b") as fh:
            if size:
                fh.write(b"\x00" * size)
                fh.flush()
                os.fsync(fh.fileno())
        path.unlink()
    except OSError:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.debug("Unable to delete %s", path, exc_info=True)


def _fallback_paths(app_dir: Path) -> tuple[Path, Path]:
    return app_dir / _FALLBACK_FILE, app_dir / _FALLBACK_KEY_FILE


def _fallback_salt(app_dir: Path) -> bytes:
    salt_path = app_dir / _FALLBACK_SALT_FILE
    if salt_path.exists():
        salt = salt_path.read_bytes()
        if len(salt) >= 16:
            return salt[:32]
    salt = secrets.token_bytes(16)
    atomic_write_bytes(salt_path, salt)
    return salt


def _fallback_cipher(app_dir: Path) -> Any:
    if Fernet is None or PBKDF2HMAC is None or hashes is None:
        raise RuntimeError("cryptography is not available for encrypted fallback storage")
    _, key_path = _fallback_paths(app_dir)
    if key_path.exists():
        secret = key_path.read_bytes()
    else:
        secret = secrets.token_bytes(32)
        atomic_write_bytes(key_path, secret)
    import base64

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_fallback_salt(app_dir),
        iterations=390000,
    )
    return Fernet(base64.urlsafe_b64encode(kdf.derive(secret)))


def _read_fallback(app_dir: Path) -> dict[str, str]:
    store_path, _ = _fallback_paths(app_dir)
    if not store_path.exists():
        return {}
    try:
        cipher = _fallback_cipher(app_dir)
        payload = cipher.decrypt(store_path.read_bytes())
        data = json.loads(payload.decode("utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (OSError, ValueError, InvalidToken, RuntimeError):
        log.warning("Encrypted fallback secret store could not be read")
    return {}


def _write_fallback(app_dir: Path, data: dict[str, str]) -> None:
    store_path, _ = _fallback_paths(app_dir)
    cipher = _fallback_cipher(app_dir)
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    atomic_write_bytes(store_path, cipher.encrypt(payload))


def _account(key: str) -> str:
    return f"config:{key}"


def set_secret(app_dir: Path, key: str, value: str) -> None:
    """Store a secret in keyring, falling back to encrypted local storage."""
    value = str(value)
    if keyring is not None:
        try:
            keyring.set_password(SERVICE_NAME, _account(key), value)
            data = _read_fallback(app_dir)
            if key in data:
                data.pop(key, None)
                if data:
                    _write_fallback(app_dir, data)
                else:
                    store_path, _ = _fallback_paths(app_dir)
                    secure_delete(store_path)
            return
        except Exception:
            log.warning("System keyring failed; using encrypted fallback for %s", key, exc_info=True)
    data = _read_fallback(app_dir)
    data[key] = value
    _write_fallback(app_dir, data)


def get_secret(app_dir: Path, key: str) -> str:
    """Read a secret from keyring or encrypted fallback."""
    if keyring is not None:
        try:
            value = keyring.get_password(SERVICE_NAME, _account(key))
            if value is not None:
                return value
        except Exception:
            log.warning("System keyring read failed for %s", key, exc_info=True)
    return _read_fallback(app_dir).get(key, "")


def delete_secret(app_dir: Path, key: str) -> None:
    """Delete a secret from both keyring and encrypted fallback."""
    if keyring is not None:
        try:
            keyring.delete_password(SERVICE_NAME, _account(key))
        except Exception:
            pass
    data = _read_fallback(app_dir)
    if key in data:
        data.pop(key, None)
        if data:
            _write_fallback(app_dir, data)
        else:
            store_path, _ = _fallback_paths(app_dir)
            secure_delete(store_path)
