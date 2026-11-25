from prometheus_client import Counter, Histogram

CLUSTERING_VECTORS_TOTAL = Counter(
    "dsm_clustering_vectors_total",
    "Total de vectores procesados por el Clustering Engine C5",
    ["status", "granularity"],
)

CLUSTERING_TRANSITIONS_TOTAL = Counter(
    "dsm_clustering_transitions_total",
    "Total de transiciones de clúster detectadas por granularidad en C5",
    ["granularity"],
)

CLUSTERING_OUTLIERS_TOTAL = Counter(
    "dsm_clustering_outliers_total",
    "Total de asignaciones clasificadas como outlier (-1) por granularidad en C5",
    ["granularity"],
)

CLUSTERING_PROCESSING_LATENCY_SECONDS = Histogram(
    "dsm_clustering_processing_latency_seconds",
    "Latencia interna de procesamiento y persistencia por vector en C5",
)

CLUSTERING_INGESTED_TO_PROFILE_LATENCY_SECONDS = Histogram(
    "dsm_clustering_ingested_to_profile_latency_seconds",
    "Latencia total desde ingested_at en C2 hasta la persistencia del perfil en MongoDB",
)
