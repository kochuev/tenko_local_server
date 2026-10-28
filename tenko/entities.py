from dataclasses import dataclass
from datetime import datetime, timezone

from .protocol import SCHEDULES, number
from .schedule_editor import DAY_NAMES, editor_state


@dataclass(frozen=True)
class Entity:
    key: str
    name: str
    kind: str = "sensor"
    unit: str | None = None
    device_class: str | None = None
    measurement: bool = False
    category: str | None = "diagnostic"
    setting: str | None = None
    index: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float = 1
    action: str | None = None
    options: tuple[str, ...] = ()


ENTITIES = [
    Entity("air", "Air temperature", unit="°C", device_class="temperature", measurement=True, category=None),
    Entity("flow", "Flow temperature", unit="°C", device_class="temperature", measurement=True, category=None),
    Entity("return", "Return temperature", unit="°C", device_class="temperature", measurement=True, category=None),
    Entity("pmt_temperature", "PMT reported temperature", unit="°C", device_class="temperature", measurement=True),
    Entity("pressure", "Pressure", unit="bar", device_class="pressure", measurement=True, category=None),
    Entity("capacity", "Nominal capacity (not current draw)", unit="kW"),
    Entity("stage_1_capacity", "Stage 1 rated capacity", unit="kW"),
    Entity("stage_2_capacity", "Stage 2 rated capacity", unit="kW"),
]
for key, name in (
    ("pump", "Pump operating state"), ("ten_1", "TEN 1 operating state"),
    ("ten_2", "TEN 2 operating state"), ("heating", "Modulation heating state"),
    ("pmt_state", "PMT operating state"), ("frost", "AF-5 phase"),
    ("error", "Raw boiler error"), ("sensor_type", "Air sensor type"),
    ("clock", "Boiler clock (timezone unknown)"), ("weekday", "Raw weekday code"),
    ("raw_status", "Separate raw status"), ("serial", "Serial number"),
    ("firmware", "Firmware"), ("command_state", "Settings upload status"),
    ("command_error", "Settings command error"), ("stage_conflict", "Manual-stage duplicate consistency"),
    ("raw_fields", "Raw protocol diagnostics"), ("parse_errors", "Report parsing"),
):
    ENTITIES.append(Entity(key, name))
for key, name in (
    ("ten_1_on", "TEN 1 heating"), ("ten_2_on", "TEN 2 heating"),
    ("heating_on", "Modulation heating"), ("status_heating", "Separate heating (assumed 0/1)"),
):
    ENTITIES.append(Entity(key, name, kind="binary_sensor", device_class="heat", category=None))
ENTITIES.extend([
    Entity("active_elements", "Active elements"),
    Entity("total_elements", "Total elements"),
    Entity("last_report", "Last parameter report", device_class="timestamp"),
    Entity("last_status", "Last separate status report", device_class="timestamp"),
    Entity("statistics_days", "Boiler statistics period", unit="d"),
    Entity("period_amount", "Boiler period consumption (presumed kWh)", unit="kWh"),
    Entity("day_amount", "Boiler 1-day consumption (presumed kWh)", unit="kWh"),
    Entity("week_amount", "Boiler 7-day consumption (presumed kWh)", unit="kWh"),
])
for i in range(12):
    ENTITIES.append(Entity(f"month_{i}", f"Boiler monthly index {i} (presumed kWh)", unit="kWh"))
for schedule in SCHEDULES:
    ENTITIES.append(Entity(f"schedule_{schedule}", f"{schedule} stored schedule"))


def control(key, name, setting, index=None, kind="number", low=None, high=None, step=1, unit=None):
    ENTITIES.append(Entity(key, name, kind=kind, unit=unit, category="config", setting=setting,
                           index=index, minimum=low, maximum=high, step=step))


control("mode", "Control mode", "USE", kind="select")
control("constant_enabled", "Constant temperature enabled", "TMP", 0, "switch")
control("constant_target", "Stored air target", "TMP", 1, low=7, high=40, step=.1, unit="°C")
for prefix, field in (("flow", "FI"), ("return", "RE")):
    control(f"{prefix}_cutoff", f"{prefix.title()} cutoff", field, 0, low=10, high=75, unit="°C")
    control(f"{prefix}_hysteresis", f"{prefix.title()} restart drop", field, 1, low=1, high=9, unit="°C")
