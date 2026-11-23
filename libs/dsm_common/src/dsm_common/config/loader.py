"""Carga y validación de archivos de configuración analítica YAML."""

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class HleNoiseRule(BaseModel):
    """Regla para descartar ruido operativo del LMS."""

    model_config = ConfigDict(extra="allow")

    component: str | None = None
    eventname_contains: str | None = None


class HleRule(BaseModel):
    """Regla de mapeo de evento técnico a Evento de Alto Nivel."""

    hle: str = Field(..., min_length=1)
    match: dict[str, Any]


class HleCatalogConfig(BaseModel):
    """Esquema del catálogo versionado de Eventos de Alto Nivel (HLE)."""

    version: str
    status: str = "PROVISIONAL"
    default_hle: str = "OTRO"
    ignore_noise: list[HleNoiseRule] = Field(default_factory=list)
    rules: list[HleRule]


class FeaturesConfig(BaseModel):
    """Esquema de extractores de características habilitados."""

    version: str
    status: str = "PROVISIONAL"
    enabled_extractors: list[str]


class WindowDefinition(BaseModel):
    """Definición de una granularidad temporal de ventana disjunta."""

    model_config = ConfigDict(extra="allow")

    type: str = "tumbling"
    duration_seconds: int | None = None
    mode: str | None = None
    close_on_eof: bool | None = None


class WindowsConfig(BaseModel):
    """Esquema de ventanas múltiples simultáneas."""

    version: str
    grace_period_seconds: int = Field(ge=0)
    active_granularities: list[str]
    windows: dict[str, WindowDefinition]


class ClusteringConfig(BaseModel):
    """Configuración del algoritmo de stream clustering."""

    algorithm: str
    seed: int = 42
    params: dict[str, Any] = Field(default_factory=dict)


class ProcessMiningConfig(BaseModel):
    """Configuración del motor de descubrimiento de procesos."""

    algorithm: str = "dfg"
    include_boundaries: bool = True
    min_edge_frequency: int = Field(default=1, ge=1)


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"El archivo YAML debe contener un mapeo raíz: {path}")
    return raw


def compute_yaml_hash(path: Path) -> str:
    """Calcula el hash SHA-256 del archivo YAML para trazabilidad por run_id."""
    if not path.is_file():
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_hle_catalog(path: Path) -> HleCatalogConfig:
    """Carga y valida config/hle_catalog.yaml."""
    return HleCatalogConfig.model_validate(_load_yaml_dict(path))


def load_features_config(path: Path) -> FeaturesConfig:
    """Carga y valida config/features.yaml."""
    return FeaturesConfig.model_validate(_load_yaml_dict(path))


def load_windows_config(path: Path) -> WindowsConfig:
    """Carga y valida config/windows.yaml."""
    return WindowsConfig.model_validate(_load_yaml_dict(path))


def load_clustering_config(path: Path) -> ClusteringConfig:
    """Carga y valida config/clustering.yaml."""
    return ClusteringConfig.model_validate(_load_yaml_dict(path))


def load_process_mining_config(path: Path) -> ProcessMiningConfig:
    """Carga y valida config/process_mining.yaml."""
    return ProcessMiningConfig.model_validate(_load_yaml_dict(path))
