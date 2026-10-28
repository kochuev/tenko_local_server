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

from tenko.protocol import form

ROOT = Path(__file__).resolve().parents[1]


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
        for kind, key in (("button", "cancel_pending"), ("button", "editor_apply_all"),
                          ("number", "schedule_MO_01_hour"), ("binary_sensor", "status_heating")):
            self.client.publish(f"homeassistant/{kind}/tenko_211229_005/{key}/config",
                                '{"name":"Obsolete control"}', qos=1, retain=True).wait_for_publish(3)
        self.docker("run", "-d", "--name", self.app, "--network", self.network,
                    "--read-only", "--cap-drop", "ALL", "-p", "127.0.0.1::9080",
                    "-e", f"MQTT_HOST={self.broker}", "-e", "MQTT_USERNAME=bridge",
                    "-e", "MQTT_PASSWORD=test-only", "-e", "LOG_LEVEL=debug", "tenko-local:latest")
        self.set_base()
        self.raw = form(next(line for line in (ROOT / "prompt.md").read_text().splitlines()
                             if line.startswith("sn=")).encode())
        self.assertEqual(self.poll(), "nochange")
        self.wait_state(lambda value: value.get("schedule_mode") == "Whole week")

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
        for kind, key in (("button", "cancel_pending"), ("button", "editor_apply_all"),
                          ("number", "schedule_MO_01_hour"), ("binary_sensor", "status_heating")):
            self.wait(lambda: self.latest.get(f"homeassistant/{kind}/tenko_211229_005/{key}/config") == "")
        with self.messages_lock:
            hours = json.loads(self.latest["homeassistant/select/tenko_211229_005/schedule_MO_01_hour/config"])
        self.assertEqual(hours["options"], [str(hour) for hour in range(24)])
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
        self.assertEqual(values["heating_on"], "On")
        with self.messages_lock:
            for key in ("ten_1_on", "ten_2_on", "heating_on"):
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
                        and value["schedule_mode"] == "Individual days")
