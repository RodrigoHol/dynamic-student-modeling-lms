"""Configuración operativa cargada desde variables de entorno (prefijo DSM_)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Ajustes globales de infraestructura y servicio."""

    model_config = SettingsConfigDict(
        env_prefix="DSM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    kafka_bootstrap_servers: str = "localhost:9092"
    pseudonym_salt: str = "change-me-in-production-secret-salt"
    default_run_id: str = "run_dev_001"
    config_dir: Path = Path("./config")

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "dsm_lms"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "dsm_neo4j_pass"

    postgres_dsn: str = "postgresql://dsm_user:dsm_pass@localhost:5432/dsm_metadata"

    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000
