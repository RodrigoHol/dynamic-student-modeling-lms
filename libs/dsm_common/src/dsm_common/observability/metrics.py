"""Métricas Prometheus compartidas para la capa de ingesta y servicios."""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

EVENTS_RECEIVED_TOTAL = Counter(
    "dsm_gateway_events_total",
    "Total de eventos procesados por el Ingestion Gateway",
    ["status"],
)

INGESTION_LATENCY_SECONDS = Histogram(
    "dsm_gateway_ingestion_latency_seconds",
    "Latencia de normalización y publicación en el Ingestion Gateway",
)

PREPROCESSOR_EVENTS_TOTAL = Counter(
    "dsm_preprocessor_events_total",
    "Total de eventos procesados por el Preprocessor C4",
    ["status"],
)

PREPROCESSOR_WINDOWS_CLOSED_TOTAL = Counter(
    "dsm_preprocessor_windows_closed_total",
    "Total de ventanas disjuntas cerradas por granularidad en el Preprocessor C4",
    ["granularity"],
)

PREPROCESSOR_LATE_EVENTS_DROPPED_TOTAL = Counter(
    "dsm_preprocessor_late_events_dropped_total",
    "Eventos tardíos descartados fuera del periodo de gracia por granularidad",
    ["granularity"],
)

PREPROCESSOR_PROCESSING_LATENCY_SECONDS = Histogram(
    "dsm_preprocessor_processing_latency_seconds",
    "Latencia de procesamiento por registro en el Preprocessor C4",
)


def render_metrics() -> tuple[bytes, str]:
    """Serializa las métricas Prometheus actuales junto con su Content-Type."""
    return generate_latest(), CONTENT_TYPE_LATEST
