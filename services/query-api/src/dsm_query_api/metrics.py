from prometheus_client import Counter, Gauge, Histogram

QUERY_REQUESTS_TOTAL = Counter(
    "dsm_query_api_requests_total",
    "Total de peticiones HTTP atendidas por C7 Query API",
    ["endpoint", "status"],
)

QUERY_LATENCY_SECONDS = Histogram(
    "dsm_query_api_latency_seconds",
    "Latencia de lectura sobre el estado materializado en C7 Query API",
    ["endpoint"],
)

QUERY_WS_CONNECTIONS = Gauge(
    "dsm_query_api_ws_connections",
    "Conexiones WebSocket activas hacia el Dashboard Docente",
)
