"""Configuración operativa del servicio C4 Preprocessor (prefijo DSM_)."""

from pathlib import Path

from dsm_common.config import AppSettings


class PreprocessorSettings(AppSettings):
    """Ajustes de Kafka, RocksDB y endpoint de métricas para C4 Preprocessor."""

    preprocessor_consumer_group: str = "dsm-preprocessor-v1"
    preprocessor_auto_offset_reset: str = "earliest"
    preprocessor_state_dir: Path = Path("./state/preprocessor")
    preprocessor_use_changelog_topics: bool = False
    preprocessor_metrics_host: str = "0.0.0.0"
    preprocessor_metrics_port: int = 8004
