import json
import os
import subprocess
import threading
import time
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import paho.mqtt.client as mqtt

from tenko.protocol import form, parse_report

ROOT = Path(__file__).resolve().parents[1]
OBSOLETE_DISCOVERY = (
    ("button", "cancel_pending"), ("button", "editor_apply_all"),
    ("number", "schedule_MO_01_hour"), ("binary_sensor", "status_heating"),
    ("binary_sensor", "heating_on"), ("switch", "constant_enabled"),
    ("number", "constant_target"), ("climate", "minimum_thermostat"),
    ("select", "stage_resolution_source"), ("button", "resolve_stages"),
)


@unittest.skipUnless(os.environ.get("TENKO_DOCKER_TESTS") == "1", "Opt-in Docker/MQTT integration check")
class DockerFlowTests(unittest.TestCase):
    def docker(self, *args):
        return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.STDOUT).strip()

    def mapped_port(self, name, port):
        container = json.loads(self.docker("inspect", name))[0]
        if container["State"]["Status"] == "exited":
            self.fail(f"{name} exited:\n" + self.docker("logs", "--tail", "20", name))
        bindings = container["NetworkSettings"]["Ports"]
        return bindings[f"{port}/tcp"][0]["HostPort"]

    def wait(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                result = predicate()
                if result:
                    return result
            except (OSError, KeyError, ValueError, URLError):
                pass
            time.sleep(.1)
        self.fail("Timed out waiting for expected HTTP/MQTT state")

    def setUp(self):
        self.network = "tenko-native-test-" + uuid.uuid4().hex[:8]
        self.broker = self.network + "-mqtt"
        self.app = self.network + "-app"
        self.latest = {}
        self.energy_discovery = []
        self.messages_lock = threading.Lock()
        self.client = self.make_client()
        self.addCleanup(self.cleanup)
        self.docker("network", "create", self.network)
        self.docker("run", "-d", "--name", self.broker, "--network", self.network,
                    "-p", "127.0.0.1::1883",
                    "-v", f"{ROOT}/tests/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro",
                    "eclipse-mosquitto:2", "sh", "-c",
                    "if [ ! -f /tmp/tenko-test-passwd ]; then"
                    " mosquitto_passwd -b -c /tmp/tenko-test-passwd bridge test-only"
                    " && chown mosquitto:mosquitto /tmp/tenko-test-passwd"
                    " && chmod 600 /tmp/tenko-test-passwd; fi"
                    " && exec mosquitto -c /mosquitto/config/mosquitto.conf")
        self.connect_observer()
        self.client.publish("tenko/211229_005/command/modulation", "Off", qos=1, retain=True).wait_for_publish(3)
        for kind, key in OBSOLETE_DISCOVERY:
            self.client.publish(f"homeassistant/{kind}/tenko_211229_005/{key}/config",
                                '{"name":"Obsolete control"}', qos=1, retain=True).wait_for_publish(3)
        old_energy = json.dumps({
            "name": "Boiler period consumption (presumed kWh)",
            "unique_id": "tenko_211229_005_period_amount",
            "state_topic": "tenko/211229_005/state",
            "value_template": "{{ value_json.period_amount }}",
            "unit_of_measurement": "kWh",
            "entity_category": "diagnostic",
            "device": {"identifiers": ["tenko_211229_005"], "name": "Tenko Boiler"},
        })
        self.client.publish("homeassistant/sensor/tenko_211229_005/period_amount/config",
                            old_energy, qos=1, retain=True).wait_for_publish(3)
        self.wait(lambda: self.latest.get("homeassistant/sensor/tenko_211229_005/period_amount/config") == old_energy)
        self.start_app("debug")
        self.raw = form(next(line for line in (ROOT / "prompt.md").read_text().splitlines()
                             if line.startswith("sn=")).encode())
        self.assertEqual(self.poll(), "nochange")
        self.wait_state(lambda value: value.get("schedule_mode") == "Whole week")

    def start_app(self, level):
        self.docker("run", "-d", "--name", self.app, "--network", self.network,
                    "--read-only", "--cap-drop", "ALL", "-p", "127.0.0.1::9080",
                    "-e", f"MQTT_HOST={self.broker}", "-e", "MQTT_USERNAME=bridge",
                    "-e", "MQTT_PASSWORD=test-only", "-e", f"LOG_LEVEL={level}", "tenko-local:latest")
        self.set_base()

    def cleanup(self):
        self.client.disconnect()
        self.client.loop_stop()
        for name in (self.app, self.broker):
            subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", self.network], capture_output=True)

    def connect_observer(self):
        port = int(self.wait(lambda: self.mapped_port(self.broker, 1883), timeout=10))
        self.wait(lambda: self.client.connect("127.0.0.1", port) == mqtt.MQTT_ERR_SUCCESS)
        self.client.loop_start()

    def make_client(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.network)
        client.username_pw_set("bridge", "test-only")
        client.on_connect = lambda c, u, f, r, p: c.subscribe("#", qos=1)
        client.on_message = self.on_message
        return client

    def on_message(self, client, userdata, message):
        with self.messages_lock:
            self.latest[message.topic] = message.payload.decode()
            if message.topic == "homeassistant/sensor/tenko_211229_005/period_amount/config":
                self.energy_discovery.append(message.payload.decode())

    def topic_json(self, suffix):
        with self.messages_lock:
            return json.loads(self.latest[f"tenko/211229_005/{suffix}"])

    def wait_state(self, predicate):
        return self.wait(lambda: (value if predicate(value) else None)
                         if (value := self.topic_json("state")) else None)

    def send(self, key, payload):
        self.client.publish(f"tenko/211229_005/command/{key}", payload, qos=1).wait_for_publish(3)

    def set_base(self):
        self.base = "http://127.0.0.1:" + self.wait(lambda: self.mapped_port(self.app, 9080), timeout=10)
        self.wait(lambda: json.loads(self.http("/health"))["mqtt_connected"])

    def http(self, path, body=None):
        request = Request(self.base + path, data=body,
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(request, timeout=3) as response:
            return response.read().decode()

    def poll(self):
        return self.http("/update/param", urlencode(self.raw).encode())

    def test_native_mqtt_schedule_lifecycle(self):
        for kind, key in OBSOLETE_DISCOVERY:
            self.wait(lambda: self.latest.get(f"homeassistant/{kind}/tenko_211229_005/{key}/config") == "")
        with self.messages_lock:
            hours = json.loads(self.latest["homeassistant/select/tenko_211229_005/schedule_MO_01_hour/config"])
            for kind, key in (("select", "mode"), ("select", "schedule_mode"),
                              ("number", "flow_cutoff"), ("number", "return_hysteresis"),
                              ("switch", "modulation"), ("switch", "manual_1"),
                              ("number", "pump_start"), ("number", "pmt_min")):
                payload = json.loads(self.latest[f"homeassistant/{kind}/tenko_211229_005/{key}/config"])
                self.assertNotIn("entity_category", payload)
        self.assertEqual(hours["options"], [str(hour) for hour in range(24)])
        self.assertEqual(hours["entity_category"], "config")
        self.assertEqual(self.http("/update/status", b"sn=211229_005&status=1"), "status updated")
        status_state = self.wait_state(lambda value: value["raw_status"] == "1")
        self.assertNotIn("status_heating", status_state)
        self.wait(lambda: self.topic_json("diagnostics")["status_report"]["path"] == "/update/status")
        self.send("schedule_MO_01_hour", "1")
        self.wait_state(lambda value: value["schedule_MO_01_hour"] == "1")
        self.assertIn(";MO=01,39.0/", self.poll())
        self.send("schedule_MO_01_target", "22")
        values = self.wait_state(lambda value: value["schedule_MO_01_target"] == 22)
        self.assertEqual(values["schedule_MO_layer"], "pending")
        self.assertEqual(self.topic_json("schedules/MO")["points"][0], [2, 39])
        uploaded = self.poll()
        self.assertIn(";MO=01,22.0/", uploaded)
        self.assertEqual(uploaded.count(";"), 16)

        self.docker("restart", self.app)
        self.set_base()
        self.assertEqual(self.poll(), uploaded)
        self.wait(lambda: self.topic_json("diagnostics")["status_report"]["raw"]["status"] == "1")
        self.raw["MO"] = self.raw["MO"].replace("[02,39.0]", "[01,22.0]", 1)
        self.assertEqual(self.poll(), "nochange")
        self.wait_state(lambda value: value["command_state"] == "applied" and value["schedule_MO_layer"] == "reported")
        self.wait(lambda: self.topic_json("diagnostics")["pending"] == {}
                  and self.topic_json("diagnostics")["draft"] == {})

        # A local boiler-panel change must win once no accepted command is pending.
        self.raw["MO"] = self.raw["MO"].replace("[01,22.0]", "[01,21.0]", 1)
        self.assertEqual(self.poll(), "nochange")
        self.wait_state(lambda value: value["schedule_MO_01_target"] == 21)
        self.send("schedule_TU_01_target", "21")
        self.wait(lambda: self.topic_json("diagnostics")["pending"].get("TU", [[None, None]])[0][1] == 21)
        self.assertTrue(self.poll().startswith("NewData:"))
        self.raw["TU"] = self.raw["TU"].replace(",38.0]", ",21.0]", 1)
        self.raw.update(TEN1="On", TEN2="Off", MOD="On,On,1,3")
        self.assertEqual(self.poll(), "nochange")
        values = self.wait_state(lambda value: value["schedule_TU_layer"] == "reported"
                                 and value["schedule_TU_01_target"] == 21 and value["ten_1_on"] == "On")
        self.assertEqual(values["ten_2_on"], "Off")
        self.assertEqual(values["modulated_power"], 33)
        with self.messages_lock:
            for key in ("ten_1_on", "ten_2_on"):
                payload = json.loads(self.latest[f"homeassistant/binary_sensor/tenko_211229_005/{key}/config"])
                self.assertNotIn("device_class", payload)

        self.send("schedule_mode", "Individual days")
        self.wait(lambda: self.topic_json("diagnostics")["pending"].get("USE") == "GraphW")
        self.send("editor_discard_all", "PRESS")
        self.wait_state(lambda value: "editor_discard_all" in value["command_error"])
        self.assertIn("USE=GraphW", self.poll())
        self.send("cancel_pending", "PRESS")
        self.wait_state(lambda value: "cancel_pending" in value["command_error"])
        self.assertIn("USE=GraphW", self.poll())
        self.raw["USE"] = "GraphW"
        self.assertEqual(self.poll(), "nochange")
        self.wait_state(lambda value: value["schedule_mode"] == "Individual days"
                        and value["command_state"] == "applied")

        reported_fi = parse_report(self.raw)["settings"]["FI"]
        desired_cutoff = 55 if reported_fi[0] != 55 else 54
        self.send("flow_cutoff", str(desired_cutoff))
        self.wait_state(lambda value: value["flow_cutoff"] == desired_cutoff
                        and value["command_state"] == "pending")
        self.wait(lambda: self.topic_json("diagnostics")["pending"].get("FI", [None])[0] == desired_cutoff)
        self.assertEqual(self.topic_json("diagnostics")["reported"]["FI"], reported_fi)
        self.assertTrue(self.poll().startswith("NewData:"))
        self.assertEqual(self.http("/update/status", b"sn=211229_005&status=0"), "status updated")
        values = self.wait_state(lambda value: value["raw_status"] == "0")
        self.assertEqual(values["flow_cutoff"], desired_cutoff)
        self.assertEqual(values["command_state"], "pending")

        logs = self.docker("logs", self.app)
        for expected in ("HTTP payload dumps enabled", "HTTP IN", "HTTP EXCHANGE", "MQTT IN", "MQTT OUT",
                         "sn=211229_005&status=1", "status updated", uploaded):
            self.assertIn(expected, logs)
        exchange = next(line for line in logs.splitlines()
                        if "HTTP EXCHANGE" in line and "path='/update/status'" in line)
        self.assertIn("request_body=b'sn=211229_005&status=1'", exchange)
        self.assertIn("response_body=b'status updated'", exchange)
        self.assertNotIn("Received PUBACK", logs)
        self.assertNotIn("Sending PUBLISH", logs)
        self.assertNotIn("test-only", logs)

        for path in ("/", "/api/boilers", "/static/editor.js"):
            with self.assertRaises(HTTPError) as error:
                self.http(path)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()

        self.client.disconnect()
        self.client.loop_stop()
        self.client.on_message = None
        self.client.on_connect = None
        self.client = self.make_client()
        with self.messages_lock:
            self.latest.clear()
        self.docker("restart", self.broker)
        self.connect_observer()
        topic = "homeassistant/select/tenko_211229_005/schedule_mode/config"
        def editor_discovery():
            with self.messages_lock:
                return json.loads(self.latest[topic])
        payload = self.wait(editor_discovery)
        self.assertEqual(payload["options"], ["Whole week", "Individual days", "Constant temperature"])
        self.assertNotIn("configuration_url", payload["device"])
        self.wait_state(lambda value: value["schedule_MO_01_target"] == 21
                        and value["schedule_mode"] == "Individual days"
                        and value["flow_cutoff"] == desired_cutoff and value["command_state"] == "pending")
        self.assertTrue(self.poll().startswith("NewData:"))
        self.raw["FI"] = f"[{desired_cutoff},{reported_fi[1]}]"
        self.assertEqual(self.poll(), "nochange")
        self.wait_state(lambda value: value["flow_cutoff"] == desired_cutoff
                        and value["command_state"] == "applied")

    def test_thermostats_energy_and_debug_cleanup(self):
        with self.messages_lock:
            constant = json.loads(self.latest["homeassistant/climate/tenko_211229_005/constant_thermostat/config"])
            minimum = json.loads(self.latest["homeassistant/number/tenko_211229_005/pmt_min/config"])
            maximum = json.loads(self.latest["homeassistant/number/tenko_211229_005/pmt_max/config"])
            energy = json.loads(self.latest["homeassistant/sensor/tenko_211229_005/period_amount/config"])
            migration = self.energy_discovery.copy()
            for key, name in (("clock", "Boiler clock"), ("frost", "AF-5"),
                              ("error", "Error Code"), ("pump", "Pump")):
                sensor = json.loads(self.latest[f"homeassistant/sensor/tenko_211229_005/{key}/config"])
                self.assertEqual(sensor["name"], name)
                self.assertNotIn("entity_category", sensor)
                self.assertEqual(sensor["unique_id"], f"tenko_211229_005_{key}")
            for key in ("statistics_days", "day_amount", "week_amount") + tuple(f"month_{i}" for i in range(12)):
                sensor = json.loads(self.latest[f"homeassistant/sensor/tenko_211229_005/{key}/config"])
                self.assertEqual(sensor["device"], energy["device"])
                self.assertEqual(sensor["entity_category"], "diagnostic")
        self.assertEqual(len(migration), 3)
        self.assertEqual(json.loads(migration[0])["device"]["identifiers"], ["tenko_211229_005"])
        self.assertEqual(migration[1], "")
        self.assertEqual(json.loads(migration[2]), energy)
        self.assertEqual((constant["min_temp"], constant["max_temp"], constant["temp_step"]), (7, 30, .1))
        self.assertEqual((minimum["min"], minimum["max"], minimum["step"]), (6, 15, 1))
        self.assertEqual((maximum["min"], maximum["max"], maximum["step"]), (7, 17, 1))
        self.assertEqual(self.latest["homeassistant/climate/tenko_211229_005/minimum_thermostat/config"], "")
        self.assertEqual(energy["device"]["name"], "TENKO Boiler Energy Meter")
        self.assertEqual(energy["device"]["via_device"], "tenko_211229_005")
        self.assertEqual(energy["unique_id"], "tenko_211229_005_period_amount")
        self.assertEqual(self.topic_json("state")["period_amount"], parse_report(self.raw)["decoded"]["STA"][1])
        self.client.publish("homeassistant/status", "online", qos=1).wait_for_publish(3)
        self.wait(lambda: len(self.energy_discovery) == 4)
        with self.messages_lock:
            self.assertEqual(json.loads(self.energy_discovery[-1]), energy)

        self.send("constant_target", "30.1")
        self.wait_state(lambda value: "7..30" in value["command_error"])
        self.assertEqual(self.poll(), "nochange")
        self.send("constant_mode", "heat")
        self.wait_state(lambda value: value["constant_mode"] == "heat" and value["constant_target"] == 7)
        self.assertIn(";TMP=On,7.0;", self.poll())
        self.assertIn("queued corrected TMP target 6.9 -> 7.0", self.docker("logs", self.app))
        self.raw["TMP"] = "On,7.0"
        self.assertEqual(self.poll(), "nochange")
        self.send("constant_mode", "off")
        self.wait_state(lambda value: value["constant_mode"] == "off")
        self.assertIn(";TMP=Off,7.0;", self.poll())
        self.raw["TMP"] = "Off,7.0"
        self.assertEqual(self.poll(), "nochange")
        self.send("constant_target", "20.1")
        self.wait_state(lambda value: value["constant_target"] == 20.1)
        self.send("constant_mode", "heat")
        self.wait_state(lambda value: value["constant_mode"] == "heat")
        self.assertIn(";TMP=On,20.1;", self.poll())
        self.assertEqual(self.http("/update/status", b"sn=211229_005&status=0"), "status updated")
        self.assertIn(";TMP=On,20.1;", self.poll())
        self.raw["TMP"] = "On,20.1"
        self.assertEqual(self.poll(), "nochange")
        self.wait_state(lambda value: value["command_state"] == "applied")
        self.send("constant_mode", "off")
        self.wait_state(lambda value: value["constant_mode"] == "off")
        self.assertIn(";TMP=Off,20.1;", self.poll())
        self.raw["TMP"] = "Off,20.1"
        self.assertEqual(self.poll(), "nochange")

        self.send("pmt_min", "8")
        self.wait_state(lambda value: value["pmt_min"] == 8)
        self.send("pmt_max", "12")
        self.wait_state(lambda value: value["pmt_max"] == 12)
        self.send("pmt_max", "8")
        values = self.wait_state(lambda value: "restart threshold" in value["command_error"])
        self.assertEqual((values["pmt_min"], values["pmt_max"]), (8, 12))
        self.send("pmt_enabled", "On")
        self.wait_state(lambda value: value["pmt_enabled"] == "On")
        self.assertIn(";PMT=On,08,12;", self.poll())
        self.raw["PMT"] = "[On,8,12]"
        self.assertEqual(self.poll(), "nochange")
        self.send("pmt_enabled", "Off")
        self.wait_state(lambda value: value["pmt_enabled"] == "Off")
        self.assertIn(";PMT=Off,08,12;", self.poll())
        self.raw["PMT"] = "[Off,8,12]"
        self.assertEqual(self.poll(), "nochange")

        for raw, expected in (("On,Off,1,3", 0), ("On,On,1,3", 33),
                              ("On,On,2,3", 66), ("Off,Off,1,3", None)):
            self.raw["MOD"] = raw
            self.assertEqual(self.poll(), "nochange")
            self.wait_state(lambda value: value["modulated_power"] == expected)
        self.raw["STU"] = "[On,Off]"
        self.assertEqual(self.poll(), "nochange")
        self.wait_state(lambda value: value["manual_1"] == "On" and value["manual_2"] == "Off")
        self.assertIn("using STU", self.docker("logs", self.app))

        self.docker("rm", "-f", "-v", self.app)
        self.start_app("INFO")
        self.assertEqual(self.poll(), "nochange")
        values = self.wait_state(lambda value: "day_amount" not in value and "raw_status" not in value)
        self.assertIn("period_amount", values)
        self.assertNotIn("pmt_temperature", values)
        self.assertEqual((values["pmt_min"], values["pmt_max"], values["pmt_enabled"]), (8, 12, "Off"))
        self.assertNotIn("month_0", values)
        self.wait(lambda: self.latest.get("tenko/211229_005/diagnostics") == "")
        for key in ("raw_fields", "stage_conflict", "statistics_days", "day_amount", "week_amount") + tuple(
                f"month_{i}" for i in range(12)):
            self.wait(lambda: self.latest.get(f"homeassistant/sensor/tenko_211229_005/{key}/config") == "")
        with self.messages_lock:
            for key in ("pump", "clock", "error", "frost", "period_amount"):
                payload = json.loads(self.latest[f"homeassistant/sensor/tenko_211229_005/{key}/config"])
                self.assertNotIn("entity_category", payload)
