from fastapi import APIRouter

from app.db import DbSession
from app.deps import CurrentUser
from app.schemas.auth import DemoSwitchRequest, LoginRequest, TokenResponse, UserOut
from app.services import users

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(data: LoginRequest, db: DbSession) -> TokenResponse:
    return users.login(db, data)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/demo-accounts")
def demo_accounts(db: DbSession, user: CurrentUser) -> list[UserOut]:
    """The seeded demo accounts a demo user can switch to (403 for real accounts)."""
    return [UserOut.model_validate(u) for u in users.demo_accounts(db, user)]


@router.post("/demo-switch")
def demo_switch(data: DemoSwitchRequest, db: DbSession, user: CurrentUser) -> TokenResponse:
    return users.switch_demo(db, user, data.email)
