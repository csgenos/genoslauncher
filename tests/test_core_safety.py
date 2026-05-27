from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.core import instances as instances_core
from src.core import modpack_archive
from src.core import config as config_core
from src.core import cloud_sync as cloud_sync_core
from src.core.java_manager import required_java_for_mc
from src.core.modrinth import ModrinthError, safe_download_path, verify_file_hash
from src.core.validators import (
    normalize_offline_username,
    safe_path_segment,
    validate_version_id,
)
from src.core import auth as auth_core


class JavaRequirementTests(unittest.TestCase):
    def test_minecraft_java_ranges(self) -> None:
        self.assertEqual(required_java_for_mc("1.20.1"), 17)
        self.assertEqual(required_java_for_mc("1.20.4"), 17)
        self.assertEqual(required_java_for_mc("1.20.5"), 21)
        self.assertEqual(required_java_for_mc("1.21.4"), 21)
        self.assertEqual(required_java_for_mc("fabric-loader-0.16.9-1.20.1"), 17)
        self.assertEqual(required_java_for_mc("2.0.0"), 21)


class ValidatorTests(unittest.TestCase):
    def test_offline_username_rules(self) -> None:
        self.assertEqual(normalize_offline_username("Player_123"), "Player_123")
        self.assertEqual(normalize_offline_username("ab"), "")
        self.assertEqual(normalize_offline_username("../bad"), "")

    def test_version_id_rejects_path_segments(self) -> None:
        self.assertEqual(validate_version_id("fabric-loader-0.16.9-1.21.4"), "fabric-loader-0.16.9-1.21.4")
        with self.assertRaises(ValueError):
            validate_version_id("../versions/1.21.4")

    def test_safe_path_segment(self) -> None:
        self.assertEqual(safe_path_segment("../bad/name", "x"), "_bad_name")


class DownloadIntegrityTests(unittest.TestCase):
    def test_safe_download_path_blocks_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            # resolve() normalises Windows 8.3 short paths so both sides match
            self.assertEqual(safe_download_path(base, "mod.jar").parent, base.resolve())
            with self.assertRaises(ModrinthError):
                safe_download_path(base, "../mod.jar")

    def test_verify_file_hash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "file.jar"
            data = b"known bytes"
            path.write_bytes(data)
            self.assertTrue(verify_file_hash(path, hashlib.sha1(data).hexdigest(), hashlib.sha512(data).hexdigest()))
            self.assertFalse(verify_file_hash(path, "0" * 40, ""))


class InstanceGroupingTests(unittest.TestCase):
    def test_group_defaults_and_sanitization(self) -> None:
        self.assertEqual(instances_core.normalize_instance_group("", "vanilla"), "Vanilla")
        self.assertEqual(instances_core.normalize_instance_group("  My Group!!  ", "custom"), "My Group_")

    def test_list_instances_normalizes_group(self) -> None:
        sample = [{"id": "a", "name": "A", "directory": "C:/tmp/a", "type": "custom"}]
        with patch.object(instances_core.config, "get", return_value=sample):
            items = instances_core.list_instances()
        self.assertEqual(items[0]["group"], "Custom")

    def test_validate_instance_reports_missing_directory(self) -> None:
        ok, issues = instances_core.validate_instance({"id": "x", "mc_version": "1.21.4", "directory": "Z:/missing/path"})
        self.assertFalse(ok)
        self.assertTrue(any("does not exist" in i for i in issues))


