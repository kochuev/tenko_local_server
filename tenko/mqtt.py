import json
import logging
import threading
import time

import paho.mqtt.client as mqtt

from .entities import BY_KEY, ENTITIES, REMOVED_ENTITIES, discovery, state
from .protocol import SCHEDULES, SERIAL
from .schedule_editor import SCHEDULE_MODES, details

LOG = logging.getLogger(__name__)


class Bridge:
    def __init__(self, config, store):
        self.config, self.store = config, store
        self.connected = False
        self.stopping = threading.Event()
        self.publish_lock = threading.RLock()
        self.firmwares = {}
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=config.mqtt_client_id,
                                  clean_session=True)
        self.client.max_queued_messages_set(4096)
        self.client.enable_logger(LOG)
        if config.mqtt_username:
            self.client.username_pw_set(config.mqtt_username, config.mqtt_password)
        if config.mqtt_tls:
            self.client.tls_set(ca_certs=config.mqtt_ca_file or None)
        self.client.will_set(f"{config.mqtt_prefix}/bridge/availability", "offline", qos=1, retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.on_subscribe = self.on_subscribe
        self.client.reconnect_delay_set(min_delay=1, max_delay=60)

    def start(self):
        self.client.connect_async(self.config.mqtt_host, self.config.mqtt_port, keepalive=30)
        self.client.loop_start()
        self.worker = threading.Thread(target=self.tick, name="mqtt-freshness", daemon=True)
        self.worker.start()

    def stop(self):
        self.stopping.set()
        if hasattr(self, "worker"):
            self.worker.join(timeout=6)
        if self.connected:
            info = self.publish(f"{self.config.mqtt_prefix}/bridge/availability", "offline")
            if info is not None:
                info.wait_for_publish(timeout=3)
        self.client.disconnect()
        self.client.loop_stop()

    def publish(self, topic, value):
        if not self.connected:
            return None
        payload = json.dumps(value, allow_nan=False, separators=(",", ":")) if isinstance(value, (dict, list)) else value
        LOG.debug("MQTT OUT topic=%r qos=1 retain=true payload=%r", topic, payload)
        info = self.client.publish(topic, payload, qos=1, retain=True)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            LOG.error("MQTT publish rejected for %s: %s", topic, mqtt.error_string(info.rc))
        return info

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            LOG.error("MQTT connection refused: %s", reason_code)
            return
        self.connected = True
        LOG.info("Connected to MQTT")
        result, _ = client.subscribe([(f"{self.config.mqtt_prefix}/+/command/+", 1),
                                      (f"{self.config.discovery_prefix}/status", 1)])
        if result != mqtt.MQTT_ERR_SUCCESS:
            LOG.error("MQTT subscriptions failed: %s", mqtt.error_string(result))
        self.publish(f"{self.config.mqtt_prefix}/bridge/availability", "online")
        self.refresh(discover=True)

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        if not self.stopping.is_set():
            LOG.warning("MQTT disconnected: %s; reconnecting", reason_code)

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        for reason in reason_codes:
            if reason.is_failure:
                LOG.error("Broker rejected a command/birth subscription: %s; check MQTT ACLs", reason)

    def on_message(self, client, userdata, message):
        LOG.debug("MQTT IN topic=%r retain=%s payload=%r", message.topic, message.retain, message.payload)
        if message.topic == f"{self.config.discovery_prefix}/status":
            if message.payload == b"online":
                self.refresh(discover=True)
            return
        if message.retain:
            LOG.warning("Ignored retained control command on %s", message.topic)
            return
        remainder = message.topic.removeprefix(self.config.mqtt_prefix + "/").split("/")
        if len(remainder) != 3 or remainder[1] != "command" or not SERIAL.fullmatch(remainder[0]):
            return
        serial, _, key = remainder
        try:
            if len(message.payload) > 65536:
                raise ValueError("Command exceeds 64 KiB")
            if self.config.allowed_serials and serial not in self.config.allowed_serials:
                raise ValueError("Serial not allowed")
            payload = message.payload.decode("utf-8")
            if key == "settings":
                self.store.command(serial, json.loads(payload))
            else:
                entity = BY_KEY.get(key)
                if not entity or not (entity.setting or entity.action):
                    raise ValueError(f"Unknown control: {key}")
                if entity.action:
                    if entity.kind == "button" and payload != "PRESS":
                        raise ValueError("Button payload must be PRESS")
                    self.store.editor_command(serial, entity.action, payload)
                else:
                    if key == "schedule_mode":
                        if payload not in SCHEDULE_MODES:
                            raise ValueError("Choose Whole week, Individual days, or Constant temperature")
                        payload = SCHEDULE_MODES[payload]
                    self.store.component_command(serial, entity.setting, entity.index, payload)
        except (ValueError, KeyError, UnicodeError) as exc:
            LOG.warning("Rejected MQTT command %s: %s", message.topic, exc)
            try:
                self.store.command_error(serial, str(exc))
            except KeyError:
                return
            except OSError:
                self.command_io_error(serial)
                return
        except OSError:
            self.command_io_error(serial)
            return
        self.emit(serial)

    def command_io_error(self, serial):
        LOG.exception("MQTT command NOT accepted for %s: state could not be persisted", serial)
        try:
            values = state(self.store.get(serial))
        except KeyError:
            return
        values.update(command_state="error", command_error="Command NOT accepted: persistence failed; inspect service logs")
        self.publish(f"{self.config.mqtt_prefix}/{serial}/state", values)

    def emit(self, serial, discover=False):
        # Always reread under the publication lock so concurrent HTTP/MQTT updates
        # cannot publish an older snapshot after a newer one.
        with self.publish_lock:
            record = self.store.get(serial)
            config = self.config
            base = f"{config.mqtt_prefix}/{serial}"
            firmware = record.get("report", {}).get("decoded", {}).get("VER")
            if discover or self.firmwares.get(serial, object()) != firmware:
                for kind, key in REMOVED_ENTITIES:
                    self.publish(f"{config.discovery_prefix}/{kind}/tenko_{serial}/{key}/config", "")
                self.publish(f"{base}/schedule_editor", "")
                for entity in ENTITIES:
                    self.publish(f"{config.discovery_prefix}/{entity.kind}/tenko_{serial}/{entity.key}/config",
                                 discovery(entity, serial, firmware, config))
                if self.connected:
                    self.firmwares[serial] = firmware
            self.publish(f"{base}/state", state(record))
            self.availability(record)
            report = record.get("report", {})
            self.publish(f"{base}/diagnostics", {
                "raw": report.get("raw", {}), "decoded": report.get("decoded", {}),
                "parse_errors": report.get("parse_errors", []), "stage_conflict": report.get("stage_conflict"),
                "pending": record["pending"], "reported": report.get("settings", {}),
                "draft": record["draft"],
                "command_error": record["command_error"], "attempts": record["attempts"],
                "separate_raw_status": record["status"],
                "status_report": record["status_report"],
                "status_interpretation": "ASSUMED: 0=off, 1=on; other codes unknown",
                "stage_equivalence": "ASSUMED: ST1/ST2 enable flags duplicate STU",
                "energy_units": "presumed kWh; scaling/reset/month ordering unverified",
                "monthly_values": report.get("decoded", {}).get("YSt"),
            })
            for key in SCHEDULES:
                self.publish(f"{base}/schedules/{key}", details(record, key))

    def availability(self, record):
        now = time.time()
        base = f"{self.config.mqtt_prefix}/{record['serial']}"
        for field, topic in (("last_report", "availability"), ("last_status", "status_availability")):
            online = record[field] is not None and now - record[field] < self.config.freshness_timeout
            self.publish(f"{base}/{topic}", "online" if online else "offline")

    def refresh(self, discover=False):
        for record in self.store.all():
            self.emit(record["serial"], discover)

    def tick(self):
        while not self.stopping.wait(5):
            try:
                for serial in self.store.expire():
                    self.emit(serial)
                for record in self.store.all():
                    with self.publish_lock:
                        self.availability(self.store.get(record["serial"]))
            except (OSError, ValueError) as exc:
                LOG.error("Availability update failed: %s", exc)
