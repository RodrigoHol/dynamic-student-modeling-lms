"""Interfaz abstracta para extractores de características por ventana."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from dsm_common.schemas import CanonicalEvent


class FeatureExtractor(ABC):
    """Calcula una o más características numéricas sobre los eventos de una ventana."""

    name: str

    @abstractmethod
    def compute(
        self,
        events: list[CanonicalEvent],
        window_meta: dict[str, Any],
    ) -> dict[str, float]:
        """Devuelve un diccionario `{nombre_feature: valor_numerico}`."""
