from dataclasses import dataclass
from datetime import date, datetime, timezone

from .protocol import SCHEDULES, number
from .schedule_editor import DAY_LABELS, POINT_CONTROLS, editor_state

CONTROL_MODES = {"Whole week": "GraphD", "Individual days": "GraphW", "Constant temperature": "Temp"}


@dataclass(frozen=True)
class Entity:
    key: str
    name: str
    kind: str = "sensor"
    unit: str | None = None
    device_class: str | None = None
    measurement: bool = False
    category: str | None = None
    setting: str | None = None
    index: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float = 1
    action: str | None = None
    options: tuple[str, ...] = ()
    debug_only: bool = False
    energy_device: bool = False


ENTITIES = [
    Entity("air", "Air temperature", unit="°C", device_class="temperature", measurement=True, category=None),
    Entity("flow", "Flow temperature", unit="°C", device_class="temperature", measurement=True, category=None),
    Entity("return", "Return temperature", unit="°C", device_class="temperature", measurement=True, category=None),
    Entity("pressure", "Pressure", unit="bar", device_class="pressure", measurement=True, category=None),
    Entity("boiler_date", "Boiler Date", device_class="date"),
    Entity("modulated_power", "Modulated Power", unit="%", measurement=True),
    Entity("period_amount", "Energy", unit="kWh", device_class="energy", energy_device=True),
    Entity("constant_thermostat", "Constant temperature", kind="climate"),
]
for key, name in (
    ("pump", "Pump"), ("frost", "AF-5"), ("error", "Error Code"),
    ("clock", "Boiler clock"), ("boiler_weekday", "Boiler Weekday"),
    ("command_state", "Settings upload status"),
    ("command_error", "Settings command error"), ("sensor_type", "Air sensor type"),
):
    ENTITIES.append(Entity(key, name))
for key, name, unit in (
    ("capacity", "Nominal power", "kW"),
    ("stage_1_capacity", "Stage 1 nominal power", "kW"),
    ("stage_2_capacity", "Stage 2 nominal power", "kW"),
):
    ENTITIES.append(Entity(key, name, unit=unit))
for key, name, unit in (
    ("raw_status", "Separate raw status", None),
    ("raw_fields", "Raw protocol diagnostics", None), ("parse_errors", "Report parsing", None),
):
    ENTITIES.append(Entity(key, name, unit=unit, category="diagnostic", debug_only=True))
for key, name, unit in (
    ("statistics_days", "Boiler statistics period", "d"),
    ("day_amount", "Boiler 1-day consumption", "kWh"),
    ("week_amount", "Boiler 7-day consumption", "kWh"),
):
    ENTITIES.append(Entity(key, name, unit=unit, category="diagnostic",
                           debug_only=True, energy_device=True))
for key, name in (
    ("ten_1_on", "Heating element 1"), ("ten_2_on", "Heating element 2"),
):
    ENTITIES.append(Entity(key, name, kind="binary_sensor", category=None))
ENTITIES.extend([
    Entity("last_report", "Last parameter report", device_class="timestamp",
           category="diagnostic", debug_only=True),
    Entity("last_status", "Last separate status report", device_class="timestamp",
           category="diagnostic", debug_only=True),
])
for i in range(12):
    ENTITIES.append(Entity(f"month_{i}", f"Boiler monthly index {i}", unit="kWh",
                           category="diagnostic", debug_only=True, energy_device=True))


def control(key, name, setting, index=None, kind="number", low=None, high=None, step=1, unit=None):
    ENTITIES.append(Entity(key, name, kind=kind, unit=unit, setting=setting,
                           index=index, minimum=low, maximum=high, step=step))


ENTITIES.append(Entity("mode", "Control mode", kind="select",
                       setting="USE", options=tuple(CONTROL_MODES)))
control("pmt_enabled", "Maintaining Minimum Temperature (MMT)", "PMT", 0, "switch")
control("pmt_min", "MMT Min Temperature", "PMT", 1, low=6, high=15, unit="°C")
control("pmt_max", "MMT Max Temperature", "PMT", 2, low=7, high=17, unit="°C")
for prefix, field in (("flow", "FI"), ("return", "RE")):
    control(f"{prefix}_cutoff", f"{prefix.title()} cutoff", field, 0, low=10, high=75, unit="°C")
    control(f"{prefix}_hysteresis", f"{prefix.title()} restart drop", field, 1, low=1, high=9, unit="°C")
control("modulation", "Power Modulation Mode", "MOD", kind="switch")
control("manual_1", "Stage 1 (mod only)", "STU", 0, "switch")
control("manual_2", "Stage 2 (mod only)", "STU", 1, "switch")
control("pump_start", "Pump Pre-Circulation Time", "pNA", 0, low=1, high=15, unit="min")
control("pump_stop", "Pump Post-Run Time", "pNA", 1, low=1, high=15, unit="min")
for key, (day, slot, component) in POINT_CONTROLS.items():
    field = "hour" if component == 0 else "target (0=OFF)"
    ENTITIES.append(Entity(
        key, f"{DAY_LABELS[day]} slot {slot + 1:02d} {field}",
        kind="select" if component == 0 else "number", category="config",
        action=key, minimum=0, maximum=23 if component == 0 else 40,
        step=1 if component == 0 else .1, unit=None if component == 0 else "°C",
        options=tuple(str(hour) for hour in range(24)) if component == 0 else ()))
