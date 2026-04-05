import json
import logging
import os

import redis

_redis_client = None
_redis_pool = None

logger = logging.getLogger(__name__)


def get_redis():
    """Get or create a Redis connection using a connection pool.

    Returns None if Redis is unavailable.
    """
    global _redis_client, _redis_pool
    if _redis_client is not None:
        return _redis_client

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        _redis_pool = redis.ConnectionPool.from_url(redis_url, max_connections=20)
        _redis_client = redis.Redis(connection_pool=_redis_pool, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        _redis_pool = None
        return None


def reset_redis():
    """Reset the Redis connection (for testing)."""
    global _redis_client, _redis_pool
    _redis_client = None
    _redis_pool = None


def warm_cache(app):
    """Pre-warm Redis cache with the most recently active URLs.

    Loads up to 100 active URLs into Redis on app startup to reduce
    cold-start latency for the most common redirects.
    """
    r = get_redis()
    if r is None:
        return

    try:
        with app.app_context():
            from app.database import db
            from app.models.url import URL

            db.connect(reuse_if_open=True)
            rows = (
                URL.select(URL.short_code, URL.original_url, URL.id, URL.user_id)
                .where(URL.is_active == True)  # noqa: E712
                .order_by(URL.id.desc())
                .limit(100)
                .dicts()
            )
            count = 0
            for row in rows:
                cache_key = f"url:{row['short_code']}"
                cache_value = json.dumps({
                    "original_url": row["original_url"],
                    "url_id": row["id"],
                    "user_id": row["user_id"],
                })
                r.setex(cache_key, 300, cache_value)
                count += 1
            logger.info(f"Cache warm-up complete: {count} URLs loaded")
    except Exception as e:
        logger.warning(f"Cache warm-up failed: {e}")
