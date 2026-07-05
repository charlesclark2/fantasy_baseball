#!/usr/bin/env bash
# =============================================================================
# INC-16-P6 / INC-16-P6a — service-liveness healthcheck (host-cron, every 5 min).
#
# INC-16-P6a (2026-06-28): two false-positive suppressions so CD deploys don't page:
#   1. Deploy lock — deploy.sh writes /tmp/credence_deploy_in_progress; while it
#      exists healthcheck skips entirely and resets the fail counter.
#   2. Debounce — requires FAIL_THRESHOLD (3) consecutive failed checks before
#      paging. A transient single-check recreate window cannot page; a real
#      sustained outage still pages within ~15 min (3 × 5 min).
#
# A plain EC2 ping says "box is up" but misses a crashed container or a daemon
# that stopped ticking. This asserts the CORE services are running + reachable
# and pages (once per cooldown) if not. The run-once `capture-*` services are
# intentionally NOT checked (they exit by design).
#
# Install: a line in capture.crontab runs this every 5 min as ec2-user.
# =============================================================================
set -uo pipefail
APP_DIR="${APP_DIR:-/home/ec2-user/app}"
COMPOSE="docker compose -f ${APP_DIR}/services/dagster/aws/docker-compose.yml"
COOLDOWN_FILE="/tmp/credence_healthcheck_last_alert"
COOLDOWN_S="${HEALTHCHECK_COOLDOWN_S:-3600}"    # at most one page/hour for a sustained outage
FAIL_COUNT_FILE="/tmp/credence_healthcheck_fail_count"
FAIL_THRESHOLD="${HEALTHCHECK_FAIL_THRESHOLD:-3}"  # consecutive failures before paging (~15 min)
DEPLOY_LOCK="/tmp/credence_deploy_in_progress"

# shellcheck source=/dev/null
source "${APP_DIR}/services/dagster/aws/notify.sh"

# --- deploy-aware suppression -------------------------------------------------
# If a CD deploy is in progress, containers may be transiently restarting.
# Reset the fail counter (deploy will restore a healthy state) and skip this run.
if [ -f "$DEPLOY_LOCK" ]; then
  echo "[healthcheck $(date -u +%H:%M:%S)] deploy in progress — skipping check, counter reset"
  echo "0" > "$FAIL_COUNT_FILE"
  exit 0
fi

CORE_SERVICES=(dagster-postgres dagster-codeloc dagster-daemon dagster-webserver dbt-runner flaresolverr caddy)
fails=()

# 1) every core service must be in the running set
running="$($COMPOSE ps --status running --services 2>/dev/null)"
for svc in "${CORE_SERVICES[@]}"; do
  echo "$running" | grep -qx "$svc" || fails+=("container down: ${svc}")
done

# 2) HTTP reachability — dagit on the host loopback; internal services via a container
curl -fsS -o /dev/null --max-time 10 http://localhost:3000 2>/dev/null \
  || fails+=("dagit unreachable on localhost:3000")
$COMPOSE exec -T dagster-codeloc curl -fsS --max-time 10 http://dbt-runner:8080/health 2>/dev/null | grep -q '"ok"' \
  || fails+=("dbt-runner /health not ok")
# Byparr (INC-26, 2026-07-05 — replaced EOL FlareSolverr) is FlareSolverr-API-compatible but its GET /
# does NOT echo the literal "flaresolverr" the old probe grepped for (and its / may not even 200 — it's a
# FastAPI app), so that content-string assertion FALSE-PAGED CRITICAL every run while Byparr was Up
# (healthy) and pulling rows. Probe /health for a 2xx (Byparr's own Docker HEALTHCHECK uses it), falling
# back to / for a classic FlareSolverr — reachability only, NO response-body string match.
$COMPOSE exec -T dagster-codeloc sh -c 'curl -fsS -o /dev/null --max-time 10 http://flaresolverr:8191/health || curl -fsS -o /dev/null --max-time 10 http://flaresolverr:8191/' 2>/dev/null \
  || fails+=("flaresolverr unreachable on :8191")

if [ "${#fails[@]}" -eq 0 ]; then
  echo "[healthcheck $(date -u +%H:%M:%S)] OK — all core services up"
  echo "0" > "$FAIL_COUNT_FILE"
  exit 0
fi

# --- debounce: require FAIL_THRESHOLD consecutive failures before paging ------
fail_count="$(cat "$FAIL_COUNT_FILE" 2>/dev/null || echo 0)"
fail_count=$((fail_count + 1))
echo "$fail_count" > "$FAIL_COUNT_FILE"

if [ "$fail_count" -lt "$FAIL_THRESHOLD" ]; then
  echo "[healthcheck $(date -u +%H:%M:%S)] FAIL ${fail_count}/${FAIL_THRESHOLD} — not paging yet: ${fails[*]}" >&2
  exit 1
fi

# cooldown: suppress repeat pages within COOLDOWN_S of the last one
now="$(date +%s)"
if [ -f "$COOLDOWN_FILE" ]; then
  last="$(cat "$COOLDOWN_FILE" 2>/dev/null || echo 0)"
  if [ $((now - last)) -lt "$COOLDOWN_S" ]; then
    echo "[healthcheck] FAIL but within cooldown — not re-paging: ${fails[*]}" >&2
    exit 1
  fi
fi
echo "$now" > "$COOLDOWN_FILE"

body="The orchestration box has unhealthy core service(s):

$(printf '  - %s\n' "${fails[@]}")
First action: aws ssm start-session --target i-07594af1679f81c38, then
  cd ${APP_DIR}/services/dagster/aws && docker compose ps
  docker compose logs --tail=100 <service>"
notify CRITICAL "box service(s) unhealthy" "$body"
echo "[healthcheck] PAGED: ${fails[*]}" >&2
exit 1
