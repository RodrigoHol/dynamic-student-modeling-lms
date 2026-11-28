from __future__ import annotations

from dsm_common.config import ProcessMiningConfig
from dsm_core.process_mining.base import ProcessDiscovery
from dsm_core.process_mining.pm4py_dfg import PM4PyDFGDiscovery

PROCESS_DISCOVERY_REGISTRY: dict[str, type[ProcessDiscovery]] = {
    "dfg": PM4PyDFGDiscovery,
}


def create_process_discovery(config: ProcessMiningConfig) -> ProcessDiscovery:
    """Instancia el motor de descubrimiento declarado en ``config/process_mining.yaml``."""
    key = config.algorithm.strip().lower()
    discovery_cls = PROCESS_DISCOVERY_REGISTRY.get(key)
    if discovery_cls is None:
        supported = ", ".join(sorted(PROCESS_DISCOVERY_REGISTRY))
        raise ValueError(
            f"Algoritmo de minería de procesos no soportado: '{config.algorithm}'. "
            f"Opciones válidas: {supported}"
        )
    return discovery_cls(include_boundaries=config.include_boundaries)
