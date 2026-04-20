from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from loguru import logger

from nanobot.agent.hook import AgentHook, AgentHookContext


@dataclass(slots=True)
class RedisStreamConfig:
    redis_url: str
    channel_prefix: str = "nanobot:stream:"


class RedisStreamHook(AgentHook):
    def __init__(self, *, cfg: RedisStreamConfig, request_id: str):
        self._cfg = cfg
        self._request_id = request_id
        self._redis = None
        self._channel = f"{cfg.channel_prefix}{request_id}"

    def wants_streaming(self) -> bool:
        return True

    def _client(self):
        if self._redis is not None:
            return self._redis
        from redis.asyncio import Redis  # type: ignore

        self._redis = Redis.from_url(self._cfg.redis_url, decode_responses=True)
        return self._redis

    async def on_stream(self, context: AgentHookContext, delta: str) -> None:
        if not delta:
            return
        try:
            await self._client().publish(self._channel, json.dumps({"type": "delta", "delta": delta}))
        except Exception:
            logger.exception("RedisStreamHook publish failed")

    async def on_stream_end(self, context: AgentHookContext, *, resuming: bool) -> None:
        try:
            await self._client().publish(self._channel, json.dumps({"type": "end"}))
        except Exception:
            logger.exception("RedisStreamHook publish end failed")

