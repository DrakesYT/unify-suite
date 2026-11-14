"""User administration. Admins only: who can sign in, with which role and department."""

import uuid

from fastapi import APIRouter, Depends

from app.db import DbSession
from app.deps import CurrentUser, require_roles
from app.models.enums import Role
from app.schemas.auth import PasswordSet, UserAdminOut, UserCreate, UserUpdate
from app.services import users

router = APIRouter(
    prefix="/api/users", tags=["users"], dependencies=[Depends(require_roles(Role.admin))]
)


@router.get("")
def list_users(db: DbSession) -> list[UserAdminOut]:
    return [UserAdminOut.model_validate(u) for u in users.list_users(db)]


@router.post("", status_code=201)
def create_user(data: UserCreate, db: DbSession, user: CurrentUser) -> UserAdminOut:
    return UserAdminOut.model_validate(users.create_user(db, data, actor=user))


@router.patch("/{user_id}")
def update_user(
    user_id: uuid.UUID, data: UserUpdate, db: DbSession, user: CurrentUser
) -> UserAdminOut:
    return UserAdminOut.model_validate(users.update_user(db, user_id, data, user))


@router.post("/{user_id}/password")
def set_password(
    user_id: uuid.UUID, data: PasswordSet, db: DbSession, user: CurrentUser
) -> UserAdminOut:
    """Give a user a new password. Every session of theirs ends."""
    return UserAdminOut.model_validate(users.set_password(db, user_id, data.password, user))
