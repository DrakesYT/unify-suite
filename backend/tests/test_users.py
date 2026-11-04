import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import AuditLog
from app.models.enums import Department, Role
from app.schemas.auth import UserCreate
from app.security import verify_password
from app.services.users import create_user


def _data(**overrides: str) -> UserCreate:
    fields = {
        "email": "Dana@Unify.Example.com",
        "full_name": "Dana",
        "role": Role.manager,
        "department": Department.finance,
        "password": "long-enough-password",
    } | overrides
    return UserCreate(**fields)  # type: ignore[arg-type]


def test_create_user_hashes_password_and_lowercases_email(db: Session) -> None:
    user = create_user(db, _data())

    assert user.email == "dana@unify.example.com"
    assert user.password_hash != "long-enough-password"
    assert verify_password("long-enough-password", user.password_hash)
    assert db.scalar(select(AuditLog.action)) == "user.created"


def test_duplicate_email_is_409(db: Session) -> None:
    create_user(db, _data())

    with pytest.raises(ApiError) as exc:
        create_user(db, _data(email="dana@unify.example.com"))
    assert exc.value.status_code == 409


@pytest.mark.parametrize("password", ["short", "é" * 40])
def test_password_rules(password: str) -> None:
    with pytest.raises(ValidationError):
        _data(password=password)


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _data(role="superuser")
