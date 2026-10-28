import logging
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    http_host: str = "0.0.0.0"
    http_port: int = 9080
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_client_id: str = "tenko-local"
    mqtt_tls: bool = False
    mqtt_ca_file: str = ""
    mqtt_prefix: str = "tenko"
    discovery_prefix: str = "homeassistant"
    freshness_timeout: int = 180
    confirmation_timeout: int = 600
    state_path: str = "data/state.json"
    status_path: str = "/update/status"
    status_method: str = "POST"
    no_change_body: str = "nochange"
    allowed_serials: tuple[str, ...] = ()
    log_level: str = "INFO"

    @classmethod
    def from_env(cls):
        values = {}
        integers = {"http_port", "mqtt_port", "freshness_timeout", "confirmation_timeout"}
        for key in cls.__dataclass_fields__:
            text = os.environ.get(key.upper())
            if text is None:
                continue
            if key in {"status_path", "status_method"} and not text.strip():
                continue
            if key in integers:
                values[key] = int(text)
            elif key == "mqtt_tls":
                if text.lower() not in {"true", "false", "1", "0"}:
                    raise ValueError("MQTT_TLS must be true or false")
                values[key] = text.lower() in {"true", "1"}
            elif key == "allowed_serials":
                values[key] = tuple(s.strip() for s in text.split(",") if s.strip())
            elif key in {"log_level", "status_method"}:
                values[key] = text.upper()
            else:
                values[key] = text
        result = cls(**values)
        for port in (result.http_port, result.mqtt_port):
            if not 1 <= port <= 65535:
                raise ValueError("Ports must be between 1 and 65535")
        if min(result.freshness_timeout, result.confirmation_timeout) < 1:
            raise ValueError("Timeouts must be positive seconds")
        if result.log_level not in logging.getLevelNamesMapping():
            raise ValueError("LOG_LEVEL must be a Python logging level, e.g. INFO or DEBUG")
        if bool(result.status_path) != bool(result.status_method):
            raise ValueError("Set both STATUS_PATH and STATUS_METHOD, or neither")
        if result.status_path and (
            not result.status_path.startswith("/")
            or result.status_path.startswith(("/api", "/static"))
            or result.status_path in {"/", "/health", "/update/param"}
            or result.status_method not in {"POST", "PUT", "PATCH"}
        ):
            raise ValueError("Status requires a distinct path and POST, PUT, or PATCH method")
        if result.no_change_body not in {"", "nochange"}:
            raise ValueError("NO_CHANGE_BODY must be empty or nochange")
        for prefix in (result.mqtt_prefix, result.discovery_prefix):
            if not prefix or any(c in prefix for c in "+#\x00") or prefix.endswith("/"):
                raise ValueError("MQTT prefixes must be nonempty and contain no wildcards")
        return result
