import uuid
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
