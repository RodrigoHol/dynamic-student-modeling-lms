"""Nombres canónicos de topics de Apache Kafka."""


class Topics:
    """Constantes de topics utilizados en la arquitectura Kappa."""

    CANONICAL_EVENTS = "lms.events.canonical"
    DLQ_EVENTS = "lms.events.dlq"
    FEATURES = "analytics.features"
    TRACES = "analytics.traces"
    ASSIGNMENTS = "analytics.assignments"
