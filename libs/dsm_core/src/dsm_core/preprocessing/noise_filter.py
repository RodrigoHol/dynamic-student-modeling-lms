from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from dsm_common.config import HleCatalogConfig
from dsm_common.schemas import CanonicalEvent

MatchContext = dict[str, str]

_EXACT_FIELDS = frozenset({"component", "action", "target", "eventname", "resource_type", "origin"})
_IN_FIELDS = frozenset(f"{field}_in" for field in _EXACT_FIELDS)


def extract_match_context(event: CanonicalEvent) -> MatchContext:
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


@dataclass(frozen=True, slots=True)
class CompiledRule:
    exact: tuple[tuple[str, str], ...]
    in_sets: tuple[tuple[str, frozenset[str]], ...]
    eventname_contains: str | None
    is_empty: bool = False

    def matches(self, context: MatchContext) -> bool:
        if self.is_empty:
            return False
        for field_name, expected in self.exact:
            if context.get(field_name, "") != expected:
                return False
        for field_name, allowed in self.in_sets:
            if context.get(field_name, "") not in allowed:
                return False
        if self.eventname_contains is None:
            return True
        return bool(self.eventname_contains) and (
            self.eventname_contains in context.get("eventname", "")
        )


def compile_rule(criteria: Mapping[str, Any]) -> CompiledRule:
    if not criteria:
        return CompiledRule(exact=(), in_sets=(), eventname_contains=None, is_empty=True)

    exact: list[tuple[str, str]] = []
    in_sets: list[tuple[str, frozenset[str]]] = []
    eventname_contains: str | None = None

    for key, expected in criteria.items():
        if key in _EXACT_FIELDS:
            exact.append((key, str(expected).strip().lower()))
        elif key in _IN_FIELDS:
            if not isinstance(expected, Iterable) or isinstance(expected, (str, bytes)):
                raise ValueError(f"El criterio '{key}' requiere una lista de valores.")
            base_field = key.removesuffix("_in")
            allowed = frozenset(str(item).strip().lower() for item in expected)
            in_sets.append((base_field, allowed))
        elif key == "eventname_contains":
            eventname_contains = str(expected).strip().lower()
        else:
            raise ValueError(f"Criterio de regla HLE/ruido no soportado: '{key}'.")

    return CompiledRule(
        exact=tuple(exact),
        in_sets=tuple(in_sets),
        eventname_contains=eventname_contains,
    )


def rule_matches(criteria: Mapping[str, Any], context: MatchContext) -> bool:
    return compile_rule(criteria).matches(context)


class NoiseFilter:
    def __init__(self, catalog: HleCatalogConfig) -> None:
        self._rules: tuple[CompiledRule, ...] = tuple(
            compile_rule(rule.model_dump(exclude_none=True)) for rule in catalog.ignore_noise
        )

    def matches_context(self, context: MatchContext) -> bool:
        return any(rule.matches(context) for rule in self._rules)

    def is_noise(self, event: CanonicalEvent) -> bool:
        if not self._rules:
            return False
        return self.matches_context(extract_match_context(event))
