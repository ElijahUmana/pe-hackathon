"""Tests for the /urls CRUD and redirect endpoints."""

import json

from app.models.event import Event

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(client, username="testuser", email="testuser@example.com"):
    resp = client.post("/users", json={"username": username, "email": email})
    return resp.get_json()


def _create_url(client, url="https://example.com", user_id=None, title=None):
    payload = {"url": url}
    if user_id is not None:
        payload["user_id"] = user_id
    if title is not None:
        payload["title"] = title
    return client.post("/urls", json=payload)


# ---------------------------------------------------------------------------
# Create URL
# ---------------------------------------------------------------------------

def test_create_url_valid(client):
    resp = _create_url(client)
    assert resp.status_code == 201
    data = resp.get_json()
    assert "short_code" in data
    assert data["original_url"] == "https://example.com"
    assert data["is_active"] is True


def test_create_url_with_user(client):
    user = _create_user(client)
    resp = _create_url(client, user_id=user["id"])
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["user_id"]["id"] == user["id"]


def test_create_url_with_title(client):
    resp = _create_url(client, title="My Link")
    assert resp.status_code == 201
    assert resp.get_json()["title"] == "My Link"


def test_create_url_missing_url_field(client):
    resp = client.post("/urls", json={"title": "no url"})
    assert resp.status_code == 400


def test_create_url_empty_url(client):
    resp = client.post("/urls", json={"url": ""})
    assert resp.status_code == 400


def test_create_url_invalid_format(client):
    """Oracle Hint 5: single word like 'hello' must be rejected."""
    resp = client.post("/urls", json={"url": "hello"})
    assert resp.status_code == 400


def test_create_url_ftp_rejected(client):
    resp = client.post("/urls", json={"url": "ftp://files.example.com/file.txt"})
    assert resp.status_code == 400


def test_create_url_non_json_body(client):
    """Oracle Hint 6: plain text body must be rejected."""
    resp = client.post("/urls", data="https://example.com", content_type="text/plain")
    assert resp.status_code == 400


