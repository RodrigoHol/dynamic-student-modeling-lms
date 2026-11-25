from dsm_common.config import AppSettings


class ClusteringServiceSettings(AppSettings):
    clustering_consumer_group: str = "dsm-clustering-v1"
    clustering_auto_offset_reset: str = "earliest"
    clustering_metrics_host: str = "0.0.0.0"
    clustering_metrics_port: int = 8005
