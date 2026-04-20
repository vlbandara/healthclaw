from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Verdict:
    passed: bool
    reason: str = ""


def contains_judge(*, output: str, expected_contains: str) -> Verdict:
    exp = (expected_contains or "").strip()
    if not exp:
        return Verdict(passed=True, reason="no expectation")
    ok = exp.lower() in (output or "").lower()
    return Verdict(passed=ok, reason=f"expected substring: {exp!r}")

