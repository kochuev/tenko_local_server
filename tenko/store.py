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
                record.setdefault("schedule_editor", new_editor())
                record.setdefault("status_report", {})
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
                "status_report": {}}

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
            if report["stage_conflict"]:
                LOG.warning("%s: ST1/ST2 disagree with STU; using STU", raw["sn"])
            if report["parse_errors"]:
                LOG.warning("%s: malformed report: %s", raw["sn"], report["parse_errors"])
                self._write(record)
                return record, "nochange"
            if record["pending"] and record["sent_at"] is not None:
                if all(report["settings"].get(k) == v for k, v in record["pending"].items()):
                    confirmed = [k for k, v in record["pending"].items() if record["draft"].get(k) == v]
                    for key in confirmed:
                        del record["draft"][key]
                    if confirmed:
                        record["draft_revision"] += 1
                    record.update(pending={}, command_state="applied", command_error=None,
                                  sent_at=None, queued_at=None)
            response = "nochange"
            if record["pending"]:
                complete = {**report["settings"], **record["pending"]}
                try:
                    validate_pending_temperature(report["settings"], record["pending"])
                    response = serialize(complete)
                    record["attempts"] += 1
                    if record["sent_at"] is None:
                        record["sent_at"] = now
                    expired = now - record["queued_at"] > self.timeout
                    record["command_state"] = "error" if expired else "pending"
                    record["command_error"] = (
                        "Confirmation timed out; settings remain pending and will be retried" if expired else None)
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
        candidate = {**record["report"]["settings"], **record["pending"], **patch}
        validate_pending_temperature(record["report"]["settings"], {**record["pending"], **patch})
        serialize(candidate)
        record.update(pending={**record["pending"], **patch}, sent_at=None,
                      queued_at=time.time(), attempts=0, command_state="pending", command_error=None)
        record["revision"] += 1
        self._write(record)
        return record

    def component_command(self, serial, key, index, value):
        with self.lock:
            record = self._read(serial)
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
                if (record["pending"] and record["queued_at"]
                        and time.time() - record["queued_at"] > self.timeout
                        and record["command_state"] != "error"):
                    record.update(command_state="error",
                                  command_error="Confirmation timed out; settings remain pending and will be retried")
                    self._write(record)
                    changed.append(serial)
            return changed
