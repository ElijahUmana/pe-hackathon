import os

import redis

_redis_client = None


def get_redis():
    """Get or create a Redis connection. Returns None if Redis is unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


def reset_redis():
    """Reset the Redis connection (for testing)."""
    global _redis_client
    _redis_client = None
