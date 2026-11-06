"""Auth guards used by routers: who is calling, and may they touch this department."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import ratelimit
from app.config import CSRF_HEADER, CSRF_HEADER_VALUE, SESSION_COOKIE
from app.db import DbSession
from app.errors import ApiError
from app.models import User
from app.models.enums import Department, Role
from app.security import read_access_token
from app.services import sessions
from app.services.authz import can_access

_bearer = HTTPBearer(auto_error=False)
_CHALLENGE = {"WWW-Authenticate": "Bearer"}
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """The signed-in user, from `Authorization: Bearer` (API clients) or the session cookie
    (browsers). The session must still be open: signing out ends it on the server."""
    if credentials is not None:
        token = credentials.credentials
    else:
        token = request.cookies.get(SESSION_COOKIE)
        # The cookie rides along on any request to this site; the custom header proves a
        # data-changing request came from our own pages (see CSRF_HEADER in config).
        csrf_ok = request.headers.get(CSRF_HEADER) == CSRF_HEADER_VALUE
        if token and request.method not in _READ_METHODS and not csrf_ok:
            raise ApiError(403, "csrf_check_failed", "Request blocked: missing CSRF header")
    if not token:
        raise ApiError(401, "not_authenticated", "Sign in required", _CHALLENGE)
    claims = read_access_token(token)
    user = db.get(User, claims.user_id) if claims else None
    if (
        claims is None
        or user is None
        or not user.is_active
        or not sessions.is_open(db, claims.session_id, user.id)
    ):
        raise ApiError(401, "invalid_token", "Session is invalid or expired", _CHALLENGE)
    request.state.session_id = claims.session_id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[User], User]:
    def guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ApiError(403, "forbidden", "Your role cannot do this")
        return user

    return guard


def require_department(department: Department) -> Callable[[Request, User], User]:
    """Router-level guard: reads need read access, every other method needs write access."""

    def guard(request: Request, user: CurrentUser) -> User:
        write = request.method not in _READ_METHODS
        if not can_access(user, department, write=write):
            raise ApiError(403, "forbidden", f"No access to {department} data")
        return user

    return guard


def client_ip(request: Request) -> str:
    """The visitor's address. Caddy passes the real one on (see the Caddyfile), and uvicorn's
    proxy-header handling puts it here."""
    return request.client.host if request.client else "unknown"


def spend_ai_run(request: Request, user: User) -> None:
    """Count one model-backed request against the user's and the IP's budget (429 when spent)."""
    ip = client_ip(request)
    wait = max(
        ratelimit.ai_runs_by_user.retry_after(str(user.id)),
        ratelimit.ai_runs_by_ip.retry_after(ip),
    )
    if wait:
        raise ratelimit.too_many("You have used up the AI requests for now.", wait)
    ratelimit.ai_runs_by_user.hit(str(user.id))
    ratelimit.ai_runs_by_ip.hit(ip)
