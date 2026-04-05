"""Tests for the /health endpoint."""

from unittest.mock import patch


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


def test_health_returns_degraded_when_db_fails(client):
    """Health endpoint returns degraded status when DB is unreachable."""
    from app.database import db

    # db is a DatabaseProxy; patch execute_sql on the underlying object
    real_db = db.obj
    with patch.object(real_db, "execute_sql", side_effect=Exception("connection refused")):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"
