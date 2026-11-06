from fastapi import APIRouter, Request, Response

from app.config import JWT_TTL_S, SESSION_COOKIE, SESSION_COOKIE_PATH, get_settings
from app.db import DbSession
from app.deps import CurrentUser, client_ip
from app.models import User
from app.schemas.auth import DemoSwitchRequest, LoginRequest, SessionOut, UserOut
from app.services import users

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _signed_in(response: Response, user: User, token: str) -> SessionOut:
    """Hand the token to the browser as an HttpOnly cookie: page scripts can never read it."""
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=JWT_TTL_S,
        path=SESSION_COOKIE_PATH,
        secure=get_settings().session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return SessionOut(expires_in=JWT_TTL_S, user=UserOut.model_validate(user))


@router.post("/login")
def login(data: LoginRequest, request: Request, db: DbSession, response: Response) -> SessionOut:
    user, token = users.login(db, data, client_ip(request))
    return _signed_in(response, user, token)


@router.post("/logout", status_code=204)
def logout(request: Request, db: DbSession, user: CurrentUser) -> Response:
    """End this session on the server and remove the cookie."""
    users.logout(db, user, request.state.session_id)
    response = Response(status_code=204)
    response.delete_cookie(
        SESSION_COOKIE,
        path=SESSION_COOKIE_PATH,
        secure=get_settings().session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return response


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/demo-accounts")
def demo_accounts(db: DbSession, user: CurrentUser) -> list[UserOut]:
    """The seeded demo accounts a demo user can switch to (403 for real accounts)."""
    return [UserOut.model_validate(u) for u in users.demo_accounts(db, user)]


@router.post("/demo-switch")
def demo_switch(
    data: DemoSwitchRequest, request: Request, db: DbSession, user: CurrentUser, response: Response
) -> SessionOut:
    target, token = users.switch_demo(db, user, data.email, request.state.session_id)
    return _signed_in(response, target, token)
