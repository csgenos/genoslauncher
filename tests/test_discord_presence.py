from __future__ import annotations

import io
import json
import struct
import unittest
from unittest.mock import patch

from src.core import config as config_core
from src.core import discord_presence as presence_core


def _read_packet(blob: bytes, offset: int = 0) -> tuple[int, dict, int]:
    opcode, length = struct.unpack_from("<II", blob, offset)
    start = offset + 8
    end = start + length
    return opcode, json.loads(blob[start:end].decode("utf-8")), end


class DiscordPresencePayloadTests(unittest.TestCase):
    def test_launcher_activity_uses_configured_logo_asset(self) -> None:
        activity = presence_core.build_launcher_activity("Settings", start_time=123, large_image="glauncherlogo")

        self.assertEqual(activity["details"], "Using GenosLauncher")
        self.assertEqual(activity["state"], "Browsing Settings")
        self.assertEqual(activity["timestamps"]["start"], 123)
        self.assertEqual(activity["assets"]["large_image"], "glauncherlogo")

    def test_playing_activity_avoids_sensitive_identity_or_server_ip(self) -> None:
        activity = presence_core.build_playing_activity(
            "1.20.1",
            "Survival Pack",
            multiplayer=True,
            start_time=123,
            large_image="glauncherlogo",
        )

        self.assertEqual(activity["details"], "Playing Minecraft")
        self.assertEqual(activity["state"], "Survival Pack - multiplayer")
        self.assertNotIn("192.0.2.10", json.dumps(activity))
        self.assertNotIn("Microsoft", json.dumps(activity))

    def test_packet_writer_sends_handshake_then_activity(self) -> None:
        fake_pipe = io.BytesIO()
        presence = presence_core.DiscordPresence()
        activity = presence_core.build_launcher_activity("Home", start_time=123, large_image="glauncherlogo")

        with (
            patch.object(presence, "_is_enabled", return_value=True),
            patch.object(presence, "_configured_client_id", return_value=presence_core.DISCORD_APPLICATION_ID),
            patch.object(presence, "_open_pipe", return_value=fake_pipe),
        ):
            presence._update_blocking(activity)

        packet = fake_pipe.getvalue()
        opcode, payload, offset = _read_packet(packet)
        self.assertEqual(opcode, 0)
        self.assertEqual(payload["client_id"], presence_core.DISCORD_APPLICATION_ID)

        opcode, payload, _ = _read_packet(packet, offset)
        self.assertEqual(opcode, 1)
        self.assertEqual(payload["cmd"], "SET_ACTIVITY")
        self.assertEqual(payload["args"]["activity"]["state"], "Browsing Home")

    def test_clear_without_existing_pipe_does_not_connect(self) -> None:
        presence = presence_core.DiscordPresence()
        with patch.object(presence, "_open_pipe", side_effect=AssertionError("should not connect")):
            presence._update_blocking(None, force=True)


class DiscordPresenceConfigTests(unittest.TestCase):
    def test_discord_config_validation(self) -> None:
        cfg = config_core.Config.__new__(config_core.Config)

        self.assertEqual(
            config_core.Config._validate_value(cfg, "discord_presence_client_id", "1524019146030055444"),
            "1524019146030055444",
        )
        self.assertEqual(
            config_core.Config._validate_value(cfg, "discord_presence_client_id", "not-a-snowflake"),
            config_core.DEFAULT_CONFIG["discord_presence_client_id"],
        )
        self.assertEqual(
            config_core.Config._validate_value(cfg, "discord_presence_large_image", "glauncherlogo"),
            "glauncherlogo",
        )
        self.assertEqual(
            config_core.Config._validate_value(cfg, "discord_presence_large_image", "../logo"),
            config_core.DEFAULT_CONFIG["discord_presence_large_image"],
        )


if __name__ == "__main__":
    unittest.main()
