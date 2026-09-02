"""
Distributed-capable rate limiter (P0 hardening).

backend/main.py used to keep rate-limit counters in a plain in-process
dict — safe for a single worker, but with `uvicorn --workers 2` (already
the docker-compose.yml command) each worker has its OWN counters, so a
client sees roughly N times the intended limit and can shape requests to
land on whichever worker is least loaded. `allow_request()` is a drop-in
replacement: distributed via Redis sliding-window when REDIS_URL is
configured, and the exact same in-memory sliding window as before when
it isn't.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict

from .redis_client import get_redis

log = logging.getLogger(__name__)

_memory_store: dict[str, list[float]] = defaultdict(list)


def allow_request(key: str, ceiling: int, window_seconds: int = 60) -> bool:
    """
    Sliding-window check. Returns True (and records this request) if under
    the limit, False if the caller should be rejected (e.g. HTTP 429).
    """
    now = time.time()
    redis_client = get_redis()
    if redis_client is not None:
        try:
            return _allow_redis(redis_client, key, ceiling, window_seconds, now)
        except Exception as e:                                          # noqa: BLE001
            log.warning("Redis rate-limit check failed (%s) — falling back "
                        "to in-process counter for this request.", e)
    return _allow_memory(key, ceiling, window_seconds, now)


def _allow_redis(client, key: str, ceiling: int, window_seconds: int, now: float) -> bool:
    """
    Sorted-set sliding window: each member is a unique per-request token
    scored by its timestamp; expired entries are trimmed before counting.

    Small race window between the ZCARD check and the ZADD write under
    heavy concurrent load can allow a slight overshoot — acceptable for
    rate limiting (unlike a financial quota, a few extra requests during a
    race is a minor cost, not a correctness bug), and cheaper than a
    Lua-script-enforced atomic version.
    """
    redis_key = f"ratelimit:{key}"
    client.zremrangebyscore(redis_key, 0, now - window_seconds)
    if client.zcard(redis_key) >= ceiling:
        return False
    # Unique member per call — two requests in the same millisecond must
    # not collide and silently count as one.
    member = f"{now:.6f}:{id(object())}"
    pipe = client.pipeline()
    pipe.zadd(redis_key, {member: now})
    pipe.expire(redis_key, window_seconds + 5)
    pipe.execute()
    return True


def _allow_memory(key: str, ceiling: int, window_seconds: int, now: float) -> bool:
    bucket = _memory_store[key]
    bucket[:] = [t for t in bucket if now - t < window_seconds]
    if len(bucket) >= ceiling:
        return False
    bucket.append(now)
    return True
