"""Rules for new passwords on real accounts: long enough, not a well-known password, and not built
from the person's own email name or the product name."""

import re

from app.config import PASSWORD_MAX_BYTES, PASSWORD_MIN_LEN

# The most used passwords in public breach lists (and obvious ones for this product). A password
# that is one of these, ignoring case, digits and symbols at either end, is refused.
_COMMON_WORDS = """
password passw0rd p@ssword p@ssw0rd password1 password123 passwordpassword qwerty qwertyuiop
qwerty123 qwertyuiop123 asdfghjkl zxcvbnm 1q2w3e4r 1qaz2wsx qazwsx iloveyou letmein welcome
welcome1 welcome123 admin administrator root toor changeme default secret monkey dragon football
baseball superman batman sunshine princess shadow master freedom trustno1 whatever starwars
pokemon computer internet michael jennifer jordan hunter killer soccer hockey cricket pakistan
karachi lahore islamabad abc123 abcdef abcdefgh 123456 1234567 12345678 123456789 1234567890
0987654321 111111 000000 123123 654321 666666 777777 888888 987654321 unify unifysuite suite
vultr hackathon demo demopassword test testing tester user username login access company manager
employee executive finance sales support procurement
"""
COMMON = frozenset(_COMMON_WORDS.split())


def _core(password: str) -> str:
    """Lower-case, with digits and symbols trimmed from both ends (Password123! → password)."""
    return re.sub(r"^[\W\d_]+|[\W\d_]+$", "", password.lower())


def problems(password: str, email: str | None = None) -> list[str]:
    """Why a new password is not acceptable; empty when it is."""
    found: list[str] = []
    if len(password) < PASSWORD_MIN_LEN:
        found.append(f"use at least {PASSWORD_MIN_LEN} characters")
    if len(password.encode()) > PASSWORD_MAX_BYTES:
        found.append(f"use at most {PASSWORD_MAX_BYTES} bytes")
    lowered = password.lower()
    if lowered in COMMON or _core(password) in COMMON or len(set(lowered)) <= 3:
        found.append("it is a common or very simple password")
    name = (email or "").split("@")[0].lower()
    if len(name) >= 3 and name in lowered:
        found.append("it contains your email name")
    if "unify" in lowered:
        found.append("it contains the product name")
    return found
