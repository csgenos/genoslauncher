from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.core import auth as auth_core
from src.core import config as config_core
from src.core import launcher as launcher_core


def _account(verified_at: datetime | None) -> dict:
    data = {
        "name": "VerifiedPlayer",
        "id": "0123456789abcdef0123456789abcdef",
        "access_token": "minecraft-token",
        "refresh_token": "refresh-token",
    }
    if verified_at is not None:
        data["last_verified_at"] = verified_at.isoformat()
    return data


class OfflineGraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
        self.manager = auth_core.AuthManager()

    def _set_account(self, verified_at: datetime | None) -> None:
        self.manager._account = _account(verified_at)
        self.manager._token_acquired_at = 0.0

    def test_fresh_in_memory_token_launches_online_without_refresh(self) -> None:
        self._set_account(self.now)
        self.manager._token_acquired_at = auth_core.time.monotonic()
        with patch.object(self.manager, "_refresh_account") as refresh:
            credentials = self.manager.prepare_launch_credentials(now=self.now)
        refresh.assert_not_called()
        self.assertEqual(credentials.mode, "online")
        self.assertEqual(credentials.token, "minecraft-token")

    def test_transient_failure_uses_verified_identity_inside_grace(self) -> None:
        self._set_account(self.now - timedelta(days=6, hours=23))
        with patch.object(
            self.manager,
            "_refresh_account",
            side_effect=auth_core.AuthUnavailableError("network unavailable"),
        ):
            credentials = self.manager.prepare_launch_credentials(now=self.now)
        self.assertEqual(credentials.mode, "offline_grace")
        self.assertEqual(credentials.username, "VerifiedPlayer")
        self.assertEqual(credentials.uuid, _account(self.now)["id"])
        self.assertEqual(credentials.token, "offline")

    def test_exact_168_hour_boundary_is_allowed(self) -> None:
        self._set_account(self.now - timedelta(days=7))
        with patch.object(
            self.manager,
            "_refresh_account",
            side_effect=auth_core.AuthUnavailableError("network unavailable"),
        ):
            credentials = self.manager.prepare_launch_credentials(now=self.now)
        self.assertEqual(credentials.mode, "offline_grace")

    def test_expired_missing_malformed_and_future_timestamps_are_blocked(self) -> None:
        invalid_values = [
            None,
            self.now - timedelta(days=7, microseconds=1),
            self.now + timedelta(seconds=1),
        ]
        for verified_at in invalid_values:
            with self.subTest(verified_at=verified_at):
                self._set_account(verified_at)
                with patch.object(
                    self.manager,
                    "_refresh_account",
                    side_effect=auth_core.AuthUnavailableError("network unavailable"),
                ):
                    with self.assertRaises(auth_core.LaunchAuthError):
                        self.manager.prepare_launch_credentials(now=self.now)

        account = _account(self.now)
        account["last_verified_at"] = "not-a-date"
        self.manager._account = account
        with patch.object(
            self.manager,
            "_refresh_account",
            side_effect=auth_core.AuthUnavailableError("network unavailable"),
        ):
            with self.assertRaises(auth_core.LaunchAuthError):
                self.manager.prepare_launch_credentials(now=self.now)

    def test_explicit_rejection_never_uses_grace(self) -> None:
        self._set_account(self.now)
        with (
            patch.object(
                self.manager,
                "_refresh_account",
                side_effect=auth_core.AuthRejectedError("invalid_grant"),
            ),
            patch.object(auth_core, "_store_account"),
            patch.object(auth_core, "_store_account_for"),
        ):
            with self.assertRaisesRegex(auth_core.LaunchAuthError, "rejected"):
                self.manager.prepare_launch_credentials(now=self.now)
        self.assertEqual(self.manager.verification_state, "sign_in_required")
        self.assertTrue(self.manager._account["reauth_required"])

    def test_successful_refresh_returns_online_credentials(self) -> None:
        self._set_account(None)
        refreshed = _account(self.now)
        with patch.object(self.manager, "_refresh_account", return_value=refreshed):
            credentials = self.manager.prepare_launch_credentials(now=self.now)
        self.assertEqual(credentials.mode, "online")
        self.assertEqual(credentials.token, "minecraft-token")

    def test_rejection_state_survives_account_switch(self) -> None:
        rejected = _account(self.now)
        rejected["reauth_required"] = True
        with (
            patch.object(auth_core, "_load_account_for", return_value=rejected),
            patch.object(auth_core, "_store_account"),
            patch.object(auth_core.config, "update"),
        ):
            self.assertTrue(self.manager.switch_account("VerifiedPlayer"))
        self.assertEqual(self.manager.verification_state, "sign_in_required")
        with self.assertRaises(auth_core.LaunchAuthError):
            self.manager.prepare_launch_credentials(now=self.now)


