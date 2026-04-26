from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nanobot.bus.events import InboundMessage
from nanobot.config.schema import Config
from nanobot.evals.judge import Verdict, contains_judge, not_contains_judge
from nanobot.executor.turn import TurnExecutor, TurnExecutorDeps
from nanobot.providers.base import LLMProvider, LLMResponse
from nanobot.store.file import FileMemoryRepository, FileSessionRepository


@dataclass(slots=True)
class EvalCase:
    id: str
    tenant_external_id: str
    session_key: str
    input: str
    expected_contains: str
    tags: list[str]


@dataclass(slots=True)
class EvalResult:
    case_id: str
    passed: bool
    output: str
    reason: str


class EvalProvider(LLMProvider):
    """Deterministic provider for evals (no network, no secrets).

    This keeps evals fast and CI-friendly while still exercising the TurnExecutor + session plumbing.
    """

    def __init__(self):
        super().__init__(api_key=None, api_base=None)
        self._facts: dict[tuple[str, str], str] = {}

    async def chat(self, messages: list[dict[str, object]], **_kwargs: Any) -> LLMResponse:  # type: ignore[override]
        # Find last user message content (string only for smoke evals).
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = str(msg.get("content") or "")
                break

        # Very small rule set for the bundled smoke dataset.
        if "pong" in last_user.lower():
            return LLMResponse(content="pong")

        # Remember: my dog's name is X.
        if "remember" in last_user.lower() and "dog" in last_user.lower() and "name is" in last_user.lower():
            # naive parse
            name = last_user.split("name is", 1)[1].strip().strip(".")
            self._facts[("dog_name", "default")] = name
            return LLMResponse(content=f"Got it. {name}.")

        if "what is my dog's name" in last_user.lower():
            name = self._facts.get(("dog_name", "default"), "")
            return LLMResponse(content=name or "I don't know yet.")

        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "eval-provider"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(json.loads(line))
    return items


def load_dataset(name: str) -> list[EvalCase]:
    here = Path(__file__).parent / "datasets"
    path = here / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    cases = []
    for item in _load_jsonl(path):
        cases.append(
            EvalCase(
                id=str(item["id"]),
                tenant_external_id=str(item.get("tenant_external_id") or "eval"),
                session_key=str(item.get("session_key") or "api:eval"),
                input=str(item.get("input") or ""),
                expected_contains=str(item.get("expected_contains") or ""),
                tags=list(item.get("tags") or []),
            )
        )
    return cases


async def run_dataset(*, config: Config, dataset: str) -> list[EvalResult]:
    provider: LLMProvider = EvalProvider()

    # Local eval runner uses file-backed repositories so it can run without Postgres.
    workspace = config.workspace_path
    session_repo = FileSessionRepository(workspace)
    memory_repo = FileMemoryRepository(workspace)

    executor = TurnExecutor(
        TurnExecutorDeps(
            config=config,
            provider=provider,
            session_repo=session_repo,
            memory_repo=memory_repo,
        )
    )

    results: list[EvalResult] = []
    for case in load_dataset(dataset):
        msg = InboundMessage(
            channel="eval",
            sender_id=case.tenant_external_id,
            chat_id="eval",
            content=case.input,
            session_key_override=case.session_key,
        )
        out = await executor.execute(tenant_id=case.tenant_external_id, message=msg)
        verdict: Verdict = contains_judge(output=out.content, expected_contains=case.expected_contains)
        if verdict.passed and "style:no_ai_phrase" in (case.tags or []):
            verdict = not_contains_judge(output=out.content, forbidden=["as an ai"])
        results.append(
            EvalResult(
                case_id=case.id,
                passed=verdict.passed,
                output=out.content,
                reason=verdict.reason,
            )
        )
    return results

