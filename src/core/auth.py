"""
Microsoft Account authentication — device code flow.

Flow (OAuth 2.0 Device Authorization Grant):
  1. Request device code from Microsoft
  2. Show user_code in UI and open microsoft.com/devicelogin
  3. Poll token endpoint on background thread
  4. Exchange MS access token for Xbox Live → XSTS → Minecraft credentials
  5. Persist refresh token in system keyring (or encrypted fallback)
  6. Silently refresh on next launch with stored refresh token

No redirect URIs, no local HTTP server, no Azure setup required for end users.
The APP_CLIENT_ID below must be set once by the publisher (portal.azure.com).

Security:
  S-Z-001: Fernet-encrypted fallback with machine-bound PBKDF2 key; secure delete on logout
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
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

# ---------------------------------------------------------------------------
# Publisher configuration
# ---------------------------------------------------------------------------

# Register your own Azure App at portal.azure.com:
#   - Accounts: Personal Microsoft accounts only
#   - Platform: Mobile and desktop applications (public client)
#   - Enable: "Allow public client flows" → Device code flow
#   - No client secret needed
# Then set the GENOS_AZURE_CLIENT_ID environment variable (or CI secret) to
# your Application (client) ID.  Leaving it empty causes the sign-in flow to
# surface a clear configuration error instead of using another project's quota.
APP_CLIENT_ID = os.environ.get("GENOS_AZURE_CLIENT_ID", "")

# ---------------------------------------------------------------------------
# Microsoft / Xbox / Minecraft API endpoints
# ---------------------------------------------------------------------------

_TENANT           = "consumers"
_DEVICE_CODE_URL  = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/devicecode"
_TOKEN_URL        = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/token"
_SCOPE            = "XboxLive.signin offline_access"
_XBL_URL          = "https://user.auth.xboxlive.com/user/authenticate"
_XSTS_URL         = "https://xsts.auth.xboxlive.com/xsts/authorize"
_MC_LOGIN_URL     = "https://api.minecraftservices.com/authentication/login_with_xbox"
_MC_PROFILE_URL   = "https://api.minecraftservices.com/minecraft/profile"

_KEYRING_SERVICE  = "GenosLauncher"
_KEYRING_ACCOUNT  = "ms_account_json"
_FALLBACK_STORE   = APP_DIR / ".auth_store"

_HTTP = _req.Session()
_HTTP.headers.update({"User-Agent": "GenosLauncher/0.2.0"})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AuthError(Exception):
    """Raised on any authentication failure."""


# ---------------------------------------------------------------------------
# Fallback encryption helpers (S-Z-001)
# ---------------------------------------------------------------------------

def _derive_fallback_key() -> bytes:
    import uuid
    machine_id = str(uuid.getnode()).encode()
    salt = b"GenosLauncher-fallback-auth-v1"
    if _CRYPTO_OK:
        kdf = PBKDF2HMAC(algorithm=_hashes.SHA256(), length=32, salt=salt, iterations=100_000)
        return _b64.urlsafe_b64encode(kdf.derive(machine_id))
    import base64
    return base64.urlsafe_b64encode(hashlib.sha256(salt + machine_id).digest())


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
    import base64
    return base64.b64decode(data).decode()


def _secure_delete(path: Path) -> None:
    try:
        size = path.stat().st_size
        if size > 0:
            with open(path, "r+b") as fh:
                fh.write(os.urandom(size))
                fh.flush()
                os.fsync(fh.fileno())
        path.unlink()
    except OSError:
        path.unlink(missing_ok=True)


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
        except Exception:
            pass
    ciphertext = _encrypt(payload)
    _FALLBACK_STORE.write_bytes(ciphertext)
    if os.name != "nt":
        try:
            os.chmod(_FALLBACK_STORE, 0o600)
        except OSError:
            pass


def _load_account() -> Optional[dict]:
    if _KEYRING_OK:
        try:
            payload = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
            if payload:
                return json.loads(payload)
        except Exception:
            pass
    if _FALLBACK_STORE.exists():
        try:
            return json.loads(_decrypt(_FALLBACK_STORE.read_bytes()))
        except Exception:
            pass
    return None


def _delete_account() -> None:
    if _KEYRING_OK:
        try:
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
        except Exception:
            pass
    if _FALLBACK_STORE.exists():
        _secure_delete(_FALLBACK_STORE)


# ---------------------------------------------------------------------------
# Device code flow
# ---------------------------------------------------------------------------

def _request_device_code(client_id: str) -> dict:
    """
    Request a device code from Microsoft.
    Returns dict with: device_code, user_code, verification_uri, expires_in, interval.
    """
    resp = _HTTP.post(_DEVICE_CODE_URL, data={
        "client_id": client_id,
        "scope":     _SCOPE,
    }, timeout=15)
    if not resp.ok:
        raise AuthError(f"Device code request failed ({resp.status_code}): {resp.text[:200]}")
    return resp.json()


def _poll_ms_token(
    client_id:   str,
    device_code: str,
    interval:    int,
    stop_event:  threading.Event,
) -> dict:
    """
    Poll until the user completes sign-in or the code expires.
    Returns MS token dict: {access_token, refresh_token, ...}.
    Raises AuthError on cancel, expiry, or user denial.
    """
    while not stop_event.is_set():
        stop_event.wait(interval)
        if stop_event.is_set():
            raise AuthError("Sign-in cancelled.")
        resp = _HTTP.post(_TOKEN_URL, data={
            "client_id":   client_id,
            "grant_type":  "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
        }, timeout=15)
        data = resp.json()
        err = data.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval = min(interval + 5, 30)
            continue
        if err == "expired_token":
            raise AuthError("Sign-in code expired. Please try again.")
        if err == "access_denied":
            raise AuthError("Sign-in was denied or cancelled in the browser.")
        if err:
            raise AuthError(data.get("error_description", err))
        return data
    raise AuthError("Sign-in cancelled.")


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
    Manages Microsoft / Minecraft account authentication using device code flow.

    Usage:
        auth_manager.load_stored()                # restore session on startup
        auth_manager.start_login(on_code_ready,   # device code UI flow
                                 on_success,
                                 on_error)
        auth_manager.refresh_async()              # silent background refresh
        auth_manager.logout()                     # secure wipe
    """

    def __init__(self) -> None:
        self._account: Optional[dict] = None
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()

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
    # Persistence
    # ------------------------------------------------------------------

    def load_stored(self) -> bool:
        data = _load_account()
        if data and data.get("name") and data.get("refresh_token"):
            self._account = data
            return True
        return False

    # ------------------------------------------------------------------
    # Device code login
    # ------------------------------------------------------------------

    def start_login(
        self,
        on_code_ready: Callable[[str, str, int], None],
        on_success:    Callable[[dict], None],
        on_error:      Callable[[str], None],
    ) -> None:
        """
        Start the device code login flow on a background thread.

        on_code_ready(user_code, verification_uri, expires_in)
            Called when Microsoft returns the code to show the user.
        on_success(account_dict)
            Called when login completes.
        on_error(message)
            Called on any failure.
        """
        client_id = APP_CLIENT_ID or config.get("azure_client_id", "")
        if not client_id:
            on_error(
                "Microsoft sign-in is not configured for this build.\n\n"
                "If you are a developer, register an Azure App at portal.azure.com "
                "and set APP_CLIENT_ID in src/core/auth.py."
            )
            return

        self._cancel_event.clear()
        threading.Thread(
            target=self._login_thread,
            args=(client_id, on_code_ready, on_success, on_error),
            daemon=True,
        ).start()

    def cancel_login(self) -> None:
        """Cancel an in-progress device code flow."""
        self._cancel_event.set()

    def _login_thread(
        self,
        client_id:     str,
        on_code_ready: Callable,
        on_success:    Callable,
        on_error:      Callable,
    ) -> None:
        try:
            code_data = _request_device_code(client_id)
        except Exception as exc:
            on_error(str(exc))
            return

        user_code        = code_data["user_code"]
        verification_uri = code_data.get("verification_uri", "https://microsoft.com/devicelogin")
        expires_in       = code_data.get("expires_in", 900)
        interval         = code_data.get("interval", 5)
        device_code      = code_data["device_code"]

        on_code_ready(user_code, verification_uri, expires_in)

        try:
            ms_tokens = _poll_ms_token(client_id, device_code, interval, self._cancel_event)
            account   = _ms_token_to_minecraft(
                ms_tokens["access_token"],
                ms_tokens.get("refresh_token", ""),
            )
            with self._lock:
                self._account = account
            _store_account(account)
            on_success(account)
        except AuthError as exc:
            on_error(str(exc))
        except Exception as exc:
            on_error(f"Unexpected error during sign-in:\n{exc}")

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    def refresh(self) -> bool:
        if not self.refresh_token:
            return False
        client_id = APP_CLIENT_ID or config.get("azure_client_id", "")
        if not client_id:
            return False
        try:
            ms_tokens = _refresh_ms_token(client_id, self.refresh_token)
            account   = _ms_token_to_minecraft(
                ms_tokens["access_token"],
                ms_tokens.get("refresh_token", self.refresh_token),
            )
            with self._lock:
                self._account = account
            _store_account(account)
            return True
        except Exception as exc:
            log.warning("Token refresh failed: %s", exc)
            return False

    def refresh_async(self) -> None:
        threading.Thread(target=self.refresh, daemon=True).start()

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(self) -> None:
        self._cancel_event.set()
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
            resp = _HTTP.get(url, timeout=10)
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