def test_create_url_plain_string_json(client):
    """Oracle Hint 6: a JSON string (not object) must be rejected."""
    resp = client.post(
        "/urls",
        data=json.dumps("https://example.com"),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_create_url_array_body(client):
    """Oracle Hint 6: a JSON array must be rejected."""
    resp = client.post(
        "/urls",
        data=json.dumps(["https://example.com"]),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_create_url_nonexistent_user_id(client):
    """Oracle Hint 3: nonexistent user_id must return 404."""
    resp = client.post("/urls", json={"url": "https://example.com", "user_id": 99999})
    assert resp.status_code == 404


def test_create_url_invalid_user_id_type(client):
    resp = client.post("/urls", json={"url": "https://example.com", "user_id": "abc"})
    assert resp.status_code == 400


def test_create_same_url_twice_different_short_codes(client):
    """Oracle Hint 1 (Twin's Paradox): same URL produces different short codes."""
    resp1 = _create_url(client, url="https://twin.example.com")
    resp2 = _create_url(client, url="https://twin.example.com")
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    code1 = resp1.get_json()["short_code"]
    code2 = resp2.get_json()["short_code"]
    assert code1 != code2


# ---------------------------------------------------------------------------
# Redirect
# ---------------------------------------------------------------------------

def test_redirect_existing_active_url(client):
    """Oracle Hint 2: redirect must return 302 and create an event."""
    create_resp = _create_url(client, url="https://redirect.example.com")
    short_code = create_resp.get_json()["short_code"]
    url_id = create_resp.get_json()["id"]

    resp = client.get(f"/{short_code}")
    assert resp.status_code == 302
    assert "redirect.example.com" in resp.headers["Location"]

    # An event of type "redirect" must have been created.
    redirect_events = list(
        Event.select().where(
            (Event.url_id == url_id) & (Event.event_type == "redirect")
        )
    )
    assert len(redirect_events) == 1


def test_redirect_nonexistent_short_code(client):
    resp = client.get("/ZZZZZZ")
    assert resp.status_code == 404
    # No redirect event should exist for a nonexistent code.
    redirect_events = list(
        Event.select().where(Event.event_type == "redirect")
    )
    assert len(redirect_events) == 0


def test_redirect_creates_multiple_events(client):
    """Oracle Hint 2: each redirect creates a separate event."""
    create_resp = _create_url(client, url="https://multi.example.com")
    short_code = create_resp.get_json()["short_code"]
    url_id = create_resp.get_json()["id"]

    client.get(f"/{short_code}")
    client.get(f"/{short_code}")
    client.get(f"/{short_code}")

    redirect_events = list(
        Event.select().where(
            (Event.url_id == url_id) & (Event.event_type == "redirect")
        )
    )
    assert len(redirect_events) == 3


# ---------------------------------------------------------------------------
# Delete (soft delete)
# ---------------------------------------------------------------------------

def test_delete_url_soft_delete(client):
    create_resp = _create_url(client, url="https://softdel.example.com")
    url_id = create_resp.get_json()["id"]

    resp = client.delete(f"/urls/{url_id}")
    assert resp.status_code == 204

    # URL still exists but is_active is False.
    get_resp = client.get(f"/urls/{url_id}")
    assert get_resp.status_code == 200
    assert get_resp.get_json()["is_active"] is False


def test_redirect_deleted_url_returns_404(client):
    """Oracle Hint 4 (Slumbering Guide): inactive URL returns 404, no event."""
    create_resp = _create_url(client, url="https://deadlink.example.com")
    short_code = create_resp.get_json()["short_code"]
    url_id = create_resp.get_json()["id"]

    client.delete(f"/urls/{url_id}")

    resp = client.get(f"/{short_code}")
    assert resp.status_code == 404

    # No redirect event should have been created for the inactive URL.
    redirect_events = list(
        Event.select().where(
            (Event.url_id == url_id) & (Event.event_type == "redirect")
        )
    )
    assert len(redirect_events) == 0


def test_delete_nonexistent_url(client):
    resp = client.delete("/urls/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update URL
# ---------------------------------------------------------------------------

def test_update_url_original(client):
    create_resp = _create_url(client, url="https://old.example.com")
    url_id = create_resp.get_json()["id"]
    resp = client.put(f"/urls/{url_id}", json={"url": "https://new.example.com"})
    assert resp.status_code == 200
    assert resp.get_json()["original_url"] == "https://new.example.com"


def test_update_url_title(client):
    create_resp = _create_url(client, url="https://titled.example.com")
    url_id = create_resp.get_json()["id"]
    resp = client.put(f"/urls/{url_id}", json={"title": "New Title"})
    assert resp.status_code == 200
    assert resp.get_json()["title"] == "New Title"


def test_update_url_is_active(client):
    create_resp = _create_url(client, url="https://toggle.example.com")
    url_id = create_resp.get_json()["id"]
    resp = client.put(f"/urls/{url_id}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.get_json()["is_active"] is False


def test_update_url_invalid_url(client):
    create_resp = _create_url(client, url="https://valid.example.com")
    url_id = create_resp.get_json()["id"]
    resp = client.put(f"/urls/{url_id}", json={"url": "not-a-url"})
    assert resp.status_code == 400


def test_update_url_invalid_is_active(client):
    create_resp = _create_url(client, url="https://boolcheck.example.com")
    url_id = create_resp.get_json()["id"]
    resp = client.put(f"/urls/{url_id}", json={"is_active": "yes"})
    assert resp.status_code == 400


def test_update_nonexistent_url(client):
    resp = client.put("/urls/99999", json={"url": "https://ghost.example.com"})
    assert resp.status_code == 404


def test_update_url_non_json(client):
    create_resp = _create_url(client, url="https://nonjson.example.com")
    url_id = create_resp.get_json()["id"]
    resp = client.put(f"/urls/{url_id}", data="text", content_type="text/plain")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# List URLs
# ---------------------------------------------------------------------------

def test_list_urls_empty(client):
    resp = client.get("/urls")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_list_urls_returns_created(client):
    _create_url(client, url="https://list1.example.com")
    _create_url(client, url="https://list2.example.com")
    resp = client.get("/urls")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 2


# ---------------------------------------------------------------------------
# Get URL by ID
# ---------------------------------------------------------------------------

def test_get_url_by_id(client):
    create_resp = _create_url(client, url="https://getbyid.example.com")
    url_id = create_resp.get_json()["id"]
    resp = client.get(f"/urls/{url_id}")
    assert resp.status_code == 200
    assert resp.get_json()["original_url"] == "https://getbyid.example.com"


def test_get_nonexistent_url(client):
    resp = client.get("/urls/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# URL stats
# ---------------------------------------------------------------------------

def test_url_stats_no_redirects(client):
    create_resp = _create_url(client, url="https://stats.example.com")
    url_id = create_resp.get_json()["id"]
    resp = client.get(f"/urls/{url_id}/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["redirect_count"] == 0


def test_url_stats_with_redirects(client):
    create_resp = _create_url(client, url="https://statsfull.example.com")
    url_id = create_resp.get_json()["id"]
    short_code = create_resp.get_json()["short_code"]

    client.get(f"/{short_code}")
    client.get(f"/{short_code}")

    resp = client.get(f"/urls/{url_id}/stats")
    assert resp.status_code == 200
    assert resp.get_json()["redirect_count"] == 2


def test_url_stats_nonexistent(client):
    resp = client.get("/urls/99999/stats")
    assert resp.status_code == 404
