#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

require_bin curl

BASE_URL=""
HOST="${PROD_HOST:-}"
USER_NAME="${PROD_USER:-root}"
APP_DIR="${PROD_APP_DIR:-/opt/healthclaw}"
LOG_SINCE="${LOG_SINCE:-15m}"
OUT_DIR=""
RETRIES="${SMOKE_RETRIES:-20}"
SLEEP_SECONDS="${SMOKE_SLEEP_SECONDS:-3}"
MAX_DISK_USE_PERCENT="${PROD_MAX_DISK_USE_PERCENT:-90}"
MIN_MEM_AVAILABLE_MB="${PROD_MIN_MEM_AVAILABLE_MB:-256}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --user)
      USER_NAME="$2"
      shift 2
      ;;
    --app-dir)
      APP_DIR="$2"
      shift 2
      ;;
    --since)
      LOG_SINCE="$2"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --retries)
      RETRIES="$2"
      shift 2
      ;;
    --sleep-seconds)
      SLEEP_SECONDS="$2"
      shift 2
      ;;
    *)
      prod_die "Unknown argument: $1"
      ;;
  esac
done

BASE_URL="${BASE_URL:-$(default_base_url "${HOST}")}"
OUT_DIR="${OUT_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/healthclaw-smoke.XXXXXX")}"
ensure_dir "${OUT_DIR}"
ensure_dir "${OUT_DIR}/endpoints"

FAILURES=()
ENDPOINTS=(healthz readyz metrics api/admin/status)

prod_log "Running smoke checks against ${BASE_URL}"

for endpoint in "${ENDPOINTS[@]}"; do
  safe_name="${endpoint//\//_}"
  headers_path="${OUT_DIR}/endpoints/${safe_name}.headers"
  body_path="${OUT_DIR}/endpoints/${safe_name}.body"
  url="${BASE_URL%/}/${endpoint}"
  http_code=""
  attempt=1
  while (( attempt <= RETRIES )); do
    http_code="$(curl -sS -X GET -H 'Accept: application/json' -D "${headers_path}" -o "${body_path}" -w '%{http_code}' "${url}" || true)"
    if [[ "${http_code}" =~ ^2 ]]; then
      break
    fi
    if (( attempt < RETRIES )); then
      sleep "${SLEEP_SECONDS}"
    fi
    attempt=$((attempt + 1))
  done
  if [[ ! "${http_code}" =~ ^2 ]]; then
    FAILURES+=("endpoint:${endpoint}:http_${http_code}")
  fi
done

if [[ -n "${HOST}" ]]; then
  require_bin ssh
  target="$(ssh_target "${HOST}" "${USER_NAME}")"
  prod_log "Collecting remote compose status from ${target}:${APP_DIR}"
  ssh "${target}" "uptime" >"${OUT_DIR}/remote-uptime.txt" 2>"${OUT_DIR}/remote-uptime.stderr" || FAILURES+=("host:uptime_failed")
  ssh "${target}" "free -m" >"${OUT_DIR}/remote-free.txt" 2>"${OUT_DIR}/remote-free.stderr" || FAILURES+=("host:memory_snapshot_failed")
  ssh "${target}" "df -Pm /" >"${OUT_DIR}/remote-df-root.txt" 2>"${OUT_DIR}/remote-df-root.stderr" || FAILURES+=("host:disk_snapshot_failed")
  ssh "${target}" "docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}|{{.NetIO}}|{{.BlockIO}}'" >"${OUT_DIR}/docker-stats.txt" 2>"${OUT_DIR}/docker-stats.stderr" || FAILURES+=("host:docker_stats_failed")
  ssh "${target}" "cd '${APP_DIR}' && docker compose ps" >"${OUT_DIR}/docker-compose-ps.txt" 2>"${OUT_DIR}/docker-compose-ps.stderr" || FAILURES+=("remote:docker_compose_ps_failed")
  ssh "${target}" "cd '${APP_DIR}' && docker compose logs --since '${LOG_SINCE}' --timestamps --no-color" >"${OUT_DIR}/docker-compose-logs.txt" 2>"${OUT_DIR}/docker-compose-logs.stderr" || FAILURES+=("remote:docker_compose_logs_failed")
  if [[ -f "${OUT_DIR}/docker-compose-ps.txt" ]]; then
    if grep -Eiq 'unhealthy|restarting|dead|exit [1-9]' "${OUT_DIR}/docker-compose-ps.txt"; then
      FAILURES+=("remote:compose_unhealthy")
    fi
  fi
  if [[ -f "${OUT_DIR}/docker-compose-logs.txt" ]]; then
    if grep -Eiq 'Traceback|ERROR|Exception|Restarting|health\.worker\.crashed|spawn_failed|queue_failed' "${OUT_DIR}/docker-compose-logs.txt"; then
      FAILURES+=("remote:log_pattern_match")
    fi
  fi
  if [[ -f "${OUT_DIR}/remote-free.txt" ]]; then
    mem_available_mb="$(awk '/^Mem:/ {print $7}' "${OUT_DIR}/remote-free.txt" | tail -n 1)"
    if [[ "${mem_available_mb}" =~ ^[0-9]+$ ]] && (( mem_available_mb < MIN_MEM_AVAILABLE_MB )); then
      FAILURES+=("host:memory_available_low")
    fi
  fi
  if [[ -f "${OUT_DIR}/remote-df-root.txt" ]]; then
    disk_use_percent="$(awk 'NR==2 {gsub(/%/, "", $5); print $5}' "${OUT_DIR}/remote-df-root.txt")"
    if [[ "${disk_use_percent}" =~ ^[0-9]+$ ]] && (( disk_use_percent >= MAX_DISK_USE_PERCENT )); then
      FAILURES+=("host:disk_usage_high")
    fi
  fi
fi

STATUS="ok"
if (( ${#FAILURES[@]} > 0 )); then
  STATUS="failed"
fi

python3 - "${OUT_DIR}" "${BASE_URL}" "${STATUS}" "${HOST}" "${APP_DIR}" "${LOG_SINCE}" "${FAILURES[@]-}" <<'PY'
import json
import sys
from datetime import datetime, timezone

out_dir, base_url, status, host, app_dir, log_since, *failures = sys.argv[1:]
failures = [item for item in failures if item]
payload = {
    "checkedAt": datetime.now(timezone.utc).isoformat(),
    "status": status,
    "baseUrl": base_url,
    "host": host,
    "appDir": app_dir,
    "logSince": log_since,
    "failures": failures,
}
with open(f"{out_dir}/summary.json", "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
PY

cat "${OUT_DIR}/summary.json"

if (( ${#FAILURES[@]} > 0 )); then
  exit 1
fi
