"""Auth layer unit tests — no database required."""

from __future__ import annotations

import time

import pytest

from nanobot.auth.passwords import hash_password, verify_password
from nanobot.auth.tokens import (
    hash_api_key,
    mint_api_key,
    mint_pairing_code,
    mint_session_token,
    verify_session_token,
)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_hash_password_roundtrip():
    pw = "correct-horse-battery"
    stored = hash_password(pw)
    assert verify_password(stored, pw)


def test_wrong_password_fails():
    stored = hash_password("secret")
    assert not verify_password(stored, "wrong")


def test_hashes_are_unique():
    a = hash_password("same")
    b = hash_password("same")
    assert a != b  # different salt each time


# ---------------------------------------------------------------------------
# API key tokens
# ---------------------------------------------------------------------------


def test_mint_api_key_format():
    raw, key_hash, prefix = mint_api_key()
    assert raw.startswith("nb_live_")
    assert len(key_hash) == 64  # sha256 hex
    assert raw.startswith(prefix)


def test_api_key_hash_matches():
    raw, key_hash, _ = mint_api_key()
    assert hash_api_key(raw) == key_hash


def test_api_keys_are_unique():
    k1, _, _ = mint_api_key()
    k2, _, _ = mint_api_key()
    assert k1 != k2


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------


def test_session_token_roundtrip(monkeypatch):
    monkeypatch.setenv("NANOBOT_ONBOARDING_TOKEN_SECRET", "test-secret-abc")
    token = mint_session_token("user-123", "tenant-456")
    claims = verify_session_token(token)
    assert claims is not None
    assert claims.user_id == "user-123"
    assert claims.tenant_id == "tenant-456"
    assert claims.exp > int(time.time())


def test_tampered_session_token_rejected(monkeypatch):
    monkeypatch.setenv("NANOBOT_ONBOARDING_TOKEN_SECRET", "test-secret-abc")
    token = mint_session_token("user-123", "tenant-456")
    # Flip a character in the signature part
    parts = token.rsplit(".", 1)
    bad_token = parts[0] + "." + parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
    assert verify_session_token(bad_token) is None


def test_wrong_secret_rejects_token(monkeypatch):
    monkeypatch.setenv("NANOBOT_ONBOARDING_TOKEN_SECRET", "secret-A")
    token = mint_session_token("u", "t")
    monkeypatch.setenv("NANOBOT_ONBOARDING_TOKEN_SECRET", "secret-B")
    assert verify_session_token(token) is None


def test_session_token_none_for_garbage(monkeypatch):
    monkeypatch.setenv("NANOBOT_ONBOARDING_TOKEN_SECRET", "test-secret-abc")
    assert verify_session_token("not.a.real.token") is None
    assert verify_session_token("") is None


# ---------------------------------------------------------------------------
# Pairing codes
# ---------------------------------------------------------------------------


def test_pairing_code_format():
    code = mint_pairing_code()
    assert code.isdigit()
    assert len(code) == 6
    assert 100000 <= int(code) <= 999999


def test_pairing_codes_are_unique():
    codes = {mint_pairing_code() for _ in range(50)}
    # With 900000 possible values, 50 samples should almost never collide
    assert len(codes) > 40
