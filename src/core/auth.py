"""
Microsoft Account authentication manager for GenosLauncher.

Flow (PKCE, no client secret — safe for public desktop apps):
  1. get_secure_login_data  → (state, code_challenge, code_verifier)
  2. Build login URL with PKCE params and open browser
  3. Local HTTP server captures callback on localhost:{port}
  4. parse_auth_code_url + complete_login → CompleteLoginResponse
  5. Store refresh_token in system keyring
  6. complete_refresh re-uses the stored token on future launches

Security fixes applied:
  S-Z-001: Fernet-encrypted fallback with machine-bound PBKDF2 key; secure delete on logout
  S-Y-002: Dynamic port binding (increments on EADDRINUSE); threading.Event for clean shutdown
  S-X-009: APP_DIR permissions handled in config.py; fallback file set to 0o600
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import keyring
    _KEYRING_OK = True
except ImportError:
    _KEYRING_OK = False
    print("[Auth] Warning: keyring not installed — tokens stored in encrypted fallback file.")

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    import base64 as _b64
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False
    print("[Auth] Warning: cryptography not installed — install it for secure fallback storage.")

from minecraft_launcher_lib.microsoft_account import (
    complete_login,
    complete_refresh,
    get_login_url,
    get_secure_login_data,
    parse_auth_code_url,
)

from .config import APP_DIR, config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KEYRING_SERVICE    = "GenosLauncher"
_KEYRING_ACCOUNT    = "ms_account_json"
_FALLBACK_STORE     = APP_DIR / ".auth_store"

DEFAULT_CLIENT_ID      = ""
DEFAULT_REDIRECT_PORT  = 8090
_PORT_SEARCH_RANGE     = 10


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AuthError(Exception):
    """Raised on any authentication failure."""


class NoClientIdError(AuthError):
    """Raised when no Azure client ID has been configured."""


# ---------------------------------------------------------------------------
# Fallback encryption helpers (S-Z-001)
# ---------------------------------------------------------------------------

def _derive_fallback_key() -> bytes:
    """
    Derive a Fernet-compatible key bound to this machine.
    Uses PBKDF2-HMAC-SHA256(machine_MAC, fixed_salt, 100k iterations).
    """
    import uuid
    machine_id = str(uuid.getnode()).encode("utf-8")
    salt = b"GenosLauncher-fallback-auth-v1"

    if _CRYPTO_OK:
        kdf = PBKDF2HMAC(
            algorithm=_hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        raw = kdf.derive(machine_id)
        return _b64.urlsafe_b64encode(raw)

    # Fallback if cryptography not installed — plain SHA-256 (weak but better than nothing)
    import base64
    digest = hashlib.sha256(salt + machine_id).digest()
    return base64.urlsafe_b64encode(digest)


def _encrypt_payload(payload: str) -> bytes:
    if _CRYPTO_OK:
        return Fernet(_derive_fallback_key()).encrypt(payload.encode("utf-8"))
    import base64
    return base64.b64encode(payload.encode("utf-8"))


def _decrypt_payload(data: bytes) -> str:
    if _CRYPTO_OK:
        try:
            return Fernet(_derive_fallback_key()).decrypt(data).decode("utf-8")
        except (InvalidToken, Exception):
            pass
    # Legacy / non-Fernet fallback (base64 or plaintext)
    try:
        import base64
        return base64.b64decode(data).decode("utf-8")
    except Exception:
        return data.decode("utf-8", errors="replace")


def _secure_delete(path: Path) -> None:
    """Overwrite file with random bytes before unlinking (S-Z-001)."""
    try:
        size = path.stat().st_size
        if size > 0:
            with open(path, "r+b") as fh:
                fh.write(os.urandom(size))
                fh.flush()
                os.fsync(fh.fileno())
        path.unlink()
    except OSError:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _store_account(data: dict) -> None:
    """Persist account JSON to keyring (or encrypted fallback file)."""
    payload = json.dumps(data)
    if _KEYRING_OK:
        try:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, payload)
            if _FALLBACK_STORE.exists():
                _secure_delete(_FALLBACK_STORE)
            return
        except Exception as exc:
            print(f"[Auth] Keyring write failed ({exc}), using encrypted fallback.")
    ciphertext = _encrypt_payload(payload)
    _FALLBACK_STORE.write_bytes(ciphertext)
    if os.name != "nt":
        try:
            os.chmod(_FALLBACK_STORE, 0o600)
        except OSError:
            pass


def _load_account() -> Optional[dict]:
    """Load persisted account JSON from keyring (or encrypted fallback file)."""
    if _KEYRING_OK:
        try:
            payload = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
            if payload:
                return json.loads(payload)
        except Exception:
            pass
    if _FALLBACK_STORE.exists():
        try:
            raw = _FALLBACK_STORE.read_bytes()
            payload = _decrypt_payload(raw)
            return json.loads(payload)
        except Exception:
            pass
    return None


def _delete_account() -> None:
    """Remove persisted account from keyring / fallback file."""
    if _KEYRING_OK:
        try:
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
        except Exception:
            pass
    if _FALLBACK_STORE.exists():
        _secure_delete(_FALLBACK_STORE)


def _login_response_to_dict(resp) -> dict:
    return {
        "id":            resp.id,
        "name":          resp.name,
        "access_token":  resp.access_token,
        "refresh_token": resp.refresh_token,
    }


# ---------------------------------------------------------------------------
# Local callback HTTP server (S-Y-002)
# ---------------------------------------------------------------------------

class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Captures the OAuth2 redirect URL and signals the login thread."""

    captured_url: Optional[str] = None
    done_event:   Optional[threading.Event] = None

    def do_GET(self) -> None:
        _CallbackHandler.captured_url = f"http://localhost{self.path}"
        if _CallbackHandler.done_event is not None:
            _CallbackHandler.done_event.set()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<!DOCTYPE html><html><body style='"
            b"font-family:system-ui,sans-serif;text-align:center;padding-top:80px;"
            b"background:#F8F9FA;color:#111827'>"
            b"<h2 style='font-size:24px;font-weight:700'>Login successful!</h2>"
            b"<p style='color:#4B5563'>You can close this tab and return to GenosLauncher.</p>"
            b"</body></html>"
        )

    def log_message(self, *_args) -> None:
        pass


