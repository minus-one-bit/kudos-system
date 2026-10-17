"""SQLite connection helpers and schema initialisation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'employee'
                  CHECK (role IN ('employee', 'admin')),
    is_active     INTEGER NOT NULL DEFAULT 1
                  CHECK (is_active IN (0, 1)),
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_active
    ON users (is_active, display_name);

CREATE TABLE IF NOT EXISTS kudos (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id             INTEGER NOT NULL REFERENCES users(id),
    recipient_id          INTEGER NOT NULL REFERENCES users(id),
    message               TEXT NOT NULL
                          CHECK (length(message) BETWEEN 1 AND 500),
    is_visible            INTEGER NOT NULL DEFAULT 1
                          CHECK (is_visible IN (0, 1)),
    is_deleted            INTEGER NOT NULL DEFAULT 0
                          CHECK (is_deleted IN (0, 1)),
    moderated_by          INTEGER REFERENCES users(id),
    moderated_at          TEXT,
    reason_for_moderation TEXT
                          CHECK (reason_for_moderation IS NULL
                                 OR length(reason_for_moderation) <= 300),
    created_at            TEXT NOT NULL,
    CHECK (sender_id <> recipient_id)
);

CREATE INDEX IF NOT EXISTS idx_kudos_feed
    ON kudos (is_deleted, is_visible, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_kudos_sender_time
    ON kudos (sender_id, created_at);

CREATE INDEX IF NOT EXISTS idx_kudos_recipient_time
    ON kudos (recipient_id, created_at);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires
    ON sessions (expires_at);

CREATE TABLE IF NOT EXISTS moderation_audit (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kudos_id   INTEGER NOT NULL REFERENCES kudos(id),
    admin_id   INTEGER NOT NULL REFERENCES users(id),
    action     TEXT NOT NULL CHECK (action IN ('hide', 'unhide', 'delete')),
    reason     TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_kudos
    ON moderation_audit (kudos_id, created_at DESC);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with foreign keys enabled and row access by name.

    ``check_same_thread=False`` is required because FastAPI runs synchronous
    dependencies and route handlers in a worker-thread pool; the connection is
    still used by only one request at a time.
    """
    parent = Path(db_path).expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: str) -> None:
    """Create the schema if it does not exist. Safe to call on every start."""
    connection = connect(db_path)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()
