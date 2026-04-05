"""Tests for the /health endpoint."""


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "status" in data


def test_health_contains_database_key(client):
    resp = client.get("/health")
    data = resp.get_json()
    assert "database" in data


def test_health_database_connected(client):
    resp = client.get("/health")
    data = resp.get_json()
    assert data["database"] == "connected"
    assert data["status"] == "ok"
