"""Sign-in sessions: one row per sign-in, so a token can be ended before it expires."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import JWT_TTL_S
from app.models import User, UserSession
from app.models.base import utcnow
from app.security import create_access_token


def start(db: Session, user: User, now: datetime | None = None) -> str:
    """Open a session for `user` and return its access token. The caller commits."""
    issued = now or utcnow()
    # Housekeeping: this user's sessions that ran out are no longer needed.
    db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at < issued)
    )
    session = UserSession(
        id=uuid.uuid4(), user_id=user.id, expires_at=issued + timedelta(seconds=JWT_TTL_S)
    )
    db.add(session)
    db.flush()
    return create_access_token(user.id, session.id, now=issued)


def is_open(
    db: Session, session_id: uuid.UUID, user_id: uuid.UUID, now: datetime | None = None
) -> bool:
    session = db.get(UserSession, session_id)
    return (
        session is not None
        and session.user_id == user_id
        and session.revoked_at is None
        and session.expires_at > (now or utcnow())
    )


def revoke(db: Session, session_id: uuid.UUID) -> None:
    """End one session (sign-out, role switch). The caller commits."""
    session = db.get(UserSession, session_id)
    if session is not None and session.revoked_at is None:
        session.revoked_at = utcnow()
