from __future__ import annotations

import base64
import hashlib
import hmac
import os


def hash_password(password: str) -> str:
    """Hash a password using scrypt (stdlib, no extra deps)."""
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    payload = salt + dk
    return base64.b64encode(payload).decode("ascii")


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        data = base64.b64decode(stored_hash.encode("ascii"))
        salt = data[:16]
        stored_dk = data[16:]
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk, stored_dk)
    except Exception:
        return False
