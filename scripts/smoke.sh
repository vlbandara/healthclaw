#!/usr/bin/env bash
# Smoke test: confirm a running Healthclaw stack is actually serving.
#
#   ./scripts/smoke.sh                 # checks http://localhost:8080
#   HEALTHCLAW_URL=https://host ./scripts/smoke.sh
#
# Exits non-zero (and prints why) if the orchestrator never becomes healthy.
set -euo pipefail

URL="${HEALTHCLAW_URL:-http://localhost:${HEALTH_HTTP_PORT:-8080}}"
TIMEOUT="${SMOKE_TIMEOUT_SECONDS:-120}"

echo "→ waiting for ${URL}/healthz (up to ${TIMEOUT}s)"
deadline=$(( $(date +%s) + TIMEOUT ))
until curl -fsS "${URL}/healthz" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "✗ ${URL}/healthz never responded within ${TIMEOUT}s" >&2
        exit 1
    fi
    sleep 2
done
echo "✓ /healthz ok"

echo "→ checking ${URL}/readyz"
if curl -fsS "${URL}/readyz" >/dev/null 2>&1; then
    echo "✓ /readyz ok"
else
    # readyz returns 503 while subsystems warm up; report but don't fail the smoke.
    echo "! /readyz not ready yet (continuing)"
fi

echo "→ checking landing page"
curl -fsS "${URL}/" >/dev/null
echo "✓ landing page served"

echo "✓ Healthclaw is up at ${URL}"
