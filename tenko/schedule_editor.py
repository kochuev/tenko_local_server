import copy

from .protocol import SCHEDULES, number, validate_setting

DAY_NAMES = dict(zip(SCHEDULES, ("Every day", "Monday", "Tuesday", "Wednesday",
                                 "Thursday", "Friday", "Saturday", "Sunday")))


def new_editor():
    return {"day": "ED", "slot": 1, "copy_to": "MO", "restore_targets": {}, "stage_source": "ST1/ST2"}


def points(record, day):
    return (record["draft"].get(day) or record["pending"].get(day)
            or record.get("report", {}).get("settings", {}).get(day))


def layer(record, day):
    if day in record["draft"] and record["draft"][day] != record["pending"].get(day):
        return "draft"
    if day in record["pending"]:
        return "pending"
    return "reported" if points(record, day) else "no data"


def details(record):
    editor = record.get("schedule_editor", new_editor())
    day, slot = editor["day"], editor["slot"] - 1
    selected = points(record, day)
    error = None
    if selected:
        try:
            validate_setting(day, selected)
        except ValueError as exc:
            error = str(exc)
    reported = record.get("report", {}).get("settings", {}).get(day)
    return {
        "day": day, "day_name": DAY_NAMES[day], "slot": slot + 1,
        "layer": layer(record, day), "points": selected,
        "reported": reported, "pending": record["pending"].get(day),
        "draft": record["draft"].get(day), "validation_error": error,
        "note": "Editor fields show draft/pending values, NOT confirmation. Zero target means OFF.",
    }


def editor_state(record):
    editor = record.get("schedule_editor", new_editor())
    info = details(record)
    selected, reported = info["points"], info["reported"]
    slot = editor["slot"] - 1
    value = selected[slot] if selected else [None, None]
    observed = reported[slot] if reported else [None, None]
    has_drafts = any(day in record["draft"] for day in SCHEDULES)
    return {
        "editor_day": DAY_NAMES[editor["day"]], "editor_slot": str(editor["slot"]),
        "editor_hour": number(value[0]), "editor_target": number(value[1]),
        "editor_off": ("On" if value[1] == 0 else "Off") if number(value[1]) is not None else None,
        "editor_copy_to": DAY_NAMES[editor["copy_to"]],
        "editor_layer": info["layer"],
        "editor_validation": ("invalid" if info["validation_error"] else "valid") if selected else "no data",
        "editor_day_summary": f"{len(selected)} points ({info['layer']})" if selected else None,
        "editor_reported_hour": number(observed[0]), "editor_reported_target": number(observed[1]),
        "editor_apply_day": "ready" if editor["day"] in record["draft"] else None,
        "editor_apply_all": "ready" if has_drafts else None,
        "editor_discard_day": "ready" if editor["day"] in record["draft"] else None,
        "editor_discard_all": "ready" if record["draft"] else None,
        "editor_copy_day": "ready" if selected else None,
        "editor_copy_week": "ready" if selected else None,
        "cancel_pending": "ready" if record["pending"] else None,
        "stage_resolution_source": editor["stage_source"],
        "resolve_stages": "ready" if record.get("report", {}).get("stage_conflict") else None,
    }


def edit(record, action, payload):
    """Mutate a local draft, or return a validated patch to queue for the boiler."""
    editor = record.setdefault("schedule_editor", new_editor())
    day, slot = editor["day"], editor["slot"] - 1
    if action in {"editor_day", "editor_copy_to"}:
        reverse = {name: key for key, name in DAY_NAMES.items()}
        if payload not in reverse:
            raise ValueError(f"{action}: choose a discovered day name")
        editor["day" if action == "editor_day" else "copy_to"] = reverse[payload]
    elif action == "editor_slot":
        if payload not in tuple(str(i) for i in range(1, 11)):
            raise ValueError("Slot must be 1..10")
        editor["slot"] = int(payload)
    elif action == "stage_resolution_source":
        if payload not in ("ST1/ST2", "STU"):
            raise ValueError("Choose ST1/ST2 or STU as the duplicate resolution source")
        editor["stage_source"] = payload
    elif action in {"editor_hour", "editor_target", "editor_off"}:
        selected = copy.deepcopy(points(record, day))
        if not selected or len(selected) != 10:
            raise ValueError("A reported ten-slot schedule is required before editing")
        if action == "editor_hour":
            hour = number(payload)
            if hour is None or hour != int(hour) or not 0 <= hour <= 23:
                raise ValueError("Hour must be a whole number 0..23")
            selected[slot][0] = int(hour)
        else:
            memory_key = f"{day}:{slot}"
            current = number(selected[slot][1])
            if action == "editor_off":
                if payload not in ("On", "Off"):
                    raise ValueError("OFF switch expects On or Off")
                if payload == "On":
                    if current is not None and 7 <= current <= 40:
                        editor["restore_targets"][memory_key] = current
                    target = 0
                elif current == 0:
                    target = editor["restore_targets"].get(memory_key)
                    if target is None:
                        raise ValueError("No previous non-OFF target; set a 7..40 C target explicitly")
                else:
                    target = current
            else:
                target = number(payload)
            if target is None or (target != 0 and not 7 <= target <= 40) or abs(target * 10 - round(target * 10)) > 1e-7:
                raise ValueError("Target must be 0=OFF or 7..40 C in 0.1 C steps")
            selected[slot][1] = target
            if target:
                editor["restore_targets"][memory_key] = target
        record["draft"][day] = selected
        record["draft_revision"] += 1
    elif action in {"editor_apply_day", "editor_apply_all"}:
        days = [day] if action == "editor_apply_day" else SCHEDULES
        patch = {key: validate_setting(key, record["draft"][key])
                 for key in days if key in record["draft"]}
        if not patch:
            raise ValueError("No draft schedules to apply")
        return patch
    elif action in {"editor_discard_day", "editor_discard_all"}:
        if action == "editor_discard_day":
            record["draft"].pop(day, None)
        else:
            record["draft"] = {}
        record["draft_revision"] += 1
    elif action in {"editor_copy_day", "editor_copy_week"}:
        selected = points(record, day)
        if not selected:
            raise ValueError("Selected source day has no stored points")
        destinations = [editor["copy_to"]] if action == "editor_copy_day" else SCHEDULES[1:]
        for destination in destinations:
            record["draft"][destination] = copy.deepcopy(selected)
        record["draft_revision"] += 1
    elif action == "resolve_stages":
        report = record.get("report", {})
        if not report.get("stage_conflict"):
            raise ValueError("There is no reported duplicate-stage conflict")
        decoded = report["decoded"]
        flags = ([decoded["ST1"][0], decoded["ST2"][0]]
                 if editor["stage_source"] == "ST1/ST2" else decoded["STU"])
        return {"STU": validate_setting("STU", flags)}
    else:
        raise ValueError(f"Unknown editor action: {action}")
    return None
