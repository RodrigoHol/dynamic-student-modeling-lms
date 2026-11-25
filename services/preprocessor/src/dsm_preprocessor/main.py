"""Punto de entrada ejecutable para C4 Preprocessor (`/health`, `/metrics` y loop Quix)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dsm_common.observability import render_metrics
from dsm_preprocessor.app import build_application
from dsm_preprocessor.config import PreprocessorSettings


class _HealthAndMetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            body = json.dumps({"status": "ok", "service": "preprocessor"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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


def _start_observability_server(host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), _HealthAndMetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> None:
    """Inicia el servidor de salud/métricas y ejecuta continuamente C4 Preprocessor."""
    settings = PreprocessorSettings()
    server = _start_observability_server(
        settings.preprocessor_metrics_host,
        settings.preprocessor_metrics_port,
    )
    app, sdf = build_application(settings)
    try:
        app.run(sdf)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
