"""UTC timestamp helpers.

All database timestamps are ISO-8601 UTC strings, which sort correctly and are
unambiguous when the service runs in more than one timezone.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def now_iso() -> str:
    return to_iso(utc_now())


def iso_minus(**kwargs: float) -> str:
    """ISO timestamp for `now - timedelta(**kwargs)` (e.g. minutes=10)."""
    return to_iso(utc_now() - timedelta(**kwargs))


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)
