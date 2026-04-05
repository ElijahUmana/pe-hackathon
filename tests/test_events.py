"""Tests for the /events endpoints."""


def _seed_url(client, url="https://event-test.example.com"):
    """Create a URL and return its data."""
    resp = client.post("/urls", json={"url": url})
    return resp.get_json()


def test_list_events_empty(client):
    resp = client.get("/events")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_list_events_after_url_creation(client):
    """Creating a URL generates a 'created' event."""
    _seed_url(client)
    resp = client.get("/events")
    assert resp.status_code == 200
    events = resp.get_json()
    assert len(events) >= 1
    assert any(e["event_type"] == "created" for e in events)


def test_list_events_filter_by_type(client):
    _seed_url(client)
    resp = client.get("/events?type=created")
    assert resp.status_code == 200
    events = resp.get_json()
    assert all(e["event_type"] == "created" for e in events)


def test_list_events_filter_nonexistent_type(client):
    _seed_url(client)
    resp = client.get("/events?type=nonexistent")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_url_events_endpoint(client):
    url_data = _seed_url(client, url="https://url-events.example.com")
    url_id = url_data["id"]
    short_code = url_data["short_code"]

    # Generate a redirect event
    client.get(f"/{short_code}")

    resp = client.get(f"/urls/{url_id}/events")
    assert resp.status_code == 200
    events = resp.get_json()
    event_types = {e["event_type"] for e in events}
    assert "created" in event_types
    assert "redirect" in event_types


def test_url_events_nonexistent_url(client):
    resp = client.get("/urls/99999/events")
    assert resp.status_code == 404


def test_events_pagination(client):
    _seed_url(client, url="https://page1.example.com")
    _seed_url(client, url="https://page2.example.com")
    _seed_url(client, url="https://page3.example.com")

    resp = client.get("/events?page=1&per_page=2")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 2

    resp2 = client.get("/events?page=2&per_page=2")
    assert resp2.status_code == 200
    assert len(resp2.get_json()) == 1
