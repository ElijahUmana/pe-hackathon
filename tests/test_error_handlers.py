"""Tests for global error handlers returning JSON responses."""


def test_404_returns_json_for_unknown_route(client):
    """A request to a completely unknown route returns JSON 404, not HTML."""
    resp = client.get("/this-route-does-not-exist-anywhere")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data is not None
    assert "error" in data


def test_405_returns_json_for_wrong_method(client):
    """Using the wrong HTTP method returns JSON 405, not HTML."""
    resp = client.patch("/urls")
    assert resp.status_code == 405
    data = resp.get_json()
    assert data is not None
    assert "error" in data


def test_405_delete_on_list_endpoint(client):
    """DELETE on /users (a GET/POST-only endpoint) returns 405 JSON."""
    resp = client.delete("/users")
    assert resp.status_code == 405
    data = resp.get_json()
    assert data is not None
    assert "error" in data
