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

# `autoheal` is in the core set on purpose: it is the actor that restarts an `unhealthy` byparr, and a
# watchdog nobody watches reproduces the very outage it exists to prevent.
CORE_SERVICES=(dagster-postgres dagster-codeloc dagster-daemon dagster-webserver dbt-runner flaresolverr caddy autoheal)
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
#
# ⚠️ 2026-08-03 (7-DAY SILENT FANGRAPHS OUTAGE): the probe below said "2xx" in its comment but did not
# ASSERT one. `curl -f` only fails on >= 400, so a REDIRECT passes it — and Byparr's GET / answers
# `301 Moved Permanently`. So when /health began returning 500 (its Camoufox browser could no longer
# launch: "BrowserType.launch: Connection closed while reading from the driver"), the `||` fell through
# to / , collected the 301, exited 0, and this check reported GREEN for SEVEN DAYS while every FanGraphs
# ingest failed. The `||` fallback — added so a classic FlareSolverr without /health still passes —
# silently converted a real health failure into a pass. CURE: compare the ACTUAL status code and require
# 2xx on one of the two endpoints; a 3xx/4xx/5xx from BOTH is now a failure. Timeout is 20s (not 10s)
# because /health may launch a browser; the 3-consecutive-failure debounce absorbs transient slowness.
$COMPOSE exec -T dagster-codeloc sh -c '
  for u in http://flaresolverr:8191/health http://flaresolverr:8191/; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 20 "$u" 2>/dev/null)
    case "$code" in 2??) exit 0 ;; esac
  done
  exit 1
' 2>/dev/null \
  || fails+=("flaresolverr: no 2xx from /health or / on :8191 (solver likely up but browser dead)")

# 3) CLOCK SKEW vs S3 (INC-42, 2026-08-11) — the failure mode nothing here could see.
# AWS SigV4 puts a timestamp in every signature, and S3 rejects a request signed more than ~15 min
# (900s) from ITS clock with `RequestTimeTooSkewed` (HTTP 403). On 2026-08-11 the box clock drifted
# past that bound and every DuckDB-over-S3 read 403'd — `run_w1_lakehouse --w3pre-only` HALTed at the
# INC-23 DESCRIBE, freezing the served game-state flatten.
# ⭐ WHY NO EXISTING CHECK SAW IT: botocore AUTO-CORRECTS for skew (it reads S3's Date header, caches
# the offset and retries), so every boto3 capture kept writing on the half-hour and looked perfectly
# healthy, while DuckDB `httpfs` — and delta-rs/object_store, same category — sign with the local
# clock and hard-fail. Writers green, readers dead. Containers up, endpoints 2xx, nothing to see.
# ⭐ MEASURE AGAINST S3'S OWN CLOCK, not a local NTP daemon's estimate of itself: S3's `Date` header
# IS the clock that decides whether a signature is accepted. Needs no credentials — the root endpoint
# answers 403/400 and still carries `Date`.
# ⛔ NEVER add `-f` to this curl: `-f` suppresses output on >=400, so it would discard the header we
# came for the moment S3 answers 403 (the `curl -f`/301 lesson). ⛔ NEVER add `-L` either: the root
# endpoint answers 307 to aws.amazon.com, and following it would measure a DIFFERENT host's clock.
# ⛔ NEVER use awk's `IGNORECASE` here — it is a GNU-awk extension; under BSD/mawk it silently matches
# nothing, the check reports UNEVALUABLE every 5 min, and an over-paging monitor gets muted.
# `tolower($0) ~ /^date:/` is portable. Verified live against the real endpoint, not assumed.
_skew_max="${CLOCK_SKEW_MAX_S:-300}"   # page well below the 900s hard bound, so drift is caught with runway
_s3_date="$(curl -sS -m 10 -o /dev/null -D - https://s3.us-east-2.amazonaws.com 2>/dev/null \
            | awk 'tolower($0) ~ /^date:/{sub(/^[^:]*:[ \t]*/,""); sub(/\r$/,""); print; exit}')"
if [ -z "$_s3_date" ]; then
  # Unevaluable is NOT a pass (NF1.7(a)) — a check that did not run must never be scored healthy.
  fails+=("clock skew UNEVALUABLE: no Date header from s3.us-east-2.amazonaws.com")
else
  _s3_epoch="$(date -u -d "$_s3_date" +%s 2>/dev/null || echo "")"
  if [ -z "$_s3_epoch" ]; then
    fails+=("clock skew UNEVALUABLE: could not parse S3 Date '${_s3_date}'")
  else
    _skew=$(( $(date -u +%s) - _s3_epoch )); _skew="${_skew#-}"
    if [ "$_skew" -ge "$_skew_max" ]; then
      fails+=("clock skew ${_skew}s vs S3 (SigV4 hard-fails at ~900s — INC-42: DuckDB/delta-rs S3 reads will 403; check chronyd)")
    fi
  fi
fi

# 4) container HEALTH — a container can sit `running` yet `unhealthy` INDEFINITELY.
# ⚠️ 2026-08-03: Byparr ran `Up 3 weeks (unhealthy)` with `restarts=0` — its own Docker HEALTHCHECK was
# red the whole time, but check (1) above only asks whether the container is in the RUNNING set (an
# unhealthy container still is), and `restart: unless-stopped` only reacts to a process EXIT, which never
# happened. So Docker knew, and nothing asked it. This reads the health status Docker already tracks.
# `starting` is NOT a failure (transient post-restart); a service with no HEALTHCHECK declared reports
# `none` and is skipped rather than scored healthy (NF1.7(a) — an unevaluable check is not a pass).
for svc in "${CORE_SERVICES[@]}"; do
  cid="$($COMPOSE ps -q "$svc" 2>/dev/null | head -1)"
  [ -n "$cid" ] || continue   # already reported by check (1) if genuinely down
  hs="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo none)"
  [ "$hs" = "unhealthy" ] && fails+=("container unhealthy: ${svc}")
done

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
