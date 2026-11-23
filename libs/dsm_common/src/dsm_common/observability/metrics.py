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


def render_metrics() -> tuple[bytes, str]:
    """Serializa las métricas Prometheus actuales junto con su Content-Type."""
    return generate_latest(), CONTENT_TYPE_LATEST
