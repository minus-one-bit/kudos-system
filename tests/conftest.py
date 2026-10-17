"""Shared pytest fixtures: a fresh app, seeded users, helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import connect  # noqa: E402
from app.main import create_app  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.timeutil import now_iso  # noqa: E402

# Explicit ids keep the tests readable.
USERS = [
    (1, "alice", "Alice Nguyen", "alice@example.com", "alice123!", "employee"),
    (2, "bob", "Bob Patel", "bob@example.com", "bob123!", "employee"),
    (3, "carol", "Carol Smith", "carol@example.com", "carol123!", "employee"),
    (4, "admin", "Admin User", "admin@example.com", "admin123!", "admin"),
]


def _seed_users(db_path: str) -> None:
    connection = connect(db_path)
    try:
        for user_id, username, display_name, email, password, role in USERS:
            connection.execute(
                "INSERT INTO users "
                "(id, username, display_name, email, password_hash, role, "
                " is_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                (
                    user_id,
                    username,
                    display_name,
                    email,
                    hash_password(password),
                    role,
                    now_iso(),
                ),
            )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture()
def app(tmp_path):
    application = create_app(str(tmp_path / "test.db"))
    _seed_users(application.state.db_path)
    return application


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db(app):
    connection = connect(app.state.db_path)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture()
def login():
    def _login(client: TestClient, username: str = "alice", password: str = "alice123!"):
        response = client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        return response

    return _login


@pytest.fixture()
def csrf():
    def _csrf(client: TestClient) -> str:
        response = client.get("/api/me")
        assert response.status_code == 200, response.text
        return response.json()["csrf_token"]

    return _csrf


@pytest.fixture()
def auth_headers(csrf):
    def _headers(client: TestClient) -> dict[str, str]:
        return {"X-CSRF-Token": csrf(client)}

    return _headers


@pytest.fixture()
def insert_kudos(db):
    def _insert(
        sender_id: int = 1,
        recipient_id: int = 2,
        message: str = "Thanks!",
        created_at: str | None = None,
        is_visible: int = 1,
    ) -> int:
        cursor = db.execute(
            "INSERT INTO kudos "
            "(sender_id, recipient_id, message, is_visible, is_deleted, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (sender_id, recipient_id, message, is_visible, created_at or now_iso()),
        )
        db.commit()
        return int(cursor.lastrowid)

    return _insert
