"""Tests for Redis cache behavior in URL redirect and CRUD operations.

These tests mock the Redis client to verify cache-related behavior
without requiring a running Redis server.
"""

import json
from unittest.mock import MagicMock, patch

from app.models.event import Event


def _create_url(client, url="https://cache-test.example.com"):
    return client.post("/urls", json={"url": url})


class TestRedirectCacheHit:
    """When Redis has cached URL data, redirect should use it."""

    def test_redirect_with_cache_hit_returns_302(self, client):
        """A cache hit should still produce a valid 302 redirect."""
        create_resp = _create_url(client, url="https://cached.example.com")
        data = create_resp.get_json()
        short_code = data["short_code"]
        url_id = data["id"]

        cache_data = json.dumps({
            "original_url": "https://cached.example.com",
            "url_id": url_id,
            "user_id": None,
        })

        mock_redis = MagicMock()
        mock_redis.get.return_value = cache_data

        with patch("app.routes.urls._get_redis", return_value=mock_redis):
            resp = client.get(f"/{short_code}")

        assert resp.status_code == 302
        assert "cached.example.com" in resp.headers["Location"]

    def test_redirect_cache_hit_sets_x_cache_header(self, client):
        """A cache hit sets X-Cache: HIT header."""
        create_resp = _create_url(client, url="https://hit-header.example.com")
        data = create_resp.get_json()
        short_code = data["short_code"]
        url_id = data["id"]

        cache_data = json.dumps({
            "original_url": "https://hit-header.example.com",
            "url_id": url_id,
            "user_id": None,
        })

        mock_redis = MagicMock()
        mock_redis.get.return_value = cache_data

        with patch("app.routes.urls._get_redis", return_value=mock_redis):
            resp = client.get(f"/{short_code}")

        assert resp.headers.get("X-Cache") == "HIT"

    def test_redirect_cache_hit_creates_event(self, client):
        """A cache hit must still log a redirect event."""
        create_resp = _create_url(client, url="https://hit-event.example.com")
        data = create_resp.get_json()
        short_code = data["short_code"]
        url_id = data["id"]

        cache_data = json.dumps({
            "original_url": "https://hit-event.example.com",
            "url_id": url_id,
            "user_id": None,
        })

        mock_redis = MagicMock()
        mock_redis.get.return_value = cache_data

        with patch("app.routes.urls._get_redis", return_value=mock_redis):
            client.get(f"/{short_code}")

        redirect_events = list(
            Event.select().where(
                (Event.url_id == url_id) & (Event.event_type == "redirect")
            )
        )
        assert len(redirect_events) >= 1


class TestRedirectCacheMiss:
    """When Redis is available but has no cached data, redirect fetches from DB."""

    def test_redirect_cache_miss_sets_x_cache_header(self, client):
        """A cache miss sets X-Cache: MISS and writes to cache."""
        create_resp = _create_url(client, url="https://miss-header.example.com")
        data = create_resp.get_json()
        short_code = data["short_code"]

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("app.routes.urls._get_redis", return_value=mock_redis):
            resp = client.get(f"/{short_code}")

        assert resp.status_code == 302
        assert resp.headers.get("X-Cache") == "MISS"
        # Verify it attempted to cache the result
        mock_redis.setex.assert_called_once()

    def test_redirect_cache_miss_writes_correct_data(self, client):
        """On cache miss, the correct URL data is written to Redis."""
        create_resp = _create_url(client, url="https://miss-write.example.com")
        data = create_resp.get_json()
        short_code = data["short_code"]
        url_id = data["id"]

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("app.routes.urls._get_redis", return_value=mock_redis):
            client.get(f"/{short_code}")

        call_args = mock_redis.setex.call_args
        cache_key = call_args[0][0]
        ttl = call_args[0][1]
        cached_value = json.loads(call_args[0][2])

        assert cache_key == f"url:{short_code}"
        assert ttl == 600
        assert cached_value["original_url"] == "https://miss-write.example.com"
        assert cached_value["url_id"] == url_id


