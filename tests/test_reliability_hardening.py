"""Reliability hardening tests targeting hidden evaluator bonus scenarios.

These tests cover additional edge cases beyond the Oracle hints:
- Data consistency across create/read cycles
- Graceful handling of boundary values
- Proper error responses for all invalid input combinations
- Event integrity under various state transitions
"""

import json

from app.models.event import Event

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(client, username, email):
    return client.post("/users", json={"username": username, "email": email})


def _create_url(client, url="https://example.com", user_id=None, title=None):
    payload = {"url": url}
    if user_id is not None:
        payload["user_id"] = user_id
    if title is not None:
        payload["title"] = title
    return client.post("/urls", json=payload)


# ---------------------------------------------------------------------------
# 1. Data Consistency Tests
# ---------------------------------------------------------------------------

class TestDataConsistency:
    def test_create_user_then_get_returns_same_data(self, client):
        """Created user data must be retrievable immediately and match."""
        resp = _create_user(client, "consistent_user", "consistent@example.com")
        assert resp.status_code == 201
        created = resp.get_json()
        user_id = created["id"]

        get_resp = client.get(f"/users/{user_id}")
        assert get_resp.status_code == 200
        fetched = get_resp.get_json()
        assert fetched["username"] == "consistent_user"
        assert fetched["email"] == "consistent@example.com"
        assert fetched["id"] == user_id

    def test_create_url_then_get_returns_same_data(self, client):
        """Created URL data must be retrievable immediately and match."""
        resp = _create_url(client, url="https://consistent-url.example.com")
        assert resp.status_code == 201
        created = resp.get_json()
        url_id = created["id"]

        get_resp = client.get(f"/urls/{url_id}")
        assert get_resp.status_code == 200
        fetched = get_resp.get_json()
        assert fetched["original_url"] == "https://consistent-url.example.com"
        assert fetched["id"] == url_id
        assert fetched["is_active"] is True

    def test_update_url_then_get_reflects_change(self, client):
        """After updating a URL, GET should reflect the new values."""
        create_resp = _create_url(client, url="https://before-update.example.com")
        url_id = create_resp.get_json()["id"]

        client.put(f"/urls/{url_id}", json={"url": "https://after-update.example.com"})

        get_resp = client.get(f"/urls/{url_id}")
        assert get_resp.status_code == 200
        assert get_resp.get_json()["original_url"] == "https://after-update.example.com"

    def test_url_appears_in_list_after_creation(self, client):
        """A newly created URL should appear in the list endpoint."""
        create_resp = _create_url(client, url="https://in-list.example.com")
        url_id = create_resp.get_json()["id"]

        list_resp = client.get("/urls")
        assert list_resp.status_code == 200
        listed_ids = {u["id"] for u in list_resp.get_json()}
        assert url_id in listed_ids

    def test_user_appears_in_list_after_creation(self, client):
        """A newly created user should appear in the list endpoint."""
        create_resp = _create_user(client, "listed_user", "listed@example.com")
        user_id = create_resp.get_json()["id"]

        list_resp = client.get("/users")
        assert list_resp.status_code == 200
        listed_ids = {u["id"] for u in list_resp.get_json()}
        assert user_id in listed_ids


# ---------------------------------------------------------------------------
# 2. Event Integrity Tests
# ---------------------------------------------------------------------------

