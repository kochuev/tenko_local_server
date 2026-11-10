import copy
import fcntl
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

from .protocol import THERMOSTAT_COMMANDS, number, parse_report, serialize, validate_setting
from .schedule_editor import edit, new_editor

LOG = logging.getLogger(__name__)


def validate_pending_temperature(reported, pending):
    if "TMP" not in pending:
        return
    value = pending["TMP"]
    try:
        validate_setting("TMP", value)
    except ValueError:
        original = reported.get("TMP")
        # Turning off must remain possible without inventing a replacement
        # for an out-of-range target received from older boiler firmware.
        if (isinstance(value, list) and len(value) == 2 and value[0] == "Off"
                and isinstance(original, list) and len(original) == 2 and value[1] == original[1]):
            return
        raise


class Store:
    def __init__(self, path, confirmation_timeout=600):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.path = Path(path)
        self.process_lock = open(str(self.path) + ".lock", "a")
        try:
            fcntl.flock(self.process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.records = json.loads(self.path.read_text()) if self.path.exists() else {}
            if not isinstance(self.records, dict):
                raise ValueError("State file must contain a serial-keyed object")
            for serial, record in self.records.items():
                if not isinstance(record, dict) or record.get("serial") != serial:
                    raise ValueError("Invalid boiler record in state file")
                legacy_constant_state = "constant_setting" not in record
                record.setdefault("schedule_editor", new_editor())
                record.setdefault("status_report", {})
                record.setdefault("constant_setting", None)
                record.setdefault("pending_since", {
                    key: record.get("queued_at") or time.time() for key in record.get("pending", {})
                })
                reported = record.get("report", {}).get("settings", {})
                if (record["constant_setting"] is None
                        and reported.get("USE") == "Temp"
                        and isinstance(reported.get("TMP"), list)):
                    record["constant_setting"] = copy.deepcopy(reported["TMP"])
                pending_tmp = record.get("pending", {}).get("TMP")
                if (record["constant_setting"] is None and isinstance(pending_tmp, list)
                        and len(pending_tmp) == 2 and pending_tmp[0] == "Off"
                        and number(pending_tmp[1]) is not None):
                    record["constant_setting"] = copy.deepcopy(pending_tmp)
                legacy_schedule_report = (
                    legacy_constant_state
                    and reported.get("USE") in ("GraphD", "GraphW")
                )
                if (legacy_schedule_report and isinstance(pending_tmp, list)
                        and len(pending_tmp) == 2 and pending_tmp[0] == "Off"
                        and number(pending_tmp[1]) is not None):
                    record["constant_setting"] = copy.deepcopy(pending_tmp)
                if legacy_schedule_report and record["pending"].pop("TMP", None) is not None:
                    record["pending_since"].pop("TMP", None)
                    if not record["pending"]:
                        record.update(command_state="error",
                                      command_error="Legacy TMP upload cannot be confirmed in schedule mode")
                    self._refresh_queued_at(record)
                if set(self._new(serial)) - record.keys():
                    raise ValueError(f"Incomplete persisted record for {serial}")
        except Exception:
            self.process_lock.close()
            raise
        self.timeout = confirmation_timeout

    def close(self):
        self.process_lock.close()

    def _read(self, serial):
        return copy.deepcopy(self.records[serial])

    def _write(self, record):
        records = {**self.records, record["serial"]: record}
        payload = json.dumps(records, allow_nan=False, indent=2)
        descriptor, name = tempfile.mkstemp(prefix=".tenko-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self.records = copy.deepcopy(records)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _new(self, serial):
        return {"serial": serial, "report": {}, "last_report": None, "status": None,
                "last_status": None, "pending": {}, "sent_at": None, "queued_at": None,
                "attempts": 0, "command_state": "idle", "command_error": None,
                "draft": {}, "draft_revision": 0, "revision": 0, "schedule_editor": new_editor(),
                "status_report": {}, "constant_setting": None, "pending_since": {}}

    def get(self, serial):
        with self.lock:
            return self._read(serial)

    def all(self):
        with self.lock:
            return [copy.deepcopy(self.records[key]) for key in sorted(self.records)]

    def report(self, raw):
        report = parse_report(raw)
        now = time.time()
        with self.lock:
            try:
                record = self._read(raw["sn"])
            except KeyError:
                record = self._new(raw["sn"])
            record.update(report=report, last_report=now)
            record["revision"] += 1
            reported_tmp = report["settings"].get("TMP")
            if report["settings"].get("USE") == "Temp" and isinstance(reported_tmp, list):
                if record["constant_setting"] is None or "TMP" not in record["pending"]:
                    # Preserve the saved target when firmware substitutes its inactive 6.9 C sentinel.
                    if record["constant_setting"] is None or reported_tmp != ["Off", 6.9]:
                        record["constant_setting"] = copy.deepcopy(reported_tmp)
            if report["stage_conflict"]:
                LOG.warning("%s: ST1/ST2 disagree with STU; using STU", raw["sn"])
            if report["parse_errors"]:
                LOG.warning("%s: malformed report: %s", raw["sn"], report["parse_errors"])
                self._write(record)
                return record, "nochange"
            if record["pending"] and record["sent_at"] is not None:
                confirmed = []
                for key, value in record["pending"].items():
                    reported = report["settings"].get(key)
                    if key == "TMP":
                        if report["settings"].get("USE") != "Temp" or not isinstance(reported, list):
                            continue
                        # The boiler reports the effective schedule temperature outside Temp
                        # mode. With the constant thermostat off, only its mode is observable.
                        matches = (reported[0] == "Off" if value[0] == "Off" else reported == value)
                    else:
                        matches = reported == value
                    if matches:
                        confirmed.append(key)
                for key in confirmed:
                    was_draft = record["draft"].get(key) == record["pending"][key]
                    del record["pending"][key]
                    record["pending_since"].pop(key, None)
                    if was_draft:
                        del record["draft"][key]
                        record["draft_revision"] += 1
                if not record["pending"] and confirmed:
                    record.update(command_state="applied", command_error=None,
                                  sent_at=None, queued_at=None)
                elif confirmed:
                    record.update(command_state="pending", command_error=None)
                self._refresh_queued_at(record)
            response = "nochange"
            if record["pending"]:
                complete = {**report["settings"], **record["pending"]}
                constant_setting = record["pending"].get("TMP", record["constant_setting"])
                if constant_setting is None:
                    record.update(command_state="error",
                                  command_error="Set a constant temperature target before uploading settings")
                    self._write(record)
                    return record, "nochange"
                complete["TMP"] = constant_setting
                try:
                    validate_pending_temperature(
                        {"TMP": record["constant_setting"]}, record["pending"])
                    response = serialize(complete)
                    record["attempts"] += 1
                    if record["sent_at"] is None:
                        record["sent_at"] = now
                    expired_key = self._expired_key(record, now)
                    record["command_state"] = "error" if expired_key else "pending"
                    record["command_error"] = (
                        self._timeout_message(record, expired_key) if expired_key else None)
                except (ValueError, TypeError, OverflowError) as exc:
                    record.update(command_state="error", command_error=str(exc))
                    LOG.warning("%s: settings blocked: %s", raw["sn"], exc)
            self._write(record)
            return record, response

    def status(self, raw, method=None, path=None):
        if "status" not in raw or len(raw["status"]) > 256:
            raise ValueError("Missing or oversized status")
        with self.lock:
            try:
                record = self._read(raw["sn"])
            except KeyError:
                record = self._new(raw["sn"])
            record.update(status=raw["status"], last_status=time.time(),
                          status_report={"raw": raw, "method": method, "path": path})
            self._write(record)
            return record

    def command(self, serial, patch, revision=None):
        if not isinstance(patch, dict) or not patch:
            raise ValueError("Expected a nonempty settings object")
        normalized = {k: validate_setting(k, v) for k, v in patch.items()}
        with self.lock:
            record = self._read(serial)
            if revision is not None and revision != record["revision"]:
                raise ValueError("Report/command changed; reload before applying")
            return self._queue(record, normalized)

    def _queue(self, record, patch):
        """Queue a validated patch, preserving unchanged reported components."""
        if not record["report"] or record["report"]["parse_errors"]:
            raise ValueError("A valid parameter report is required before setting controls")
        now = time.time()
        pending = {**record["pending"], **patch}
        if "TMP" in patch:
            record["constant_setting"] = copy.deepcopy(patch["TMP"])
        mode = pending.get("USE", record["report"]["settings"].get("USE"))
        if mode in ("GraphD", "GraphW") and "USE" in patch and "TMP" not in patch:
            pending.pop("TMP", None)
            record["pending_since"].pop("TMP", None)
        if mode == "Temp" and "USE" in patch and "TMP" not in pending:
            if record["constant_setting"] is None:
                raise ValueError("Set a constant temperature target before selecting Constant temperature")
            pending["TMP"] = copy.deepcopy(record["constant_setting"])
        constant_setting = pending.get("TMP", record["constant_setting"])
        if constant_setting is None:
            raise ValueError("Set a constant temperature target before uploading settings")
        candidate = {**record["report"]["settings"], **record["pending"], **patch,
                     "TMP": constant_setting}
        validate_pending_temperature({"TMP": record["constant_setting"]}, pending)
        serialize(candidate)
        for key, value in pending.items():
            if record["pending"].get(key) != value or key not in record["pending_since"]:
                record["pending_since"][key] = now
        record["pending"] = pending
        self._refresh_queued_at(record)
        record.update(sent_at=None, attempts=0,
                      command_state="pending" if pending else "applied", command_error=None)
        record["revision"] += 1
        self._write(record)
        return record

    @staticmethod
    def _refresh_queued_at(record):
        record["queued_at"] = min(record["pending_since"].values(), default=None)

    def _expired_key(self, record, now):
        return next((key for key, queued_at in record["pending_since"].items()
                     if now - queued_at > self.timeout), None)

    def _timeout_message(self, record, key):
        requested = record["pending"].get(key)
        reported = record.get("report", {}).get("settings", {}).get(key)
        return (f"Confirmation timed out for {key}: requested {requested!r}, "
                f"last reported {reported!r}; settings remain pending and will be retried")

    def component_command(self, serial, key, index, value):
        with self.lock:
            record = self._read(serial)
            if key == "TMP":
                settings = record["pending"].get("TMP", record["constant_setting"])
                if not isinstance(settings, list) or len(settings) != 2:
                    if index != 1:
                        raise ValueError("Set a constant temperature target before choosing a thermostat mode")
                    settings = ["Off", None]
                updated = copy.deepcopy(settings)
                updated[index] = value
                return self.command(serial, {key: updated})
            settings = {**record.get("report", {}).get("settings", {}), **record["pending"]}
            if index is None:
                updated = value
            else:
                if key not in settings:
                    raise ValueError(f"No unambiguous reported {key}; submit the complete tuple")
                updated = copy.deepcopy(settings[key])
                updated[index] = value
            return self.command(serial, {key: updated})

    def thermostat_command(self, serial, command, value):
        key, index = THERMOSTAT_COMMANDS[command]
        if index != 0:
            return self.component_command(serial, key, index, value)
        enabled_mode = "heat" if key == "TMP" else "heat_cool"
        if value not in ("off", enabled_mode):
            raise ValueError(f"Thermostat mode must be off or {enabled_mode}")
        with self.lock:
            record = self._read(serial)
            settings = {**record.get("report", {}).get("settings", {}), **record["pending"]}
            if key == "TMP":
                constant_setting = record["pending"].get("TMP", record["constant_setting"])
                if isinstance(constant_setting, list):
                    settings[key] = constant_setting
                elif record.get("report", {}).get("settings", {}).get("USE") != "Temp":
                    raise ValueError("Set a constant temperature target before choosing a thermostat mode")
            if key not in settings:
                raise ValueError(f"No reported {key}; wait for a valid parameter report")
            updated = copy.deepcopy(settings[key])
            updated[0] = "Off" if value == "off" else "On"
            original_target = None
            if key == "TMP" and value == "heat":
                original_target = number(updated[1])
                if original_target is None:
                    raise ValueError("TMP: a numeric target is required before enabling Heat")
                updated[1] = round(min(30, max(7, original_target)), 1)
            if value != "off":
                updated = validate_setting(key, updated)
            result = self._queue(record, {key: updated})
            if original_target is not None and original_target != updated[1]:
                LOG.warning("%s: enabling Heat queued corrected TMP target %s -> %s C",
                            serial, original_target, updated[1])
            return result

    def editor_command(self, serial, action, payload):
        with self.lock:
            record = self._read(serial)
            patch = edit(record, action, payload)
            if patch:
                return self._queue(record, patch)
            self._write(record)
            return record

    def command_error(self, serial, message):
        with self.lock:
            record = self._read(serial)
            record.update(command_error=message, command_state="error")
            self._write(record)
            LOG.warning("%s: command rejected: %s", serial, message)
            return record

    def expire(self):
        with self.lock:
            changed = []
            for serial in self.records:
                record = self._read(serial)
                expired_key = self._expired_key(record, time.time())
                if record["pending"] and expired_key and record["command_state"] != "error":
                    record.update(command_state="error",
                                  command_error=self._timeout_message(record, expired_key))
                    self._write(record)
                    changed.append(serial)
            return changed
