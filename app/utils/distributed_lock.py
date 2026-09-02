"""
Distributed lock (P0 hardening — scheduler/worker coordination).

Redis SETNX-with-TTL lock. Falls back to "always acquires" when Redis
isn't configured — the same "degrade to single-process behavior" pattern
used everywhere else optional infra is involved (see redis_client.py).

A no-op fallback is safe here specifically because job_service.run_job()
already enforces real idempotency via a unique DB constraint on
workflow_runs — this lock exists to stop multiple scheduler replicas from
redundantly racing each other into that constraint (wasted queries, noisy
IntegrityErrors), not to be the last line of defense against a duplicate
send. Don't reuse this lock as a substitute for that DB-level guarantee.
"""
from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager

from ..services.redis_client import get_redis

log = logging.getLogger(__name__)


@contextmanager
def try_lock(name: str, ttl_seconds: int = 30):
    """
    Context manager — yields True if the lock was acquired (caller should
    do the guarded work) or False if another holder already has it (caller
    should skip this round). Always yields True when Redis isn't configured.

    `ttl_seconds` should comfortably exceed how long the guarded work
    normally takes — an expired-but-still-running holder means a second
    replica can start the same work concurrently, so size it for the
    workload (e.g. a scheduler tick that dispatches jobs, not the jobs
    themselves running to completion).
    """
    client = get_redis()
    if client is None:
        yield True
        return

    token = str(uuid.uuid4())
    key = f"lock:{name}"
    acquired = False
    try:
        acquired = bool(client.set(key, token, nx=True, ex=ttl_seconds))
        yield acquired
    finally:
        if acquired:
            try:
                # Best-effort "only release what we own" — not a fully
                # atomic compare-and-delete (would need a Lua script), but
                # the TTL already bounds how long a mistaken release could
                # matter, so this is an acceptable simplification.
                if client.get(key) == token:
                    client.delete(key)
            except Exception:                                            # noqa: BLE001
                log.debug("distributed_lock: release failed for %s (TTL will clear it)", key)
