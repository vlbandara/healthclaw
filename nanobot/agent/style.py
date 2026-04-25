from __future__ import annotations

import re


_BANNED_OPENERS: list[tuple[re.Pattern[str], str]] = [
    # Remove generic assistant framing when it leads the message.
    (re.compile(r"^\s*it sounds like[^.?!]*[.?!]\s*", re.IGNORECASE), ""),
    (re.compile(r"^\s*i understand your concern[^.?!]*[.?!]\s*", re.IGNORECASE), ""),
    (re.compile(r"^\s*it['’]s okay to feel that way[^.?!]*[.?!]\s*", re.IGNORECASE), ""),
]


def sanitize_assistant_text(text: str) -> str:
    out = (text or "").strip()
    if not out:
        return out
    for pat, repl in _BANNED_OPENERS:
        out = pat.sub(repl, out, count=1).strip()
    return out

