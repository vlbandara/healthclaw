from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from loguru import logger
import asyncio


@dataclass(slots=True)
class RedisLockConfig:
    redis_url: str
    prefix: str = "nanobot:lock:"
    default_ttl_s: int = 120


class RedisDistributedLock:
    """A small Redis distributed lock.

    Uses SET NX PX for acquisition and a Lua script for safe release.
    """

    _RELEASE_LUA = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    else
        return 0
    end
    """

    def __init__(self, cfg: RedisLockConfig):
        self._cfg = cfg
        self._client = None

    def _client_obj(self):
        if self._client is not None:
            return self._client
        from redis.asyncio import Redis  # type: ignore

        self._client = Redis.from_url(self._cfg.redis_url, decode_responses=True)
        return self._client

    def key(self, name: str) -> str:
        return f"{self._cfg.prefix}{name}"

    async def acquire(self, name: str, *, ttl_s: int | None = None, wait_s: int = 10) -> str | None:
        key = self.key(name)
        token = secrets.token_urlsafe(18)
        ttl = int((ttl_s or self._cfg.default_ttl_s) * 1000)

        client = self._client_obj()
        deadline = time.time() + max(0, int(wait_s))

        while True:
            ok = await client.set(key, token, nx=True, px=ttl)
            if ok:
                return token
            if time.time() >= deadline:
                return None
            await asyncio.sleep(0.05)

    async def release(self, name: str, token: str) -> bool:
        key = self.key(name)
        client = self._client_obj()
        try:
            res = await client.eval(self._RELEASE_LUA, 1, key, token)
            return bool(res)
        except Exception:
            logger.exception("Redis lock release failed")
            return False


class lock:
    """Async context manager around RedisDistributedLock.acquire/release."""

    def __init__(
        self,
        manager: RedisDistributedLock,
        name: str,
        *,
        ttl_s: int | None = None,
        wait_s: int = 10,
    ):
        self._mgr = manager
        self._name = name
        self._ttl_s = ttl_s
        self._wait_s = wait_s
        self._token: str | None = None

    async def __aenter__(self):
        token = await self._mgr.acquire(self._name, ttl_s=self._ttl_s, wait_s=self._wait_s)
        if not token:
            raise TimeoutError(f"Failed to acquire distributed lock: {self._name}")
        self._token = token
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._token:
            await self._mgr.release(self._name, self._token)
        self._token = None
        return False