class AuthResponseClassificationTests(unittest.TestCase):
    def test_transient_statuses_are_unavailable(self) -> None:
        for status in (408, 429, 500, 503):
            response = SimpleNamespace(ok=False, status_code=status)
            with self.subTest(status=status):
                with self.assertRaises(auth_core.AuthUnavailableError):
                    auth_core._require_auth_response(response, "Microsoft")

    def test_client_errors_are_rejected(self) -> None:
        for status in (400, 401, 403, 404):
            response = SimpleNamespace(ok=False, status_code=status)
            with self.subTest(status=status):
                with self.assertRaises(auth_core.AuthRejectedError):
                    auth_core._require_auth_response(response, "Microsoft")

    def test_ownership_verified_profile_receives_timestamp(self) -> None:
        now = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)

        class Response:
            ok = True
            status_code = 200

            def __init__(self, payload: dict) -> None:
                self._payload = payload

            def json(self) -> dict:
                return self._payload

        responses = [
            Response({"Token": "xbl", "DisplayClaims": {"xui": [{"uhs": "userhash"}]}}),
            Response({"Token": "xsts"}),
            Response({"access_token": "minecraft-token"}),
        ]
        profile = Response({"name": "VerifiedPlayer", "id": "official-uuid"})
        with (
            patch.object(auth_core._HTTP, "post", side_effect=responses),
            patch.object(auth_core._HTTP, "get", return_value=profile),
            patch.object(auth_core, "_utc_now", return_value=now),
        ):
            account = auth_core._ms_token_to_minecraft("ms-token", "refresh-token")

        self.assertEqual(account["last_verified_at"], now.isoformat())
        self.assertEqual(account["id"], "official-uuid")


class MicrosoftOnlyMigrationTests(unittest.TestCase):
    def test_migration_purges_offline_profiles_and_usage(self) -> None:
        stored = {
            "offline_accounts": ["LocalOne", "LocalTwo"],
            "allow_online_launch_token": False,
            "last_account": "LocalOne",
            "account_last_used": {
                "LocalOne": "old",
                "MicrosoftUser": "keep",
            },
            "account_last_used_LocalTwo": "old",
            "ms_usernames": ["MicrosoftUser"],
        }
        self.assertTrue(config_core._migrate_microsoft_only_config(stored))
        self.assertNotIn("offline_accounts", stored)
        self.assertNotIn("allow_online_launch_token", stored)
        self.assertNotIn("account_last_used_LocalTwo", stored)
        self.assertEqual(stored["last_account"], "")
        self.assertEqual(stored["account_last_used"], {"MicrosoftUser": "keep"})


class LaunchCredentialIntegrationTests(unittest.TestCase):
    def test_launch_worker_uses_central_credentials(self) -> None:
        credentials = auth_core.LaunchCredentials(
            "VerifiedPlayer",
            "official-uuid",
            "offline",
            "offline_grace",
            datetime.now(timezone.utc) + timedelta(days=1),
        )
        captured: dict = {}

        def build_command(*, version, minecraft_directory, options):
            captured.update(options)
            return ["java", "-version"]

        class FakeProcess:
            returncode = 0

            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def wait(self, timeout=None) -> int:
                return 0

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            worker = launcher_core.LaunchWorker("1.20.1")
            config_values = {
                "minecraft_dir": str(root),
                "java_path": "java",
                "ram_mb": 4096,
                "resolution_width": 1280,
                "resolution_height": 720,
                "fullscreen": False,
                "jvm_preset": "performance",
                "jvm_args": "",
            }
            with (
                patch.object(launcher_core, "MLL_AVAILABLE", True),
                patch.object(launcher_core.auth_manager, "prepare_launch_credentials", return_value=credentials),
                patch.object(launcher_core, "find_instance_for_version", return_value=None),
                patch.object(launcher_core, "_get_installed_versions_cached", return_value={"1.20.1"}),
                patch.object(launcher_core.config, "get", side_effect=lambda key, default=None: config_values.get(key, default)),
                patch.object(launcher_core, "get_preset_args", return_value=""),
                patch.object(launcher_core, "LOGS_DIR", root),
                patch.object(
                    launcher_core,
                    "mll",
                    SimpleNamespace(command=SimpleNamespace(get_minecraft_command=build_command)),
                    create=True,
                ),
                patch.object(launcher_core.subprocess, "Popen", FakeProcess),
            ):
                worker._run()

        self.assertEqual(captured["username"], "VerifiedPlayer")
        self.assertEqual(captured["uuid"], "official-uuid")
        self.assertEqual(captured["token"], "offline")


if __name__ == "__main__":
    unittest.main()
