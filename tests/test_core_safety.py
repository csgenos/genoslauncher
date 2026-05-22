from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
