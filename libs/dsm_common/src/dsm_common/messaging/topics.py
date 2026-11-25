from typing import Final


class Topics:
    CANONICAL_EVENTS: Final[str] = "lms.events.canonical"
    DLQ_EVENTS: Final[str] = "lms.events.dlq"
    FEATURES: Final[str] = "analytics.features"
    TRACES: Final[str] = "analytics.traces"
    ASSIGNMENTS: Final[str] = "analytics.assignments"
