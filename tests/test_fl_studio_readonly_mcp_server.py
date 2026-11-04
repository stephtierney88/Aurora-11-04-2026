import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from fl_studio_readonly_mcp_server import (
    DEVICE_SCRIPT_FILENAME,
    DEVICE_SCRIPT_FOLDER,
    READBACK_SCHEMA,
    FlStudioReadOnlyError,
    FlStudioReadOnlyMcpServer,
    decode_fl_studio_sysex_data,
    discover_fl_studio_executable,
    discover_fl_studio_readback_path,
    install_device_script,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = PROJECT_ROOT / "fl_studio_readonly_mcp_server.py"
DEVICE_SOURCE = PROJECT_ROOT / "fl_studio_device_script.py"
LAUNCHER_PATH = PROJECT_ROOT / "fl-studio-readonly-mcp.cmd"


class FlStudioReadOnlyMcpServerTests(unittest.TestCase):
    def make_server(self, temp_dir: str, *, stale_after_seconds: float = 10.0):
        root = Path(temp_dir) / "aurora"
        root.mkdir()
        fl = Path(temp_dir) / "FL64.exe"
        fl.write_bytes(b"fixture")
        user_data = Path(temp_dir) / "Image-Line"
        readback = Path(temp_dir) / "aurora_readback.json"
        server = FlStudioReadOnlyMcpServer(
            root,
            fl_executable=fl,
            user_data_root=user_data,
            device_script_source=DEVICE_SOURCE,
            readback_path=readback,
            stale_after_seconds=stale_after_seconds,
            midi_capture_enabled=False,
        )
        return server, root, fl, user_data, readback

    @staticmethod
    def request(server, method, params=None, request_id=1):
        return server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )

    @staticmethod
    def readback_payload():
        return {
            "schema_version": READBACK_SCHEMA,
            "bridge_version": "0.1.0",
            "read_only": True,
            "active": True,
            "session_id": "abc123",
            "sequence": 7,
            "captured_at_unix_ms": int(time.time() * 1000),
            "fl": {"version": "25.2.5.5319", "midi_scripting_api_version": 38},
            "device": {"port": 17},
            "project": {"changed_flag": 1},
            "transport": {
                "is_playing": False,
                "is_recording": False,
                "loop_mode": 1,
                "song_position_ms": 1250.0,
                "song_length_ms": 8000,
                "position_hint": "1:01:000",
            },
            "capabilities": {
                "version_readback": True,
                "project_dirty_readback": True,
                "transport_readback": True,
                "transport_control": False,
                "project_mutation": False,
                "arbitrary_python": False,
            },
        }

    def test_explicit_fl_discovery_requires_existing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "FL64.exe"
            executable.write_bytes(b"fixture")
            self.assertEqual(discover_fl_studio_executable(executable), executable.resolve())
            self.assertIsNone(discover_fl_studio_executable(Path(temp_dir) / "missing.exe"))

    def test_default_readback_path_is_local_app_data_and_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            explicit = Path(temp_dir) / "custom.json"
            self.assertEqual(discover_fl_studio_readback_path(explicit), explicit.resolve())

        expected = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        self.assertEqual(
            discover_fl_studio_readback_path(),
            (expected / "Aurora" / "aurora_readback.json").resolve(),
        )

    def test_install_device_script_is_idempotent_and_refuses_unapproved_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = (
                Path(temp_dir)
                / DEVICE_SCRIPT_FOLDER
                / DEVICE_SCRIPT_FILENAME
            )
            readback = Path(temp_dir) / "runtime" / "aurora_readback.json"
            first = install_device_script(
                DEVICE_SOURCE, target, readback_path=readback
            )
            second = install_device_script(
                DEVICE_SOURCE, target, readback_path=readback
            )
            target.write_text("# name=Different Script\n", encoding="utf-8")
            with self.assertRaisesRegex(FlStudioReadOnlyError, "different Aurora"):
                install_device_script(DEVICE_SOURCE, target)

            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
            self.assertTrue(first["readback_directory_prepared"])
            self.assertEqual(first["readback_directory"], str(readback.parent.resolve()))
            self.assertTrue(readback.parent.is_dir())
            self.assertEqual(len(first["source_sha256"]), 64)

    def test_installer_rejects_invalid_source_before_preparing_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "invalid_device.py"
            target = root / "target" / DEVICE_SCRIPT_FILENAME
            readback = root / "runtime" / "aurora_readback.json"
            source.write_text("# name=Different Script\n", encoding="utf-8")

            with self.assertRaisesRegex(FlStudioReadOnlyError, "required Aurora"):
                install_device_script(source, target, readback_path=readback)

            self.assertFalse(target.parent.exists())
            self.assertFalse(readback.parent.exists())

    def test_tools_and_device_script_have_no_daw_mutation_authority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, _ = self.make_server(temp_dir)
            tools = self.request(server, "tools/list")["result"]["tools"]
            posture = server.capability_posture()

        self.assertEqual(
            {row["name"] for row in tools},
            {
                "fl_studio_get_installation",
                "fl_studio_get_bridge_status",
                "fl_studio_observe",
            },
        )
        self.assertTrue(all(row["annotations"]["readOnlyHint"] for row in tools))
        self.assertTrue(all(not row["annotations"]["destructiveHint"] for row in tools))
        self.assertTrue(all(value is False for value in posture["authority"].values()))

        script = DEVICE_SOURCE.read_text(encoding="utf-8")
        forbidden = (
            "transport.start(",
            "transport.stop(",
            "transport.record(",
            "setSongPos(",
            "plugins.",
            "eval(",
            "exec(",
            "OnMidiMsg",
            "OnControlChange",
        )
        for text in forbidden:
            self.assertNotIn(text, script)

        self.assertNotIn("__file__", script)
        self.assertNotIn("open(", script)
        self.assertNotIn("os.", script)
        self.assertIn("device.midiOutSysex", script)
        self.assertIn("SYSEX_PREFIX", script)
        self.assertIn("math.isfinite", script)

    def test_sysex_decoder_accepts_only_bounded_aurora_json(self):
        payload = self.readback_payload()
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("ascii")
        prefix = bytes([0x7D, 0x41, 0x55, 0x52, 0x01])

        self.assertEqual(
            decode_fl_studio_sysex_data(prefix + encoded),
            payload,
        )
        self.assertIsNone(decode_fl_studio_sysex_data(b"not-aurora"))
        with self.assertRaisesRegex(FlStudioReadOnlyError, "size limit"):
            decode_fl_studio_sysex_data(prefix + b"x" * 2048, maximum_bytes=1024)

    def test_missing_readback_is_an_explicit_unavailable_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, _ = self.make_server(temp_dir)
            status = server.bridge_status()

        self.assertFalse(status["available"])
        self.assertFalse(status["fresh"])
        self.assertEqual(status["reason"], "readback_missing")

    def test_invalid_readback_returns_a_terminal_failed_receipt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, readback = self.make_server(temp_dir)
            readback.write_text(
                json.dumps({"schema_version": "unknown", "read_only": True}),
                encoding="utf-8",
            )
            receipt = server.observation_receipt(
                {"client_id": "codex.local", "request_id": "req-invalid"}
            )

        self.assertEqual(receipt["result"], "failed")
        self.assertEqual(receipt["observation"]["reason"], "invalid_readback")
        self.assertTrue(receipt["error"])
        self.assertTrue(receipt["terminal"])
        self.assertFalse(receipt["uncertain"])
        self.assertFalse(receipt["mutation_attempted"])

    def test_readback_is_bounded_sanitized_and_fresh(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, readback = self.make_server(temp_dir)
            payload = self.readback_payload()
            payload["customer_id"] = "must-not-escape"
            payload["project"]["title"] = "private-project-title"
            payload["transport"]["position_hint"] = {
                "private": "nested-value-must-not-escape"
            }
            readback.write_text(json.dumps(payload), encoding="utf-8")
            status = server.bridge_status()

        encoded = json.dumps(status)
        self.assertTrue(status["available"])
        self.assertTrue(status["fresh"])
        self.assertTrue(status["active"])
        self.assertEqual(status["readback"]["transport"]["song_position_ms"], 1250.0)
        self.assertNotIn("must-not-escape", encoded)
        self.assertNotIn("private-project-title", encoded)
        self.assertNotIn("nested-value-must-not-escape", encoded)
        self.assertNotIn("customer_id", encoded)
        self.assertEqual(status["readback"]["transport"]["position_hint"], "")

    def test_readback_does_not_coerce_string_booleans_or_nonfinite_numbers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, readback = self.make_server(temp_dir)
            payload = self.readback_payload()
            payload["active"] = "false"
            payload["transport"]["is_playing"] = "false"
            payload["transport"]["song_position_ms"] = "NaN"
            payload["capabilities"]["transport_readback"] = "true"
            readback.write_text(json.dumps(payload), encoding="utf-8")
            status = server.bridge_status()

        self.assertFalse(status["active"])
        self.assertFalse(status["readback"]["active"])
        self.assertFalse(status["readback"]["transport"]["is_playing"])
        self.assertEqual(status["readback"]["transport"]["song_position_ms"], 0.0)
        self.assertFalse(status["readback"]["capabilities"]["transport_readback"])

    def test_stale_readback_is_never_reported_active(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, readback = self.make_server(
                temp_dir, stale_after_seconds=2.0
            )
            readback.write_text(json.dumps(self.readback_payload()), encoding="utf-8")
            old = time.time() - 30
            os.utime(readback, (old, old))
            status = server.bridge_status()

        self.assertTrue(status["available"])
        self.assertFalse(status["fresh"])
        self.assertFalse(status["active"])
        self.assertEqual(status["reason"], "stale")

    def test_rewritten_old_capture_is_still_stale(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, readback = self.make_server(temp_dir)
            payload = self.readback_payload()
            payload["captured_at_unix_ms"] -= 60_000
            readback.write_text(json.dumps(payload), encoding="utf-8")
            receipt = server.observation_receipt({"client_id": "test", "request_id": "old"})
            self.assertEqual(receipt["result"], "unavailable")
            self.assertFalse(receipt["observation"]["fresh"])
            self.assertEqual(receipt["observation"]["reason"], "stale")

    def test_missing_or_future_capture_time_is_not_fresh(self):
        for timestamp in (None, 0, True, "NaN", int(time.time() * 1000) + 60_000):
            with self.subTest(timestamp=timestamp), tempfile.TemporaryDirectory() as temp_dir:
                server, _, _, _, readback = self.make_server(temp_dir)
                payload = self.readback_payload()
                payload["captured_at_unix_ms"] = timestamp
                readback.write_text(json.dumps(payload), encoding="utf-8")
                status = server.bridge_status()
                self.assertFalse(status["fresh"])
                self.assertFalse(status["active"])
                self.assertEqual(status["reason"], "invalid_capture_time")

    def test_midi_capture_uses_a_private_temporary_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, readback = self.make_server(temp_dir)
            payload = self.readback_payload()
            payload["customer_id"] = "private-data"
            encoded = bytes([0x7D, 0x41, 0x55, 0x52, 0x01]) + json.dumps(payload).encode("ascii")
            port = MagicMock()
            port.__enter__.return_value = port
            port.poll.return_value = SimpleNamespace(type="sysex", data=encoded)
            fake_mido = SimpleNamespace(
                get_input_names=lambda: ["Aurora FL Bridge"], open_input=lambda name: port,
            )
            # Another CLI/server process may already own the former shared .tmp path.
            other_writer = readback.with_name(readback.name + ".tmp")
            other_writer.write_text("other-writer", encoding="utf-8")
            server.midi_capture_enabled = True
            with patch.dict(sys.modules, {"mido": fake_mido}):
                status = server.bridge_status()
            self.assertTrue(status["active"])
            self.assertEqual(status["midi_capture"]["reason"], "captured")
            self.assertNotIn("private-data", readback.read_text(encoding="utf-8"))
            self.assertEqual(other_writer.read_text(encoding="utf-8"), "other-writer")

    def test_failed_midi_replace_preserves_readback_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, readback = self.make_server(temp_dir)
            original = json.dumps(self.readback_payload())
            readback.write_text(original, encoding="utf-8")
            encoded = bytes([0x7D, 0x41, 0x55, 0x52, 0x01]) + original.encode("ascii")
            port = MagicMock()
            port.__enter__.return_value = port
            port.poll.return_value = SimpleNamespace(type="sysex", data=encoded)
            fake_mido = SimpleNamespace(
                get_input_names=lambda: ["Aurora FL Bridge"], open_input=lambda name: port,
            )
            server.midi_capture_enabled = True
            before = set(readback.parent.iterdir())
            with patch.dict(sys.modules, {"mido": fake_mido}), patch(
                "fl_studio_readonly_mcp_server.os.replace", side_effect=PermissionError,
            ):
                server.bridge_status()
            self.assertEqual(server._last_midi_capture["reason"], "capture_failed")
            self.assertEqual(readback.read_text(encoding="utf-8"), original)
            self.assertEqual(set(readback.parent.iterdir()), before)

    def test_observation_receipt_preserves_identity_and_is_terminal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, readback = self.make_server(temp_dir)
            readback.write_text(json.dumps(self.readback_payload()), encoding="utf-8")
            first = server.observation_receipt(
                {"client_id": "codex.local", "request_id": "req-001"}
            )
            second = server.observation_receipt(
                {"client_id": "codex.local", "request_id": "req-001"}
            )

        self.assertEqual(first["client_id"], "codex.local")
        self.assertEqual(first["request_id"], "req-001")
        self.assertEqual(first["normalized_command_digest"], second["normalized_command_digest"])
        self.assertEqual(first["admission"]["decision"], "allow")
        self.assertEqual(first["result"], "observed")
        self.assertTrue(first["terminal"])
        self.assertFalse(first["uncertain"])
        self.assertFalse(first["mutation_attempted"])
        self.assertFalse(first["automatic_replay_allowed"])

    def test_bad_request_token_is_rejected_before_observation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, _ = self.make_server(temp_dir)
            with self.assertRaisesRegex(FlStudioReadOnlyError, "request_id"):
                server.observation_receipt(
                    {"client_id": "codex.local", "request_id": "bad request"}
                )

    def test_resources_and_prompt_are_discoverable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _, _ = self.make_server(temp_dir)
            resources = self.request(server, "resources/list")["result"]["resources"]
            prompts = self.request(server, "prompts/list")["result"]["prompts"]
            prompt = self.request(
                server,
                "prompts/get",
                {"name": "fl_studio_readonly_preflight", "arguments": {}},
            )["result"]

        self.assertEqual(len(resources), 3)
        self.assertEqual(len(prompts), 1)
        text = prompt["messages"][0]["content"]["text"]
        self.assertIn("Do not start or stop playback", text)

    def test_stdio_round_trip_and_notification_silence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, root, fl, user_data, readback = self.make_server(temp_dir)
            del server
            messages = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ]
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SERVER_PATH),
                    "--root",
                    str(root),
                    "--fl",
                    str(fl),
                    "--user-data-root",
                    str(user_data),
                    "--readback",
                    str(readback),
                ],
                input="".join(json.dumps(row) + "\n" for row in messages),
                text=True,
                capture_output=True,
                timeout=10,
                check=True,
            )

        responses = [
            json.loads(line) for line in completed.stdout.splitlines() if line.strip()
        ]
        self.assertEqual([row["id"] for row in responses], [1, 2])
        self.assertEqual(len(responses[1]["result"]["tools"]), 3)
        self.assertEqual(completed.stderr, "")

    @unittest.skipUnless(sys.platform == "win32", "Windows launcher regression")
    def test_windows_launcher_forwards_self_check(self):
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "call", str(LAUNCHER_PATH), "--self-check", "--no-midi-capture"],
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["server_name"], "fl-studio-readonly")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["installation_found"])


if __name__ == "__main__":
    unittest.main()
