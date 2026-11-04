import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import JWT_TTL_S
from app.errors import ApiError
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserOut
from app.security import burn_password_check, create_access_token, hash_password, verify_password
from app.services import audit

logger = logging.getLogger(__name__)


def _invalid_credentials() -> ApiError:
    return ApiError(
        401, "invalid_credentials", "Email or password is incorrect", {"WWW-Authenticate": "Bearer"}
    )


def create_user(db: Session, data: UserCreate, actor: User | None = None) -> User:
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise ApiError(409, "email_taken", "A user with this email already exists")
    user = User(
        email=data.email,
        full_name=data.full_name,
        role=data.role,
        department=data.department,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        action="user.created",
        entity="user",
        entity_id=user.id,
        actor_id=actor.id if actor else None,
        detail={"role": user.role, "department": user.department},
    )
    db.commit()
    return user


def login(db: Session, data: LoginRequest) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == data.email))
    if user is None:
        burn_password_check()
    if user is None or not verify_password(data.password, user.password_hash):
        audit.record(db, action="auth.login_failed", entity="user", detail={"email": data.email})
        db.commit()
        logger.info("login_failed")
        raise _invalid_credentials()
    if not user.is_active:
        raise ApiError(403, "account_disabled", "This account is disabled")

    audit.record(db, action="auth.login", entity="user", entity_id=user.id, actor_id=user.id)
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=JWT_TTL_S,
        user=UserOut.model_validate(user),
    )
