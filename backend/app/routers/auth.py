from fastapi import APIRouter

from app.db import DbSession
from app.deps import CurrentUser
from app.schemas.auth import LoginRequest, TokenResponse, UserOut
from app.services import users

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(data: LoginRequest, db: DbSession) -> TokenResponse:
    return users.login(db, data)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
