"""
Microsoft Account authentication — PKCE Authorization Code Flow.

Flow (OAuth 2.0 for Native Apps, RFC 8252 + PKCE):
  1. Generate a PKCE code verifier + S256 challenge
  2. Open the system browser to Microsoft's authorization URL
  3. A temporary local HTTP server on a random loopback port catches the redirect
  4. Exchange the authorization code for tokens (PKCE — no client secret needed)
  5. Exchange the MS access token for Xbox Live → XSTS → Minecraft credentials
  6. Persist the refresh token in the system keyring (or an encrypted fallback)
  7. Silently refresh on next launch with the stored refresh token

Azure App setup (portal.azure.com):
  - Supported account types: Personal Microsoft accounts (consumers)
  - Platform: Mobile and desktop applications (public client)
  - Redirect URI: http://localhost  (loopback — any port is allowed)
  - Enable "Allow public client flows"
  - No client secret needed — PKCE provides proof-of-possession

Security:
  S-Z-001: Fernet-encrypted fallback with machine-bound PBKDF2 key; secure delete on logout
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import logging
import os
import re as _re
import secrets
import socket
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

import requests as _req

try:
    import keyring
    _KEYRING_OK = True
except ImportError:
    _KEYRING_OK = False

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    import base64 as _b64
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

from .config import APP_DIR, config
from .secure_store import atomic_write_bytes, secure_delete as _secure_delete_file

# ---------------------------------------------------------------------------
# Publisher configuration
# ---------------------------------------------------------------------------

# Xbox Live public client ID — used by HMCL, MultiMC, and many open-source
# Minecraft launchers. No Azure registration required for end users.
# Replace via GENOS_AZURE_CLIENT_ID env var or CI secret if you want your
# own registered app instead.
_BUILTIN_CLIENT_ID = "00000000402b5328"


def _resolve_client_id() -> str:
    """Return the best available OAuth client ID.

    Priority: GENOS_AZURE_CLIENT_ID env var (CI/dev builds)
              → user override stored in config (advanced users)
              → project built-in ID (normal end-user path)
    """
    return (
        os.environ.get("GENOS_AZURE_CLIENT_ID", "")
        or config.get("azure_client_id", "")
        or _BUILTIN_CLIENT_ID
    )

# ---------------------------------------------------------------------------
# Microsoft / Xbox / Minecraft API endpoints
# ---------------------------------------------------------------------------

_TENANT         = "consumers"
_AUTH_URL       = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/authorize"
_TOKEN_URL      = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/token"
_SCOPE          = "XboxLive.signin offline_access"
_REDIRECT_PATH  = "/callback"
_XBL_URL        = "https://user.auth.xboxlive.com/user/authenticate"
_XSTS_URL       = "https://xsts.auth.xboxlive.com/xsts/authorize"
_MC_LOGIN_URL   = "https://api.minecraftservices.com/authentication/login_with_xbox"
_MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"

_KEYRING_SERVICE = "GenosLauncher"
_KEYRING_ACCOUNT = "ms_account_json"
_FALLBACK_STORE  = APP_DIR / ".auth_store"

_HTTP = _req.Session()
from .._version import __version__ as _VERSION
_HTTP.headers.update({"User-Agent": f"GenosLauncher/{_VERSION}"})
_STORAGE_WARNING = ""


def _set_storage_warning(message: str) -> None:
    global _STORAGE_WARNING
    _STORAGE_WARNING = message
    log.warning(message)


def credential_storage_warning() -> str:
    return _STORAGE_WARNING


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AuthError(Exception):
    """Raised on any authentication failure."""


# ---------------------------------------------------------------------------
# Fallback encryption helpers (S-Z-001)
# ---------------------------------------------------------------------------

def _derive_fallback_key() -> bytes:
    """Derive the Fernet key for the fallback credential store.

    Uses a random 32-byte secret written to APP_DIR/.fallback_key on first
    run.  This key is non-reproducible from public information (unlike a MAC
    address), making the fallback store infeasible to decrypt without direct
    access to the installation directory.
    """
    key_file = APP_DIR / ".fallback_key"
    try:
        if key_file.exists():
            key_material = key_file.read_bytes()
        else:
            key_material = os.urandom(32)
            atomic_write_bytes(key_file, key_material)
    except OSError as exc:
        log.warning("Could not read/write fallback key file: %s", exc)
        key_material = hashlib.sha256(str(id(key_file)).encode()).digest()
    salt = b"GenosLauncher-fallback-auth-v1"
    kdf = PBKDF2HMAC(algorithm=_hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    return _b64.urlsafe_b64encode(kdf.derive(key_material))


def _encrypt(payload: str) -> bytes:
    if not _CRYPTO_OK:
        raise RuntimeError(
            "The 'cryptography' package is required to store credentials securely "
            "when the system keyring is unavailable.  "
            "Run: pip install cryptography"
        )
    return Fernet(_derive_fallback_key()).encrypt(payload.encode())


def _decrypt(data: bytes) -> str:
    if _CRYPTO_OK:
        # Let InvalidToken propagate to the caller — it will treat the
        # stored data as unreadable and prompt re-authentication.
        return Fernet(_derive_fallback_key()).decrypt(data).decode()
    # _CRYPTO_OK is False: the store was written without encryption (legacy
    # path that no longer exists in _encrypt).  Attempt plain base64 decode
    # so that old installations are handled gracefully on upgrade.
    import base64 as _b64_legacy
    return _b64_legacy.b64decode(data).decode()


def _secure_delete(path: Path) -> None:
    _secure_delete_file(path)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _store_account(data: dict) -> None:
    payload = json.dumps(data)
    if _KEYRING_OK:
        try:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, payload)
            if _FALLBACK_STORE.exists():
                _secure_delete(_FALLBACK_STORE)
            return
        except Exception as exc:
            _set_storage_warning(
                f"System keyring write failed; using encrypted fallback credential file: {exc}"
            )
    ciphertext = _encrypt(payload)
    atomic_write_bytes(_FALLBACK_STORE, ciphertext)


def _load_account() -> Optional[dict]:
    if _KEYRING_OK:
        try:
            payload = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
            if payload:
                return json.loads(payload)
        except Exception as exc:
            _set_storage_warning(
                f"System keyring read failed; trying encrypted fallback credential file: {exc}"
            )
    if _FALLBACK_STORE.exists():
        try:
            return json.loads(_decrypt(_FALLBACK_STORE.read_bytes()))
        except Exception as exc:
            _set_storage_warning(f"Encrypted fallback credential file is unreadable: {exc}")
    return None


def _delete_account() -> None:
    if _KEYRING_OK:
        try:
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
        except Exception as exc:
            log.warning("System keyring delete failed: %s", exc)
            pass
    if _FALLBACK_STORE.exists():
        _secure_delete(_FALLBACK_STORE)


# ---------------------------------------------------------------------------
# Per-username account helpers (multi-account support)
# ---------------------------------------------------------------------------

def _account_key(username: str) -> str:
    return "ms_account_" + _re.sub(r"[^a-z0-9]", "_", username.lower())


def _fallback_path_for(username: str) -> Path:
    return APP_DIR / ("." + _account_key(username))


def _store_account_for(data: dict) -> None:
    """Store an account under its username-specific key without affecting the active slot."""
    username = data.get("name", "")
    if not username:
        return
    key      = _account_key(username)
    fallback = _fallback_path_for(username)
    payload  = json.dumps(data)
    if _KEYRING_OK:
        try:
            keyring.set_password(_KEYRING_SERVICE, key, payload)
            if fallback.exists():
                _secure_delete(fallback)
            return
        except Exception as exc:
            _set_storage_warning(
                f"System keyring write failed for {username}; using encrypted fallback: {exc}"
            )
    ciphertext = _encrypt(payload)
    atomic_write_bytes(fallback, ciphertext)


def _load_account_for(username: str) -> Optional[dict]:
    key      = _account_key(username)
    fallback = _fallback_path_for(username)
    if _KEYRING_OK:
        try:
            payload = keyring.get_password(_KEYRING_SERVICE, key)
            if payload:
                return json.loads(payload)
        except Exception as exc:
            _set_storage_warning(
                f"System keyring read failed for {username}; trying encrypted fallback: {exc}"
            )
    if fallback.exists():
        try:
            return json.loads(_decrypt(fallback.read_bytes()))
        except Exception as exc:
            _set_storage_warning(f"Encrypted fallback for {username} is unreadable: {exc}")
    return None


def _delete_account_for(username: str) -> None:
    key      = _account_key(username)
    fallback = _fallback_path_for(username)
    if _KEYRING_OK:
        try:
            keyring.delete_password(_KEYRING_SERVICE, key)
        except Exception as exc:
            log.warning("System keyring delete failed for %s: %s", username, exc)
            pass
    if fallback.exists():
        _secure_delete(fallback)


def _register_username(username: str) -> None:
    usernames = list(config.get("ms_usernames", []))
    if username not in usernames:
        usernames.append(username)
    config.update({"ms_usernames": usernames})


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256 PKCE."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _build_auth_url(
    client_id: str,
    redirect_uri: str,
    challenge: str,
    state: str,
) -> str:
    params = {
        "client_id":             client_id,
        "response_type":         "code",
        "redirect_uri":          redirect_uri,
        "scope":                 _SCOPE,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
        "state":                 state,
        "prompt":                "select_account",
    }
    return _AUTH_URL + "?" + urllib.parse.urlencode(params)


def _exchange_code(
    client_id: str,
    code: str,
    redirect_uri: str,
    verifier: str,
) -> dict:
    """Exchange an authorization code for MS access + refresh tokens."""
    resp = _HTTP.post(_TOKEN_URL, data={
        "client_id":     client_id,
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  redirect_uri,
        "code_verifier": verifier,
    }, timeout=15)
    if not resp.ok:
        raise AuthError(f"Token exchange failed ({resp.status_code}): {resp.text[:200]}")
    data = resp.json()
    if "error" in data:
        raise AuthError(data.get("error_description", data["error"]))
    return data


def _create_callback_server(
    expected_state: str,
    stop_event: threading.Event,
) -> tuple[http.server.HTTPServer, dict[str, str]]:
    """
    Bind the local OAuth callback server before opening the browser.

    Binding with port 0 removes the find-free-port race and using 127.0.0.1
    matches the redirect URI exactly on systems where localhost prefers IPv6.
    """
    result: dict[str, str] = {}
    server_ref: list[http.server.HTTPServer] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            recv_state = params.get("state", [""])[0]
            if recv_state != expected_state:
                result["error"] = "State mismatch — possible CSRF. Please try again."
                self._respond(self._error_html("State mismatch. Please try signing in again."))
            else:
                err = params.get("error", [""])[0]
                if err:
                    desc = params.get("error_description", [err])[0]
                    result["error"] = desc
                    self._respond(self._error_html(desc))
                else:
                    result["code"] = params.get("code", [""])[0]
                    self._respond(self._success_html())

            threading.Thread(target=server_ref[0].shutdown, daemon=True).start()

        def _respond(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        @staticmethod
        def _success_html() -> str:
            return (
                "<!DOCTYPE html><html><head><title>Sign-in complete</title></head>"
                "<body style='font-family:sans-serif;text-align:center;padding:60px;"
                "background:#1a1a2e;color:#e0e0e0;'>"
                "<h2 style='color:#4CAF50;'>&#10003; Signed in successfully!</h2>"
                "<p>You can close this tab and return to GenosLauncher.</p>"
                "</body></html>"
            )

        @staticmethod
        def _error_html(message: str) -> str:
            safe = (message.replace("&", "&amp;")
                           .replace("<", "&lt;")
                           .replace(">", "&gt;"))
            return (
                "<!DOCTYPE html><html><head><title>Sign-in failed</title></head>"
                "<body style='font-family:sans-serif;text-align:center;padding:60px;"
                "background:#1a1a2e;color:#e0e0e0;'>"
                "<h2 style='color:#f44336;'>&#10007; Sign-in failed</h2>"
                f"<p>{safe}</p>"
                "<p>Close this tab and try again in GenosLauncher.</p>"
                "</body></html>"
            )

        def log_message(self, fmt: str, *args: object) -> None:
            pass  # suppress HTTP access log noise

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    server_ref.append(server)
    return server, result


def _wait_for_callback(
    server: http.server.HTTPServer,
    result: dict[str, str],
    stop_event: threading.Event,
    timeout: int = 300,
) -> str:
    """
    Run a local HTTP server until the OAuth callback arrives.
    Returns the authorization code, or raises AuthError on cancel/error/timeout.
    """

    def _watchdog() -> None:
        stop_event.wait(timeout)
        server.shutdown()

    threading.Thread(target=_watchdog, daemon=True).start()
    server.serve_forever()
    server.server_close()

    if stop_event.is_set():
        raise AuthError("Sign-in cancelled.")
    if "error" in result:
        raise AuthError(result["error"])
    if "code" not in result:
        raise AuthError("Sign-in timed out. Please try again.")
    return result["code"]


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

def _refresh_ms_token(client_id: str, refresh_token: str) -> dict:
    """Exchange a stored refresh token for new MS access + refresh tokens."""
    resp = _HTTP.post(_TOKEN_URL, data={
        "client_id":     client_id,
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "scope":         _SCOPE,
    }, timeout=15)
    if not resp.ok:
        raise AuthError(f"Token refresh failed ({resp.status_code})")
    data = resp.json()
    if "error" in data:
        raise AuthError(data.get("error_description", data["error"]))
    return data


# ---------------------------------------------------------------------------
# Xbox Live → XSTS → Minecraft token chain
# ---------------------------------------------------------------------------

def _ms_token_to_minecraft(ms_access_token: str, ms_refresh_token: str) -> dict:
    """
    Exchange a Microsoft access token for Minecraft credentials.
    Returns account dict: {name, id, access_token, refresh_token}.
    """
    # Xbox Live
    xbl = _HTTP.post(_XBL_URL, json={
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName":   "user.auth.xboxlive.com",
            "RpsTicket":  f"d={ms_access_token}",
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType":    "JWT",
    }, headers={"Accept": "application/json"}, timeout=15)
    xbl.raise_for_status()
    xbl_data  = xbl.json()
    xbl_token = xbl_data["Token"]
    userhash  = xbl_data["DisplayClaims"]["xui"][0]["uhs"]

    # XSTS
    xsts = _HTTP.post(_XSTS_URL, json={
        "Properties": {
            "SandboxId":  "RETAIL",
            "UserTokens": [xbl_token],
        },
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType":    "JWT",
    }, headers={"Accept": "application/json"}, timeout=15)
    xsts.raise_for_status()
    xsts_token = xsts.json()["Token"]

    # Minecraft token
    mc = _HTTP.post(_MC_LOGIN_URL, json={
        "identityToken": f"XBL3.0 x={userhash};{xsts_token}",
    }, timeout=15)
    mc.raise_for_status()
    mc_token = mc.json()["access_token"]

    # Minecraft profile
    profile = _HTTP.get(_MC_PROFILE_URL, headers={
        "Authorization": f"Bearer {mc_token}",
    }, timeout=15)
    profile.raise_for_status()
    prof = profile.json()

    if "error" in prof:
        raise AuthError(
            "This Microsoft account does not own Minecraft: Java Edition.\n"
            "Purchase it at minecraft.net to play online."
        )

    return {
        "name":          prof["name"],
        "id":            prof["id"],
        "access_token":  mc_token,
        "refresh_token": ms_refresh_token,
    }


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------

class AuthManager:
    """
    Manages Microsoft / Minecraft account authentication using PKCE browser flow.

    Usage:
        auth_manager.load_stored()                # restore session on startup
        auth_manager.start_login(on_browser_opened,  # PKCE browser flow
                                 on_success,
                                 on_error)
        auth_manager.refresh_async()              # silent background refresh
        auth_manager.logout()                     # secure wipe
    """

    _TOKEN_MAX_AGE = 50 * 60  # seconds — proactively refresh before the ~60-min MS expiry

    def __init__(self) -> None:
        self._account: Optional[dict] = None
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._add_cancel_event = threading.Event()
        self._token_acquired_at: float = 0.0
        self._generation = 0

    # ------------------------------------------------------------------
    # Properties  (all reads hold _lock to prevent torn reads on logout/refresh)
    # ------------------------------------------------------------------

    @property
    def is_logged_in(self) -> bool:
        with self._lock:
            return bool(self._account and self._account.get("access_token"))

    @property
    def username(self) -> str:
        with self._lock:
            return (self._account or {}).get("name", "")

    @property
    def uuid(self) -> str:
        with self._lock:
            return (self._account or {}).get("id", "")

    @property
    def access_token(self) -> str:
        with self._lock:
            return (self._account or {}).get("access_token", "")

    @property
    def refresh_token(self) -> str:
        with self._lock:
            return (self._account or {}).get("refresh_token", "")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load_stored(self) -> bool:
        data = _load_account()
        if data and data.get("name") and data.get("refresh_token"):
            with self._lock:
                self._account = data
                # _token_acquired_at stays 0.0 so ensure_token_fresh() will
                # always do a proactive refresh on the first launch attempt.
            return True
        return False

    # ------------------------------------------------------------------
    # PKCE browser login
    # ------------------------------------------------------------------

    def start_login(
        self,
        on_browser_opened: Callable[[str], None],
        on_success:        Callable[[dict], None],
        on_error:          Callable[[str], None],
    ) -> None:
        """
        Start the PKCE browser login flow on a background thread.

        on_browser_opened(auth_url)
            Called once the system browser has been opened. auth_url can be
            stored by the caller to re-open the browser if needed.
        on_success(account_dict)
            Called when login completes successfully.
        on_error(message)
            Called on any failure.
        """
        client_id = _resolve_client_id()
        if not client_id:
            on_error(
                "Microsoft sign-in could not start — no client ID is configured.\n\n"
                "If you built GenosLauncher from source, set the "
                "GENOS_AZURE_CLIENT_ID environment variable or paste a "
                "client ID in Settings → Microsoft Authentication."
            )
            return

        self._cancel_event.clear()
        with self._lock:
            self._generation += 1
            generation = self._generation
        threading.Thread(
            target=self._login_thread_pkce,
            args=(client_id, generation, on_browser_opened, on_success, on_error),
            daemon=True,
        ).start()

    def cancel_login(self) -> None:
        """Cancel an in-progress login flow."""
        self._cancel_event.set()
        self._add_cancel_event.set()

    def _login_thread_pkce(
        self,
        client_id:         str,
        generation:        int,
        on_browser_opened: Callable,
        on_success:        Callable,
        on_error:          Callable,
    ) -> None:
        try:
            verifier, challenge = _pkce_pair()
            state = secrets.token_urlsafe(16)
            server, result = _create_callback_server(state, self._cancel_event)
        except OSError as exc:
            on_error(f"Could not start local sign-in server: {exc}")
            return

        port = server.server_address[1]
        redirect_uri = f"http://127.0.0.1:{port}{_REDIRECT_PATH}"
        auth_url = _build_auth_url(client_id, redirect_uri, challenge, state)

        webbrowser.open(auth_url)
        on_browser_opened(auth_url)

        try:
            code      = _wait_for_callback(server, result, self._cancel_event)
            ms_tokens = _exchange_code(client_id, code, redirect_uri, verifier)
            account   = _ms_token_to_minecraft(
                ms_tokens["access_token"],
                ms_tokens.get("refresh_token", ""),
            )
            with self._lock:
                if generation != self._generation or self._cancel_event.is_set():
                    raise AuthError("Sign-in cancelled.")
                self._account = account
                self._token_acquired_at = time.monotonic()
                _store_account(account)
                _store_account_for(account)
                _register_username(account["name"])
                config.update({"active_ms_username": account["name"], "last_account": account["name"]})
            on_success(account)
        except AuthError as exc:
            on_error(str(exc))
        except Exception as exc:
            on_error(f"Unexpected error during sign-in:\n{exc}")

    # ------------------------------------------------------------------
    # Multi-account management
    # ------------------------------------------------------------------

    def list_ms_accounts(self) -> list[str]:
        """Return all stored Microsoft account usernames."""
        return list(config.get("ms_usernames", []))

    def add_account(
        self,
        on_browser_opened: Callable[[str], None],
        on_success:        Callable[[dict], None],
        on_error:          Callable[[str], None],
    ) -> None:
        """
        Add an additional Microsoft account without replacing the currently active one.
        on_success receives the new account dict.
        """
        client_id = _resolve_client_id()
        if not client_id:
            on_error(
                "Microsoft sign-in could not start — no client ID is configured.\n\n"
                "Set the GENOS_AZURE_CLIENT_ID environment variable or paste a "
                "client ID in Settings → Microsoft Authentication."
            )
            return
        self._add_cancel_event.clear()
        threading.Thread(
            target=self._add_account_thread,
            args=(client_id, on_browser_opened, on_success, on_error, self._add_cancel_event),
            daemon=True,
        ).start()

    def _add_account_thread(
        self,
        client_id:         str,
        on_browser_opened: Callable,
        on_success:        Callable,
        on_error:          Callable,
        stop_event:        threading.Event,
    ) -> None:
        try:
            verifier, challenge = _pkce_pair()
            state = secrets.token_urlsafe(16)
            server, result = _create_callback_server(state, stop_event)
        except OSError as exc:
            on_error(f"Could not start local sign-in server: {exc}")
            return
        port = server.server_address[1]
        redirect_uri = f"http://127.0.0.1:{port}{_REDIRECT_PATH}"
        auth_url = _build_auth_url(client_id, redirect_uri, challenge, state)
        webbrowser.open(auth_url)
        on_browser_opened(auth_url)
        try:
            code      = _wait_for_callback(server, result, stop_event)
            ms_tokens = _exchange_code(client_id, code, redirect_uri, verifier)
            account   = _ms_token_to_minecraft(
                ms_tokens["access_token"],
                ms_tokens.get("refresh_token", ""),
            )
            _store_account_for(account)
            _register_username(account["name"])
            on_success(account)
        except AuthError as exc:
            on_error(str(exc))
        except Exception as exc:
            on_error(f"Unexpected error adding account:\n{exc}")

    def switch_account(self, username: str) -> bool:
        """Switch the active Microsoft account. Returns True on success."""
        data = _load_account_for(username)
        if not data:
            return False
        with self._lock:
            self._account = data
            self._token_acquired_at = 0.0  # force proactive refresh on next launch
        _store_account(data)
        config.update({"active_ms_username": username, "last_account": username})
        return True

    def remove_ms_account(self, username: str) -> None:
        """Remove a stored Microsoft account."""
        _delete_account_for(username)
        usernames = [u for u in config.get("ms_usernames", []) if u != username]
        config.update({"ms_usernames": usernames})
        with self._lock:
            if self._account and self._account.get("name") == username:
                self._account = None
        if config.get("active_ms_username") == username:
            config.update({"active_ms_username": "", "last_account": ""})
            _delete_account()

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    def refresh(self) -> bool:
        with self._lock:
            account_snapshot = dict(self._account or {})
            generation = self._generation
            refresh_token = account_snapshot.get("refresh_token", "")
        if not refresh_token:
            return False
        client_id = _resolve_client_id()
        if not client_id:
            return False
        try:
            ms_tokens = _refresh_ms_token(client_id, refresh_token)
            account   = _ms_token_to_minecraft(
                ms_tokens["access_token"],
                ms_tokens.get("refresh_token", refresh_token),
            )
            with self._lock:
                if generation != self._generation:
                    return False
                self._account = account
                self._token_acquired_at = time.monotonic()
                _store_account(account)
                _store_account_for(account)
            return True
        except Exception as exc:
            log.warning("Token refresh failed: %s", exc)
            return False

    def refresh_async(self) -> None:
        threading.Thread(target=self.refresh, daemon=True).start()

    def ensure_token_fresh(self, force: bool = False) -> bool:
        """Synchronously refresh the access token if it is approaching expiry.

        Called on the LaunchWorker thread just before launch so Minecraft
        always starts with a valid token.  No-op when offline or when the
        token was acquired less than _TOKEN_MAX_AGE seconds ago. Returns False
        when an online account needs refresh but refresh fails.
        """
        with self._lock:
            if not self._account:
                return True
            age = time.monotonic() - self._token_acquired_at
        if force or age >= self._TOKEN_MAX_AGE:
            return self.refresh()
        return True

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(self) -> None:
        self._cancel_event.set()
        self._add_cancel_event.set()
        with self._lock:
            self._generation += 1
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
            resp = _HTTP.get(url, timeout=10, stream=True)
            if not resp.ok:
                return False
            max_bytes = 2 * 1024 * 1024
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    return False
                chunks.append(chunk)
            atomic_write_bytes(dest, b"".join(chunks))
            return True
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

auth_manager = AuthManager()
