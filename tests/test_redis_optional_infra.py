"""
Redis-optional infrastructure tests (P0 hardening).

No live Redis server is available in this environment, so the "Redis
configured and reachable" branches are tested against a mock client that
implements the exact subset of the redis-py API these modules use
(pipeline/zadd/zremrangebyscore/zcard/set-nx/get/delete). The "Redis not
configured" branches are tested for real — that's the actual default
behavior of this codebase today.
"""
import unittest
from unittest.mock import MagicMock, patch

from app.services import redis_client, rate_limiter
from app.utils import distributed_lock


class NoRedisConfiguredTests(unittest.TestCase):
    """The default state of this app: REDIS_URL unset."""

    def setUp(self):
        redis_client.reset_for_tests()

    def test_01_get_redis_returns_none_without_url(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("REDIS_URL", None)
            self.assertIsNone(redis_client.get_redis())

    def test_02_rate_limiter_falls_back_to_memory(self):
        rate_limiter._memory_store.clear()
        results = [rate_limiter.allow_request("k1", ceiling=3, window_seconds=60) for _ in range(4)]
        self.assertEqual(results, [True, True, True, False])

    def test_03_lock_always_acquires_without_redis(self):
        with distributed_lock.try_lock("some-lock") as acquired:
            self.assertTrue(acquired)


class MockRedisRateLimiterTests(unittest.TestCase):
    """Exercise the distributed path against a mock client with real semantics."""

    def _fake_pipeline(self, client):
        pipe = MagicMock()
        pipe.zadd = MagicMock()
        pipe.expire = MagicMock()
        pipe.execute = MagicMock(return_value=[True, True])
        return pipe

    def test_04_allows_under_ceiling(self):
        client = MagicMock()
        client.zremrangebyscore.return_value = 0
        client.zcard.return_value = 2   # 2 existing, ceiling 3 -> allowed
        client.pipeline.side_effect = lambda: self._fake_pipeline(client)

        with patch.object(rate_limiter, "get_redis", return_value=client):
            allowed = rate_limiter.allow_request("k", ceiling=3, window_seconds=60)
        self.assertTrue(allowed)
        client.pipeline.assert_called_once()

    def test_05_blocks_at_ceiling(self):
        client = MagicMock()
        client.zremrangebyscore.return_value = 0
        client.zcard.return_value = 3   # already at ceiling 3 -> blocked
        client.pipeline.side_effect = lambda: self._fake_pipeline(client)

        with patch.object(rate_limiter, "get_redis", return_value=client):
            allowed = rate_limiter.allow_request("k", ceiling=3, window_seconds=60)
        self.assertFalse(allowed)
        client.pipeline.assert_not_called()  # never gets to recording the request

    def test_06_redis_error_falls_back_to_memory(self):
        client = MagicMock()
        client.zremrangebyscore.side_effect = RuntimeError("connection reset")
        rate_limiter._memory_store.clear()

        with patch.object(rate_limiter, "get_redis", return_value=client):
            allowed = rate_limiter.allow_request("k2", ceiling=1, window_seconds=60)
        self.assertTrue(allowed)  # fell back to memory and succeeded there


class MockRedisLockTests(unittest.TestCase):

    def test_07_acquires_when_key_absent(self):
        client = MagicMock()
        client.set.return_value = True   # SET NX succeeded
        client.get.return_value = None   # irrelevant to this branch

        with patch.object(distributed_lock, "get_redis", return_value=client):
            with distributed_lock.try_lock("resource-a") as acquired:
                self.assertTrue(acquired)
        client.set.assert_called_once()
        _, kwargs = client.set.call_args
        self.assertTrue(kwargs.get("nx"))

    def test_08_does_not_acquire_when_already_held(self):
        client = MagicMock()
        client.set.return_value = None   # SET NX failed — someone else holds it

        with patch.object(distributed_lock, "get_redis", return_value=client):
            with distributed_lock.try_lock("resource-b") as acquired:
                self.assertFalse(acquired)
        client.delete.assert_not_called()  # never held it, must not release it

    def test_09_releases_only_if_still_owner(self):
        client = MagicMock()
        client.set.return_value = True

        captured_token = {}

        def fake_get(key):
            return captured_token.get(key)

        def fake_set(key, token, nx=True, ex=None):
            captured_token[key] = token
            return True

        client.set.side_effect = fake_set
        client.get.side_effect = fake_get

        with patch.object(distributed_lock, "get_redis", return_value=client):
            with distributed_lock.try_lock("resource-c") as acquired:
                self.assertTrue(acquired)
        client.delete.assert_called_once_with("lock:resource-c")


if __name__ == "__main__":
    unittest.main()
