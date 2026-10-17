"""Seed demo users and sample kudos. Idempotent: safe to run on every start."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/seed.py` as well as `python -m scripts.seed`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_settings  # noqa: E402
from app.db import connect, init_db  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.timeutil import now_iso  # noqa: E402

DEMO_USERS = [
    ("admin", "Admin User", "admin@datacom.example", "admin123!", "admin"),
    ("alice", "Alice Nguyen", "alice.nguyen@datacom.example", "alice123!", "employee"),
    ("bob", "Bob Patel", "bob.patel@datacom.example", "bob123!", "employee"),
    ("carol", "Carol Smith", "carol.smith@datacom.example", "carol123!", "employee"),
    ("dave", "Dave Kim", "dave.kim@datacom.example", "dave123!", "employee"),
]

SAMPLE_KUDOS = [
    ("alice", "bob", "Thanks for unblocking the release — you saved the sprint!"),
    ("bob", "carol", "Great facilitation in the architecture review. Clear and kind."),
    ("carol", "dave", "Appreciate you covering the on-call shift at short notice."),
    ("dave", "alice", "Your onboarding notes made my first week so much easier."),
]


def seed(db_path: str) -> None:
    init_db(db_path)
    connection = connect(db_path)
    try:
        for username, display_name, email, password, role in DEMO_USERS:
            exists = connection.execute(
                "SELECT 1 FROM users WHERE username = ?", (username,)
            ).fetchone()
            if exists:
                continue
            connection.execute(
                "INSERT INTO users "
                "(username, display_name, email, password_hash, role, is_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?)",
                (username, display_name, email, hash_password(password), role, now_iso()),
            )
        connection.commit()

        kudos_count = connection.execute("SELECT COUNT(*) FROM kudos").fetchone()[0]
        if kudos_count == 0:
            ids = {
                row["username"]: row["id"]
                for row in connection.execute("SELECT id, username FROM users")
            }
            for sender, recipient, message in SAMPLE_KUDOS:
                connection.execute(
                    "INSERT INTO kudos "
                    "(sender_id, recipient_id, message, is_visible, is_deleted, created_at) "
                    "VALUES (?, ?, ?, 1, 0, ?)",
                    (ids[sender], ids[recipient], message, now_iso()),
                )
            connection.commit()

        users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        kudos = connection.execute("SELECT COUNT(*) FROM kudos").fetchone()[0]
        print(f"Seeded {db_path}: {users} users, {kudos} kudos")
    finally:
        connection.close()


def main() -> None:
    seed(load_settings().db_path)


if __name__ == "__main__":
    main()
