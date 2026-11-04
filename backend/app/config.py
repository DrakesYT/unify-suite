"""Settings read from environment variables. Constants live here too."""

from functools import lru_cache

from pydantic_settings import BaseSettings

DB_CONNECT_TIMEOUT_S = 5


class Settings(BaseSettings):
    database_url: str
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env vars
