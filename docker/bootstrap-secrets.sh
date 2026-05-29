#!/bin/sh
# One-shot secret bootstrap for Healthclaw.
#
# Generates a Fernet vault key and a Postgres password on first run and
# persists them to a shared volume so that no human ever has to copy a
# template or run a key-generation one-liner. Idempotent: existing secrets
# are left untouched, so encrypted data and the database password stay
# stable across restarts.
set -e

SECRETS_DIR="${HEALTHCLAW_SECRETS_DIR:-/secrets}"
APP_ENV="${SECRETS_DIR}/app.env"
PG_PASSWORD_FILE="${SECRETS_DIR}/postgres_password"

mkdir -p "$SECRETS_DIR"

if [ -f "$APP_ENV" ] && [ -f "$PG_PASSWORD_FILE" ]; then
    echo "healthclaw-bootstrap: secrets already present, leaving them untouched"
    exit 0
fi

python - "$APP_ENV" "$PG_PASSWORD_FILE" <<'PY'
import os
import secrets
import sys

from cryptography.fernet import Fernet

app_env, pg_password_file = sys.argv[1], sys.argv[2]

vault_key = os.environ.get("HEALTH_VAULT_KEY", "").strip() or Fernet.generate_key().decode()
pg_password = os.environ.get("POSTGRES_PASSWORD", "").strip() or secrets.token_hex(24)

with open(pg_password_file, "w", encoding="utf-8") as fh:
    fh.write(pg_password)

with open(app_env, "w", encoding="utf-8") as fh:
    fh.write(f"HEALTH_VAULT_KEY={vault_key}\n")
    fh.write(f"POSTGRES_PASSWORD={pg_password}\n")

print("healthclaw-bootstrap: generated vault key and postgres password")
PY

# World-readable within this private volume so the non-root orchestrator/worker
# (uid 1000) and the postgres user (uid 999) can read their secrets.
chmod 644 "$APP_ENV" "$PG_PASSWORD_FILE" 2>/dev/null || true
