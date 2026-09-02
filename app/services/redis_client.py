"""
Optional Redis client (P0 hardening — distributed rate limiting/locking).

Every caller in this codebase must treat Redis as OPTIONAL infrastructure:
absent REDIS_URL, or if the configured Redis is unreachable, `get_redis()`
returns None and callers fall back to a documented, safe, single-process
behavior (see rate_limiter.py, distributed_lock.py). This mirrors how
DATABASE_URL already works for Postgres — the app never hard-fails for
lack of infra that hasn't been provisioned yet, it just runs in a mode
with weaker guarantees and logs that fact.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_client = None
_attempted = False


def get_redis():
    """Return a connected redis.Redis client, or None.

    None means: REDIS_URL isn't set, the `redis` package isn't installed,
    or the configured Redis couldn't be reached. Cached after the first
    attempt — if Redis comes up later, restart the process to pick it up
    (consistent with how DATABASE_URL is resolved once at startup).
    """
    global _client, _attempted
    if _attempted:
        return _client
    _attempted = True

    url = os.getenv("REDIS_URL", "")
    if not url:
        log.info("REDIS_URL not set — rate limiting/locking run in single-process mode.")
        return None
    try:
        import redis
    except ImportError:
        log.warning("REDIS_URL is set but the `redis` package isn't installed "
                    "(pip install redis) — falling back to single-process mode.")
        return None
    try:
        client = redis.from_url(
            url, decode_responses=True,
            socket_connect_timeout=3, socket_timeout=3,
        )
        client.ping()
        _client = client
        log.info("Redis connected: %s", url.rsplit("@", 1)[-1])
    except Exception as e:                                              # noqa: BLE001
        log.warning("REDIS_URL is set but Redis is unreachable (%s) — "
                    "falling back to single-process mode.", e)
        _client = None
    return _client


def reset_for_tests():
    """Test-only: clear the cached client so get_redis() re-attempts."""
    global _client, _attempted
    _client, _attempted = None, False
