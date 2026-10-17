"""Moderation permissions, state transitions and audit trail."""

from __future__ import annotations


def _create_kudos(client, headers, message: str = "A questionable message") -> int:
    response = client.post(
        "/api/kudos",
        json={"recipient_id": 2, "message": message},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_non_admin_cannot_moderate(client, login, auth_headers):
    login(client)
    kudos_id = _create_kudos(client, auth_headers(client))

    response = client.post(
        f"/api/admin/kudos/{kudos_id}/hide",
        json={"reason": "inappropriate"},
        headers=auth_headers(client),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_non_admin_cannot_open_the_admin_page(client, login):
    login(client)

    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 403


def test_admin_hides_and_unhides_a_kudos(client, login, auth_headers):
    login(client)
    kudos_id = _create_kudos(client, auth_headers(client))

    login(client, "admin", "admin123!")
    headers = auth_headers(client)

    hidden = client.post(
        f"/api/admin/kudos/{kudos_id}/hide",
        json={"reason": "Inappropriate language"},
        headers=headers,
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["is_visible"] is False
    assert hidden.json()["moderated_by"]["display_name"] == "Admin User"
    assert hidden.json()["reason_for_moderation"] == "Inappropriate language"

    public_feed = client.get("/api/kudos").json()
    assert all(item["id"] != kudos_id for item in public_feed["items"])

    admin_list = client.get("/api/admin/kudos").json()
    item = next(entry for entry in admin_list["items"] if entry["id"] == kudos_id)
    assert item["is_visible"] is False
    assert item["is_deleted"] is False

    restored = client.post(
        f"/api/admin/kudos/{kudos_id}/unhide",
        json={"reason": "Hidden by mistake"},
        headers=headers,
    )
    assert restored.status_code == 200
    assert restored.json()["is_visible"] is True

    public_feed = client.get("/api/kudos").json()
    assert any(item["id"] == kudos_id for item in public_feed["items"])


def test_admin_delete_is_a_soft_delete(client, login, auth_headers):
    login(client)
    kudos_id = _create_kudos(client, auth_headers(client))

    login(client, "admin", "admin123!")
    headers = auth_headers(client)

    deleted = client.request(
        "DELETE",
        f"/api/admin/kudos/{kudos_id}",
        json={"reason": "Spam and abuse"},
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["is_deleted"] is True
    assert deleted.json()["is_visible"] is False

    assert all(
        item["id"] != kudos_id for item in client.get("/api/kudos").json()["items"]
    )

    admin_list = client.get("/api/admin/kudos").json()
    item = next(entry for entry in admin_list["items"] if entry["id"] == kudos_id)
    assert item["is_deleted"] is True

    # Deleted is terminal in v1.
    again = client.post(
        f"/api/admin/kudos/{kudos_id}/hide",
        json={"reason": "Trying again"},
        headers=headers,
    )
    assert again.status_code == 404


def test_moderation_requires_a_reason(client, login, auth_headers):
    login(client)
    kudos_id = _create_kudos(client, auth_headers(client))

    login(client, "admin", "admin123!")
    response = client.post(
        f"/api/admin/kudos/{kudos_id}/hide",
        json={"reason": ""},
        headers=auth_headers(client),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_moderation_writes_an_audit_trail(client, login, auth_headers, db):
    login(client)
    kudos_id = _create_kudos(client, auth_headers(client))

    login(client, "admin", "admin123!")
    headers = auth_headers(client)
    client.post(
        f"/api/admin/kudos/{kudos_id}/hide",
        json={"reason": "First review"},
        headers=headers,
    )
    client.post(
        f"/api/admin/kudos/{kudos_id}/unhide",
        json={"reason": "Appeal upheld"},
        headers=headers,
    )

    rows = db.execute(
        "SELECT action, reason FROM moderation_audit "
        "WHERE kudos_id = ? ORDER BY id",
        (kudos_id,),
    ).fetchall()

    assert [row["action"] for row in rows] == ["hide", "unhide"]
    assert [row["reason"] for row in rows] == ["First review", "Appeal upheld"]


def test_admin_moderation_requires_csrf(client, login, auth_headers):
    login(client)
    kudos_id = _create_kudos(client, auth_headers(client))

    login(client, "admin", "admin123!")
    response = client.post(
        f"/api/admin/kudos/{kudos_id}/hide",
        json={"reason": "No CSRF header"},
        headers={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_CSRF"


def test_admin_page_lists_hidden_kudos(client, login, insert_kudos):
    insert_kudos(message="Hidden from the feed", is_visible=0)
    login(client, "admin", "admin123!")

    response = client.get("/admin")

    assert response.status_code == 200
    assert "Hidden from the feed" in response.text
    assert "Hidden" in response.text
