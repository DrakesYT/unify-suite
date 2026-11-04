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

PAGE_LIMIT_DEFAULT = 50
PAGE_LIMIT_MAX = 200

UPLOAD_MAX_BYTES = 10 * 1024 * 1024
PDF_MAX_PAGES = 50
DOCUMENT_MAX_CHARS = 20_000  # text sent to the LLM is cut to this length

LLM_MAX_TOKENS = 2_000  # includes the model's hidden reasoning tokens
AGENT_RETRY_DELAYS_S = (2, 8)  # two retries: wait 2 s, then 8 s


class Settings(BaseSettings):
    database_url: str
    jwt_secret: SecretStr = Field(min_length=32)
    log_level: str = "INFO"
    upload_dir: str = "/data/uploads"
    llm_base_url: str = "https://api.vultrinference.com/v1"
    llm_model: str = "glm-5.3-flash"
    llm_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env vars
