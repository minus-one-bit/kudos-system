"""Application settings, loaded once per app instance."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    db_path: str = "kudos.db"
    session_cookie: str = "kudos_session"
    session_ttl_hours: int = 8
    secure_cookies: bool = False

    max_message_length: int = 500
    feed_page_size: int = 20
    feed_max_page_size: int = 50
    users_max_results: int = 200

    duplicate_window_minutes: int = 10
    max_kudos_per_hour: int = 20
    max_kudos_per_recipient_per_hour: int = 3
    max_urls_per_message: int = 2
    moderation_reason_min: int = 3
    moderation_reason_max: int = 300

    moderation_blocklist: tuple[str, ...] = field(default_factory=tuple)


def load_settings(db_path: str | None = None) -> Settings:
    """Build settings from environment variables, with *db_path* taking priority."""
    raw_blocklist = os.environ.get("KUDOS_BLOCKLIST", "")
    blocklist = tuple(
        term.strip().lower() for term in raw_blocklist.split(",") if term.strip()
    )
    return Settings(
        db_path=db_path or os.environ.get("KUDOS_DB", "kudos.db"),
        session_cookie=os.environ.get("KUDOS_SESSION_COOKIE", "kudos_session"),
        session_ttl_hours=int(os.environ.get("KUDOS_SESSION_TTL_HOURS", "8")),
        secure_cookies=_env_flag("KUDOS_SECURE_COOKIES", False),
        moderation_blocklist=blocklist,
    )
