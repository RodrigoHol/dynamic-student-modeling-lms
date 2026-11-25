from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from dsm_common.config import AppSettings
from dsm_common.privacy import pseudonymize_user_id
from dsm_common.schemas import CanonicalEvent, DlqEvent, RawEventInput, make_dlq_event
from dsm_common.time import utc_now


def normalize_or_dlq(payload: Any, settings: AppSettings) -> CanonicalEvent | DlqEvent:
    now = utc_now()
    if not isinstance(payload, dict):
        return make_dlq_event(
            payload,
            "El payload del evento debe ser un objeto JSON.",
            received_at=now,
        )

    try:
        raw = RawEventInput.model_validate(payload)
        pseudo_u = pseudonymize_user_id(raw.raw_user_id, settings.pseudonym_salt)
    except (ValidationError, ValueError) as exc:
        return make_dlq_event(payload, str(exc), received_at=now)

    return CanonicalEvent(
        event_id=str(uuid4()),
        run_id=raw.run_id or settings.default_run_id,
        u=pseudo_u,
        a=raw.action,
        r=raw.resource,
        t=raw.timestamp,
        ingested_at=now,
        M=raw.metadata,
    )
