"""Offline console contracts; no native UI, API or runtime process required."""
import copy
import http.client
import json
import subprocess
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from aurora_validation_console import (
    PRESETS, ROOT, ValidationService, digest, make_server, validate_profile, write_json,
)


class ProfileTests(unittest.TestCase):
    def test_presets_round_trip_without_mutation(self):
        for preset in PRESETS.values():
            before = copy.deepcopy(preset)
            self.assertEqual(validate_profile(preset), before)
            self.assertEqual(preset, before)

    def test_unknown_or_live_fields_rejected(self):
        for field, value in (("live", True), ("command", "SHUTDOWN_RUNTIME()"), ("api_key", "example")):
            with self.assertRaises(ValueError):
                validate_profile(dict(PRESETS["effort"], **{field: value}))

    def test_strict_limits_and_combinations(self):
        for field, value in (("max_calls", 4), ("max_calls", True), ("timeout_seconds", 61),
                             ("timeout_seconds", 9), ("timeout_seconds", 12.5), ("prompt", ""),
                             ("changed_effort", "ultra"), ("model", "unknown"), ("transport", "live")):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_profile(dict(PRESETS["effort"], **{field: value}))
        with self.assertRaises(ValueError):
            validate_profile(dict(PRESETS["model"], transport="responses"))


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Catalog compilation is deliberately once per server, not every poll.
        cls.temp = tempfile.TemporaryDirectory(prefix="aurora-vc-unit-")
        cls.service = ValidationService(ROOT, cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.service.close()
        cls.temp.cleanup()

    def test_catalog_parity_and_all_subsystem_tags(self):
        catalog = self.service.catalog
        self.assertEqual(len(catalog["commands"]), catalog["runtime_binding_count"] + catalog["desktop_binding_count"])
        self.assertTrue(all(row["subsystems"] for row in catalog["commands"]))
        self.assertTrue(any(row["aliases"] for row in catalog["commands"]))

    def test_dry_run_does_not_spawn_or_persist(self):
        before = self.service.records("runs")
        with patch("subprocess.Popen", side_effect=AssertionError("No process in preview")):
            result = self.service.preview(PRESETS["effort"], self.service.identity["fingerprint"])
        self.assertFalse(result["runtime_mutated"])
        self.assertEqual(result["real_api_calls"], 0)
        self.assertEqual(self.service.records("runs"), before)

    def test_stale_and_changed_source_rejected(self):
        with self.assertRaises(ValueError):
            self.service.preview(PRESETS["effort"], "old")
        with patch("aurora_validation_console.source_identity", return_value={"fingerprint": "changed"}):
            with self.assertRaises(ValueError):
                self.service.preview(PRESETS["effort"], self.service.identity["fingerprint"])

    def test_saved_profiles_have_content_versions(self):
        first = self.service.save_profile(PRESETS["effort"])
        changed = self.service.save_profile(dict(PRESETS["effort"], name="Edited"))
        self.assertNotEqual(first["version"], changed["version"])
        self.assertIn(first, self.service.records("profiles"))

    def test_duplicate_request_reuses_evidence_and_conflicting_retry_rejects(self):
        request = str(uuid.uuid4())
        profile = PRESETS["effort"]
        row = dict(self.service.preview(profile, self.service.identity["fingerprint"]),
                   run_id=request, status="passed")
        write_json(self.service.storage / "runs" / (request + ".json"), row)
        with patch("threading.Thread", side_effect=AssertionError("Duplicate must not spawn")):
            self.assertEqual(self.service.start(profile, self.service.identity["fingerprint"], request), row)
        with self.assertRaises(ValueError):
            self.service.start(dict(profile, name="different"), self.service.identity["fingerprint"], request)

    def test_invalid_run_id_cannot_escape_storage(self):
        with self.assertRaises(ValueError):
            self.service.start(PRESETS["effort"], self.service.identity["fingerprint"], "../../outside")

    def test_second_owner_cannot_open_store(self):
        with self.assertRaises(ValueError):
            ValidationService(ROOT, self.temp.name)

    def test_restart_marks_running_unknown_without_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "runs").mkdir()
            write_json(root / "runs" / "interrupted.json", {"status": "running"})
            service = ValidationService(ROOT, root)
            try:
                self.assertEqual(service.records("runs")[0]["status"], "interrupted_unknown")
                self.assertIsNone(service.thread)
            finally:
                service.close()

    def test_cancel_nonactive_does_not_affect_other_run(self):
        self.assertEqual(self.service.cancel("unowned")["status"], "not_active")

    def test_startup_failure_removes_owned_fixture(self):
        with patch("subprocess.Popen", side_effect=OSError("injected startup failure")):
            row = self.service.start(PRESETS["effort"], self.service.identity["fingerprint"], str(uuid.uuid4()))
            self.service.thread.join(10)
        result = next(r for r in self.service.records("runs") if r["run_id"] == row["run_id"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["cleanup"], {"worker_stopped": True, "fixture_removed": True})

    def test_copy_failure_removes_owned_fixture(self):
        with patch("shutil.copy2", side_effect=OSError("injected copy failure")):
            row = self.service.start(PRESETS["effort"], self.service.identity["fingerprint"], str(uuid.uuid4()))
            self.service.thread.join(10)
        result = next(r for r in self.service.records("runs") if r["run_id"] == row["run_id"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["cleanup"]["fixture_removed"])

    def test_timeout_kills_only_owned_process_and_reports_unknown_restoration(self):
        class StalledProcess:
            pid, returncode = 123, None
            def poll(self):
                return self.returncode
            def wait(self, timeout):
                if self.returncode is None:
                    raise subprocess.TimeoutExpired("fixture", timeout)
                return self.returncode
            def terminate(self):
                self.returncode = -1
            kill = terminate
        process = StalledProcess()
        row = dict(self.service.preview(PRESETS["effort"], self.service.identity["fingerprint"]),
                   run_id=str(uuid.uuid4()), status="running", result=None)
        with patch("subprocess.Popen", return_value=process), patch("time.monotonic", side_effect=[0, 100, 101]):
            self.service._run(row)
        self.assertEqual(row["status"], "timed_out")
        self.assertTrue(row["cleanup"]["worker_stopped"])
        self.assertTrue(row["cleanup"]["fixture_removed"])
        self.assertIsNone(row["result"])


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="aurora-vc-http-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.service = ValidationService(ROOT, cls.temp.name)
        cls.addClassCleanup(cls.service.close)
        cls.server, cls.token = make_server(cls.service)
        cls.addClassCleanup(cls.server.server_close)
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.start()
        def stop_server():
            cls.server.shutdown()
            cls.thread.join(3)
        cls.addClassCleanup(stop_server)

    def request(self, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("POST" if body is not None else "GET", path,
                               json.dumps(body) if body is not None else None,
                               headers or {})
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def auth(self):
        return {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}

    def test_auth_required_and_origin_host_checked(self):
        self.assertEqual(self.request("/api/catalog")[0], 401)
        self.assertEqual(self.request("/api/catalog", headers=self.auth())[0], 200)
        self.assertEqual(self.request("/api/catalog", headers=dict(self.auth(), Origin="https://outside.invalid"))[0], 403)
        self.assertEqual(self.request("/api/catalog", headers=dict(self.auth(), Host="outside.invalid"))[0], 403)

    def test_static_page_is_self_contained_and_has_security_headers(self):
        for path in ("/", "/style.css", "/app.js"):
            code, body, headers = self.request(path)
            self.assertEqual(code, 200)
            self.assertTrue(body)
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("/../aurora2.py")[0], 404)

    def test_preview_and_profile_errors_are_structured(self):
        code, body, _ = self.request("/api/preview", {"profile": PRESETS["model"],
            "fingerprint": self.service.identity["fingerprint"]}, self.auth())
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["real_api_calls"], 0)
        self.assertEqual(self.request("/api/preview", {"profile": {}}, self.auth())[0], 400)
        self.assertEqual(self.request("/api/live", {}, self.auth())[0], 404)


if __name__ == "__main__":
    unittest.main()
