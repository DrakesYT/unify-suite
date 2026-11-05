import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.config import PASSWORD_MAX_BYTES, PASSWORD_MIN_LEN
from app.models.enums import Department, Role


def _lower(value: str) -> str:
    return value.lower()


def _fits_bcrypt(value: str) -> str:
    if len(value.encode()) > PASSWORD_MAX_BYTES:
        raise ValueError(f"must be at most {PASSWORD_MAX_BYTES} bytes")
    return value


Email = Annotated[EmailStr, AfterValidator(_lower)]
NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN_LEN), AfterValidator(_fits_bcrypt)]


class LoginRequest(BaseModel):
    email: Email
    password: Annotated[str, Field(min_length=1, max_length=256)]


class UserCreate(BaseModel):
    email: Email
    full_name: Annotated[str, Field(min_length=1, max_length=120)]
    role: Role
    department: Department
    password: NewPassword


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    department: Department


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class DemoSwitchRequest(BaseModel):
    email: Email
