import copy

from .protocol import SCHEDULES, number, validate_setting

DAY_NAMES = dict(zip(SCHEDULES, ("Whole week", "Monday", "Tuesday", "Wednesday",
                                 "Thursday", "Friday", "Saturday", "Sunday")))
SCHEDULE_MODES = {"Whole week": "GraphD", "Individual days": "GraphW", "Constant temperature": "Temp"}
POINT_CONTROLS = {
    f"schedule_{day}_{slot + 1:02d}_{field}": (day, slot, component)
    for day in SCHEDULES for slot in range(10)
    for component, field in enumerate(("hour", "target"))
}
DAY_BUTTONS = {f"schedule_{day}_{action}": (day, action)
               for day in SCHEDULES for action in ("apply", "discard")}


def new_editor():
    return {"stage_source": "ST1/ST2"}


def points(record, day):
    return (record["draft"].get(day) or record["pending"].get(day)
            or record.get("report", {}).get("settings", {}).get(day))


def layer(record, day):
    if day in record["draft"] and record["draft"][day] != record["pending"].get(day):
        return "draft"
    if day in record["pending"]:
        return "pending"
    return "reported" if points(record, day) else "no data"


def details(record, day):
    selected = points(record, day)
    error = None
    if selected:
        try:
            validate_setting(day, selected)
        except ValueError as exc:
            error = str(exc)
    return {
        "day": day, "day_name": DAY_NAMES[day], "layer": layer(record, day),
        "points": record.get("report", {}).get("settings", {}).get(day),
        "displayed_points": selected, "pending": record["pending"].get(day),
        "draft": record["draft"].get(day), "validation_error": error,
        "note": "Point controls show draft/pending values, NOT confirmation. Zero target means OFF.",
    }


def editor_state(record):
    values = {}
    for key, (day, slot, component) in POINT_CONTROLS.items():
        selected = points(record, day)
        values[key] = number(selected[slot][component]) if selected else None
    for day in SCHEDULES:
        info = details(record, day)
        values[f"schedule_{day}_layer"] = info["layer"]
        values[f"schedule_{day}_validation"] = (
            "invalid" if info["validation_error"] else "valid") if info["displayed_points"] else "no data"
    for key, (day, _) in DAY_BUTTONS.items():
        values[key] = "ready" if day in record["draft"] else None
    values.update(
        editor_apply_all="ready" if any(day in record["draft"] for day in SCHEDULES) else None,
        editor_discard_all="ready" if record["draft"] else None,
        stage_resolution_source=record.get("schedule_editor", new_editor())["stage_source"],
        resolve_stages="ready" if record.get("report", {}).get("stage_conflict") else None,
    )
    return values


def edit(record, action, payload):
    """Edit a fixed point locally, or return a fully validated settings patch."""
    if action in POINT_CONTROLS:
        day, slot, component = POINT_CONTROLS[action]
        selected = copy.deepcopy(points(record, day))
        if not selected or len(selected) != 10:
            raise ValueError("A reported ten-point schedule is required before editing")
        value = number(payload)
        if component == 0:
            if value is None or value != int(value) or not 0 <= value <= 23:
                raise ValueError("Hour must be a whole number 0..23")
            value = int(value)
        elif (value is None or (value != 0 and not 7 <= value <= 40)
              or abs(value * 10 - round(value * 10)) > 1e-7):
            raise ValueError("Target must be 0=OFF or 7..40 C in 0.1 C steps")
        selected[slot][component] = value
        record["draft"][day] = selected
        record["draft_revision"] += 1
    elif action in DAY_BUTTONS or action in {"editor_apply_all", "editor_discard_all"}:
        day, operation = DAY_BUTTONS.get(action, (None, "apply" if action == "editor_apply_all" else "discard"))
        days = (day,) if day else SCHEDULES
        if operation == "apply":
            patch = {key: validate_setting(key, record["draft"][key])
                     for key in days if key in record["draft"]}
            if not patch:
                raise ValueError("No draft schedules to apply")
            return patch
        if day:
            record["draft"].pop(day, None)
        else:
            record["draft"] = {}
        record["draft_revision"] += 1
    elif action == "stage_resolution_source":
        if payload not in ("ST1/ST2", "STU"):
            raise ValueError("Choose ST1/ST2 or STU as the duplicate resolution source")
        record.setdefault("schedule_editor", new_editor())["stage_source"] = payload
    elif action == "resolve_stages":
        report = record.get("report", {})
        if not report.get("stage_conflict"):
            raise ValueError("There is no reported duplicate-stage conflict")
        decoded = report["decoded"]
        source = record.get("schedule_editor", new_editor())["stage_source"]
        flags = [decoded["ST1"][0], decoded["ST2"][0]] if source == "ST1/ST2" else decoded["STU"]
        return {"STU": validate_setting("STU", flags)}
    else:
        raise ValueError(f"Unknown schedule action: {action}")
    return None
