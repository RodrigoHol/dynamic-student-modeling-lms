from prometheus_client import Counter, Histogram

PM_TRACES_TOTAL = Counter(
    "dsm_process_mining_traces_total",
    "Total de trazas procesadas por el Process Mining Engine C6",
    ["status", "granularity"],
)

PM_ASSIGNMENTS_TOTAL = Counter(
    "dsm_process_mining_assignments_total",
    "Total de asignaciones de clúster procesadas por C6",
    ["status", "granularity"],
)

PM_GRAPHS_PERSISTED_TOTAL = Counter(
    "dsm_process_mining_graphs_persisted_total",
    "Total de grafos DFG persistidos en Neo4j por alcance y granularidad",
    ["scope", "granularity"],
)

PM_PROCESSING_LATENCY_SECONDS = Histogram(
    "dsm_process_mining_processing_latency_seconds",
    "Latencia interna de procesamiento y persistencia por mensaje en C6",
)

PM_INGESTED_TO_GRAPH_LATENCY_SECONDS = Histogram(
    "dsm_process_mining_ingested_to_graph_latency_seconds",
    "Latencia total desde ingested_at en C2 hasta la persistencia del grafo DFG en Neo4j",
    ["scope"],
)
