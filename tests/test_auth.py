"""Authentication, session and authorization tests."""

from __future__ import annotations


def test_login_success_and_me(client, login):
    login(client)

    response = client.get("/api/me")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "alice"
    assert body["user"]["display_name"] == "Alice Nguyen"
    assert body["user"]["role"] == "employee"
    assert body["csrf_token"]


def test_login_wrong_password(client):
    response = client.post(
        "/login",
        data={"username": "alice", "password": "not-the-password"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert "Invalid username or password" in response.text


def test_login_unknown_user(client):
    response = client.post(
        "/login",
        data={"username": "nobody", "password": "whatever"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert "Invalid username or password" in response.text


def test_dashboard_requires_login(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_api_requires_authentication(client):
    assert client.get("/api/kudos").status_code == 401
    assert client.get("/api/users").status_code == 401


def test_logout_invalidates_the_session(client, login, csrf):
    login(client)
    token = csrf(client)

    response = client.post(
        "/logout", data={"csrf_token": token}, follow_redirects=False
    )

    assert response.status_code == 303
    assert client.get("/api/me").status_code == 401


def test_logout_requires_a_valid_csrf_token(client, login):
    login(client)

    response = client.post(
        "/logout", data={"csrf_token": "wrong"}, follow_redirects=False
    )

    assert response.status_code == 403


def test_expired_session_is_rejected(client, login, db):
    login(client)
    db.execute(
        "UPDATE sessions SET expires_at = ?", ("2000-01-01T00:00:00+00:00",)
    )
    db.commit()

    assert client.get("/api/me").status_code == 401


def test_password_is_never_returned(client, login):
    login(client)

    body = client.get("/api/me").json()

    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]
