"""Post-run evaluation for background tasks (heartbeat & cron).

After the agent executes a background task, this module makes a lightweight
LLM call to decide whether the result warrants notifying the user.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

from nanobot.utils.prompt_templates import render_template

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider

_EVALUATE_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "evaluate_notification",
            "description": "Decide whether the user should be notified about this background task result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "should_notify": {
                        "type": "boolean",
                        "description": "true = result contains actionable/important info the user should see; false = routine or empty, safe to suppress",
                    },
                    "reason": {
                        "type": "string",
                        "description": "One-sentence reason for the decision",
                    },
                },
                "required": ["should_notify"],
            },
        },
    }
]


_SUPPRESSION_RESPONSE_PATTERNS = (
    re.compile(r"\balready\s+sent\b.*\bnot\s+resending\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\balready\s+sent\b.*\bnot\s+doubling\s+up\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\balready\s+reached\s+out\b.*\bnot\s+sending\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bnot\s+sending\s+(?:a|another|the)?\s*(?:third|ping|nudge|message)\b", re.IGNORECASE),
    re.compile(r"\b(?:standing\s+by|holding\s+position)\b.*\b(?:reply|surface|cycle|attempts?)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(?:attempts?|nudges?|pings?|check-?ins?)\b.*\benough\b.*\bholding\b", re.IGNORECASE | re.DOTALL),
)


def _looks_like_internal_suppression_response(response: str) -> bool:
    """Detect no-op background-agent decisions that should never reach users."""
    text = re.sub(r"<think>.*?</think>", "", str(response or ""), flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in _SUPPRESSION_RESPONSE_PATTERNS)


async def evaluate_response(
    response: str,
    task_context: str,
    provider: LLMProvider,
    model: str,
) -> bool:
    """Decide whether a background-task result should be delivered to the user.

    Uses a lightweight tool-call LLM request (same pattern as heartbeat
    ``_decide()``).  Falls back to ``True`` (notify) on any failure so
    that important messages are never silently dropped.
    """
    if _looks_like_internal_suppression_response(response):
        logger.info("evaluate_response: suppressing internal no-op background response")
        return False

    try:
        llm_response = await provider.chat_with_retry(
            messages=[
                {"role": "system", "content": render_template("agent/evaluator.md", part="system")},
                {"role": "user", "content": render_template(
                    "agent/evaluator.md",
                    part="user",
                    task_context=task_context,
                    response=response,
                )},
            ],
            tools=_EVALUATE_TOOL,
            model=model,
            max_tokens=256,
            temperature=0.0,
        )

        if not llm_response.has_tool_calls:
            logger.warning("evaluate_response: no tool call returned, defaulting to notify")
            return True

        args = llm_response.tool_calls[0].arguments
        should_notify = args.get("should_notify", True)
        reason = args.get("reason", "")
        logger.info("evaluate_response: should_notify={}, reason={}", should_notify, reason)
        return bool(should_notify)

    except Exception:
        logger.exception("evaluate_response failed, defaulting to notify")
        return True