for day in SCHEDULES:
    ENTITIES.append(Entity(f"schedule_{day}_validation", f"Schedule {DAY_LABELS[day]}",
                           category="diagnostic"))
BY_KEY = {entity.key: entity for entity in ENTITIES}
RECREATE_ENTITIES = (
    "pump", "frost", "error", "clock", "sensor_type",
    "capacity", "stage_1_capacity", "stage_2_capacity",
) + tuple(
    entity.key for entity in ENTITIES
    if entity.energy_device or (entity.setting and entity.key not in POINT_CONTROLS)
) + tuple(f"schedule_{day}_validation" for day in SCHEDULES)
REMOVED_ENTITIES = (
    ("select", "schedule_mode"),
    ("select", "editor_day"), ("select", "editor_slot"), ("select", "editor_copy_to"),
    ("number", "editor_hour"), ("number", "editor_target"), ("switch", "editor_off"),
    ("button", "editor_apply_day"), ("button", "editor_discard_day"),
    ("button", "editor_copy_day"), ("button", "editor_copy_week"), ("button", "cancel_pending"),
    ("sensor", "editor_layer"), ("sensor", "editor_validation"), ("sensor", "editor_day_summary"),
    ("sensor", "editor_reported_hour"), ("sensor", "editor_reported_target"),
    ("button", "editor_apply_all"), ("button", "editor_discard_all"),
    ("binary_sensor", "status_heating"),
    ("binary_sensor", "heating_on"), ("sensor", "heating"), ("sensor", "ten_1"), ("sensor", "ten_2"),
    ("sensor", "pmt_state"), ("sensor", "pmt_temperature"),
    ("sensor", "serial"), ("sensor", "firmware"),
    ("switch", "constant_enabled"), ("number", "constant_target"),
    ("climate", "minimum_thermostat"),
    ("select", "stage_resolution_source"), ("button", "resolve_stages"),
    ("sensor", "stage_conflict"), ("sensor", "weekday"),
    ("sensor", "active_elements"), ("sensor", "total_elements"),
) + tuple(
    ("number", key) for key, (_, _, component) in POINT_CONTROLS.items() if component == 0
) + tuple(
    ("button", f"schedule_{day}_{action}") for day in SCHEDULES for action in ("apply", "discard")
) + tuple(
    ("sensor", key) for day in SCHEDULES for key in (f"schedule_{day}", f"schedule_{day}_layer"))


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None


def enabled_entities(config):
    return [entity for entity in ENTITIES if not entity.debug_only or config.log_level.upper() == "DEBUG"]


def modulated_power(decoded):
    values = decoded.get("MOD")
    if not isinstance(values, list) or len(values) != 4 or values[0] != "On":
        return None
    if values[1] == "Off":
        return 0
    active, total = number(values[2]), number(values[3])
    if (values[1] != "On" or active is None or total is None or not active.is_integer()
            or not total.is_integer() or not 0 <= active <= total or total <= 0):
        return None
    return int(active) * 100 // int(total)