control("pmt_enabled", "PMT preset enabled", "PMT", 0, "switch")
control("pmt_min", "PMT restart threshold", "PMT", 1, low=6, high=15, unit="°C")
control("pmt_max", "PMT stop threshold", "PMT", 2, low=7, high=17, unit="°C")
control("modulation", "Automatic modulation enabled", "MOD", kind="switch")
control("manual_1", "Manual stage 1 enable (modulation off only)", "STU", 0, "switch")
control("manual_2", "Manual stage 2 enable (modulation off only)", "STU", 1, "switch")
control("pump_start", "Pump lead-in delay", "pNA", 0, low=1, high=15, unit="min")
control("pump_stop", "Pump run-on delay", "pNA", 1, low=1, high=15, unit="min")
ENTITIES.extend([
    Entity("editor_day", "Schedule editor day", kind="select", category="config",
           action="editor_day", options=tuple(DAY_NAMES.values())),
    Entity("editor_slot", "Schedule editor slot", kind="select", category="config",
           action="editor_slot", options=tuple(str(i) for i in range(1, 11))),
    Entity("editor_hour", "Schedule draft hour", kind="number", category="config",
           action="editor_hour", minimum=0, maximum=23),
    Entity("editor_target", "Schedule draft target (0=OFF)", kind="number", unit="°C", category="config",
           action="editor_target", minimum=0, maximum=40, step=.1),
    Entity("editor_off", "Schedule draft OFF", kind="switch", category="config", action="editor_off"),
    Entity("editor_copy_to", "Schedule copy destination", kind="select", category="config",
           action="editor_copy_to", options=tuple(DAY_NAMES.values())),
    Entity("stage_resolution_source", "Manual-stage conflict source", kind="select", category="config",
           action="stage_resolution_source", options=("ST1/ST2", "STU")),
])
for key, name in (
    ("editor_apply_day", "Apply selected schedule draft"),
    ("editor_apply_all", "Apply all schedule drafts"),
    ("editor_discard_day", "Discard selected schedule draft"),
    ("editor_discard_all", "Discard all drafts"),
    ("editor_copy_day", "Copy selected schedule to destination"),
    ("editor_copy_week", "Copy selected schedule to whole week"),
    ("cancel_pending", "Cancel pending settings upload"),
    ("resolve_stages", "Resolve manual-stage conflict using selected source"),
):
    ENTITIES.append(Entity(key, name, kind="button", category="config", action=key))
for key, name in (
    ("editor_layer", "Schedule editor layer"),
    ("editor_validation", "Schedule editor validation"),
    ("editor_day_summary", "Schedule editor day summary"),
):
    ENTITIES.append(Entity(key, name))
ENTITIES.extend([
    Entity("editor_reported_hour", "Schedule selected reported hour"),
    Entity("editor_reported_target", "Schedule selected reported target", unit="°C"),
])
BY_KEY = {entity.key: entity for entity in ENTITIES}


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None


