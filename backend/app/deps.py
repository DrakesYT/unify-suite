"""Auth guards used by routers: who is calling, and may they touch this department."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import DbSession
from app.errors import ApiError
from app.models import User
from app.models.enums import Department, Role
from app.security import read_access_token
from app.services.authz import can_access

_bearer = HTTPBearer(auto_error=False)
_CHALLENGE = {"WWW-Authenticate": "Bearer"}
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise ApiError(401, "not_authenticated", "Sign in required", _CHALLENGE)
    user_id = read_access_token(credentials.credentials)
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise ApiError(401, "invalid_token", "Session is invalid or expired", _CHALLENGE)
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
