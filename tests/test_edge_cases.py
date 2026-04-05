"""
Edge-case tests targeting all Oracle hidden test scenarios.

Each test is named after the Oracle hint it validates.
"""

import json

from app.models.event import Event

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_url(client, url="https://example.com", user_id=None):
    payload = {"url": url}
    if user_id is not None:
        payload["user_id"] = user_id
    return client.post("/urls", json=payload)


def _create_user(client, username, email):
    return client.post("/users", json={"username": username, "email": email})


# ---------------------------------------------------------------------------
# Oracle Hint 1 - Twin's Paradox
# ---------------------------------------------------------------------------

def test_twins_paradox_same_url_different_codes(client):
    """Submitting the exact same URL twice must produce two different short codes."""
    target = "https://twins.example.com"
    r1 = _create_url(client, url=target)
    r2 = _create_url(client, url=target)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.get_json()["short_code"] != r2.get_json()["short_code"]


def test_twins_paradox_different_ids(client):
    """Each submission creates a distinct URL record."""
    target = "https://twins2.example.com"
    r1 = _create_url(client, url=target)
    r2 = _create_url(client, url=target)
    assert r1.get_json()["id"] != r2.get_json()["id"]


# ---------------------------------------------------------------------------
# Oracle Hint 2 - Unseen Observer
# ---------------------------------------------------------------------------

def test_unseen_observer_redirect_creates_event(client):
    """A redirect MUST create a redirect event."""
    resp = _create_url(client, url="https://observer.example.com")
    url_id = resp.get_json()["id"]
    short_code = resp.get_json()["short_code"]

    client.get(f"/{short_code}")

    events = list(
        Event.select().where(
            (Event.url_id == url_id) & (Event.event_type == "redirect")
        )
    )
    assert len(events) == 1


def test_unseen_observer_multiple_redirects_multiple_events(client):
    """Each redirect creates its own event."""
    resp = _create_url(client, url="https://multi-observer.example.com")
    url_id = resp.get_json()["id"]
    short_code = resp.get_json()["short_code"]

    for _ in range(5):
        client.get(f"/{short_code}")

    events = list(
        Event.select().where(
            (Event.url_id == url_id) & (Event.event_type == "redirect")
        )
    )
    assert len(events) == 5


def test_unseen_observer_event_has_details(client):
    """Redirect events should record ip and user_agent in details."""
    resp = _create_url(client, url="https://detail-observer.example.com")
    url_id = resp.get_json()["id"]
    short_code = resp.get_json()["short_code"]

    client.get(f"/{short_code}")

    event = Event.select().where(
        (Event.url_id == url_id) & (Event.event_type == "redirect")
    ).get()
    details = json.loads(event.details)
    assert "ip" in details
    assert "user_agent" in details


# ---------------------------------------------------------------------------
# Oracle Hint 3 - Unwitting Stranger
# ---------------------------------------------------------------------------

def test_unwitting_stranger_missing_url_field(client):
    """Missing required 'url' field must return 400."""
    resp = client.post("/urls", json={"title": "no url here"})
    assert resp.status_code == 400


def test_unwitting_stranger_nonexistent_user_id(client):
    """Providing a user_id that doesn't exist must return 404."""
    resp = _create_url(client, url="https://stranger.example.com", user_id=99999)
    assert resp.status_code == 404


def test_unwitting_stranger_missing_username_for_user(client):
    """Creating a user without a username must return 400."""
    resp = client.post("/users", json={"email": "nobody@example.com"})
    assert resp.status_code == 400


def test_unwitting_stranger_missing_email_for_user(client):
    """Creating a user without email must return 400."""
    resp = client.post("/users", json={"username": "nobody"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Oracle Hint 4 - Slumbering Guide
# ---------------------------------------------------------------------------

def test_slumbering_guide_inactive_url_404(client):
    """A soft-deleted (inactive) URL must return 404 on redirect."""
    resp = _create_url(client, url="https://sleeper.example.com")
    url_id = resp.get_json()["id"]
    short_code = resp.get_json()["short_code"]

    client.delete(f"/urls/{url_id}")

    redirect_resp = client.get(f"/{short_code}")
    assert redirect_resp.status_code == 404


def test_slumbering_guide_no_event_for_inactive(client):
    """No redirect event must be logged for an inactive URL."""
    resp = _create_url(client, url="https://noevent-sleeper.example.com")
    url_id = resp.get_json()["id"]
    short_code = resp.get_json()["short_code"]

    client.delete(f"/urls/{url_id}")
    client.get(f"/{short_code}")

    redirect_events = list(
        Event.select().where(
            (Event.url_id == url_id) & (Event.event_type == "redirect")
        )
    )
    assert len(redirect_events) == 0


def test_slumbering_guide_deactivate_via_update(client):
    """Setting is_active=False via PUT also makes redirect return 404."""
    resp = _create_url(client, url="https://deactivate-put.example.com")
    url_id = resp.get_json()["id"]
    short_code = resp.get_json()["short_code"]

    client.put(f"/urls/{url_id}", json={"is_active": False})

    redirect_resp = client.get(f"/{short_code}")
    assert redirect_resp.status_code == 404


# ---------------------------------------------------------------------------
# Oracle Hint 5 - Deceitful Scroll
# ---------------------------------------------------------------------------

def test_deceitful_scroll_single_word_rejected(client):
    """A single word like 'hello' is not a valid URL and must be rejected."""
    resp = client.post("/urls", json={"url": "hello"})
    assert resp.status_code == 400


def test_deceitful_scroll_no_scheme_rejected(client):
    resp = client.post("/urls", json={"url": "example.com"})
    assert resp.status_code == 400


def test_deceitful_scroll_ftp_rejected(client):
    resp = client.post("/urls", json={"url": "ftp://files.example.com"})
    assert resp.status_code == 400


def test_deceitful_scroll_empty_rejected(client):
    resp = client.post("/urls", json={"url": ""})
    assert resp.status_code == 400


def test_deceitful_scroll_whitespace_rejected(client):
    resp = client.post("/urls", json={"url": "   "})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Oracle Hint 6 - Fractured Vessel
# ---------------------------------------------------------------------------

def test_fractured_vessel_plain_text_body(client):
    """Plain text body (not JSON) must be rejected."""
    resp = client.post("/urls", data="https://example.com", content_type="text/plain")
    assert resp.status_code == 400


def test_fractured_vessel_json_string_body(client):
    """A JSON string (not an object) must be rejected."""
    resp = client.post(
        "/urls",
        data=json.dumps("https://example.com"),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_fractured_vessel_json_array_body(client):
    """A JSON array must be rejected."""
    resp = client.post(
        "/urls",
        data=json.dumps(["https://example.com"]),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_fractured_vessel_empty_body(client):
    """Empty body with JSON content type must be rejected."""
    resp = client.post("/urls", data="", content_type="application/json")
    assert resp.status_code == 400


def test_fractured_vessel_form_encoded_body(client):
    """Form-encoded body must be rejected."""
    resp = client.post(
        "/urls",
        data="url=https://example.com",
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 400


def test_fractured_vessel_users_plain_text(client):
    """Plain text to /users must also be rejected."""
    resp = client.post("/users", data="some text", content_type="text/plain")
    assert resp.status_code == 400
