"""Domain logic: users, sessions, kudos, moderation and abuse controls."""

from __future__ import annotations

import re
import sqlite3
from datetime import timedelta
from typing import Any

from .config import Settings
from .security import (
    hash_password,
    new_csrf_token,
    new_token,
    verify_password,
)
from .timeutil import iso_minus, now_iso, parse_iso, to_iso, utc_now

URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)

# Used to keep the login response time similar for unknown usernames.
_DUMMY_PASSWORD_HASH = hash_password("this-password-is-never-valid")


class ServiceError(Exception):
    """A domain error that maps directly to an API response."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers or {}


# --------------------------------------------------------------------------- users


def _user_dict(row: sqlite3.Row, include_email: bool = False) -> dict[str, Any]:
    user = {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
    }
    if include_email:
        user["email"] = row["email"]
    return user


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)
    ).fetchone()
    return _user_dict(row) if row else None


def list_users(
    conn: sqlite3.Connection,
    exclude_id: int,
    query: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT * FROM users WHERE is_active = 1 AND id <> ?"
    )
    params: list[Any] = [exclude_id]
    if query:
        sql += " AND (lower(display_name) LIKE ? OR lower(username) LIKE ?)"
        needle = f"%{query.strip().lower()}%"
        params.extend([needle, needle])
    sql += " ORDER BY display_name COLLATE NOCASE LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_user_dict(row) for row in rows]


def authenticate(
    conn: sqlite3.Connection, username: str, password: str
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1",
        ((username or "").strip(),),
    ).fetchone()

    stored_hash = row["password_hash"] if row else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(password or "", stored_hash)
    if row is None or not password_ok:
        raise ServiceError(
            "INVALID_CREDENTIALS", "Invalid username or password.", 401
        )
    return _user_dict(row, include_email=True)


# --------------------------------------------------------------------------- sessions


def create_session(
    conn: sqlite3.Connection, user_id: int, ttl_hours: int
) -> tuple[str, str]:
    """Create a server-side session and return ``(token, csrf_token)``."""
    token = new_token()
    csrf_token = new_csrf_token()
    now = utc_now()
    conn.execute(
        "INSERT INTO sessions (token, user_id, csrf_token, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            token,
            user_id,
            csrf_token,
            to_iso(now),
            to_iso(now + timedelta(hours=ttl_hours)),
        ),
    )
    conn.commit()
    return token, csrf_token


def delete_session(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def get_session_user(
    conn: sqlite3.Connection, token: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve a session cookie to ``(user, csrf_token)``.

    Expired sessions are deleted lazily on access.
    """
    row = conn.execute(
        "SELECT u.id, u.username, u.display_name, u.email, u.role, "
        "       s.csrf_token, s.expires_at "
        "FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token = ? AND u.is_active = 1",
        (token,),
    ).fetchone()
    if row is None:
        return None, None
    try:
        expired = parse_iso(row["expires_at"]) <= utc_now()
    except ValueError:
        expired = True
    if expired:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        return None, None
    return _user_dict(row), row["csrf_token"]


def cleanup_expired_sessions(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now_iso(),))
    conn.commit()


# --------------------------------------------------------------------------- kudos

KUDOS_SELECT = """
SELECT k.id, k.message, k.created_at, k.is_visible, k.is_deleted,
       k.moderated_by, k.moderated_at, k.reason_for_moderation,
       s.id AS sender_id, s.display_name AS sender_name,
       r.id AS recipient_id, r.display_name AS recipient_name,
       m.display_name AS moderator_name
FROM kudos k
JOIN users s ON s.id = k.sender_id
JOIN users r ON r.id = k.recipient_id
LEFT JOIN users m ON m.id = k.moderated_by
"""

FEED_WHERE = " WHERE k.is_deleted = 0 AND k.is_visible = 1"


def _display_time(value: str | None) -> str | None:
    if not value:
        return None
    return value[:16].replace("T", " ") + " UTC"


