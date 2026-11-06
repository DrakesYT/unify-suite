"""Sliding-window rate limits, kept in memory.

One backend process serves the API (uvicorn without workers), so a dictionary is enough: no Redis.
A restart forgets the counts, which only ever errs towards letting people back in.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from app.config import (
    AI_RUNS_PER_IP,
    AI_RUNS_PER_USER,
    AI_WINDOW_S,
    LOGIN_FAILURES_PER_ACCOUNT,
    LOGIN_FAILURES_PER_IP,
    LOGIN_WINDOW_S,
)
from app.errors import ApiError

MAX_KEYS = 50_000  # a flood of distinct keys can't grow memory without bound


class RateLimiter:
    def __init__(
        self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            return deque()
        while hits and hits[0] <= now - self.window_s:
            hits.popleft()
        if not hits:
            del self._hits[key]
        return hits

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may act again; 0 if it may act now."""
        with self._lock:
            now = self._clock()
            hits = self._recent(key, now)
            if len(hits) < self.limit:
                return 0
            return max(1, math.ceil(hits[0] + self.window_s - now))

    def hit(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            if key not in self._hits and len(self._hits) >= MAX_KEYS:
                self._prune(now)
            self._recent(key, now)
            self._hits.setdefault(key, deque()).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()

    def _prune(self, now: float) -> None:
        for key in list(self._hits):
            self._recent(key, now)
        while len(self._hits) >= MAX_KEYS:  # still full: forget the oldest keys first
            del self._hits[next(iter(self._hits))]


# Failed sign-ins. There is deliberately no lock-out per account alone: anyone could then lock
# the shared demo accounts by typing wrong passwords. The account limit is per account *and* IP.
login_failures_by_ip = RateLimiter(LOGIN_FAILURES_PER_IP, LOGIN_WINDOW_S)
login_failures_by_account = RateLimiter(LOGIN_FAILURES_PER_ACCOUNT, LOGIN_WINDOW_S)

# Model calls cost money; the demo password is shared, so each user and each IP gets a budget.
ai_runs_by_user = RateLimiter(AI_RUNS_PER_USER, AI_WINDOW_S)
ai_runs_by_ip = RateLimiter(AI_RUNS_PER_IP, AI_WINDOW_S)

ALL = (login_failures_by_ip, login_failures_by_account, ai_runs_by_user, ai_runs_by_ip)


def too_many(message: str, retry_after: int) -> ApiError:
    minutes = max(1, math.ceil(retry_after / 60))
    return ApiError(
        429,
        "rate_limited",
        f"{message} Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
        {"Retry-After": str(retry_after)},
    )
