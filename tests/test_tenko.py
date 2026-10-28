import base64
import copy
import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode

from tenko.config import Config
from tenko.entities import BY_KEY, ENTITIES, discovery, state
from tenko.mqtt import Bridge
from tenko.protocol import ORDER, SCHEDULES, form, parse_report, serialize, validate_setting
from tenko.server import create_server
from tenko.store import Store


ROOT = Path(__file__).resolve().parents[1]


def captured():
    # Read the original evidence without changing historical payloads/headers.
    source = (ROOT / "prompt.md").read_text()
    body = next(line for line in source.splitlines() if line.startswith("sn="))
    return form(body.encode())


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.raw = captured()
        self.report = parse_report(self.raw)

    def test_all_37_fields_and_capture_syntax(self):
        self.assertEqual(len(self.raw), 37)
        self.assertEqual(self.report["parse_errors"], [])
        self.assertFalse(self.report["stage_conflict"])
        self.assertEqual(self.report["settings"]["TMP"], ["Off", 6.9])
        self.assertEqual(self.report["settings"]["ED"][:3], [[0, 40.0]] * 3)
        self.assertEqual(self.report["decoded"]["TIM"], [19, 23, 3, 27, 10, 26])

    def test_exact_captured_response(self):
        settings = copy.deepcopy(self.report["settings"])
        settings.update(TMP=["Off", 40], PMT=["Off", 15, 17])
        settings["ED"][3][1] = 20.4
        expected = next(line for line in (ROOT / "prompt.md").read_text().splitlines()
                        if line.startswith("NewData:"))
        self.assertEqual(serialize(settings), expected)
        self.assertEqual(sorted(settings), sorted(ORDER))

    def test_form_semicolons_url_encoding_case_and_unknown_fields(self):
        self.raw["unknown"] = "channel=CS1,Err3"
        decoded = form(urlencode(self.raw).encode())
        self.assertEqual(decoded, self.raw)
        self.assertNotIn("POW", decoded)
        self.assertTrue(decoded["ED"].endswith(";"))
        self.assertEqual(parse_report(decoded)["decoded"]["unknown"], "channel=CS1,Err3")

    def test_form_rejects_duplicate_and_invalid_serial(self):
        for body in (b"sn=x&sn=y", b"sn=bad/serial", b"TA=1", b"sn=x&bad"):
            with self.subTest(body=body), self.assertRaises(ValueError):
                form(body)

    def test_faults_preserved(self):
        self.raw.update(TA="NC", TF="WP", TR="", Davl="minErr", TEN1="Err", AF="unverified", Err="1")
        report = parse_report(self.raw)
        self.assertEqual(report["decoded"]["Err"], "1")
        self.assertEqual(report["raw"], self.raw)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "state.json")
            try:
                record, _ = store.report(self.raw)
                values = state(record)
                for key in ("air", "flow", "return", "pressure", "ten_1_on"):
                    self.assertIsNone(values[key])
                self.assertEqual(values["ten_1"], "Err")
                self.assertEqual(values["frost"], "unverified")
            finally:
                store.close()

    def test_malformed_structure_not_zero(self):
        overflow = "[[" + "00," + "9" * 400 + "]," + ",".join("[01,20]" for _ in range(9)) + "];"
        for key, value in (("FI", "[50]"), ("ED", "[[00,40.0]];"), ("ED", overflow), ("MOD", "On,Off")):
            raw = {**self.raw, key: value}
            report = parse_report(raw)
            self.assertTrue(report["parse_errors"])
            self.assertIsNone(report["decoded"][key])
            self.assertEqual(report["raw"][key], value)

    def test_settings_validate_ranges_flags_and_pairs(self):
        invalid = {
            "TA": 20, "USE": "OFF", "MOD": "On,Off,0,3", "TMP": ["On", 6.9],
            "FI": [76, 5], "RE": [45, 0], "PMT": ["On", 15, 15],
            "pNA": [1, 16], "STU": ["On", "Err"],
        }
        for key, value in invalid.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_setting(key, value)
        self.assertEqual(validate_setting("pNA", [1, 15]), [1, 15])
        for value in (True, float("nan"), float("inf"), 7.01):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_setting("TMP", ["On", value])

    def test_schedule_validation_and_off(self):
        points = [[i * 2, 0 if i % 2 else 20.1] for i in range(10)]
        self.assertEqual(validate_setting("ED", points), points)
        invalid = [points[:9], points + [[23, 20]], [[0, 20]] * 10,
                   [[i + .5, 20] for i in range(10)], [[i, 6] for i in range(10)],
                   [[i, 41] for i in range(10)], list(reversed(points))]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_setting("ED", value)

    def test_duplicate_stage_conflict_has_no_silent_winner(self):
        self.raw["STU"] = "[On,Off]"
        report = parse_report(self.raw)
        self.assertTrue(report["stage_conflict"])
        self.assertNotIn("STU", report["settings"])
        with self.assertRaises(ValueError):
            serialize(report["settings"])

    def test_unknown_flags_not_sent_as_controls(self):
        for key, value in (("MOD", "Err,Off,0,3"), ("USE", "unverified"), ("FI", "[Err,5]")):
            raw = {**self.raw, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                serialize(parse_report(raw)["settings"])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.json"
        self.store = Store(self.path)
        self.raw = captured()
        self.serial = self.raw["sn"]
        self.record, _ = self.store.report(self.raw)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_pending_retry_restart_and_confirmation(self):
        self.store.command(self.serial, {"MOD": "Off"})
        first, body = self.store.report(self.raw)
        self.assertIn(";MOD=Off;EndData", body)
        self.assertEqual(first["command_state"], "pending")
        self.store.close()
        self.store = Store(self.path)
        second, retry = self.store.report(self.raw)
        self.assertEqual(body, retry)
        self.assertEqual(second["attempts"], 2)
        self.raw["MOD"] = "Off,Off,0,3"
        confirmed, nochange = self.store.report(self.raw)
        self.assertEqual(confirmed["command_state"], "applied")
        self.assertEqual(confirmed["pending"], {})
        self.assertEqual(nochange, "nochange")

    def test_no_claim_of_success_before_delivery(self):
        self.store.command(self.serial, {"MOD": "On"})
        first, body = self.store.report(self.raw)
        self.assertTrue(body.startswith("NewData:"))
        self.assertEqual(first["command_state"], "pending")
        second, _ = self.store.report(self.raw)
        self.assertEqual(second["command_state"], "applied")

    def test_commands_merge_without_overwriting_other_pending_values(self):
        self.store.component_command(self.serial, "PMT", 1, "14")
        record = self.store.component_command(self.serial, "PMT", 2, "16")
        self.assertEqual(record["pending"]["PMT"], ["On", 14, 16])
        self.store.report(self.raw)
        self.assertEqual(self.store.get(self.serial)["pending"], {"PMT": ["On", 14, 16]})

    def test_draft_persists_and_report_does_not_replace_it(self):
        draft = {"ED": [[i * 2, 0] for i in range(10)]}
        self.store.draft(self.serial, draft, 0)
        self.store.report(self.raw)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.get(self.serial)["draft"], draft)
        with self.assertRaisesRegex(ValueError, "another editor"):
            self.store.draft(self.serial, {}, 0)

    def test_stale_command_revision_rejected(self):
        self.store.report(self.raw)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.store.command(self.serial, {"MOD": "Off"}, self.record["revision"])

    def test_timeout_remains_pending_and_cancel_is_explicit(self):
        with patch("tenko.store.time.time", return_value=1000):
            self.store.command(self.serial, {"MOD": "Off"})
        with patch("tenko.store.time.time", return_value=2000):
            self.assertEqual(self.store.expire(), [self.serial])
        record = self.store.get(self.serial)
        self.assertEqual(record["command_state"], "error")
        self.assertTrue(record["pending"])
        self.assertEqual(self.store.cancel(self.serial)["pending"], {})

    def test_atomic_write_failure_keeps_previous_file_and_memory(self):
        before = self.path.read_text()
        with patch("tenko.store.os.replace", side_effect=OSError("disk failed")):
            with self.assertRaises(OSError):
                self.store.command(self.serial, {"MOD": "Off"})
        self.assertEqual(self.path.read_text(), before)
        self.assertEqual(self.store.get(self.serial)["pending"], {})
        self.assertEqual(list(self.path.parent.glob(".tenko-*.tmp")), [])

    def test_second_process_store_is_rejected(self):
        with self.assertRaises(BlockingIOError):
            Store(self.path)

    def test_corrupt_state_not_silently_reset(self):
        path = self.path.parent / "broken.json"
        path.write_text("{bad")
        with self.assertRaises(ValueError):
            Store(path)

    def test_multiple_boilers_and_concurrent_commands(self):
        self.store.report({**self.raw, "sn": "other_001"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda item: self.store.component_command(self.serial, "pNA", *item),
                                    [(0, "4"), (1, "7")]))
        self.assertEqual(len(results), 2)
        self.assertEqual(self.store.get(self.serial)["pending"]["pNA"], [4, 7])
        self.assertEqual(self.store.get("other_001")["pending"], {})
        self.assertEqual(len(json.loads(self.path.read_text())), 2)

    def test_separate_status_never_overwrites_modulation(self):
        record = self.store.status({"sn": self.serial, "status": "1"})
        self.assertEqual(state(record)["status_heating"], "On")
        self.assertEqual(state(record)["heating_on"], "Off")
        record = self.store.status({"sn": self.serial, "status": "9"})
        self.assertIsNone(state(record)["status_heating"])
        self.assertEqual(record["status"], "9")

    def test_duplicate_flags_require_explicit_resolution(self):
        raw = {**self.raw, "STU": "[On,Off]"}
        self.store.report(raw)
        with self.assertRaises(ValueError):
            self.store.command(self.serial, {"MOD": "Off"})
        record = self.store.command(self.serial, {"STU": ["On", "Off"]})
        self.assertEqual(record["pending"]["STU"], ["On", "Off"])
        _, response = self.store.report(raw)
        self.assertIn(";STU=On,Off;", response)
        self.assertEqual(self.store.get(self.serial)["command_state"], "pending")
        self.store.report({**raw, "ST1": "On,5.0"})
        self.assertEqual(self.store.get(self.serial)["command_state"], "applied")


