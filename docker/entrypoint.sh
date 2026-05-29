#!/bin/sh
# Healthclaw container entrypoint.
#
# Loads auto-generated secrets from the shared bootstrap volume (if present)
# and derives the Postgres connection URLs at runtime, so a plain
# `docker compose up` works with zero manual configuration. Anything already
# set in the environment (e.g. via .env) always wins.
set -e

SECRETS_FILE="${HEALTHCLAW_SECRETS_FILE:-/secrets/app.env}"
if [ -f "$SECRETS_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$SECRETS_FILE"
    set +a
fi

: "${POSTGRES_USER:=nanohealth}"
: "${POSTGRES_DB:=nanohealth}"
: "${POSTGRES_HOST:=postgres}"
: "${POSTGRES_PORT:=5432}"

if [ -n "${POSTGRES_PASSWORD:-}" ]; then
    _dsn="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
    # asyncpg registry (orchestrator/worker)
    if [ -z "${NANOBOT_HEALTH_REGISTRY_URL:-}" ]; then
        export NANOBOT_HEALTH_REGISTRY_URL="$_dsn"
    fi
    # alembic migrations
    if [ -z "${NANOBOT_DATABASE_URL:-}" ]; then
        export NANOBOT_DATABASE_URL="$_dsn"
    fi
fi

exec "$@"
