import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, model_validator

from app import passwords
from app.models.enums import Department, Role


def _lower(value: str) -> str:
    return value.lower()


Email = Annotated[EmailStr, AfterValidator(_lower)]


class LoginRequest(BaseModel):
    email: Email
    password: Annotated[str, Field(min_length=1, max_length=256)]


class UserCreate(BaseModel):
    email: Email
    full_name: Annotated[str, Field(min_length=1, max_length=120)]
    role: Role
    department: Department
    password: str

    @model_validator(mode="after")
    def _strong_password(self) -> "UserCreate":
        found = passwords.problems(self.password, self.email)
        if found:
            raise ValueError("Password rejected: " + "; ".join(found))
        return self


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    department: Department


class SessionOut(BaseModel):
    """Sign-in result. The token itself travels only in the HttpOnly session cookie."""

    expires_in: int
    user: UserOut


class DemoSwitchRequest(BaseModel):
    email: Email


def _checked(password: str, email: str | None) -> None:
    found = passwords.problems(password, email)
    if found:
        raise ValueError("Password rejected: " + "; ".join(found))


class UserAdminOut(UserOut):
    """A user as the admin sees them."""

    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    role: Role | None = None
    department: Department | None = None
    is_active: bool | None = None


class PasswordSet(BaseModel):
    """An admin gives a user a new password (to pass on to them)."""

    password: Annotated[str, Field(min_length=1, max_length=256)]


class PasswordChange(BaseModel):
    """A user changes their own password."""

    current_password: Annotated[str, Field(min_length=1, max_length=256)]
    new_password: Annotated[str, Field(min_length=1, max_length=256)]
