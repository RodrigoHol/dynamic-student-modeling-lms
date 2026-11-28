from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dsm_common.time import utc_now
from dsm_query_api.config import QueryApiSettings
from dsm_query_api.schemas import UserPublic, UserRecord

_PBKDF2_ITERATIONS = 120_000
_BEARER_SCHEME = HTTPBearer(auto_error=False)

DEMO_SEED_USERS: tuple[tuple[str, str, str, str], ...] = (
    ("usr_admin", "admin", "admin123", "admin"),
    ("usr_teacher", "docente", "docente123", "teacher"),
)


def hash_password(password: str, *, salt_hex: str | None = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    parts = stored_hash.split("$")
    if len(parts) != 3 or parts[0] != "pbkdf2_sha256":
        return False
    _, salt_hex, expected_hex = parts
    candidate = hash_password(password, salt_hex=salt_hex)
    return hmac.compare_digest(candidate, f"pbkdf2_sha256${salt_hex}${expected_hex}")


def build_demo_user_records() -> list[UserRecord]:
    return [
        UserRecord(
            user_id=user_id,
            username=username,
            role=role,  # type: ignore[arg-type]
            assigned_courses=[],
            password_hash=hash_password(raw_password),
        )
        for user_id, username, raw_password, role in DEMO_SEED_USERS
    ]


def create_access_token(user: UserPublic, settings: QueryApiSettings) -> tuple[str, int]:
    now = utc_now()
    ttl_seconds = settings.jwt_expire_minutes * 60
    payload: dict[str, Any] = {
        "sub": user.user_id,
        "username": user.username,
        "role": user.role,
        "assigned_courses": user.assigned_courses,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, ttl_seconds


def decode_access_token(token: str, settings: QueryApiSettings) -> UserPublic:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token JWT inválido o expirado: {exc}",
        ) from exc

    return UserPublic(
        user_id=str(payload["sub"]),
        username=str(payload["username"]),
        role=payload["role"],
        assigned_courses=list(payload.get("assigned_courses") or []),
    )


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER_SCHEME)],
) -> UserPublic:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación Bearer.",
        )
    settings: QueryApiSettings = request.app.state.settings
    return decode_access_token(credentials.credentials, settings)


def require_roles(*allowed_roles: str) -> Callable[..., Any]:
    async def _dependency(
        user: Annotated[UserPublic, Depends(get_current_user)],
    ) -> UserPublic:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No cuentas con permisos suficientes para este recurso.",
            )
        return user

    return _dependency
