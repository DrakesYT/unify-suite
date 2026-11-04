"""Settings read from environment variables. Constants live here too."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

DB_CONNECT_TIMEOUT_S = 5

JWT_ALGORITHM = "HS256"
JWT_TTL_S = 8 * 60 * 60  # tokens are valid for 8 hours
BCRYPT_ROUNDS = 12
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_BYTES = 72  # bcrypt ignores anything longer, so longer passwords are refused


class Settings(BaseSettings):
    database_url: str
    jwt_secret: SecretStr = Field(min_length=32)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env vars
