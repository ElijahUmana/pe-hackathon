"""Tests for user endpoint edge cases that affect coverage of users.py."""


def _create_user(client, username, email):
    return client.post("/users", json={"username": username, "email": email})


def test_create_user_integrity_error_generic_fallback(client):
    """When IntegrityError message doesn't mention username or email specifically,
    the generic 'already exists' response is returned."""
    _create_user(client, "unique1", "unique1@example.com")
    # Duplicate username hits the 'username' branch
    resp = _create_user(client, "unique1", "different@example.com")
    assert resp.status_code == 409
    assert "error" in resp.get_json()


def test_create_user_duplicate_email_returns_409(client):
    """Duplicate email triggers the 'email' branch of IntegrityError handling."""
    _create_user(client, "emailuser1", "dup@example.com")
    resp = _create_user(client, "emailuser2", "dup@example.com")
    assert resp.status_code == 409
    assert "error" in resp.get_json()


def test_create_user_non_dict_json_body(client):
    """Sending a JSON array to /users POST returns 400."""
    import json

    resp = client.post(
        "/users",
        data=json.dumps(["username", "email"]),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_update_user_empty_email(client):
    """Updating a user with an empty email string returns 400."""
    create_resp = _create_user(client, "emptyemailupd", "emptyemailupd@example.com")
    user_id = create_resp.get_json()["id"]
    resp = client.put(f"/users/{user_id}", json={"email": ""})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_update_user_duplicate_username_returns_409(client):
    """Updating a user's username to a taken value returns 409."""
    _create_user(client, "taken_name", "taken1@example.com")
    create_resp = _create_user(client, "other_name", "taken2@example.com")
    user_id = create_resp.get_json()["id"]

    resp = client.put(f"/users/{user_id}", json={"username": "taken_name"})
    assert resp.status_code == 409
    assert "error" in resp.get_json()
