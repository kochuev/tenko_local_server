"""Regenerate the repetitive native Schedule view: python -m examples.generate_dashboard."""

import json
import re
from pathlib import Path

from tenko.entities import BY_KEY
from tenko.schedule_editor import DAY_NAMES

MARKER = "  # Generated Schedule view"


def entity_id(key):
    entity = BY_KEY[key]
    name = re.sub(r"[^a-z0-9]+", "_", entity.name.lower()).strip("_")
    return f"{entity.kind}.tenko_boiler_{name}"


def schedule_view():
    lines = [
        MARKER + " - regenerate before customizing entity IDs.",
        "  - title: Schedule", "    path: schedule", "    type: sections", "    max_columns: 3",
        "    sections:", "      - type: grid", "        cards:",
        "          - type: heading", "            heading: Schedule",
        "          - type: entities", "            title: Mode and upload",
        "            entities:",
    ]
    for key in ("schedule_mode", "editor_apply_all", "editor_discard_all", "command_state", "command_error"):
        lines.append(f"              - {entity_id(key)}")
    lines.extend([
        "          - type: markdown",
        "            content: >-",
        "              Each numbered line has Hour (0-23) and Target in C (0 = OFF, otherwise 7-40).",
        "              Edit all ten points, then Apply. Whole week repeats ED every day;",
        "              Individual days uses Monday-Sunday. Editing does not activate a mode.",
        "              Discard only removes drafts; queued uploads continue until confirmed.",
    ])
    for day, name in DAY_NAMES.items():
        lines.extend([
            "      - type: grid", "        cards:", "          - type: heading",
            f"            heading: {json.dumps(name)}", "          - type: entities",
            "            show_header_toggle: false", "            entities:",
        ])
        for key in (f"schedule_{day}_layer", f"schedule_{day}_validation",
                    f"schedule_{day}_apply", f"schedule_{day}_discard"):
            lines.append(f"              - {entity_id(key)}")
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
