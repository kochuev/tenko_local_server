import math
import re
from urllib.parse import parse_qsl

SCHEDULES = ("ED", "MO", "TU", "WE", "TH", "FR", "SA", "SU")
ORDER = ("USE", "TMP", "MO", "TU", "WE", "TH", "FR", "SA", "SU", "ED",
         "FI", "RE", "PMT", "pNA", "STU", "MOD")
TUPLES = {"PM": 2, "ST1": 2, "ST2": 2, "STA": 2, "YSt": 12, "TIM": 6,
          "TMP": 2, "FI": 2, "RE": 2, "PMT": 3, "pNA": 2, "MOD": 4, "STU": 2}
NUMBER_FIELDS = {"TA", "TF", "TR", "Pow", "Davl", "StD", "StW"}
SERIAL = re.compile(r"[A-Za-z0-9_-]{1,80}")
DECIMAL = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def scalar(text):
    if DECIMAL.fullmatch(text):
        value = number(text)
        if value is not None:
            return value
    return text


def form(body):
    pairs = parse_qsl(body.decode("utf-8", errors="strict"), keep_blank_values=True,
                      strict_parsing=True, max_num_fields=100, separator="&",
                      encoding="utf-8", errors="strict")
    raw = {}
    for key, value in pairs:
        if key in raw:
            raise ValueError(f"Duplicate form key: {key}")
        raw[key] = value
    if not SERIAL.fullmatch(raw.get("sn", "")):
        raise ValueError("Missing or invalid sn")
    return raw


def parse_report(raw):
    decoded, errors = {}, []
    for key, text in raw.items():
        try:
            if key in SCHEDULES:
                match = re.fullmatch(r"\[\s*(.*?)\s*\];?", text)
                if not match:
                    raise ValueError("expected nested schedule array")
                points = re.findall(r"\[\s*(\d{1,2})\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\]", match[1])
                residue = re.sub(r"\[\s*\d{1,2}\s*,\s*[+-]?\d+(?:\.\d+)?\s*\]", "", match[1])
                if len(points) != 10 or residue.replace(",", "").strip():
                    raise ValueError("expected ten hour/temperature pairs")
                if any(number(t) is None for _, t in points):
                    raise ValueError("schedule target is not a finite number")
                decoded[key] = [[int(h), float(t)] for h, t in points]
            elif key in TUPLES:
                value = text.strip()
                if value.startswith("[") and value.endswith("]"):
                    value = value[1:-1]
                parts = value.split(",")
                if len(parts) != TUPLES[key] or any("[" in p or "]" in p for p in parts):
                    raise ValueError(f"expected {TUPLES[key]} components")
                decoded[key] = [scalar(p.strip()) for p in parts]
            elif key in NUMBER_FIELDS:
                decoded[key] = scalar(text)
            else:
                decoded[key] = text
        except ValueError as exc:
            errors.append(f"{key}: {exc}")
            decoded[key] = None
    settings = {key: decoded[key] for key in ORDER if decoded.get(key) is not None}
    if "MOD" in settings:
        settings["MOD"] = settings["MOD"][0]
    duplicate = None
    if all(isinstance(decoded.get(k), list) for k in ("ST1", "ST2", "STU")):
        flags = [decoded["ST1"][0], decoded["ST2"][0]]
        duplicate = flags != decoded["STU"]
        if duplicate:
            settings.pop("STU", None)
    return {"raw": raw, "decoded": decoded, "settings": settings,
            "parse_errors": errors, "stage_conflict": duplicate}


def validate_setting(key, value):
    if key not in ORDER:
        raise ValueError(f"Unsupported setting: {key}")

    def numeric(v, low, high, step=1):
        n = number(v)
        if n is None or not low <= n <= high or abs(n / step - round(n / step)) > 1e-7:
            raise ValueError(f"{key}: expected {low}..{high} in steps of {step}")
        return n

    def flag(v):
        if v not in ("On", "Off"):
            raise ValueError(f"{key}: expected On or Off")
        return v

    if key == "USE":
        if value not in ("Temp", "GraphD", "GraphW"):
            raise ValueError("USE: expected Temp, GraphD, or GraphW")
        return value
    if key == "MOD":
        return flag(value)
    length = 10 if key in SCHEDULES else {"TMP": 2, "FI": 2, "RE": 2,
                                          "PMT": 3, "pNA": 2, "STU": 2}[key]
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{key}: expected {length} slots/components")
    if key in SCHEDULES:
        result = []
        for point in value:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"{key}: each point must be [hour, target]")
            hour = int(numeric(point[0], 0, 23))
            target = 0.0 if number(point[1]) == 0 else numeric(point[1], 7, 40, .1)
            if result and hour <= result[-1][0]:
                raise ValueError(f"{key}: new schedules require strictly increasing hours")
            result.append([hour, target])
        return result
    if key == "TMP":
        return [flag(value[0]), numeric(value[1], 7, 40, .1)]
    if key in ("FI", "RE"):
        return [numeric(value[0], 10, 75), numeric(value[1], 1, 9)]
    if key == "PMT":
        result = [flag(value[0]), numeric(value[1], 6, 15), numeric(value[2], 7, 17)]
        if result[1] >= result[2]:
            raise ValueError("PMT: restart threshold must be less than stop threshold")
        return result
    if key == "pNA":
        return [numeric(v, 1, 15) for v in value]
    return [flag(v) for v in value]


def serialize(settings):
    missing = set(ORDER) - settings.keys()
    if missing:
        raise ValueError(f"Cannot send complete settings; missing {', '.join(sorted(missing))}")

    def numeric(v, whole=False):
        n = number(v)
        if n is None or (whole and n != int(n)):
            raise ValueError("Cannot serialize a nonnumeric or fractional integer setting")
        return int(n) if whole else n

    def flag(v):
        if v not in ("On", "Off"):
            raise ValueError("Cannot serialize unknown setting flag")
        return v

    values = {}
    for key in ORDER:
        value = settings[key]
        if key in SCHEDULES:
            if not isinstance(value, list) or len(value) != 10:
                raise ValueError(f"{key}: expected ten slots")
            formatted = []
            for h, t in value:
                hour, target = numeric(h, True), numeric(t)
                if not 0 <= hour <= 23:
                    raise ValueError(f"{key}: invalid reported hour")
                formatted.append(f"{hour:02d},{target:04.1f}")
            values[key] = "/".join(formatted)
        elif key == "TMP":
            values[key] = f"{flag(value[0])},{numeric(value[1]):.1f}"
        elif key == "FI":
            values[key] = f"{numeric(value[0], True):02d},{numeric(value[1]):04.1f}"
        elif key in ("RE", "pNA"):
            values[key] = ",".join(f"{numeric(v, True):02d}" for v in value)
        elif key == "PMT":
            values[key] = f"{flag(value[0])},{numeric(value[1], True):02d},{numeric(value[2], True):02d}"
        elif key == "STU":
            values[key] = ",".join(flag(v) for v in value)
        elif key == "MOD":
            values[key] = flag(value)
        else:
            if value not in ("Temp", "GraphD", "GraphW"):
                raise ValueError("Cannot serialize unknown control mode")
            values[key] = value
        if any(c in values[key] for c in ";:=\r\n"):
            raise ValueError(f"Unsafe response value for {key}")
    # Unchanged captured schedules may contain duplicates and TMP may be 6.9.
    # They are preserved, not revalidated against stricter new-user-input rules.
    return "NewData:" + ";".join(f"{k}={values[k]}" for k in ORDER) + ";EndData"