class ArchiveRoundTripTests(unittest.TestCase):
    def test_zip_export_and_import(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            src = base / "instance"
            src.mkdir()
            (src / "mods").mkdir()
            (src / "mods" / "example.jar").write_bytes(b"jar")
            inst = {"id": "a", "name": "A", "mc_version": "1.21.4", "directory": str(src), "type": "custom"}
            out_zip = base / "out.zip"
            modpack_archive.export_instance_zip(inst, out_zip)
            self.assertTrue(out_zip.exists())

            imported_dir = base / "imported"

            def _fake_create(name: str, version_id: str, directory=None, jvm_args: str = "") -> dict:
                imported_dir.mkdir(parents=True, exist_ok=True)
                return {
                    "id": "imp-1",
                    "name": name,
                    "mc_version": version_id,
                    "directory": str(imported_dir),
                    "type": "custom",
                }

            with patch("src.core.modpack_archive.create_custom_instance", side_effect=_fake_create):
                imported = modpack_archive.import_instance_archive(out_zip, "Imported")
            self.assertEqual(imported["id"], "imp-1")
            self.assertTrue((imported_dir / "mods" / "example.jar").exists())

    def test_mrpack_export_contains_index(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            src = base / "instance"
            src.mkdir()
            (src / "config").mkdir()
            (src / "config" / "a.txt").write_text("x", encoding="utf-8")
            inst = {"id": "a", "name": "A", "mc_version": "1.21.4", "directory": str(src), "type": "custom"}
            out_pack = base / "out.mrpack"
            modpack_archive.export_instance_mrpack(inst, out_pack)
            with zipfile.ZipFile(out_pack) as zf:
                self.assertIn("modrinth.index.json", zf.namelist())
                idx = json.loads(zf.read("modrinth.index.json").decode("utf-8"))
                self.assertEqual(idx["dependencies"]["minecraft"], "1.21.4")


class CloudSyncSafetyTests(unittest.TestCase):
    def test_push_instance_filters_sensitive_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            inst_dir = base / "instance"
            (inst_dir / "mods").mkdir(parents=True)
            (inst_dir / "mods" / "ok.jar").write_bytes(b"jar")
            (inst_dir / "logs").mkdir()
            (inst_dir / "logs" / "latest.log").write_text("secret", encoding="utf-8")
            (inst_dir / "access_token.txt").write_text("token", encoding="utf-8")

            zip_path = cloud_sync_core.push_instance(
                {"id": "custom-abc123", "directory": str(inst_dir)},
                str(base / "sync"),
            )
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = set(zf.namelist())
            self.assertIn("mods/ok.jar", names)
            self.assertNotIn("logs/latest.log", names)
            self.assertNotIn("access_token.txt", names)

    def test_pull_instance_rejects_unsafe_instance_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            archive = base / "safe.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("mods/a.jar", b"jar")
            with self.assertRaises(ValueError):
                cloud_sync_core.pull_instance("../evil", str(archive), str(base / "instances"))

    def test_pull_instance_rejects_unsafe_archive_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            archive = base / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../escape.txt", "bad")
            with self.assertRaises(ValueError):
                cloud_sync_core.pull_instance("custom-safe", str(archive), str(base / "instances"))

    def test_pull_instance_rejects_symlink_members(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            archive = base / "symlink.zip"
            info = zipfile.ZipInfo("mods/link.jar")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(info, "target")
            with self.assertRaises(ValueError):
                cloud_sync_core.pull_instance("custom-safe", str(archive), str(base / "instances"))


class AuthFlowTests(unittest.TestCase):
    def test_pkce_auth_url_uses_supplied_redirect_and_state(self) -> None:
        url = auth_core._build_auth_url("client", "http://127.0.0.1:1234/callback", "challenge", "state")
        self.assertIn("client_id=client", url)
        self.assertIn("redirect_uri=http%3A%2F%2F127.0.0.1%3A1234%2Fcallback", url)
        self.assertIn("state=state", url)
        self.assertIn("code_challenge=challenge", url)

    def test_shared_client_uses_device_code_path(self) -> None:
        with patch.object(auth_core, "_BUILTIN_CLIENT_ID", "11111111-2222-3333-4444-555555555555"):
            self.assertTrue(auth_core._uses_shared_client_id("11111111-2222-3333-4444-555555555555"))

    def test_resolve_client_id_falls_back_from_invalid_override(self) -> None:
        with patch.dict(auth_core.os.environ, {"GENOS_AZURE_CLIENT_ID": "not-a-client-id"}):
            with patch.object(auth_core.config, "get", return_value=""):
                self.assertEqual(auth_core._resolve_client_id(), auth_core._BUILTIN_CLIENT_ID)

    def test_resolve_client_id_ignores_legacy_config_override(self) -> None:
        with patch.dict(auth_core.os.environ, {}, clear=True):
            with patch.object(auth_core.config, "get", return_value="00000000402b5328"):
                self.assertEqual(auth_core._resolve_client_id(), auth_core._BUILTIN_CLIENT_ID)

    def test_resolve_client_id_ignores_blocked_first_party_override(self) -> None:
        with patch.dict(auth_core.os.environ, {}, clear=True):
            with patch.object(auth_core.config, "get", return_value="04f0c124-f2bc-4f59-8241-bf6df9866bbd"):
                self.assertEqual(auth_core._resolve_client_id(), auth_core._BUILTIN_CLIENT_ID)

    def test_resolve_client_id_allows_legacy_env_when_opted_in(self) -> None:
        with patch.dict(
            auth_core.os.environ,
            {
                "GENOS_AZURE_CLIENT_ID": "1234567890ABCDEF",
                "GENOS_ALLOW_LEGACY_AZURE_CLIENT_ID": "1",
            },
            clear=True,
        ):
            with patch.object(auth_core.config, "get", return_value=""):
                self.assertEqual(auth_core._resolve_client_id(), "1234567890ABCDEF")

    def test_redirect_uri_is_derived_from_bound_server(self) -> None:
        stop_event = auth_core.threading.Event()
        with patch.object(
            auth_core.config,
            "get",
            side_effect=lambda key, default="": {
                "auth_redirect_host": "localhost",
                "auth_redirect_path": "/callback",
            }.get(key, default),
        ):
            server, _ = auth_core._create_callback_server("state", stop_event)
            try:
                redirect_uri = auth_core._redirect_uri_for_server(server)
                self.assertTrue(redirect_uri.startswith("http://"))
                self.assertIn(f":{server.server_address[1]}/callback", redirect_uri)
            finally:
                server.server_close()

    def test_device_code_request_validates_payload(self) -> None:
        class _Resp:
            ok = True
            content = b"{}"

            def json(self) -> dict:
                return {"device_code": "device", "user_code": "ABCD-EFGH", "verification_uri": "https://www.microsoft.com/link"}

        with patch.object(auth_core._HTTP, "post", return_value=_Resp()):
            data = auth_core._request_device_code("client")
        self.assertEqual(data["user_code"], "ABCD-EFGH")

    def test_shared_client_prefers_pkce_even_when_device_code_enabled(self) -> None:
        with patch.object(
            auth_core.config,
            "get",
            side_effect=lambda key, default="": "device_code" if key == "auth_fallback_flow" else default,
        ):
            self.assertFalse(auth_core._should_use_device_code_for_client(auth_core._BUILTIN_CLIENT_ID))

    def test_custom_client_can_use_device_code_when_enabled(self) -> None:
        with patch.object(
            auth_core.config,
            "get",
            side_effect=lambda key, default="": "device_code" if key == "auth_fallback_flow" else default,
        ):
            self.assertTrue(auth_core._should_use_device_code_for_client("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))

    def test_oauth_error_message_handles_first_party_consent_block(self) -> None:
        message = auth_core._oauth_error_message(
            "invalid_request",
            "The application is a first party application and users are not permitted to consent.",
        )
        self.assertIn("blocked this sign-in flow", message)


class ConfigValidationTests(unittest.TestCase):
    def test_validate_preserves_unknown_runtime_keys(self) -> None:
        cfg = config_core.Config.__new__(config_core.Config)
        data = {
            "theme_mode": "dark",
            "cloud_sync_enabled": True,
            "account_last_used": {"player": "2026-05-26T00:00:00+00:00"},
            "custom_runtime_key": {"enabled": True},
        }
        cleaned = config_core.Config._validate(cfg, data)
        self.assertTrue(cleaned["cloud_sync_enabled"])
        self.assertIn("custom_runtime_key", cleaned)
        self.assertEqual(cleaned["custom_runtime_key"], {"enabled": True})
        self.assertEqual(cleaned["account_last_used"]["player"], "2026-05-26T00:00:00+00:00")

    def test_validate_azure_client_id_rejects_blocked_ids(self) -> None:
        cfg = config_core.Config.__new__(config_core.Config)
        self.assertEqual(config_core.Config._validate_value(cfg, "azure_client_id", "04f0c124-f2bc-4f59-8241-bf6df9866bbd"), "")
        self.assertEqual(config_core.Config._validate_value(cfg, "azure_client_id", "00000000402b5328"), "")


if __name__ == "__main__":
    unittest.main()
