from dsm_common.config import AppSettings


class ProcessMiningServiceSettings(AppSettings):
    process_mining_consumer_group: str = "dsm-process-mining-v1"
    process_mining_auto_offset_reset: str = "earliest"
    process_mining_metrics_host: str = "0.0.0.0"
    process_mining_metrics_port: int = 8006
