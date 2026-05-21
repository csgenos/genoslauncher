"""
Microsoft Account authentication manager for GenosLauncher.

Flow (PKCE, no client secret — safe for public desktop apps):
  1. get_secure_login_data  → (state, code_challenge, code_verifier)
  2. Build login URL with PKCE params and open browser
  3. Local HTTP server captures callback on localhost:{port}
  4. parse_auth_code_url + complete_login → CompleteLoginResponse
  5. Store refresh_token in system keyring
  6. complete_refresh re-uses the stored token on future launches

CompleteLoginResponse fields:
  access_token, refresh_token, id (UUID), name, error, errorMessage

Azure App requirements (user sets this up — see README):
  - Redirect URI: http://localhost:8090  (or whatever port)
  - Allow public client flows: Yes
  - Scope: XboxLive.signin offline_access
  - No client secret needed
"""

from __future__ import annotations

import http.server
import json
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
    print("[Auth] Warning: keyring not installed — tokens stored in plaintext config.")

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
_FALLBACK_STORE     = APP_DIR / ".auth_store"   # plaintext fallback only

DEFAULT_CLIENT_ID   = ""   # user must supply their own Azure App client ID
DEFAULT_REDIRECT_PORT = 8090


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AuthError(Exception):
    """Raised on any authentication failure."""


class NoClientIdError(AuthError):
    """Raised when no Azure client ID has been configured."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store_account(data: dict) -> None:
    """Persist account JSON to keyring (or fallback file)."""
    payload = json.dumps(data)
    if _KEYRING_OK:
        try:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, payload)
            return
        except Exception as exc:
            print(f"[Auth] Keyring write failed ({exc}), falling back to file.")
    _FALLBACK_STORE.write_text(payload, encoding="utf-8")


def _load_account() -> Optional[dict]:
    """Load persisted account JSON from keyring (or fallback file)."""
    if _KEYRING_OK:
        try:
            payload = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
            if payload:
                return json.loads(payload)
        except Exception:
            pass
    if _FALLBACK_STORE.exists():
        try:
            return json.loads(_FALLBACK_STORE.read_text(encoding="utf-8"))
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
        _FALLBACK_STORE.unlink(missing_ok=True)


def _login_response_to_dict(resp) -> dict:
    """Convert CompleteLoginResponse to a plain serialisable dict."""
    return {
        "id":            resp.id,
        "name":          resp.name,
        "access_token":  resp.access_token,
        "refresh_token": resp.refresh_token,
    }


# ---------------------------------------------------------------------------
# Local callback HTTP server
# ---------------------------------------------------------------------------

class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Captures the OAuth2 redirect and stores the full URL."""

    captured_url: Optional[str] = None   # class-level, set when redirect arrives

    def do_GET(self) -> None:
        _CallbackHandler.captured_url = f"http://localhost{self.path}"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = (
            "<!DOCTYPE html><html><body style='"
            "font-family:system-ui,sans-serif;text-align:center;padding-top:80px;"
            "background:#F8F9FA;color:#111827'>"
            "<h2 style='font-size:24px;font-weight:700'>Login successful!</h2>"
            "<p style='color:#4B5563'>You can close this tab and return to GenosLauncher.</p>"
            "</body></html>"
        )
        self.wfile.write(html.encode())

    def log_message(self, *_args) -> None:
        pass  # suppress all server logs


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------

class AuthManager:
    """
    Manages Microsoft / Minecraft account authentication.

    Usage:
        mgr = AuthManager()
        mgr.load_stored()            # populate from keyring on startup
        mgr.start_login(...)         # kick off PKCE browser flow
        mgr.refresh()                # refresh tokens silently
        mgr.logout()                 # clear all stored data
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
        """
        Restore previously stored account from keyring.
        Returns True if a valid account was found.
        """
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
        """
        Start the PKCE browser login flow on a background thread.

        on_url_ready(url)  — called with the login URL so the caller can
                             display it or open it themselves
        on_success(account_dict) — called on successful authentication
        on_error(message)  — called on any failure
        open_browser       — if True, webbrowser.open() is called automatically
        """
        client_id = config.get("azure_client_id", "")
        if not client_id:
            on_error(
                "No Azure Client ID configured.\n\n"
                "Go to Settings → Microsoft Auth and paste your "
                "Azure App (client) ID.\n\n"
                "See README for step-by-step setup instructions."
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
        port = config.get("auth_redirect_port", DEFAULT_REDIRECT_PORT)
        redirect_uri = f"http://localhost:{port}"

        try:
            # -- PKCE data ------------------------------------------------
            state, code_challenge, code_verifier = get_secure_login_data(
                client_id, redirect_uri
            )

            # Build the full PKCE-enabled auth URL
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

            # -- Local callback server ------------------------------------
            _CallbackHandler.captured_url = None

            server = http.server.HTTPServer(
                ("localhost", port), _CallbackHandler
            )
            server.timeout = 300  # 5-minute window

            deadline = time.monotonic() + 300
            while _CallbackHandler.captured_url is None:
                if time.monotonic() > deadline:
                    server.server_close()
                    on_error("Login timed out (5 min). Please try again.")
                    return
                server.handle_request()

            server.server_close()
            callback_url = _CallbackHandler.captured_url

            # -- Parse auth code ------------------------------------------
            auth_code = parse_auth_code_url(callback_url, state)
            if not auth_code:
                on_error(
                    "Could not extract authorisation code from the callback URL.\n"
                    "Ensure your Azure App redirect URI is set to:\n"
                    f"  {redirect_uri}"
                )
                return

            # -- Exchange for Minecraft token -----------------------------
            response = complete_login(
                client_id,
                None,            # no client secret (public client)
                redirect_uri,
                auth_code,
                code_verifier,
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
            on_error(str(exc))

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    def refresh(self) -> bool:
        """
        Silently refresh the stored access token using the refresh token.
        Returns True on success, False on failure.
        """
        if not self.refresh_token:
            return False

        client_id = config.get("azure_client_id", "")
        if not client_id:
            return False

        port = config.get("auth_redirect_port", DEFAULT_REDIRECT_PORT)
        redirect_uri = f"http://localhost:{port}"

        try:
            response = complete_refresh(
                client_id,
                None,
                redirect_uri,
                self.refresh_token,
            )
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
        """Refresh in a background thread (fire and forget)."""
        thread = threading.Thread(target=self.refresh, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(self) -> None:
        """Clear all stored tokens and reset state."""
        with self._lock:
            self._account = None
        _delete_account()

    # ------------------------------------------------------------------
    # Minecraft profile avatar
    # ------------------------------------------------------------------

    def fetch_avatar_url(self) -> Optional[str]:
        """
        Fetch the Minecraft skin face URL for the current account.
        Returns a URL string or None on any error.
        Uses the Crafatar API for convenience.
        """
        if not self.uuid:
            return None
        return f"https://crafatar.com/avatars/{self.uuid}?size=64&overlay"

    def download_avatar(self, dest: Path) -> bool:
        """Download the face avatar to dest. Returns True on success."""
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