def _kudos_dict(row: sqlite3.Row, include_moderation: bool = False) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": row["id"],
        "sender": {"id": row["sender_id"], "display_name": row["sender_name"]},
        "recipient": {
            "id": row["recipient_id"],
            "display_name": row["recipient_name"],
        },
        "message": row["message"],
        "created_at": row["created_at"],
        "created_at_display": _display_time(row["created_at"]),
    }
    if include_moderation:
        item.update(
            {
                "is_visible": bool(row["is_visible"]),
                "is_deleted": bool(row["is_deleted"]),
                "moderated_by": (
                    {
                        "id": row["moderated_by"],
                        "display_name": row["moderator_name"],
                    }
                    if row["moderated_by"]
                    else None
                ),
                "moderated_at": row["moderated_at"],
                "moderated_at_display": _display_time(row["moderated_at"]),
                "reason_for_moderation": row["reason_for_moderation"],
            }
        )
    return item


def list_feed(
    conn: sqlite3.Connection, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    total = conn.execute(
        "SELECT COUNT(*) FROM kudos WHERE is_deleted = 0 AND is_visible = 1"
    ).fetchone()[0]
    rows = conn.execute(
        KUDOS_SELECT
        + FEED_WHERE
        + " ORDER BY k.created_at DESC, k.id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [_kudos_dict(row) for row in rows], total


def list_kudos_admin(
    conn: sqlite3.Connection, limit: int, offset: int, include_deleted: bool
) -> tuple[list[dict[str, Any]], int]:
    where = "" if include_deleted else " WHERE k.is_deleted = 0"
    total = conn.execute("SELECT COUNT(*) FROM kudos" + where).fetchone()[0]
    rows = conn.execute(
        KUDOS_SELECT
        + where
        + " ORDER BY k.created_at DESC, k.id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [_kudos_dict(row, include_moderation=True) for row in rows], total


def get_kudos(
    conn: sqlite3.Connection, kudos_id: int, include_moderation: bool = False
) -> dict[str, Any] | None:
    row = conn.execute(KUDOS_SELECT + " WHERE k.id = ?", (kudos_id,)).fetchone()
    return _kudos_dict(row, include_moderation) if row else None


def _validate_message(message: str, settings: Settings) -> str:
    cleaned = (message or "").strip()
    if not cleaned:
        raise ServiceError(
            "VALIDATION_ERROR", "Message cannot be empty.", 422
        )
    if len(cleaned) > settings.max_message_length:
        raise ServiceError(
            "VALIDATION_ERROR",
            f"Message must be at most {settings.max_message_length} characters.",
            422,
        )
    lowered = cleaned.lower()
    for term in settings.moderation_blocklist:
        if term and term in lowered:
            raise ServiceError(
                "PROHIBITED_LANGUAGE",
                "Message contains language that is not allowed.",
                422,
            )
    if len(URL_PATTERN.findall(cleaned)) > settings.max_urls_per_message:
        raise ServiceError(
            "SPAM_SUSPECTED",
            "Message contains too many links and looks like spam.",
            422,
        )
    return cleaned


def create_kudos(
    conn: sqlite3.Connection,
    sender: dict[str, Any],
    recipient_id: int,
    message: str,
    settings: Settings,
) -> dict[str, Any]:
    cleaned = _validate_message(message, settings)

    recipient = conn.execute(
        "SELECT id FROM users WHERE id = ? AND is_active = 1", (recipient_id,)
    ).fetchone()
    if recipient is None:
        raise ServiceError(
            "INVALID_RECIPIENT", "The selected colleague is not available.", 422
        )
    if recipient_id == sender["id"]:
        raise ServiceError(
            "SELF_KUDOS_NOT_ALLOWED", "You cannot give kudos to yourself.", 422
        )

    duplicate_cutoff = iso_minus(minutes=settings.duplicate_window_minutes)
    duplicate = conn.execute(
        "SELECT 1 FROM kudos "
        "WHERE sender_id = ? AND recipient_id = ? AND message = ? "
        "  AND created_at >= ? LIMIT 1",
        (sender["id"], recipient_id, cleaned, duplicate_cutoff),
    ).fetchone()
    if duplicate:
        raise ServiceError(
            "DUPLICATE_KUDOS",
            "You have already sent this kudos recently.",
            409,
        )

    hour_cutoff = iso_minus(hours=1)
    sent_last_hour = conn.execute(
        "SELECT COUNT(*) FROM kudos WHERE sender_id = ? AND created_at >= ?",
        (sender["id"], hour_cutoff),
    ).fetchone()[0]
    if sent_last_hour >= settings.max_kudos_per_hour:
        raise ServiceError(
            "RATE_LIMITED",
            "You have sent too many kudos in the last hour. Please try again later.",
            429,
            headers={"Retry-After": "3600"},
        )

    sent_to_recipient = conn.execute(
        "SELECT COUNT(*) FROM kudos "
        "WHERE sender_id = ? AND recipient_id = ? AND created_at >= ?",
        (sender["id"], recipient_id, hour_cutoff),
    ).fetchone()[0]
    if sent_to_recipient >= settings.max_kudos_per_recipient_per_hour:
        raise ServiceError(
            "RATE_LIMITED",
            "You have sent too many kudos to this colleague in the last hour.",
            429,
            headers={"Retry-After": "3600"},
        )

    cursor = conn.execute(
        "INSERT INTO kudos "
        "(sender_id, recipient_id, message, is_visible, is_deleted, created_at) "
        "VALUES (?, ?, ?, 1, 0, ?)",
        (sender["id"], recipient_id, cleaned, now_iso()),
    )
    conn.commit()
    created = get_kudos(conn, cursor.lastrowid)
    assert created is not None
    return created


# ---------------------------------------------------------------------- moderation


def moderate_kudos(
    conn: sqlite3.Connection,
    kudos_id: int,
    admin: dict[str, Any],
    action: str,
    reason: str,
    settings: Settings,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, is_visible, is_deleted FROM kudos WHERE id = ?", (kudos_id,)
    ).fetchone()
    if row is None or row["is_deleted"]:
        raise ServiceError("NOT_FOUND", "Kudos not found.", 404)

    cleaned_reason = (reason or "").strip()
    if action in {"hide", "delete"}:
        if len(cleaned_reason) < settings.moderation_reason_min:
            raise ServiceError(
                "VALIDATION_ERROR",
                f"A reason of at least {settings.moderation_reason_min} characters is required.",
                422,
            )
        if len(cleaned_reason) > settings.moderation_reason_max:
            raise ServiceError(
                "VALIDATION_ERROR",
                f"The reason must be at most {settings.moderation_reason_max} characters.",
                422,
            )
    elif action == "unhide":
        if len(cleaned_reason) > settings.moderation_reason_max:
            raise ServiceError(
                "VALIDATION_ERROR",
                f"The reason must be at most {settings.moderation_reason_max} characters.",
                422,
            )
    else:  # pragma: no cover - guarded by the router
        raise ValueError(f"Unknown moderation action: {action}")

    if action == "hide":
        new_visible, new_deleted = 0, 0
    elif action == "unhide":
        new_visible, new_deleted = 1, 0
    else:  # delete
        new_visible, new_deleted = 0, 1

    timestamp = now_iso()
    conn.execute(
        "UPDATE kudos SET is_visible = ?, is_deleted = ?, moderated_by = ?, "
        "moderated_at = ?, reason_for_moderation = ? WHERE id = ?",
        (
            new_visible,
            new_deleted,
            admin["id"],
            timestamp,
            cleaned_reason or None,
            kudos_id,
        ),
    )
    conn.execute(
        "INSERT INTO moderation_audit "
        "(kudos_id, admin_id, action, reason, created_at) VALUES (?, ?, ?, ?, ?)",
        (kudos_id, admin["id"], action, cleaned_reason or None, timestamp),
    )
    conn.commit()

    updated = get_kudos(conn, kudos_id, include_moderation=True)
    assert updated is not None
    return updated
