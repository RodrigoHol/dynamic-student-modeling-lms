"""Normalización hacia tupla canónica y enrutamiento a DLQ."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from dsm_common.config import AppSettings
from dsm_common.privacy import pseudonymize_user_id
from dsm_common.schemas import CanonicalEvent, DlqEvent, RawEventInput


def normalize_or_dlq(
    payload: Any,
    settings: AppSettings,
) -> tuple[CanonicalEvent | None, DlqEvent | None]:
    """Valida, seudonimiza y normaliza un evento crudo, o construye un DlqEvent si falla."""
    now = datetime.now(UTC)
    if not isinstance(payload, dict):
        return None, DlqEvent(
            dlq_id=str(uuid4()),
            received_at=now,
            error_reason="El payload del evento debe ser un objeto JSON.",
            raw_payload=payload,
        )

    try:
        raw = RawEventInput.model_validate(payload)
        pseudo_u = pseudonymize_user_id(raw.raw_user_id, settings.pseudonym_salt)
    except (ValidationError, ValueError) as exc:
        return None, DlqEvent(
            dlq_id=str(uuid4()),
            received_at=now,
            error_reason=str(exc),
            raw_payload=payload,
        )

    canonical = CanonicalEvent(
        event_id=str(uuid4()),
        run_id=raw.run_id or settings.default_run_id,
        u=pseudo_u,
        a=raw.action,
        r=raw.resource,
        t=raw.timestamp,
        ingested_at=now,
        M=raw.metadata,
    )
    return canonical, None
