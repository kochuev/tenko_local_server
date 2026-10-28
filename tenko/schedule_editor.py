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


def new_editor():
    return {"stage_source": "ST1/ST2"}


def points(record, day):
    return (record["pending"].get(day)
            or record.get("report", {}).get("settings", {}).get(day))


def layer(record, day):
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
        "validation_error": error,
        "note": "Changes queue immediately. Pending values are NOT confirmation. Zero target means OFF.",
    }


def editor_state(record):
    values = {}
    for key, (day, slot, component) in POINT_CONTROLS.items():
        selected = points(record, day)
        value = number(selected[slot][component]) if selected else None
        if component == 0:
            value = str(int(value)) if value is not None and value.is_integer() and 0 <= value <= 23 else None
        values[key] = value
    for day in SCHEDULES:
        info = details(record, day)
        values[f"schedule_{day}_layer"] = info["layer"]
        values[f"schedule_{day}_validation"] = (
            "invalid" if info["validation_error"] else "valid") if info["displayed_points"] else "no data"
    return values


def edit(record, action, payload):
    """Validate a point change and return a patch without modifying other points."""
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
            if value != selected[slot][0] and (
                (slot > 0 and value <= selected[slot - 1][0])
                or (slot < 9 and value >= selected[slot + 1][0])
            ):
                raise ValueError(f"{day}: hour must be strictly between neighboring points; duplicates are not allowed")
        elif (value is None or (value != 0 and not 7 <= value <= 40)
              or abs(value * 10 - round(value * 10)) > 1e-7):
            raise ValueError("Target must be 0=OFF or 7..40 C in 0.1 C steps")
        if selected[slot][component] != value:
            selected[slot][component] = value
            return {day: selected}
    else:
        raise ValueError(f"Unknown schedule action: {action}")
    return None
