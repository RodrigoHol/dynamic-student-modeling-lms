from __future__ import annotations

from typing import Any

from dsm_common.config import ClusteringConfig
from dsm_core.clustering.base import ClusteringAlgorithm
from dsm_core.clustering.dbstream import DBSTREAMAdapter
from dsm_core.clustering.denstream import DenStreamAdapter

CLUSTERING_REGISTRY: dict[str, type[ClusteringAlgorithm]] = {
    "denstream": DenStreamAdapter,
    "dbstream": DBSTREAMAdapter,
}


def resolve_clustering_params(config: ClusteringConfig) -> dict[str, Any]:
    """Resuelve los hiperparámetros aplicables al algoritmo activo en ``ClusteringConfig``."""
    name = config.algorithm.strip().lower()
    if name not in CLUSTERING_REGISTRY:
        raise ValueError(
            f"Algoritmo de clustering no soportado: '{config.algorithm}'. "
            f"Disponibles: {sorted(CLUSTERING_REGISTRY)}"
        )

    adapter_cls = CLUSTERING_REGISTRY[name]
    if name in config.algorithm_params:
        return dict(config.algorithm_params[name])
    if config.algorithm in config.algorithm_params:
        return dict(config.algorithm_params[config.algorithm])

    if not config.params:
        return dict(adapter_cls.DEFAULT_PARAMS)

    all_known_params = set().union(*(cls.ALLOWED_PARAMS for cls in CLUSTERING_REGISTRY.values()))
    unknown = set(config.params) - all_known_params
    if unknown:
        raise ValueError(
            f"Parámetros desconocidos en config/clustering.yaml: {sorted(unknown)}."
        )

    # Si `params` contiene parámetros de otro algoritmo registrado al cambiar solo `algorithm`,
    # conserva los compatibles con el algoritmo activo y rellena los faltantes con defaults.
    compatible = {k: v for k, v in config.params.items() if k in adapter_cls.ALLOWED_PARAMS}
    if len(compatible) == len(config.params):
        return compatible
    return {**adapter_cls.DEFAULT_PARAMS, **compatible}


def create_clustering_model(
    name: str,
    params: dict[str, Any] | None = None,
    seed: int = 42,
) -> ClusteringAlgorithm:
    normalized = name.strip().lower()
    adapter_cls = CLUSTERING_REGISTRY.get(normalized)
    if adapter_cls is None:
        raise ValueError(
            f"Algoritmo de clustering no soportado: '{name}'. "
            f"Disponibles: {sorted(CLUSTERING_REGISTRY)}"
        )
    return adapter_cls(seed=seed, **(params or {}))
