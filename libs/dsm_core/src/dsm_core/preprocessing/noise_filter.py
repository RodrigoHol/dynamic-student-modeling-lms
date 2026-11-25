"""Filtrado de ruido operativo del LMS y motor de coincidencia de reglas."""

from __future__ import annotations

from typing import Any

from dsm_common.config import HleCatalogConfig
from dsm_common.schemas import CanonicalEvent


def extract_match_context(event: CanonicalEvent) -> dict[str, str]:
    """Extrae en minúsculas los campos evaluables por reglas HLE o de ruido."""
    extra = event.M.model_extra or {}
    raw_target = extra.get("target") or event.r.resource_type or ""
    raw_origin = extra.get("origin") or ""
    return {
        "component": (event.M.component or "").strip().lower(),
        "action": (event.a or "").strip().lower(),
        "eventname": (event.M.raw_eventname or "").strip().lower(),
        "target": str(raw_target).strip().lower(),
        "resource_type": (event.r.resource_type or "").strip().lower(),
        "origin": str(raw_origin).strip().lower(),
    }


def rule_matches(criteria: dict[str, Any], context: dict[str, str]) -> bool:
    """Evalúa si todos los predicados de `criteria` coinciden con `context`."""
    if not criteria:
        return False

    for key, expected in criteria.items():
        if key in {"component", "action", "target", "eventname", "resource_type", "origin"}:
            if context.get(key, "") != str(expected).strip().lower():
                return False
        elif key in {
            "component_in",
            "action_in",
            "target_in",
            "eventname_in",
            "resource_type_in",
            "origin_in",
        }:
            base_field = key.removesuffix("_in")
            allowed = {str(item).strip().lower() for item in expected}
            if context.get(base_field, "") not in allowed:
                return False
        elif key == "eventname_contains":
            needle = str(expected).strip().lower()
            if not needle or needle not in context.get("eventname", ""):
                return False
        else:
            raise ValueError(f"Criterio de regla HLE/ruido no soportado: '{key}'.")

    return True


class NoiseFilter:
    """Descarta eventos operativos sin valor pedagógico según `ignore_noise` del YAML."""

    def __init__(self, catalog: HleCatalogConfig) -> None:
        self._rules: list[dict[str, Any]] = [
            rule.model_dump(exclude_none=True) for rule in catalog.ignore_noise
        ]

    def is_noise(self, event: CanonicalEvent) -> bool:
        """Devuelve `True` si el evento coincide con alguna regla de ruido operativo."""
        if not self._rules:
            return False
        context = extract_match_context(event)
        return any(rule_matches(rule, context) for rule in self._rules)
