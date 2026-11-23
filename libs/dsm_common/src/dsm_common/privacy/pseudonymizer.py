"""Utilidades de seudonimización determinista (ADR-14, RF-03)."""

import hashlib
import hmac


def pseudonymize_user_id(
    raw_user_id: str,
    salt: str,
    prefix: str = "usr_",
    length: int = 16,
) -> str:
    """Genera un identificador seudonimizado determinista mediante HMAC-SHA256."""
    cleaned_id = raw_user_id.strip()
    if not cleaned_id:
        raise ValueError("raw_user_id no puede estar vacío.")
    if not salt:
        raise ValueError("salt no puede estar vacía.")
    if length <= 0 or length > 64:
        raise ValueError("length debe estar entre 1 y 64 caracteres hexadecimales.")

    digest = hmac.new(
        salt.encode("utf-8"),
        cleaned_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{prefix}{digest[:length]}"