def _bind_callback_server(preferred_port: int) -> tuple[http.server.HTTPServer, int]:
    """
    Bind an HTTPServer starting at preferred_port, incrementing on EADDRINUSE.
    Raises OSError if all ports in range are unavailable.
    """
    for offset in range(_PORT_SEARCH_RANGE):
        port = preferred_port + offset
        try:
            server = http.server.HTTPServer(("localhost", port), _CallbackHandler)
            return server, port
        except OSError:
            continue
    raise OSError(
        f"Could not bind OAuth callback on ports "
        f"{preferred_port}–{preferred_port + _PORT_SEARCH_RANGE - 1}. "
        "Close any conflicting applications or change the redirect port in Settings."
    )


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------

class AuthManager:
    """
    Manages Microsoft / Minecraft account authentication.

    Usage:
        mgr = AuthManager()
        mgr.load_stored()        # restore from keyring on startup
        mgr.start_login(...)     # PKCE browser flow
        mgr.refresh()            # silent token refresh
        mgr.logout()             # secure wipe
    """

    def __init__(self) -> None:
        self._account: Optional[dict] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_logged_in(self) -> bool:
        return bool(self._account and self._account.get("access_token"))

    @property
    def username(self) -> str:
        return (self._account or {}).get("name", "")

    @property
    def uuid(self) -> str:
        return (self._account or {}).get("id", "")

    @property
    def access_token(self) -> str:
        return (self._account or {}).get("access_token", "")

    @property
    def refresh_token(self) -> str:
        return (self._account or {}).get("refresh_token", "")

    # ------------------------------------------------------------------
    # Load / persist
    # ------------------------------------------------------------------

    def load_stored(self) -> bool:
        data = _load_account()
        if data and data.get("name") and data.get("refresh_token"):
            self._account = data
            return True
        return False

    # ------------------------------------------------------------------
    # Login flow
    # ------------------------------------------------------------------

    def start_login(
        self,
        on_url_ready: Callable[[str], None],
        on_success:   Callable[[dict], None],
        on_error:     Callable[[str], None],
        open_browser: bool = True,
    ) -> None:
        """Start the PKCE browser login flow on a background thread."""
        client_id = config.get("azure_client_id", "")
        if not client_id:
            on_error(
                "No Azure Client ID configured.\n\n"
                "Go to Settings → Microsoft Authentication and paste your "
                "Azure App (client) ID.\n\nSee README for step-by-step setup."
            )
            return

        thread = threading.Thread(
            target=self._login_thread,
            args=(client_id, on_url_ready, on_success, on_error, open_browser),
            daemon=True,
        )
        thread.start()

    def _login_thread(
        self,
        client_id: str,
        on_url_ready: Callable,
        on_success: Callable,
        on_error: Callable,
        open_browser: bool,
    ) -> None:
        preferred_port = config.get("auth_redirect_port", DEFAULT_REDIRECT_PORT)

        # Bind first so the actual port is known before building the auth URL (S-Y-002)
        try:
            server, actual_port = _bind_callback_server(preferred_port)
        except OSError as exc:
            on_error(str(exc))
            return

        redirect_uri = f"http://localhost:{actual_port}"
        try:
            state, code_challenge, code_verifier = get_secure_login_data(
                client_id, redirect_uri
            )
            base_url = get_login_url(client_id, redirect_uri)
            pkce_url = (
                f"{base_url}"
                f"&state={urllib.parse.quote(state)}"
                f"&code_challenge={code_challenge}"
                f"&code_challenge_method=S256"
            )

            on_url_ready(pkce_url)
            if open_browser:
                webbrowser.open(pkce_url)

            done_event = threading.Event()
            _CallbackHandler.captured_url = None
            _CallbackHandler.done_event   = done_event

            server.timeout = 1.0   # handle_request blocks at most 1s per call
            deadline = time.monotonic() + 300

            while not done_event.is_set():
                if time.monotonic() > deadline:
                    server.server_close()
                    on_error("Login timed out (5 min). Please try again.")
                    return
                server.handle_request()

            server.server_close()

            callback_url = _CallbackHandler.captured_url
            if not callback_url:
                on_error("OAuth callback did not return a URL.")
                return

            auth_code = parse_auth_code_url(callback_url, state)
            if not auth_code:
                on_error(
                    "Could not extract authorisation code from the callback URL.\n"
                    f"Ensure your Azure App redirect URI is exactly:\n  {redirect_uri}"
                )
                return

            response = complete_login(
                client_id, None, redirect_uri, auth_code, code_verifier
            )

            if getattr(response, "error", None) or getattr(response, "errorMessage", None):
                on_error(
                    getattr(response, "errorMessage", None)
                    or getattr(response, "error", "Unknown error")
                )
                return

            account = _login_response_to_dict(response)
            with self._lock:
                self._account = account
            _store_account(account)
            on_success(account)

        except Exception as exc:
            try:
                server.server_close()
            except Exception:
                pass
            on_error(str(exc))

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    def refresh(self) -> bool:
        if not self.refresh_token:
            return False
        client_id = config.get("azure_client_id", "")
        if not client_id:
            return False
        port = config.get("auth_redirect_port", DEFAULT_REDIRECT_PORT)
        redirect_uri = f"http://localhost:{port}"
        try:
            response = complete_refresh(client_id, None, redirect_uri, self.refresh_token)
            if getattr(response, "error", None):
                return False
            account = _login_response_to_dict(response)
            with self._lock:
                self._account = account
            _store_account(account)
            return True
        except Exception as exc:
            print(f"[Auth] Token refresh failed: {exc}")
            return False

    def refresh_async(self) -> None:
        threading.Thread(target=self.refresh, daemon=True).start()

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(self) -> None:
        with self._lock:
            self._account = None
        _delete_account()

    # ------------------------------------------------------------------
    # Avatar
    # ------------------------------------------------------------------

    def fetch_avatar_url(self) -> Optional[str]:
        if not self.uuid:
            return None
        return f"https://crafatar.com/avatars/{self.uuid}?size=64&overlay"

    def download_avatar(self, dest: Path) -> bool:
        url = self.fetch_avatar_url()
        if not url:
            return False
        try:
            import requests as req
            resp = req.get(url, timeout=10)
            if resp.ok:
                dest.write_bytes(resp.content)
                return True
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

auth_manager = AuthManager()
