from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar


class ClusteringAlgorithm(ABC):
    """Contrato común para algoritmos de stream clustering intercambiables."""

    name: str
    ALLOWED_PARAMS: ClassVar[frozenset[str]] = frozenset()
    DEFAULT_PARAMS: ClassVar[dict[str, Any]] = {}

    @abstractmethod
    def learn_one(self, x: dict[str, float]) -> None:
        """Actualiza incrementalmente el modelo con un vector de características."""

    @abstractmethod
    def predict_one(self, x: dict[str, float]) -> int:
        """Retorna el cluster_id asignado (-1 si es outlier o aún no hay clústeres)."""

    @abstractmethod
    def get_centroid(self, cluster_id: int) -> dict[str, float] | None:
        """Devuelve el centroide del clúster en el espacio del modelo, o None si no existe."""

    @abstractmethod
    def snapshot(self) -> dict[str, Any]:
        """Serializa centroides y micro-clústeres actuales para persistencia e interpretabilidad."""

    def distance_to_centroid(
        self,
        x: Mapping[str, float],
        cluster_id: int,
    ) -> float | None:
        if cluster_id < 0:
            return None
        centroid = self.get_centroid(cluster_id)
        if centroid is None:
            return None
        keys = set(x) | set(centroid)
        sq_sum = sum((float(x.get(k, 0.0)) - float(centroid.get(k, 0.0))) ** 2 for k in keys)
        return round(math.sqrt(sq_sum), 6)
