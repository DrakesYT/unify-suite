"""Settings read from environment variables. Constants live here too."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
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
SUSPICIOUS_MAX_FINDINGS = 5  # instruction-like lines reported per document
SUSPICIOUS_LINE_MAX_CHARS = 160

SELLER_COMPANY = "UNIFY Demo Corp"  # the company the demo users work for (email signatures)
DEFAULT_TERMS_DAYS = 30  # customer payment terms when none are on file (net 30)
RESEND_API_URL = "https://api.resend.com/emails"
EMAIL_SEND_TIMEOUT_S = 10.0

LLM_MAX_TOKENS = 4_000  # includes the model's hidden reasoning tokens
AGENT_RETRY_DELAYS_S = (2, 8)  # two retries: wait 2 s, then 8 s


class Settings(BaseSettings):
    database_url: str
    jwt_secret: SecretStr = Field(min_length=32)
    log_level: str = "INFO"
    upload_dir: str = "/data/uploads"
    llm_base_url: str = "https://api.vultrinference.com/v1"
    llm_model: str = "glm-5.3-flash"
    llm_api_key: SecretStr | None = None
    # Email (Resend). Without a key, approved emails are not sent and are marked failed.
    resend_api_key: SecretStr | None = None
    email_from: str = "UNIFY SUITE <onboarding@resend.dev>"
    # Demo safety: when set, every email goes to this one address instead of the real recipient.
    email_redirect_to: str | None = None

    @field_validator("resend_api_key", "email_redirect_to", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """docker compose passes an unset variable as an empty string."""
        return None if isinstance(value, str) and not value.strip() else value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env vars
