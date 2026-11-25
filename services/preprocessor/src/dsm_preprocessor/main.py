from __future__ import annotations

from dsm_common.observability import start_observability_server
from dsm_preprocessor.app import build_application
from dsm_preprocessor.config import PreprocessorSettings


def main() -> None:
    settings = PreprocessorSettings()
    server = start_observability_server(
        "preprocessor",
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