def state(record, config=None):
    report = record.get("report", {})
    decoded = report.get("decoded", {})
    settings = report.get("settings", {})

    def at(key, i):
        value = decoded.get(key)
        return value[i] if isinstance(value, list) and len(value) > i else None

    def binary(value):
        return value if value in ("On", "Off") else None

    current = {**settings, **record["pending"]}
    constant_setting = record.get("pending", {}).get("TMP", record.get("constant_setting"))
    if constant_setting is None and settings.get("USE") == "Temp":
        constant_setting = settings.get("TMP")
    if constant_setting is None:
        current.pop("TMP", None)
    else:
        current["TMP"] = constant_setting
    def component(key, index):
        value = current.get(key)
        return value[index] if isinstance(value, list) and len(value) > index else None

    hour, minute = number(at("TIM", 0)), number(at("TIM", 1))
    clock = (f"{int(hour):02d}:{int(minute):02d}"
             if hour is not None and minute is not None and hour.is_integer()
             and minute.is_integer() and 0 <= hour <= 23 and 0 <= minute <= 59 else None)
    day, month, year = (number(at("TIM", i)) for i in (3, 4, 5))
    boiler_date = None
    if (all(value is not None and value.is_integer() for value in (day, month, year))
            and 1 <= day <= 31 and 1 <= month <= 12 and 0 <= year <= 99):
        try:
            boiler_date = date(2000 + int(year), int(month), int(day)).isoformat()
        except ValueError:
            boiler_date = None
    weekday = number(at("TIM", 2))
    boiler_weekday = (DAY_LABELS[SCHEDULES[int(weekday)]]
                      if weekday is not None and weekday.is_integer() and 1 <= weekday <= 7 else None)
    constant_mode = {"On": "heat", "Off": "off"}.get(component("TMP", 0))
    constant_target = number(component("TMP", 1))
    if (constant_target is not None and
            (not 7 <= constant_target <= 30 or abs(constant_target * 10 - round(constant_target * 10)) > 1e-7)):
        constant_target = None
    values = {
        "air": number(decoded.get("TA")), "flow": number(decoded.get("TF")),
        "return": number(decoded.get("TR")), "pmt_temperature": number(at("PM", 1)),
        "pressure": number(decoded.get("Davl")), "capacity": number(decoded.get("Pow")),
        "stage_1_capacity": number(at("ST1", 1)), "stage_2_capacity": number(at("ST2", 1)),
        "pump": decoded.get("NA"), "ten_1": decoded.get("TEN1"), "ten_2": decoded.get("TEN2"),
        "heating": at("MOD", 1), "pmt_state": at("PM", 0),
        "frost": {"Off": "standby", "On": "checking"}.get(decoded.get("AF"), decoded.get("AF")),
        "error": decoded.get("Err"), "sensor_type": decoded.get("Sens"),
        "firmware": decoded.get("VER"), "serial": record["serial"],
        "clock": clock, "boiler_date": boiler_date, "boiler_weekday": boiler_weekday,
        "raw_status": record["status"],
        "ten_1_on": binary(decoded.get("TEN1")), "ten_2_on": binary(decoded.get("TEN2")),
        "last_report": timestamp(record["last_report"]),
        "last_status": timestamp(record["last_status"]), "command_state": record["command_state"],
        "command_error": record["command_error"] or "none",
        "raw_fields": "available" if report else None,
        "parse_errors": "error" if report.get("parse_errors") else "ok",
        "statistics_days": number(at("STA", 0)), "period_amount": number(at("STA", 1)),
        "day_amount": number(decoded.get("StD")), "week_amount": number(decoded.get("StW")),
        "modulated_power": modulated_power(decoded),
        "constant_thermostat": constant_mode, "constant_mode": constant_mode,
        "constant_enabled": component("TMP", 0), "constant_target": constant_target,
        "pmt_min": number(component("PMT", 1)), "pmt_max": number(component("PMT", 2)),
    }
    for i in range(12):
        values[f"month_{i}"] = number(at("YSt", i))
    for entity in ENTITIES:
        if entity.setting:
            value = record["pending"].get(entity.setting, settings.get(entity.setting))
            if entity.index is not None:
                value = value[entity.index] if isinstance(value, list) else None
            if entity.kind == "number":
                value = number(value)
            elif entity.kind == "switch" and value not in ("On", "Off"):
                value = None
            elif entity.key == "mode":
                value = {wire: label for label, wire in CONTROL_MODES.items()}.get(value)
            values[entity.key] = value
    values.update(editor_state(record))
    if config is not None:
        keys = {entity.key for entity in enabled_entities(config)}
        keys.update({"constant_mode", "constant_target"})
        values = {key: value for key, value in values.items() if key in keys}
    return values


def discovery(entity, serial, firmware, config):
    base = f"{config.mqtt_prefix}/{serial}"
    status_entity = entity.key in {"raw_status", "last_status"}
    availability = [
        {"topic": f"{config.mqtt_prefix}/bridge/availability"},
        {"topic": f"{base}/{'status_availability' if status_entity else 'availability'}"},
        {"topic": f"{base}/state",
         "value_template": "{{ 'online' if value_json." + entity.key + " is not none else 'offline' }}"},
    ]
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
    if entity.energy_device:
        payload["device"] = {
            "identifiers": [f"tenko_{serial}_energy_meter"], "name": "TENKO Boiler Energy Meter",
            "manufacturer": "Tenko", "via_device": f"tenko_{serial}", "serial_number": serial,
        }
    if entity.key == "modulated_power":
        payload["availability"] = availability[:2]
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
        payload["options"] = list(entity.options)
        payload.pop("optimistic", None)
    if entity.kind == "climate":
        payload.pop("state_topic")
        payload.pop("value_template")
        payload.update(
            modes=["off", "heat"],
            mode_command_topic=f"{base}/command/constant_mode",
            mode_state_topic=f"{base}/state",
            mode_state_template="{{ value_json.constant_mode }}",
            current_temperature_topic=f"{base}/state",
            current_temperature_template="{{ value_json.air }}",
            temperature_unit="C", min_temp=7, max_temp=30, temp_step=.1, precision=.1,
            temperature_command_topic=f"{base}/command/constant_target",
            temperature_state_topic=f"{base}/state",
            temperature_state_template="{{ value_json.constant_target }}",
            optimistic=False, retain=False, qos=1,
        )
    if entity.kind == "sensor" and entity.key.startswith("schedule_") and entity.key.split("_")[1] in SCHEDULES:
        schedule = entity.key.split("_")[1]
        payload.update(json_attributes_topic=f"{base}/schedules/{schedule}")
    if config.log_level.upper() == "DEBUG" and entity.key in {
        "raw_fields", "parse_errors", "command_state", "raw_status"
    }:
        payload["json_attributes_topic"] = f"{base}/diagnostics"
    return payload
