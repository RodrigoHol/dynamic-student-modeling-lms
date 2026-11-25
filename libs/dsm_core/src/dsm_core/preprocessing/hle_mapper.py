from __future__ import annotations

from dsm_common.config import HleCatalogConfig
from dsm_common.schemas import CanonicalEvent
from dsm_core.preprocessing.noise_filter import (
    CompiledRule,
    MatchContext,
    compile_rule,
    extract_match_context,
)


class HLEMapper:
    def __init__(self, catalog: HleCatalogConfig) -> None:
        self.version: str = catalog.version
        self.rules = list(catalog.rules)
        self.default_hle: str = catalog.default_hle
        self._compiled_rules: tuple[tuple[CompiledRule, str], ...] = tuple(
            (compile_rule(rule.match), rule.hle) for rule in self.rules
        )

        ordered_hles: list[str] = []
        for rule in self.rules:
            if rule.hle not in ordered_hles:
                ordered_hles.append(rule.hle)
        if self.default_hle not in ordered_hles:
            ordered_hles.append(self.default_hle)
        self.known_hles: tuple[str, ...] = tuple(ordered_hles)

    def map_context(self, context: MatchContext) -> str:
        for compiled, hle in self._compiled_rules:
            if compiled.matches(context):
                return hle
        return self.default_hle

    def map_fields(
        self,
        component: str | None,
        eventname: str | None,
        action: str,
        target: str | None = None,
        resource_type: str | None = None,
        origin: str | None = None,
    ) -> str:
        context: MatchContext = {
            "component": (component or "").strip().lower(),
            "action": (action or "").strip().lower(),
            "eventname": (eventname or "").strip().lower(),
            "target": (target or resource_type or "").strip().lower(),
            "resource_type": (resource_type or "").strip().lower(),
            "origin": (origin or "").strip().lower(),
        }
        return self.map_context(context)

    def map_event(self, event: CanonicalEvent) -> str:
        return self.map_context(extract_match_context(event))

    def with_hle(self, event: CanonicalEvent, hle: str) -> CanonicalEvent:
        updated_meta = event.M.model_copy(update={"hle": hle})
        return event.model_copy(update={"M": updated_meta})

    def enrich_event(self, event: CanonicalEvent) -> CanonicalEvent:
        return self.with_hle(event, self.map_event(event))
