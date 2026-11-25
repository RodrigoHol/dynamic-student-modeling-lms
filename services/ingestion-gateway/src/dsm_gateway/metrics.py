from prometheus_client import Counter, Histogram

EVENTS_RECEIVED_TOTAL = Counter(
    "dsm_gateway_events_total",
    "Total de eventos procesados por el Ingestion Gateway",
    ["status"],
)

INGESTION_LATENCY_SECONDS = Histogram(
    "dsm_gateway_ingestion_latency_seconds",
    "Latencia de normalización y publicación en el Ingestion Gateway",
)
