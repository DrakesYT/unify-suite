"""Settings read from environment variables. Constants live here too."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings

DB_CONNECT_TIMEOUT_S = 5

JWT_ALGORITHM = "HS256"
JWT_TTL_S = 8 * 60 * 60  # tokens are valid for 8 hours
# Browsers carry the token in this cookie: HttpOnly (page scripts can't read it), SameSite=Strict,
# and sent only to /api. A cookie-authenticated request that changes data must also carry the CSRF
# header: another site can't add a custom header to a request without CORS, which this API
# never allows.
SESSION_COOKIE = "unify_session"
SESSION_COOKIE_PATH = "/api"
CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "unify"
LOGIN_WINDOW_S = 15 * 60
LOGIN_FAILURES_PER_ACCOUNT = 5  # wrong passwords for one email from one IP per window
LOGIN_FAILURES_PER_IP = 20  # wrong passwords from one IP (any email) per window
AI_WINDOW_S = 10 * 60
AI_RUNS_PER_USER = 30  # model-backed requests per user per window
AI_RUNS_PER_IP = 60  # ...and per IP, so switching demo roles doesn't multiply the budget
BCRYPT_ROUNDS = 12
PASSWORD_MIN_LEN = 12  # real accounts (python -m app.cli create-user)
# The one shared demo password is handed to judges; rate limits, not length, protect it.
DEMO_PASSWORD_MIN_LEN = 8
PASSWORD_MAX_BYTES = 72  # bcrypt ignores anything longer, so longer passwords are refused

PAGE_LIMIT_DEFAULT = 50
PAGE_LIMIT_MAX = 200

UPLOAD_MAX_BYTES = 10 * 1024 * 1024
PDF_MAX_PAGES = 50
DOCUMENT_MAX_CHARS = 20_000  # text sent to the LLM is cut to this length
SUSPICIOUS_MAX_FINDINGS = 5  # instruction-like lines reported per document
SUSPICIOUS_LINE_MAX_CHARS = 160

DEMO_DOMAIN = "demo.example.com"  # the seeded demo accounts; they share one password
SELLER_COMPANY = "UNIFY Demo Corp"  # the company the demo users work for (email signatures)
DEFAULT_TERMS_DAYS = 30  # customer payment terms when none are on file (net 30)
OFFICE_UTC_OFFSET_HOURS = 5  # interviews are scheduled in Pakistan time (PKT, no daylight saving)
OFFICE_TZ_LABEL = "PKT"
INTERVIEW_START_HOURS = (10, 11, 14, 15, 16)  # local start times; 12:00-14:00 is lunch
INTERVIEW_MINUTES = 45
INTERVIEW_OPTIONS = 3  # slots offered per invite, one per working day
INTERVIEW_MIN_SCORE = 50  # only candidates screened at least this high can be invited
INTERVIEW_SEARCH_DAYS = 21
RESEND_API_URL = "https://api.resend.com/emails"
EMAIL_SEND_TIMEOUT_S = 10.0

BRIEF_CACHE_S = 15 * 60  # a model-written brief is reused this long while its facts hold
LLM_MAX_TOKENS = 8_000  # includes the model's hidden reasoning tokens; only used when needed
AGENT_RETRY_DELAYS_S = (2, 8)  # two retries: wait 2 s, then 8 s
# A workflow run with no step activity for this long was cut off by a restart and may be resumed
# by hand (longer than any step can take: three model attempts plus their waits).
WORKFLOW_STALE_S = 5 * 60


class Settings(BaseSettings):
    database_url: str
    jwt_secret: SecretStr = Field(min_length=32)
    log_level: str = "INFO"
    # Only ever false for the test client, which talks plain http to a fake host.
    session_cookie_secure: bool = True
    upload_dir: str = "/data/uploads"
    llm_base_url: str = "https://api.vultrinference.com/v1"
    llm_model: str = "glm-5.3-flash"
    llm_api_key: SecretStr | None = None
    # Email (Resend). Without a key, approved emails are not sent and are marked failed.
    resend_api_key: SecretStr | None = None
    email_from: str = "UNIFY SUITE <onboarding@resend.dev>"
    # Demo safety: when set, every email goes to this one address instead of the real recipient.
    email_redirect_to: str | None = None
    # Without a redirect, approved emails are refused unless real recipients are switched on here:
    # a missing setting must never turn the demo into a way to email strangers.
    email_send_to_real_recipients: bool = False
    # Sales target shown on the dashboard gauge: whole units of the currency per quarter.
    sales_quarter_target: int = Field(default=250_000, ge=1)
    sales_target_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")

    @field_validator("resend_api_key", "email_redirect_to", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """docker compose passes an unset variable as an empty string."""
        return None if isinstance(value, str) and not value.strip() else value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env vars