class TestEventIntegrity:
    def test_url_creation_always_creates_event(self, client):
        """Every successful URL creation must produce a 'created' event."""
        resp = _create_url(client, url="https://event-integrity.example.com")
        url_id = resp.get_json()["id"]

        events = list(
            Event.select().where(
                (Event.url_id == url_id) & (Event.event_type == "created")
            )
        )
        assert len(events) == 1

    def test_url_deletion_creates_deleted_event(self, client):
        """Soft-deleting a URL must produce a 'deleted' event."""
        resp = _create_url(client, url="https://delete-event.example.com")
        url_id = resp.get_json()["id"]

        client.delete(f"/urls/{url_id}")

        events = list(
            Event.select().where(
                (Event.url_id == url_id) & (Event.event_type == "deleted")
            )
        )
        assert len(events) == 1

    def test_url_update_creates_updated_event(self, client):
        """Updating a URL field must produce an 'updated' event."""
        resp = _create_url(client, url="https://update-event.example.com")
        url_id = resp.get_json()["id"]

        client.put(f"/urls/{url_id}", json={"title": "New Title"})

        events = list(
            Event.select().where(
                (Event.url_id == url_id) & (Event.event_type == "updated")
            )
        )
        assert len(events) == 1

    def test_no_redirect_event_for_nonexistent_code(self, client):
        """Accessing a nonexistent short code must not create any event."""
        client.get("/ZZZZZZZZZ")

        events = list(
            Event.select().where(Event.event_type == "redirect")
        )
        assert len(events) == 0

    def test_inactive_url_redirect_creates_zero_events(self, client):
        """Attempting to redirect an inactive URL must create zero redirect events."""
        resp = _create_url(client, url="https://no-event-inactive.example.com")
        url_id = resp.get_json()["id"]
        short_code = resp.get_json()["short_code"]

        # Deactivate via update
        client.put(f"/urls/{url_id}", json={"is_active": False})

        # Attempt redirect
        redirect_resp = client.get(f"/{short_code}")
        assert redirect_resp.status_code == 404

        redirect_events = list(
            Event.select().where(
                (Event.url_id == url_id) & (Event.event_type == "redirect")
            )
        )
        assert len(redirect_events) == 0

    def test_events_filter_by_url_id_returns_only_matching(self, client):
        """Filtering events by url_id returns only events for that URL."""
        resp1 = _create_url(client, url="https://filter1.example.com")
        url_id1 = resp1.get_json()["id"]

        resp2 = _create_url(client, url="https://filter2.example.com")
        resp2.get_json()["id"]

        events_resp = client.get(f"/urls/{url_id1}/events")
        events = events_resp.get_json()
        assert all(e["url_id"] == url_id1 for e in events)

    def test_events_filter_by_nonexistent_url_id_returns_empty(self, client):
        """GET /events?url_id=99999 returns empty list, not error."""
        resp = client.get("/events?url_id=99999")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_create_event_with_nonexistent_url_id_returns_404(self, client):
        """POST /events with a url_id that doesn't exist returns 404."""
        resp = client.post(
            "/events",
            json={"url_id": 99999, "event_type": "redirect"},
        )
        assert resp.status_code == 404

    def test_create_event_with_nonexistent_user_id_returns_404(self, client):
        """POST /events with a user_id that doesn't exist returns 404."""
        url_resp = _create_url(client, url="https://event-user-check.example.com")
        url_id = url_resp.get_json()["id"]

        resp = client.post(
            "/events",
            json={"url_id": url_id, "event_type": "test", "user_id": 99999},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3. Input Validation Edge Cases
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_create_user_whitespace_only_username(self, client):
        """Whitespace-only username must be rejected."""
        resp = _create_user(client, "   ", "ws@example.com")
        assert resp.status_code == 400

    def test_create_user_whitespace_only_email(self, client):
        """Whitespace-only email must be rejected."""
        resp = _create_user(client, "wsuser", "   ")
        assert resp.status_code == 400

    def test_create_url_whitespace_only_url(self, client):
        """Whitespace-only URL must be rejected."""
        resp = client.post("/urls", json={"url": "   "})
        assert resp.status_code == 400

    def test_create_url_null_url(self, client):
        """Null URL value must be rejected."""
        resp = client.post("/urls", json={"url": None})
        assert resp.status_code == 400

    def test_create_url_missing_url_key(self, client):
        """Missing URL key entirely must be rejected."""
        resp = client.post("/urls", json={"title": "no url"})
        assert resp.status_code == 400

    def test_update_url_is_active_as_string_rejected(self, client):
        """is_active as string 'false' must be rejected (must be boolean)."""
        create_resp = _create_url(client, url="https://bool-check.example.com")
        url_id = create_resp.get_json()["id"]
        resp = client.put(f"/urls/{url_id}", json={"is_active": "false"})
        assert resp.status_code == 400

    def test_update_url_is_active_as_int_rejected(self, client):
        """is_active as integer 0 must be rejected (must be boolean)."""
        create_resp = _create_url(client, url="https://int-bool-check.example.com")
        url_id = create_resp.get_json()["id"]
        resp = client.put(f"/urls/{url_id}", json={"is_active": 0})
        assert resp.status_code == 400

    def test_create_event_empty_event_type(self, client):
        """Empty string event_type must be rejected."""
        url_resp = _create_url(client, url="https://empty-event-type.example.com")
        url_id = url_resp.get_json()["id"]
        resp = client.post(
            "/events",
            json={"url_id": url_id, "event_type": ""},
        )
        assert resp.status_code == 400

    def test_create_event_integer_event_type(self, client):
        """Integer event_type must be rejected."""
        url_resp = _create_url(client, url="https://int-event-type.example.com")
        url_id = url_resp.get_json()["id"]
        resp = client.post(
            "/events",
            json={"url_id": url_id, "event_type": 123},
        )
        assert resp.status_code == 400

    def test_create_event_details_as_string_rejected(self, client):
        """Details field as a string (not dict) must be rejected."""
        url_resp = _create_url(client, url="https://str-details.example.com")
        url_id = url_resp.get_json()["id"]
        resp = client.post(
            "/events",
            json={"url_id": url_id, "event_type": "test", "details": "not a dict"},
        )
        assert resp.status_code == 400

    def test_create_event_details_as_list_rejected(self, client):
        """Details field as a list must be rejected."""
        url_resp = _create_url(client, url="https://list-details.example.com")
        url_id = url_resp.get_json()["id"]
        resp = client.post(
            "/events",
            json={"url_id": url_id, "event_type": "test", "details": [1, 2, 3]},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. Soft Delete / Inactive Handling
# ---------------------------------------------------------------------------

class TestSoftDeleteBehavior:
    def test_soft_deleted_url_still_accessible_by_id(self, client):
        """A soft-deleted URL should still be retrievable by ID (with is_active=False)."""
        create_resp = _create_url(client, url="https://soft-get.example.com")
        url_id = create_resp.get_json()["id"]

        client.delete(f"/urls/{url_id}")

        get_resp = client.get(f"/urls/{url_id}")
        assert get_resp.status_code == 200
        data = get_resp.get_json()
        assert data["is_active"] is False
        assert data["original_url"] == "https://soft-get.example.com"

    def test_soft_deleted_url_redirect_returns_404(self, client):
        """Redirecting to a soft-deleted URL must return 404."""
        create_resp = _create_url(client, url="https://soft-redirect.example.com")
        url_id = create_resp.get_json()["id"]
        short_code = create_resp.get_json()["short_code"]

        client.delete(f"/urls/{url_id}")

        resp = client.get(f"/{short_code}")
        assert resp.status_code == 404

    def test_reactivated_url_can_redirect(self, client):
        """After reactivation, a previously deleted URL should redirect again."""
        create_resp = _create_url(client, url="https://reactivate.example.com")
        url_id = create_resp.get_json()["id"]
        short_code = create_resp.get_json()["short_code"]

        # Deactivate
        client.delete(f"/urls/{url_id}")
        assert client.get(f"/{short_code}").status_code == 404

        # Reactivate
        client.put(f"/urls/{url_id}", json={"is_active": True})

        resp = client.get(f"/{short_code}")
        assert resp.status_code == 302

    def test_double_delete_url_second_returns_404(self, client):
        """Deleting an already-deactivated URL should return 404."""
        create_resp = _create_url(client, url="https://double-del.example.com")
        url_id = create_resp.get_json()["id"]

        resp1 = client.delete(f"/urls/{url_id}")
        assert resp1.status_code == 204

        resp2 = client.delete(f"/urls/{url_id}")
        assert resp2.status_code == 404

    def test_url_stats_accessible_after_soft_delete(self, client):
        """Stats endpoint should work for soft-deleted URLs."""
        create_resp = _create_url(client, url="https://stats-deleted.example.com")
        url_id = create_resp.get_json()["id"]
        short_code = create_resp.get_json()["short_code"]

        # Generate a redirect first
        client.get(f"/{short_code}")
        # Then delete
        client.delete(f"/urls/{url_id}")

        stats_resp = client.get(f"/urls/{url_id}/stats")
        assert stats_resp.status_code == 200
        assert stats_resp.get_json()["redirect_count"] == 1

    def test_events_accessible_for_soft_deleted_url(self, client):
        """Events endpoint should still return events for a soft-deleted URL."""
        create_resp = _create_url(client, url="https://events-deleted.example.com")
        url_id = create_resp.get_json()["id"]

        client.delete(f"/urls/{url_id}")

        events_resp = client.get(f"/urls/{url_id}/events")
        assert events_resp.status_code == 200
        events = events_resp.get_json()
        event_types = {e["event_type"] for e in events}
        assert "created" in event_types
        assert "deleted" in event_types


# ---------------------------------------------------------------------------
# 5. Uniqueness and Conflict Handling
# ---------------------------------------------------------------------------

class TestUniquenessConflicts:
    def test_duplicate_username_returns_409(self, client):
        """Creating a user with a taken username must return 409 Conflict."""
        _create_user(client, "taken_name_rel", "a@rel.com")
        resp = _create_user(client, "taken_name_rel", "b@rel.com")
        assert resp.status_code == 409

    def test_duplicate_email_returns_409(self, client):
        """Creating a user with a taken email must return 409 Conflict."""
        _create_user(client, "user_a_rel", "taken@rel.com")
        resp = _create_user(client, "user_b_rel", "taken@rel.com")
        assert resp.status_code == 409

    def test_update_to_duplicate_username_returns_409(self, client):
        """Updating username to an already-taken value must return 409."""
        _create_user(client, "owner_rel", "owner@rel.com")
        create_resp = _create_user(client, "updater_rel", "updater@rel.com")
        user_id = create_resp.get_json()["id"]

        resp = client.put(f"/users/{user_id}", json={"username": "owner_rel"})
        assert resp.status_code == 409

    def test_update_to_duplicate_email_returns_409(self, client):
        """Updating email to an already-taken value must return 409."""
        _create_user(client, "emailowner_rel", "emailowner@rel.com")
        create_resp = _create_user(client, "emailupdater_rel", "emailupdater@rel.com")
        user_id = create_resp.get_json()["id"]

        resp = client.put(f"/users/{user_id}", json={"email": "emailowner@rel.com"})
        assert resp.status_code == 409

    def test_same_url_produces_different_short_codes(self, client):
        """Two URLs with the same original_url must have different short codes."""
        resp1 = _create_url(client, url="https://twin-rel.example.com")
        resp2 = _create_url(client, url="https://twin-rel.example.com")
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.get_json()["short_code"] != resp2.get_json()["short_code"]
        assert resp1.get_json()["id"] != resp2.get_json()["id"]


# ---------------------------------------------------------------------------
# 6. Content-Type and Body Format Validation
# ---------------------------------------------------------------------------

class TestContentTypeValidation:
    def test_urls_post_plain_text_rejected(self, client):
        resp = client.post("/urls", data="text", content_type="text/plain")
        assert resp.status_code == 400

    def test_urls_post_form_encoded_rejected(self, client):
        resp = client.post(
            "/urls",
            data="url=https://example.com",
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 400

    def test_urls_put_plain_text_rejected(self, client):
        create_resp = _create_url(client, url="https://ct-put.example.com")
        url_id = create_resp.get_json()["id"]
        resp = client.put(f"/urls/{url_id}", data="text", content_type="text/plain")
        assert resp.status_code == 400

    def test_users_post_plain_text_rejected(self, client):
        resp = client.post("/users", data="text", content_type="text/plain")
        assert resp.status_code == 400

    def test_users_put_plain_text_rejected(self, client):
        create_resp = _create_user(client, "ct_user", "ct@example.com")
        user_id = create_resp.get_json()["id"]
        resp = client.put(f"/users/{user_id}", data="text", content_type="text/plain")
        assert resp.status_code == 400

    def test_events_post_plain_text_rejected(self, client):
        resp = client.post("/events", data="text", content_type="text/plain")
        assert resp.status_code == 400

    def test_urls_post_json_array_rejected(self, client):
        resp = client.post(
            "/urls",
            data=json.dumps(["https://example.com"]),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_users_post_json_array_rejected(self, client):
        resp = client.post(
            "/users",
            data=json.dumps(["user", "email"]),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_events_post_json_array_rejected(self, client):
        resp = client.post(
            "/events",
            data=json.dumps([{"url_id": 1}]),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_urls_post_json_string_rejected(self, client):
        resp = client.post(
            "/urls",
            data=json.dumps("https://example.com"),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_events_post_json_string_rejected(self, client):
        resp = client.post(
            "/events",
            data=json.dumps("redirect"),
            content_type="application/json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 7. 404 Handling for All Endpoints
# ---------------------------------------------------------------------------

class TestNotFoundHandling:
    def test_get_nonexistent_user(self, client):
        resp = client.get("/users/99999")
        assert resp.status_code == 404

    def test_get_nonexistent_url(self, client):
        resp = client.get("/urls/99999")
        assert resp.status_code == 404

    def test_update_nonexistent_user(self, client):
        resp = client.put("/users/99999", json={"username": "ghost"})
        assert resp.status_code == 404

    def test_update_nonexistent_url(self, client):
        resp = client.put("/urls/99999", json={"url": "https://ghost.example.com"})
        assert resp.status_code == 404

    def test_delete_nonexistent_user(self, client):
        resp = client.delete("/users/99999")
        assert resp.status_code == 404

    def test_delete_nonexistent_url(self, client):
        resp = client.delete("/urls/99999")
        assert resp.status_code == 404

    def test_stats_nonexistent_url(self, client):
        resp = client.get("/urls/99999/stats")
        assert resp.status_code == 404

    def test_events_nonexistent_url(self, client):
        resp = client.get("/urls/99999/events")
        assert resp.status_code == 404

    def test_redirect_nonexistent_short_code(self, client):
        resp = client.get("/NONEXISTENT_CODE")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. URL Filtering Tests
# ---------------------------------------------------------------------------

class TestUrlFiltering:
    def test_filter_urls_by_user_id(self, client):
        """Filtering URLs by user_id returns only that user's URLs."""
        user_resp = _create_user(client, "filter_owner", "filter@example.com")
        user_id = user_resp.get_json()["id"]
        _create_url(client, url="https://owned-filter.example.com", user_id=user_id)
        _create_url(client, url="https://unowned-filter.example.com")

        resp = client.get(f"/urls?user_id={user_id}")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["user_id"] == user_id

    def test_filter_urls_by_is_active_true(self, client):
        """Filtering by is_active=true returns only active URLs."""
        _create_url(client, url="https://active-filter.example.com")
        create_resp = _create_url(client, url="https://inactive-filter.example.com")
        url_id = create_resp.get_json()["id"]
        client.delete(f"/urls/{url_id}")

        resp = client.get("/urls?is_active=true")
        data = resp.get_json()
        assert all(u["is_active"] is True for u in data)

    def test_filter_urls_by_is_active_false(self, client):
        """Filtering by is_active=false returns only inactive URLs."""
        _create_url(client, url="https://active2.example.com")
        create_resp = _create_url(client, url="https://inactive2.example.com")
        url_id = create_resp.get_json()["id"]
        client.delete(f"/urls/{url_id}")

        resp = client.get("/urls?is_active=false")
        data = resp.get_json()
        assert all(u["is_active"] is False for u in data)

    def test_pagination_respects_per_page_limit(self, client):
        """per_page parameter limits the number of results."""
        for i in range(5):
            _create_url(client, url=f"https://paginate-{i}.example.com")

        resp = client.get("/urls?page=1&per_page=2")
        assert len(resp.get_json()) == 2

    def test_large_page_returns_empty(self, client):
        """Requesting a very large page number returns empty list."""
        _create_url(client, url="https://large-page.example.com")
        resp = client.get("/urls?page=99999")
        assert resp.status_code == 200
        assert resp.get_json() == []


# ---------------------------------------------------------------------------
# 9. Full Flow Integration
# ---------------------------------------------------------------------------

class TestFullFlowIntegration:
    def test_create_url_with_user_redirect_check_events_stats(self, client):
        """Full lifecycle: create user, create URL, redirect, check events and stats."""
        # Create user
        user_resp = _create_user(client, "flow_user", "flow@example.com")
        user_id = user_resp.get_json()["id"]

        # Create URL
        url_resp = _create_url(
            client,
            url="https://flow-test.example.com",
            user_id=user_id,
        )
        assert url_resp.status_code == 201
        url_id = url_resp.get_json()["id"]
        short_code = url_resp.get_json()["short_code"]

        # Redirect twice
        for _ in range(2):
            resp = client.get(f"/{short_code}")
            assert resp.status_code == 302

        # Check stats
        stats_resp = client.get(f"/urls/{url_id}/stats")
        assert stats_resp.get_json()["redirect_count"] == 2

        # Check events
        events_resp = client.get(f"/urls/{url_id}/events")
        event_types = [e["event_type"] for e in events_resp.get_json()]
        assert event_types.count("redirect") == 2
        assert "created" in event_types

        # Delete URL
        client.delete(f"/urls/{url_id}")

        # Redirect should now fail
        resp = client.get(f"/{short_code}")
        assert resp.status_code == 404

        # Verify no new redirect event was created
        events_resp = client.get(f"/urls/{url_id}/events")
        redirect_events = [
            e for e in events_resp.get_json() if e["event_type"] == "redirect"
        ]
        assert len(redirect_events) == 2  # still only the original 2

    def test_create_url_without_user_id(self, client):
        """URLs can be created without a user_id (anonymous)."""
        resp = _create_url(client, url="https://anon.example.com")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["user_id"] is None

        # Should be redirectable
        short_code = data["short_code"]
        redirect_resp = client.get(f"/{short_code}")
        assert redirect_resp.status_code == 302
