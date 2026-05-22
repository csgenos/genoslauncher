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
from src.core.java_manager import required_java_for_mc
from src.core.modrinth import ModrinthError, safe_download_path, verify_file_hash
from src.core.validators import (
    normalize_offline_username,
    safe_path_segment,
    validate_version_id,
)


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
            self.assertEqual(safe_download_path(base, "mod.jar").parent, base)
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


if __name__ == "__main__":
    unittest.main()
