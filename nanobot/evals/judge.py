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


def not_contains_judge(*, output: str, forbidden: list[str]) -> Verdict:
    out = (output or "").lower()
    for phrase in forbidden:
        if (phrase or "").lower() in out:
            return Verdict(passed=False, reason=f"forbidden phrase present: {phrase!r}")
    return Verdict(passed=True, reason="ok")

