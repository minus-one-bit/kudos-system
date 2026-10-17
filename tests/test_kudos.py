"""Kudos creation, feed, validation and abuse-control tests."""

from __future__ import annotations


def _create(
    client,
    headers,
    recipient_id: int = 2,
    message: str = "Thanks for the help!",
):
    return client.post(
        "/api/kudos",
        json={"recipient_id": recipient_id, "message": message},
        headers=headers,
    )


def test_users_excludes_the_caller(client, login):
    login(client)

    items = client.get("/api/users").json()["items"]
    ids = {user["id"] for user in items}

    assert 1 not in ids
    assert {2, 3, 4} <= ids


def test_users_can_be_filtered(client, login):
    login(client)

    items = client.get("/api/users?q=bob").json()["items"]

    assert [user["username"] for user in items] == ["bob"]


def test_create_kudos_appears_in_the_feed(client, login, auth_headers):
    login(client)
    headers = auth_headers(client)

    response = _create(client, headers)

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["sender"]["id"] == 1
    assert created["recipient"]["id"] == 2
    assert created["message"] == "Thanks for the help!"

    feed = client.get("/api/kudos").json()
    assert feed["total"] == 1
    assert feed["items"][0]["message"] == "Thanks for the help!"
    assert feed["items"][0]["sender"]["display_name"] == "Alice Nguyen"
    assert feed["items"][0]["recipient"]["display_name"] == "Bob Patel"


def test_empty_message_is_rejected(client, login, auth_headers):
    login(client)

    response = _create(client, auth_headers(client), message="   ")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_message_over_500_characters_is_rejected(client, login, auth_headers):
    login(client)

    response = _create(client, auth_headers(client), message="x" * 501)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_message_of_exactly_500_characters_is_accepted(client, login, auth_headers):
    login(client)

    response = _create(client, auth_headers(client), message="x" * 500)

    assert response.status_code == 201


def test_self_kudos_is_rejected(client, login, auth_headers):
    login(client)

    response = _create(client, auth_headers(client), recipient_id=1)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SELF_KUDOS_NOT_ALLOWED"


def test_unknown_recipient_is_rejected(client, login, auth_headers):
    login(client)

    response = _create(client, auth_headers(client), recipient_id=999)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_RECIPIENT"


def test_inactive_recipient_is_rejected(client, login, auth_headers, db):
    login(client)
    db.execute("UPDATE users SET is_active = 0 WHERE id = 2")
    db.commit()

    response = _create(client, auth_headers(client), recipient_id=2)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_RECIPIENT"


def test_duplicate_kudos_is_rejected(client, login, auth_headers):
    login(client)
    headers = auth_headers(client)

    assert _create(client, headers).status_code == 201
    duplicate = _create(client, headers)

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_KUDOS"


def test_csrf_header_is_required(client, login):
    login(client)

    response = _create(client, headers={})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_CSRF"


def test_url_flood_is_rejected(client, login, auth_headers):
    login(client)

    response = _create(
        client,
        auth_headers(client),
        message="Look at http://a.example http://b.example http://c.example",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SPAM_SUSPECTED"


def test_rate_limit_per_user(client, login, auth_headers, insert_kudos):
    login(client)
    for index in range(20):
        insert_kudos(message=f"Earlier kudos {index}")

    response = _create(client, auth_headers(client), message="One more")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert response.headers["Retry-After"] == "3600"


def test_rate_limit_per_recipient(client, login, auth_headers, insert_kudos):
    login(client)
    for index in range(3):
        insert_kudos(recipient_id=2, message=f"To Bob {index}")

    response = _create(
        client, auth_headers(client), recipient_id=2, message="One more for Bob"
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


def test_feed_pagination(client, login, insert_kudos):
    login(client)
    for index in range(25):
        insert_kudos(message=f"Kudos number {index}")

    first_page = client.get("/api/kudos?limit=10&offset=0").json()
    last_page = client.get("/api/kudos?limit=10&offset=20").json()

    assert first_page["total"] == 25
    assert len(first_page["items"]) == 10
    assert len(last_page["items"]) == 5
    assert first_page["limit"] == 10


def test_feed_limit_is_capped(client, login):
    login(client)

    body = client.get("/api/kudos?limit=9999").json()

    assert body["limit"] == 50


def test_xss_payload_is_stored_and_rendered_as_text(client, login, auth_headers):
    login(client)
    payload = '<script>alert("xss")</script>'

    response = _create(client, auth_headers(client), message=payload)

    assert response.status_code == 201
    assert response.json()["message"] == payload

    html = client.get("/").text
    assert payload not in html
    assert "&lt;script&gt;" in html


def test_hidden_kudos_is_not_in_the_public_feed(client, login, insert_kudos):
    login(client)
    visible_id = insert_kudos(message="Visible")
    insert_kudos(message="Hidden", is_visible=0)

    feed = client.get("/api/kudos").json()

    assert [item["id"] for item in feed["items"]] == [visible_id]


def test_form_submission_works_without_javascript(client, login, csrf):
    login(client)

    response = client.post(
        "/kudos",
        data={
            "recipient_id": 2,
            "message": "Submitted by a plain form",
            "csrf_token": csrf(client),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    feed = client.get("/api/kudos").json()
    assert feed["items"][0]["message"] == "Submitted by a plain form"


def test_form_submission_requires_csrf(client, login):
    login(client)

    response = client.post(
        "/kudos",
        data={"recipient_id": 2, "message": "No token"},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_form_submission_renders_validation_errors(client, login, csrf):
    login(client)

    response = client.post(
        "/kudos",
        data={"recipient_id": 2, "message": "   ", "csrf_token": csrf(client)},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert "Message cannot be empty" in response.text
    assert 'value="2"' in response.text
    assert "selected" in response.text

