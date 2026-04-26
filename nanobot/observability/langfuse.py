from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass(slots=True)
class LangfuseConfig:
    public_key: str
    secret_key: str
    host: str | None = None


def load_langfuse_config() -> LangfuseConfig | None:
    pub = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    sec = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    host = os.environ.get("LANGFUSE_HOST", "").strip() or None
    if not (pub and sec):
        return None
    return LangfuseConfig(public_key=pub, secret_key=sec, host=host)


class LangfuseTracer:
    def __init__(self, cfg: LangfuseConfig):
        self._cfg = cfg
        self._client = None

    def _get(self):
        if self._client is not None:
            return self._client
        from langfuse import Langfuse  # type: ignore

        self._client = Langfuse(
            public_key=self._cfg.public_key,
            secret_key=self._cfg.secret_key,
            host=self._cfg.host,
        )
        return self._client

    def trace_turn(
        self,
        *,
        name: str,
        tenant_id: str,
        session_key: str,
        channel: str,
        model: str,
        input_text: str,
        output_text: str,
        metadata: dict[str, Any] | None = None,
        duration_s: float | None = None,
        status: str = "ok",
    ) -> None:
        try:
            lf = self._get()
            trace = lf.trace(
                name=name,
                user_id=str(tenant_id),
                session_id=str(session_key),
                metadata={
                    "channel": channel,
                    "model": model,
                    "status": status,
                    **(metadata or {}),
                },
            )
            # Minimal generation log (we don't have exact token/cost attribution yet).
            trace.generation(
                name="turn",
                model=model,
                input=input_text,
                output=output_text,
                metadata={"duration_s": duration_s} if duration_s is not None else None,
            )
            trace.flush()
        except Exception:
            logger.exception("Langfuse trace failed")

