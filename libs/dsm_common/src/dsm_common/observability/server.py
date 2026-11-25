from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dsm_common.observability.metrics import render_metrics


def _make_handler(service_name: str) -> type[BaseHTTPRequestHandler]:
    health_payload = json.dumps({"status": "ok", "service": service_name}).encode("utf-8")

    class _HealthAndMetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(health_payload)))
                self.end_headers()
                self.wfile.write(health_payload)
                return

            if self.path == "/metrics":
                data, content_type = render_metrics()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    return _HealthAndMetricsHandler


def start_observability_server(
    service_name: str,
    host: str,
    port: int,
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), _make_handler(service_name))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