def state(record):
    report = record.get("report", {})
    decoded = report.get("decoded", {})
    settings = report.get("settings", {})

    def at(key, i):
        value = decoded.get(key)
        return value[i] if isinstance(value, list) and len(value) > i else None

    def binary(value):
        return value if value in ("On", "Off") else None

    values = {
        "air": number(decoded.get("TA")), "flow": number(decoded.get("TF")),
        "return": number(decoded.get("TR")), "pmt_temperature": number(at("PM", 1)),
        "pressure": number(decoded.get("Davl")), "capacity": number(decoded.get("Pow")),
        "stage_1_capacity": number(at("ST1", 1)), "stage_2_capacity": number(at("ST2", 1)),
        "pump": decoded.get("NA"), "ten_1": decoded.get("TEN1"), "ten_2": decoded.get("TEN2"),
        "heating": at("MOD", 1), "active_elements": number(at("MOD", 2)),
        "total_elements": number(at("MOD", 3)), "pmt_state": at("PM", 0),
        "frost": {"Off": "standby", "On": "checking"}.get(decoded.get("AF"), decoded.get("AF")),
        "error": decoded.get("Err"), "sensor_type": decoded.get("Sens"),
        "firmware": decoded.get("VER"), "serial": record["serial"],
        "clock": ",".join(str(v) for v in decoded["TIM"]) if decoded.get("TIM") else None,
        "weekday": at("TIM", 2), "raw_status": record["status"],
        "status_heating": {"0": "Off", "1": "On"}.get(record["status"]),
        "ten_1_on": binary(decoded.get("TEN1")), "ten_2_on": binary(decoded.get("TEN2")),
        "heating_on": binary(at("MOD", 1)), "last_report": timestamp(record["last_report"]),
        "last_status": timestamp(record["last_status"]), "command_state": record["command_state"],
        "command_error": record["command_error"] or "none",
        "stage_conflict": {True: "conflict", False: "consistent", None: "not verified"}[report.get("stage_conflict")],
        "raw_fields": "available" if report else None,
        "parse_errors": "error" if report.get("parse_errors") else "ok",
        "statistics_days": number(at("STA", 0)), "period_amount": number(at("STA", 1)),
        "day_amount": number(decoded.get("StD")), "week_amount": number(decoded.get("StW")),
    }
    for i in range(12):
        values[f"month_{i}"] = number(at("YSt", i))
    for schedule in SCHEDULES:
        points = settings.get(schedule)
        values[f"schedule_{schedule}"] = f"{len(points)} stored points" if points else None
    for entity in ENTITIES:
        if entity.setting:
            value = settings.get(entity.setting)
            if entity.index is not None:
                value = value[entity.index] if isinstance(value, list) else None
            if entity.kind == "number":
                value = number(value)
            elif entity.kind == "switch" and value not in ("On", "Off"):
                value = None
            elif entity.kind == "select" and value not in ("Temp", "GraphD", "GraphW"):
                value = None
            values[entity.key] = value
    values.update(editor_state(record))
    return values


def discovery(entity, serial, firmware, config):
    base = f"{config.mqtt_prefix}/{serial}"
    availability = [
        {"topic": f"{config.mqtt_prefix}/bridge/availability"},
        {"topic": f"{base}/availability"},
        {"topic": f"{base}/state",
         "value_template": "{{ 'online' if value_json." + entity.key + " is not none else 'offline' }}"},
    ]
    if entity.key in {"raw_status", "status_heating", "last_status"}:
        availability.append({"topic": f"{base}/status_availability"})
    payload = {
        "name": entity.name, "unique_id": f"tenko_{serial}_{entity.key}",
        "state_topic": f"{base}/state",
        "value_template": "{{ value_json." + entity.key + " }}",
        "availability": availability, "availability_mode": "all",
        "device": {"identifiers": [f"tenko_{serial}"], "name": "Tenko Boiler",
                   "manufacturer": "Tenko", "model": "Premium / Premium Plus",
                   "serial_number": serial, "sw_version": firmware or "unknown"},
        "origin": {"name": "Tenko local", "sw_version": "1.0.0"},
    }
    if entity.unit:
        payload["unit_of_measurement"] = entity.unit
    if entity.device_class:
        payload["device_class"] = entity.device_class
    if entity.measurement:
        payload["state_class"] = "measurement"
    if entity.category:
        payload["entity_category"] = entity.category
    if entity.setting or entity.action:
        payload.update(command_topic=f"{base}/command/{entity.key}", optimistic=False)
    if entity.kind == "button":
        payload.pop("state_topic")
        payload.pop("value_template")
        payload.pop("optimistic")
        payload["payload_press"] = "PRESS"
    if entity.kind in ("switch", "binary_sensor"):
        payload.update(payload_on="On", payload_off="Off")
    if entity.kind == "number":
        payload.update(min=entity.minimum, max=entity.maximum, step=entity.step, mode="box")
    if entity.kind == "select":
        payload["options"] = list(entity.options) if entity.options else ["Temp", "GraphD", "GraphW"]
        payload.pop("optimistic", None)
    if entity.key.startswith("schedule_"):
        schedule = entity.key.removeprefix("schedule_")
        payload.update(json_attributes_topic=f"{base}/schedules/{schedule}")
    if entity.key in {"raw_fields", "parse_errors", "stage_conflict", "command_state", "raw_status"}:
        payload["json_attributes_topic"] = f"{base}/diagnostics"
    if entity.key in {"editor_layer", "editor_validation", "editor_day_summary"}:
        payload["json_attributes_topic"] = f"{base}/schedule_editor"
    return payload