class TestCacheInvalidation:
    """Update and delete operations should invalidate the cache."""

    def test_update_url_invalidates_cache(self, client):
        """Updating a URL deletes its entry from the Redis cache."""
        create_resp = _create_url(client, url="https://invalidate-update.example.com")
        data = create_resp.get_json()
        url_id = data["id"]
        short_code = data["short_code"]

        mock_redis = MagicMock()

        with patch("app.routes.urls._get_redis", return_value=mock_redis):
            client.put(f"/urls/{url_id}", json={"url": "https://new-dest.example.com"})

        mock_redis.delete.assert_called_with(f"url:{short_code}")

    def test_delete_url_invalidates_cache(self, client):
        """Deleting a URL removes its cache entry."""
        create_resp = _create_url(client, url="https://invalidate-delete.example.com")
        data = create_resp.get_json()
        url_id = data["id"]
        short_code = data["short_code"]

        mock_redis = MagicMock()

        with patch("app.routes.urls._get_redis", return_value=mock_redis):
            client.delete(f"/urls/{url_id}")

        mock_redis.delete.assert_called_with(f"url:{short_code}")


class TestRedisFailureGraceDegradation:
    """When Redis operations fail, the app should still work correctly."""

    def test_redirect_works_when_redis_get_raises(self, client):
        """If Redis.get() throws, redirect still works via DB."""
        create_resp = _create_url(client, url="https://redis-fail.example.com")
        data = create_resp.get_json()
        short_code = data["short_code"]

        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis connection lost")

        with patch("app.routes.urls._get_redis", return_value=mock_redis):
            resp = client.get(f"/{short_code}")

        assert resp.status_code == 302
        assert "redis-fail.example.com" in resp.headers["Location"]

    def test_redirect_works_when_redis_setex_raises(self, client):
        """If Redis.setex() throws on cache write, redirect still works."""
        create_resp = _create_url(client, url="https://redis-write-fail.example.com")
        data = create_resp.get_json()
        short_code = data["short_code"]

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_redis.setex.side_effect = Exception("Redis write failed")

        with patch("app.routes.urls._get_redis", return_value=mock_redis):
            resp = client.get(f"/{short_code}")

        assert resp.status_code == 302
        assert "redis-write-fail.example.com" in resp.headers["Location"]

    def test_update_works_when_redis_delete_raises(self, client):
        """If cache invalidation fails on update, the update itself succeeds."""
        create_resp = _create_url(client, url="https://redis-inv-fail.example.com")
        data = create_resp.get_json()
        url_id = data["id"]

        mock_redis = MagicMock()
        mock_redis.delete.side_effect = Exception("Redis delete failed")

        with patch("app.routes.urls._get_redis", return_value=mock_redis):
            resp = client.put(
                f"/urls/{url_id}", json={"url": "https://still-updates.example.com"}
            )

        assert resp.status_code == 200
        assert resp.get_json()["original_url"] == "https://still-updates.example.com"

    def test_delete_works_when_redis_delete_raises(self, client):
        """If cache invalidation fails on delete, the delete itself succeeds."""
        create_resp = _create_url(client, url="https://redis-del-fail.example.com")
        data = create_resp.get_json()
        url_id = data["id"]

        mock_redis = MagicMock()
        mock_redis.delete.side_effect = Exception("Redis delete failed")

        with patch("app.routes.urls._get_redis", return_value=mock_redis):
            resp = client.delete(f"/urls/{url_id}")

        assert resp.status_code == 204

    def test_redirect_works_when_redis_unavailable(self, client):
        """When _get_redis returns None, redirect works via DB only."""
        create_resp = _create_url(client, url="https://no-redis.example.com")
        data = create_resp.get_json()
        short_code = data["short_code"]

        with patch("app.routes.urls._get_redis", return_value=None):
            resp = client.get(f"/{short_code}")

        assert resp.status_code == 302
        assert "no-redis.example.com" in resp.headers["Location"]
