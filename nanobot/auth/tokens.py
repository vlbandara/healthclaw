from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii"))


def _require_secret() -> bytes:
    secret = os.environ.get("NANOBOT_ONBOARDING_TOKEN_SECRET", "").strip()
    if not secret:
        raise RuntimeError("NANOBOT_ONBOARDING_TOKEN_SECRET is required")
    return secret.encode("utf-8")


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


def mint_api_key() -> tuple[str, str, str]:
    """Mint a new API key.

    Returns (raw_key, key_hash, prefix).
    Only raw_key is shown to the user once; store key_hash + prefix.
    """
    raw_bytes = secrets.token_bytes(32)
    raw = "nb_live_" + _b64url(raw_bytes)
    key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    prefix = raw[:16]
    return raw, key_hash, prefix


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Session cookies (signed, stateless)
# ---------------------------------------------------------------------------

_SESSION_TTL_SECONDS = 7 * 24 * 3600  # 7 days


@dataclass(slots=True)
class SessionClaims:
    user_id: str
    tenant_id: str
    exp: int


def mint_session_token(user_id: str, tenant_id: str) -> str:
    """Create a signed session token embedding user_id + tenant_id."""
    exp = int(time.time()) + _SESSION_TTL_SECONDS
    payload = json.dumps({"uid": user_id, "tid": tenant_id, "exp": exp}, separators=(",", ":"))
    payload_b64 = _b64url(payload.encode("utf-8"))
    secret = _require_secret()
    sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url(sig)}"


def verify_session_token(token: str) -> SessionClaims | None:
    """Verify and decode a session token. Returns None if invalid or expired."""
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except (ValueError, AttributeError):
        return None
    secret = _require_secret()
    expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception:
        return None
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return SessionClaims(
        user_id=str(payload["uid"]),
        tenant_id=str(payload["tid"]),
        exp=int(payload["exp"]),
    )


# ---------------------------------------------------------------------------
# Channel pairing codes (short, human-friendly) — kept for future use
# ---------------------------------------------------------------------------


def mint_pairing_code() -> str:
    """Short numeric pairing code for channel linking (6 digits)."""
    return str(secrets.randbelow(900000) + 100000)


# ---------------------------------------------------------------------------
# Telegram deep-link tokens  (one-time, stored plaintext — already high entropy)
# ---------------------------------------------------------------------------

_LINK_TOKEN_TTL = 15 * 60  # 15 minutes


def mint_link_token() -> str:
    """Generate a one-time Telegram deep-link token.

    Format: ``lnk_<32 random bytes as base64url>``
    Stored plaintext in channel_pairing_codes.code (it is already
    cryptographically random, so no need to hash).
    """
    return "lnk_" + _b64url(secrets.token_bytes(32))