class FakeBridge:
    connected = False

    def emit(self, *args):
        pass


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.json")
        self.config = Config(http_host="127.0.0.1", http_port=0, editor_password="test-password",
                             status_path="/captured-status", status_method="POST",
                             frame_ancestors="'self' https://ha.example.net")
        self.server = create_server(self.config, self.store, FakeBridge())
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.auth = {"Authorization": "Basic " + base64.b64encode(b"admin:test-password").decode()}
        self.serial = captured()["sn"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.close()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def report(self, raw=None):
        return self.request("POST", "/update/param", urlencode(raw or captured()),
                            {"Content-Type": "application/x-www-form-urlencoded"})

    def test_boiler_response_exact_body_and_current_content_length(self):
        status, body, headers = self.report()
        self.assertEqual((status, body), (200, b"nochange"))
        self.assertEqual(int(headers["Content-Length"]), len(body))
        self.store.command(self.serial, {"MOD": "Off"})
        status, body, headers = self.report()
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"NewData:"))
        self.assertEqual(int(headers["Content-Length"]), len(body))

    def test_auth_csrf_and_no_permissive_cors(self):
        self.assertEqual(self.request("GET", "/")[0], 401)
        status, body, headers = self.request("GET", "/", headers=self.auth)
        self.assertEqual(status, 200)
        self.assertIn(b"Stored temperature timetable", body)
        self.assertIn("frame-ancestors 'self' https://ha.example.net", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.report()
        self.assertEqual(self.request("POST", f"/api/boilers/{self.serial}/cancel", "{}", self.auth)[0], 403)

    def test_authenticated_api_queues_settings(self):
        self.report()
        revision = self.store.get(self.serial)["revision"]
        status, body, _ = self.request("POST", f"/api/boilers/{self.serial}/settings",
                                       json.dumps({"settings": {"MOD": "Off"}, "revision": revision}),
                                       {**self.auth, "Content-Type": "application/json", "X-Tenko-Request": "1"})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["command_state"], "pending")

    def test_status_uses_only_configured_path(self):
        status, body, _ = self.request("POST", "/captured-status", f"sn={self.serial}&status=0",
                                       {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual((status, body), (200, b"status updated"))
        self.assertEqual(self.store.get(self.serial)["status"], "0")
        self.assertNotEqual(self.request("POST", "/update/status", f"sn={self.serial}&status=0")[0], 200)

    def test_malformed_is_preserved_and_http_error_is_explicit(self):
        status, body, _ = self.report({**captured(), "FI": "[50]"})
        self.assertEqual(status, 400)
        self.assertIn(b"Malformed report", body)
        self.assertEqual(self.store.get(self.serial)["report"]["raw"]["FI"], "[50]")

    def test_health_reports_mqtt_failure_without_breaking_http(self):
        status, body, _ = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["mqtt_connected"])


class MQTTTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.json")
        self.raw = captured()
        self.serial = self.raw["sn"]
        self.record, _ = self.store.report(self.raw)
        self.config = Config(editor_password="test", editor_url="https://tenko.example.net")
        self.bridge = Bridge(self.config, self.store)
        self.messages = []
        self.bridge.publish = lambda topic, payload: self.messages.append((topic, payload))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_all_entities_have_values_and_stable_unique_ids(self):
        values = state(self.record)
        self.assertEqual(set(values), set(BY_KEY))
        identifiers = []
        for entity in ENTITIES:
            payload = discovery(entity, self.serial, "8.2w1.2", self.config)
            identifiers.append(payload["unique_id"])
            self.assertEqual(payload["device"]["name"], "Tenko Boiler")
            self.assertEqual(payload["device"]["identifiers"], [f"tenko_{self.serial}"])
            if entity.setting:
                self.assertTrue(payload["command_topic"].endswith(f"/command/{entity.key}"))
            if entity.unit == "kWh":
                self.assertNotIn("state_class", payload)
                self.assertNotIn("device_class", payload)
            if "capacity" in entity.key:
                self.assertNotIn("device_class", payload)
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(sum(e.setting == "STU" for e in ENTITIES), 2)

    def test_freshness_and_status_freshness_independent(self):
        self.bridge.availability(self.record)
        self.assertIn((f"tenko/{self.serial}/availability", "online"), self.messages)
        self.assertIn((f"tenko/{self.serial}/status_availability", "offline"), self.messages)
        with patch("tenko.mqtt.time.time", return_value=time.time() + 181):
            self.bridge.availability(self.record)
        self.assertEqual(self.messages[-2][1], "offline")

    def test_retained_command_is_never_replayed(self):
        self.bridge.on_message(None, None, SimpleNamespace(
            topic=f"tenko/{self.serial}/command/modulation", payload=b"Off", retain=True))
        self.assertEqual(self.store.get(self.serial)["pending"], {})

    def test_command_state_remains_reported_until_confirmation(self):
        self.bridge.on_message(None, None, SimpleNamespace(
            topic=f"tenko/{self.serial}/command/modulation", payload=b"Off", retain=False))
        record = self.store.get(self.serial)
        self.assertEqual(record["pending"], {"MOD": "Off"})
        self.assertEqual(state(record)["modulation"], "On")

    def test_invalid_command_reports_error(self):
        self.bridge.on_message(None, None, SimpleNamespace(
            topic=f"tenko/{self.serial}/command/air", payload=b"40", retain=False))
        self.assertEqual(self.store.get(self.serial)["command_state"], "error")

    def test_home_assistant_birth_republishes_all_discovery(self):
        self.bridge.on_message(None, None, SimpleNamespace(
            topic="homeassistant/status", payload=b"online", retain=False))
        configs = [topic for topic, payload in self.messages if topic.endswith("/config")]
        self.assertEqual(len(configs), len(ENTITIES))

    def test_structured_schedule_command(self):
        points = [[i * 2, 0 if i < 3 else 20] for i in range(10)]
        self.bridge.on_message(None, None, SimpleNamespace(
            topic=f"tenko/{self.serial}/command/settings", payload=json.dumps({"ED": points}).encode(),
            retain=False))
        self.assertEqual(self.store.get(self.serial)["pending"]["ED"], points)

    def test_storage_failure_is_visible_without_killing_mqtt_callback(self):
        with patch.object(self.store, "command", side_effect=OSError("disk full")):
            self.bridge.on_message(None, None, SimpleNamespace(
                topic=f"tenko/{self.serial}/command/modulation", payload=b"Off", retain=False))
        self.assertEqual(self.store.get(self.serial)["pending"], {})
        topic, payload = self.messages[-1]
        self.assertEqual(topic, f"tenko/{self.serial}/state")
        self.assertEqual(payload["command_state"], "error")
        self.assertIn("NOT accepted", payload["command_error"])


class ConfigTests(unittest.TestCase):
    def test_env_password_ports_and_status(self):
        with patch.dict("os.environ", {"EDITOR_PASSWORD": "test", "HTTP_PORT": "9090",
                                       "MQTT_PASSWORD": "broker-pass", "ALLOWED_SERIALS": "a,b"}, clear=True):
            config = Config.from_env()
            self.assertEqual(config.http_port, 9090)
            self.assertEqual(config.mqtt_password, "broker-pass")
            self.assertEqual(config.allowed_serials, ("a", "b"))
            self.assertEqual(config.status_path, "")

    def test_invalid_config_fails_at_startup(self):
        for values in ({}, {"EDITOR_PASSWORD": "test", "STATUS_PATH": "/status"},
                       {"EDITOR_PASSWORD": "test", "FRAME_ANCESTORS": "*"},
                       {"EDITOR_PASSWORD": "test", "MQTT_TLS": "maybe"}):
            with self.subTest(values=values), patch.dict("os.environ", values, clear=True):
                with self.assertRaises(ValueError):
                    Config.from_env()


if __name__ == "__main__":
    unittest.main()
