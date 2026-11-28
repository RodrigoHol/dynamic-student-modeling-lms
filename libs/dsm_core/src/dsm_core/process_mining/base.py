from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from dsm_common.schemas import TraceEventItem
from dsm_core.process_mining.models import DfgData


class ProcessDiscovery(ABC):
    """Contrato común para motores de descubrimiento y fusión aditiva de procesos."""

    name: str

    @abstractmethod
    def build_student_dfg(self, trace: Sequence[TraceEventItem]) -> DfgData:
        """Construye el grafo de flujo directo individual a partir de la traza del alumno."""

    @abstractmethod
    def merge_dfgs(self, dfgs: Sequence[DfgData]) -> DfgData:
        """Combina aditivamente múltiples DFG individuales en un DFG consolidado."""
