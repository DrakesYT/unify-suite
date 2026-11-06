import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ratelimit
from app.config import DEMO_DOMAIN
from app.errors import ApiError
from app.models import User
from app.models.enums import Role
from app.schemas.auth import LoginRequest, UserCreate
from app.security import burn_password_check, hash_password, verify_password
from app.services import audit, sessions

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


def login(db: Session, data: LoginRequest, client_ip: str) -> tuple[User, str]:
    """Check the password and open a session: the user and their new access token.
    Too many wrong passwords from one place are refused before the password is even checked."""
    account_key = f"{data.email}|{client_ip}"
    wait = max(
        ratelimit.login_failures_by_ip.retry_after(client_ip),
        ratelimit.login_failures_by_account.retry_after(account_key),
    )
    if wait:
        audit.record(db, action="auth.login_throttled", entity="user", detail={"email": data.email})
        db.commit()
        raise ratelimit.too_many("Too many failed sign-in attempts.", wait)

    user = db.scalar(select(User).where(User.email == data.email))
    if user is None:
        burn_password_check()
    if user is None or not verify_password(data.password, user.password_hash):
        ratelimit.login_failures_by_ip.hit(client_ip)
        ratelimit.login_failures_by_account.hit(account_key)
        audit.record(db, action="auth.login_failed", entity="user", detail={"email": data.email})
        db.commit()
        logger.info("login_failed")
        raise _invalid_credentials()
    if not user.is_active:
        raise ApiError(403, "account_disabled", "This account is disabled")

    ratelimit.login_failures_by_account.reset(account_key)
    token = sessions.start(db, user)
    audit.record(db, action="auth.login", entity="user", entity_id=user.id, actor_id=user.id)
    db.commit()
    return user, token


def logout(db: Session, user: User, session_id: uuid.UUID) -> None:
    sessions.revoke(db, session_id)
    audit.record(db, action="auth.logout", entity="user", entity_id=user.id, actor_id=user.id)
    db.commit()


# --- Demo accounts: judges can look at the app as any seeded role without re-typing a password ---


def is_demo(user: User) -> bool:
    """A seeded demo account. Admins never count, so a switch can never reach user management."""
    return user.email.endswith(f"@{DEMO_DOMAIN}") and user.role != Role.admin


def _require_demo(user: User) -> None:
    if not is_demo(user):
        raise ApiError(403, "not_demo_account", "Only demo accounts can switch roles")


def demo_accounts(db: Session, user: User) -> list[User]:
    _require_demo(user)
    rows = db.scalars(
        select(User)
        .where(User.email.like(f"%@{DEMO_DOMAIN}"), User.is_active, User.role != Role.admin)
        .order_by(User.department, User.role, User.full_name)
    )
    return [u for u in rows if is_demo(u)]


def switch_demo(db: Session, user: User, email: str, session_id: uuid.UUID) -> tuple[User, str]:
    """Sign in as another demo account. All demo accounts share one password, so this grants
    nothing a demo user could not already do; real accounts can neither switch nor be reached."""
    _require_demo(user)
    target = db.scalar(select(User).where(User.email == email))
    if target is None or not target.is_active or not is_demo(target):
        raise ApiError(404, "not_found", "No such demo account")
    audit.record(
        db,
        action="auth.demo_switch",
        entity="user",
        entity_id=target.id,
        actor_id=user.id,
        detail={"from": user.email, "to": target.email},
    )
    sessions.revoke(db, session_id)  # the old role's token stops working at once
    token = sessions.start(db, target)
    db.commit()
    return target, token
