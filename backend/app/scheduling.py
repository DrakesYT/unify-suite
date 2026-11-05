"""Picks interview times in plain code (no model): working days, office hours, no double booking."""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, timezone

from app.config import (
    INTERVIEW_MINUTES,
    INTERVIEW_OPTIONS,
    INTERVIEW_SEARCH_DAYS,
    INTERVIEW_START_HOURS,
    OFFICE_TZ_LABEL,
    OFFICE_UTC_OFFSET_HOURS,
)

OFFICE_TZ = timezone(timedelta(hours=OFFICE_UTC_OFFSET_HOURS))
Busy = Iterable[tuple[datetime, datetime]]


def _overlaps(start: datetime, end: datetime, busy: list[tuple[datetime, datetime]]) -> bool:
    return any(start < b_end and b_start < end for b_start, b_end in busy)


def pick_slots(now: datetime, busy: Busy, count: int = INTERVIEW_OPTIONS) -> list[datetime]:
    """The first free office-hour start on each of the next working days, from tomorrow on.

    Returns UTC start times. Weekends are skipped; nothing overlaps a slot already held.
    """
    taken = list(busy)
    length = timedelta(minutes=INTERVIEW_MINUTES)
    today = now.astimezone(OFFICE_TZ).date()
    picked: list[datetime] = []
    for offset in range(1, INTERVIEW_SEARCH_DAYS + 1):
        day = today + timedelta(days=offset)
        if day.weekday() >= 5:  # Saturday, Sunday
            continue
        for hour in INTERVIEW_START_HOURS:
            start = datetime(day.year, day.month, day.day, hour, tzinfo=OFFICE_TZ).astimezone(UTC)
            if not _overlaps(start, start + length, taken):
                picked.append(start)
                break
        if len(picked) == count:
            break
    return picked


def label(start: datetime) -> str:
    """'Mon 9 Nov 2026, 10:00-10:45 PKT' — the exact text the invite must contain."""
    local = start.astimezone(OFFICE_TZ)
    end = local + timedelta(minutes=INTERVIEW_MINUTES)
    return f"{local:%a} {local.day} {local:%b %Y}, {local:%H:%M}-{end:%H:%M} {OFFICE_TZ_LABEL}"
