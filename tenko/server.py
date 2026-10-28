import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .protocol import SERIAL, form

LOG = logging.getLogger(__name__)


def create_server(config, store, bridge):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            LOG.info("%s %s", self.client_address[0], fmt % args)

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def reply(self, status, body, content_type="application/json; charset=utf-8"):
            if not isinstance(body, (str, bytes)):
                body = json.dumps(body, allow_nan=False)
            data = body.encode() if isinstance(body, str) else body
            LOG.debug("HTTP EXCHANGE peer=%s method=%s path=%r status=%s request_body=%r response_body=%r",
                      self.client_address[0], self.command, self.path, status,
                      self.request_body, data)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

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
            self.request_body = None
            try:
                data = self.body() if (self.command in {"POST", "PUT", "PATCH", "DELETE"}
                                       or self.headers.get("Content-Length")
                                       or self.headers.get("Transfer-Encoding")) else b""
                self.request_body = data
                LOG.debug("HTTP IN peer=%s method=%s path=%r content_type=%s length=%s body=%r",
                          self.client_address[0], self.command, self.path,
                          self.headers.get("Content-Type"), len(data), data)
                parameter_report = path == "/update/param" and self.command == "POST"
                status_report = bool(config.status_path and path == config.status_path
                                     and self.command == config.status_method)
                if parameter_report or status_report:
                    if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                        self.reply(415, {"error": "Expected application/x-www-form-urlencoded"})
                        return
                    raw = form(data)
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
                        record = store.status(raw, method=self.command, path=path)
                        bridge.emit(record["serial"])
                        response = "status updated"
                    self.reply(200, response, "text/html; charset=UTF-8")
                    return
                if path == "/health" and self.command == "GET":
                    self.reply(200, {"http": "ok", "mqtt_connected": bridge.connected})
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
