"""Integration tests: full end-to-end flows spanning multiple endpoints."""

from app.models.event import Event


def test_full_flow_create_user_create_url_redirect_check_events(client):
    """Create user -> create URL -> redirect -> verify events exist."""
    # 1. Create user
    user_resp = client.post(
        "/users", json={"username": "integrator", "email": "integrator@example.com"}
    )
    assert user_resp.status_code == 201
    user_id = user_resp.get_json()["id"]

    # 2. Create URL linked to user
    url_resp = client.post(
        "/urls", json={"url": "https://integration.example.com", "user_id": user_id}
    )
    assert url_resp.status_code == 201
    url_data = url_resp.get_json()
    url_id = url_data["id"]
    short_code = url_data["short_code"]

    # 3. Redirect
    redirect_resp = client.get(f"/{short_code}")
    assert redirect_resp.status_code == 302

    # 4. Check events via API
    events_resp = client.get(f"/urls/{url_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.get_json()
    event_types = [e["event_type"] for e in events]
    assert "created" in event_types
    assert "redirect" in event_types

    # 5. Check stats
    stats_resp = client.get(f"/urls/{url_id}/stats")
    assert stats_resp.status_code == 200
    assert stats_resp.get_json()["redirect_count"] == 1


def test_create_url_delete_url_redirect_fails_no_new_event(client):
    """Create URL -> delete -> redirect must fail with 404 and no redirect event."""
    # 1. Create URL
    url_resp = client.post("/urls", json={"url": "https://doomed.example.com"})
    assert url_resp.status_code == 201
    url_data = url_resp.get_json()
    url_id = url_data["id"]
    short_code = url_data["short_code"]

    # 2. Delete URL (soft delete)
    del_resp = client.delete(f"/urls/{url_id}")
    assert del_resp.status_code == 204

    # 3. Redirect should fail
    redirect_resp = client.get(f"/{short_code}")
    assert redirect_resp.status_code == 404

    # 4. No redirect event should exist
    redirect_events = list(
        Event.select().where(
            (Event.url_id == url_id) & (Event.event_type == "redirect")
        )
    )
    assert len(redirect_events) == 0


def test_create_user_create_multiple_urls_list_all(client):
    """Verify listing returns all URLs created."""
    user_resp = client.post(
        "/users", json={"username": "multi", "email": "multi@example.com"}
    )
    user_id = user_resp.get_json()["id"]

    urls_created = []
    for i in range(3):
        resp = client.post(
            "/urls",
            json={"url": f"https://multi{i}.example.com", "user_id": user_id},
        )
        assert resp.status_code == 201
        urls_created.append(resp.get_json()["id"])

    list_resp = client.get("/urls")
    assert list_resp.status_code == 200
    listed_ids = {u["id"] for u in list_resp.get_json()}
    for uid in urls_created:
        assert uid in listed_ids


def test_delete_user_then_create_url_without_user(client):
    """After deleting a user, URLs can still be created without a user."""
    user_resp = client.post(
        "/users", json={"username": "ephemeral", "email": "ephemeral@example.com"}
    )
    user_id = user_resp.get_json()["id"]
    client.delete(f"/users/{user_id}")

    url_resp = client.post("/urls", json={"url": "https://orphan.example.com"})
    assert url_resp.status_code == 201


def test_update_url_then_redirect_goes_to_new_destination(client):
    """Updating a URL's destination changes where the redirect goes."""
    url_resp = client.post("/urls", json={"url": "https://old-dest.example.com"})
    url_id = url_resp.get_json()["id"]
    short_code = url_resp.get_json()["short_code"]

    # Update destination
    client.put(f"/urls/{url_id}", json={"url": "https://new-dest.example.com"})

    # Redirect should go to the new destination
    redirect_resp = client.get(f"/{short_code}")
    assert redirect_resp.status_code == 302
    assert "new-dest.example.com" in redirect_resp.headers["Location"]


def test_global_events_list_captures_all_types(client):
    """The /events endpoint captures created, redirect, and deleted events."""
    url_resp = client.post("/urls", json={"url": "https://allevents.example.com"})
    url_data = url_resp.get_json()
    url_id = url_data["id"]
    short_code = url_data["short_code"]

    # Redirect
    client.get(f"/{short_code}")

    # Delete
    client.delete(f"/urls/{url_id}")

    events_resp = client.get("/events")
    assert events_resp.status_code == 200
    event_types = {e["event_type"] for e in events_resp.get_json()}
    assert "created" in event_types
    assert "redirect" in event_types
    assert "deleted" in event_types
