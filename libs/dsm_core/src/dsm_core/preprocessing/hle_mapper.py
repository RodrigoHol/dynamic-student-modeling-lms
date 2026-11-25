"""Mapeador declarativo de eventos técnicos del LMS a Eventos de Alto Nivel (HLE)."""

from __future__ import annotations

from dsm_common.config import HleCatalogConfig
from dsm_common.schemas import CanonicalEvent
from dsm_core.preprocessing.noise_filter import extract_match_context, rule_matches


class HLEMapper:
    """Traduce eventos canónicos del LMS a categorías pedagógicas HLE según reglas YAML."""

    def __init__(self, catalog: HleCatalogConfig) -> None:
        self.version: str = catalog.version
        self.rules = list(catalog.rules)
        self.default_hle: str = catalog.default_hle

        ordered_hles: list[str] = []
        for rule in self.rules:
            if rule.hle not in ordered_hles:
                ordered_hles.append(rule.hle)
        if self.default_hle not in ordered_hles:
            ordered_hles.append(self.default_hle)
        self.known_hles: tuple[str, ...] = tuple(ordered_hles)

    def map_fields(
        self,
        component: str | None,
        eventname: str | None,
        action: str,
        target: str | None = None,
        resource_type: str | None = None,
        origin: str | None = None,
    ) -> str:
        """Mapea campos individuales de un evento al código HLE correspondiente."""
        context = {
            "component": (component or "").strip().lower(),
            "action": (action or "").strip().lower(),
            "eventname": (eventname or "").strip().lower(),
            "target": (target or resource_type or "").strip().lower(),
            "resource_type": (resource_type or "").strip().lower(),
            "origin": (origin or "").strip().lower(),
        }
        for rule in self.rules:
            if rule_matches(rule.match, context):
                return rule.hle
        return self.default_hle

    def map_event(self, event: CanonicalEvent) -> str:
        """Devuelve el código HLE correspondiente a un `CanonicalEvent`."""
        context = extract_match_context(event)
        for rule in self.rules:
            if rule_matches(rule.match, context):
                return rule.hle
        return self.default_hle

    def enrich_event(self, event: CanonicalEvent) -> CanonicalEvent:
        """Devuelve una copia del `CanonicalEvent` con `M.hle` asignado."""
        hle = self.map_event(event)
        updated_meta = event.M.model_copy(update={"hle": hle})
        return event.model_copy(update={"M": updated_meta})
