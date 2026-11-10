"""Regenerate the repetitive native Schedule view: python -m examples.generate_dashboard."""

import json
import re
from pathlib import Path

from tenko.entities import BY_KEY
from tenko.schedule_editor import DAY_LABELS

MARKER = "  # Generated Schedule view"


def entity_id(key):
    entity = BY_KEY[key]
    name = re.sub(r"[^a-z0-9]+", "_", entity.name.lower()).strip("_")
    prefix = "tenko_boiler_energy_meter" if entity.energy_device else "tenko_boiler"
    return f"{entity.kind}.{prefix}_{name}"


def schedule_view():
    lines = [
        MARKER + " - regenerate before customizing entity IDs.",
        "  - title: Schedule", "    path: schedule", "    type: sections", "    max_columns: 3",
        "    sections:", "      - type: grid", "        cards:",
        "          - type: heading", "            heading: Schedule",
        "          - type: entities", "            title: Upload status",
        "            entities:",
    ]
    for key in ("command_state", "command_error"):
        lines.append(f"              - {entity_id(key)}")
    lines.extend([
        "          - type: markdown",
        "            content: >-",
        "              Each numbered slot has Hour (0-23) and Target in C (0 = OFF, otherwise 7-40).",
        "              Each valid change queues immediately. Whole week mode repeats WW every day;",
        "              Individual days uses MO-SU. Editing does not activate a mode.",
        "              Slots may be in any order; Schedule shows ambiguous when several slots share an hour.",
        "              Queued uploads continue until confirmed.",
    ])
    for day, name in DAY_LABELS.items():
        lines.extend([
            "      - type: grid", "        cards:", "          - type: heading",
            f"            heading: {json.dumps(name)}", "          - type: entities",
            "            show_header_toggle: false", "            entities:",
        ])
        lines.append(f"              - {entity_id(f'schedule_{day}_validation')}")
        lines.extend([
            "          - type: grid", "            columns: 2", "            square: false",
            "            cards:",
        ])
        for slot in range(1, 11):
            for field in ("hour", "target"):
                key = f"schedule_{day}_{slot:02d}_{field}"
                lines.extend([
                    "              - type: entities", "                show_header_toggle: false",
                    "                entities:", f"                  - entity: {entity_id(key)}",
                    f"                    name: {json.dumps(f'{slot:02d} {field.title()}')}",
                ])
    return "\n".join(lines)


def main():
    path = Path(__file__).with_name("home-assistant.yaml")
    boiler_view = path.read_text().split(MARKER)[0].rstrip()
    path.write_text(boiler_view + "\n" + schedule_view() + "\n")


if __name__ == "__main__":
    main()
