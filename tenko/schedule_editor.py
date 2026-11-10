import copy
from collections import Counter

from .protocol import SCHEDULES, number

DAY_LABELS = dict(zip(SCHEDULES, ("WW", "MO", "TU", "WE", "TH", "FR", "SA", "SU")))
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


def duplicate_hours(selected):
    counts = Counter(int(hour) for hour, _ in selected or ())
    return sorted(hour for hour, count in counts.items() if count > 1)


def details(record, day):
    selected = points(record, day)
    return {
        "day": day, "day_name": DAY_LABELS[day],
        "reported": record.get("report", {}).get("settings", {}).get(day),
        "displayed": selected, "pending": record["pending"].get(day),
        "duplicate_hours": duplicate_hours(selected),
        "note": ("Changes queue immediately. Pending values are NOT confirmation. Zero target means OFF. "
                 "Slots may be in any order; several slots at one hour are ambiguous and resolved by the boiler."),
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
        selected = points(record, day)
        values[f"schedule_{day}_validation"] = (
            ("ambiguous" if duplicate_hours(selected) else "ok") if selected else None)
    return values


def edit(record, action, payload):
    """Validate a slot change and return a patch without modifying other slots."""
    if action in POINT_CONTROLS:
        day, slot, component = POINT_CONTROLS[action]
        selected = copy.deepcopy(points(record, day))
        if not selected or len(selected) != 10:
            raise ValueError("A reported ten-slot schedule is required before editing")
        value = number(payload)
        if component == 0:
            if value is None or value != int(value) or not 0 <= value <= 23:
                raise ValueError("Hour must be a whole number 0..23")
            value = int(value)
        elif (value is None or (value != 0 and not 7 <= value <= 40)
              or abs(value * 10 - round(value * 10)) > 1e-7):
            raise ValueError("Target must be 0=OFF or 7..40 C in 0.1 C steps")
        if selected[slot][component] != value:
            selected[slot][component] = value
            return {day: selected}
    else:
        raise ValueError(f"Unknown schedule action: {action}")
    return None
