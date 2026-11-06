"""Password hashing (bcrypt) and access tokens (JWT, HS256)."""

import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import NamedTuple

import bcrypt
import jwt

from app.config import BCRYPT_ROUNDS, JWT_ALGORITHM, JWT_TTL_S, PASSWORD_MAX_BYTES, get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode()
    if len(encoded) > PASSWORD_MAX_BYTES:
        return False
    return bcrypt.checkpw(encoded, password_hash.encode())


@lru_cache
def _dummy_hash() -> str:
    return hash_password("timing-equaliser")


def burn_password_check() -> None:
    """Spend the same time as a real check, so unknown emails can't be told apart by timing."""
    verify_password("not-the-password", _dummy_hash())


class TokenClaims(NamedTuple):
    user_id: uuid.UUID
    session_id: uuid.UUID


def create_access_token(
    user_id: uuid.UUID, session_id: uuid.UUID, now: datetime | None = None
) -> str:
    issued = now or datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": issued,
        "exp": issued + timedelta(seconds=JWT_TTL_S),
    }
    return jwt.encode(claims, get_settings().jwt_secret.get_secret_value(), JWT_ALGORITHM)


def read_access_token(token: str) -> TokenClaims | None:
    """User and session from a valid, unexpired token; None for anything else. Whether the session
    is still open is checked against the database by the caller."""
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "sid", "exp", "iat"]},
        )
        return TokenClaims(uuid.UUID(claims["sub"]), uuid.UUID(claims["sid"]))
    except (jwt.PyJWTError, ValueError, TypeError):
        return None
