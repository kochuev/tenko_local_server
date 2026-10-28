import base64
import binascii
import hmac
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .protocol import SERIAL, form
from .store import public_record

LOG = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def create_server(config, store, bridge):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            LOG.info("%s %s", self.client_address[0], fmt % args)

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def reply(self, status, body, content_type="application/json; charset=utf-8", headers=None):
            if not isinstance(body, (str, bytes)):
                body = json.dumps(body, allow_nan=False)
            data = body.encode() if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "object-src 'none'; base-uri 'none'; form-action 'self'; "
                             f"frame-ancestors {config.frame_ancestors}")
            self.send_header("Connection", "close")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

        def authorized(self):
            try:
                scheme, encoded = self.headers.get("Authorization", "").split(" ", 1)
                if scheme.lower() != "basic":
                    raise ValueError("Basic authentication required")
                supplied = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                supplied = b""
            expected = f"{config.editor_username}:{config.editor_password}".encode()
            if not hmac.compare_digest(supplied, expected):
                self.reply(401, {"error": "Editor authentication required"},
                           headers={"WWW-Authenticate": 'Basic realm="Tenko editor", charset="UTF-8"'})
                return False
            return True

        def body(self):
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Chunked requests are not supported")
            length = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= length <= 65536:
                raise ValueError("Content-Length must be 0..65536 bytes")
            data = self.rfile.read(length)
            if len(data) != length:
                raise ValueError("Incomplete request body")
            return data

        def serial_allowed(self, serial):
            if not SERIAL.fullmatch(serial):
                raise ValueError("Invalid serial")
            if config.allowed_serials and serial not in config.allowed_serials:
                raise PermissionError("Serial not allowed")

        def handle_request(self):
            path = urlsplit(self.path).path
            try:
                parameter_report = path == "/update/param" and self.command == "POST"
                status_report = bool(config.status_path and path == config.status_path
                                     and self.command == config.status_method)
                if parameter_report or status_report:
                    if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                        self.reply(415, {"error": "Expected application/x-www-form-urlencoded"})
                        return
                    raw = form(self.body())
                    self.serial_allowed(raw["sn"])
                    if parameter_report:
                        record, response = store.report(raw)
                        bridge.emit(record["serial"])
                        if record["report"]["parse_errors"]:
                            self.reply(400, {"error": "Malformed report", "details": record["report"]["parse_errors"]})
                            return
                        if response == "nochange":
                            response = config.no_change_body
                    else:
                        record = store.status(raw)
                        bridge.emit(record["serial"])
                        response = "status updated"
                    self.reply(200, response, "text/html; charset=UTF-8")
                    return
                if path == "/health" and self.command == "GET":
                    self.reply(200, {"http": "ok", "mqtt_connected": bridge.connected})
                    return
                if not self.authorized():
                    return
                if self.command == "GET":
                    if path in {"/", "/static/editor.js", "/static/editor.css"}:
                        name, mime = {
                            "/": ("index.html", "text/html; charset=utf-8"),
                            "/static/editor.js": ("editor.js", "text/javascript; charset=utf-8"),
                            "/static/editor.css": ("editor.css", "text/css; charset=utf-8"),
                        }[path]
                        self.reply(200, (STATIC / name).read_bytes(), mime)
                        return
                    if path == "/api/boilers":
                        self.reply(200, [{"serial": r["serial"], "last_report": r["last_report"]}
                                         for r in store.all()])
                        return
                parts = path.strip("/").split("/")
                if len(parts) in (3, 4) and parts[:2] == ["api", "boilers"]:
                    serial = parts[2]
                    self.serial_allowed(serial)
                    if len(parts) == 3 and self.command == "GET":
                        self.reply(200, public_record(store.get(serial), config.freshness_timeout))
                        return
                    if len(parts) == 4 and self.command in {"POST", "PUT"}:
                        if self.headers.get("X-Tenko-Request") != "1":
                            raise PermissionError("Missing X-Tenko-Request: 1 (CSRF protection)")
                        if self.headers.get_content_type() != "application/json":
                            raise ValueError("Expected application/json")
                        data = json.loads(self.body())
                        if not isinstance(data, dict):
                            raise ValueError("Expected JSON object")
                        if parts[3] == "settings" and self.command == "POST":
                            if not isinstance(data.get("revision"), int):
                                raise ValueError("Current report revision is required")
                            record = store.command(serial, data.get("settings"), data["revision"])
                        elif parts[3] == "draft" and self.command == "PUT":
                            record = store.draft(serial, data.get("draft"), data.get("revision"))
                        elif parts[3] == "cancel" and self.command == "POST":
                            record = store.cancel(serial)
                        else:
                            self.reply(404, {"error": "Unknown API action"})
                            return
                        bridge.emit(serial)
                        self.reply(200, public_record(record, config.freshness_timeout))
                        return
                self.reply(404, {"error": "Unknown path or method"})
            except PermissionError as exc:
                self.reply(403, {"error": str(exc)})
            except KeyError:
                self.reply(404, {"error": "Unknown boiler; wait for its first report"})
            except (ValueError, UnicodeError) as exc:
                LOG.warning("Rejected %s %s: %s", self.command, path, exc)
                self.reply(400, {"error": str(exc)})
            except OSError:
                LOG.exception("I/O failure handling %s %s", self.command, path)
                self.reply(500, {"error": "Storage or I/O failure; inspect service logs"})

        do_GET = handle_request
        do_POST = handle_request
        do_PUT = handle_request
        do_PATCH = handle_request
        do_DELETE = handle_request

    server = ThreadingHTTPServer((config.http_host, config.http_port), Handler)
    server.daemon_threads = False
    return server
