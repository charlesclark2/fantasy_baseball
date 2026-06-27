#!/usr/bin/env bash
# =============================================================================
# INC-16-P5 — on-box deploy (the CD payload; invoked by SSM Run Command on merge
# to main, or run manually on the box).
#
#   bash services/dagster/aws/deploy.sh
#
# Does, in order:
#   0. env-parity: every key in env.required is present AND non-empty in .env
#      (empty SHADOWS code defaults — the P4 trap). Abort before touching anything.
#   1. snapshot current images → :rollback (for auto-revert on a bad deploy)
#   2. git pull origin main (records the range for change-detection)
#   3. graceful drain — wait for in-flight Dagster runs to finish before recreate
#   4. rebuild + redeploy: `up -d --build` (core) AND `--profile capture build`
#      ⭐ the WHOLE point — a git pull does NOT update a running container; the code
#         is COPY'd into the image, so it must be rebuilt (P4 baked-image drift).
#   5. reinstall the host crontab IFF capture.crontab changed in the pull
#   6. post-deploy verify (defs load, daemon up, dbt-runner health, PEM, instance
#      role reachable from a container = IMDS hop-limit ok). On FAILURE → roll back
#      images to :rollback, recreate, exit 1 loudly (never leave a half-deploy).
# =============================================================================
set -uo pipefail

APP_DIR="${APP_DIR:-/home/ec2-user/app}"
COMPOSE="docker compose -f ${APP_DIR}/services/dagster/aws/docker-compose.yml"
ENV_FILE="${APP_DIR}/services/dagster/aws/.env"
REQUIRED="${APP_DIR}/services/dagster/aws/env.required"
CRONTAB="${APP_DIR}/services/dagster/aws/capture.crontab"
DRAIN_TIMEOUT="${DRAIN_TIMEOUT:-600}"     # seconds to wait for in-flight runs
LOCAL_GQL="http://localhost:3000/graphql"

cd "$APP_DIR"
log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }
die() { echo "[deploy ERROR] $*" >&2; exit 1; }

# --- 0. env-parity: required keys present AND non-empty (KEY= counts as MISSING)
log "env-parity check against env.required"
missing=()
while IFS= read -r key; do
  key="${key%%#*}"; key="$(echo "$key" | tr -d '[:space:]')"
  [ -z "$key" ] && continue
  val="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  [ -z "$val" ] && missing+=("$key")
done < "$REQUIRED"
if [ "${#missing[@]}" -gt 0 ]; then
  die "box .env missing/empty required keys: ${missing[*]} (empty shadows code defaults)"
fi
log "env-parity OK"

# --- 1. snapshot current images for rollback --------------------------------
ROLLBACK_IMAGES=(credence-dagster credence-dbt-runner)
for img in "${ROLLBACK_IMAGES[@]}"; do
  if docker image inspect "${img}:latest" >/dev/null 2>&1; then
    docker tag "${img}:latest" "${img}:rollback"
    log "snapshot ${img}:latest -> :rollback"
  fi
done

rollback() {
  log "ROLLING BACK to previous images"
  for img in "${ROLLBACK_IMAGES[@]}"; do
    docker image inspect "${img}:rollback" >/dev/null 2>&1 && docker tag "${img}:rollback" "${img}:latest"
  done
  $COMPOSE up -d --no-build
  die "$1"
}

# --- 2. pull -----------------------------------------------------------------
OLD_HEAD="$(git rev-parse HEAD)"
log "git pull origin main (from ${OLD_HEAD:0:8})"
git pull --ff-only origin main || die "git pull failed"
NEW_HEAD="$(git rev-parse HEAD)"
log "now at ${NEW_HEAD:0:8}"

# --- 3. graceful drain — let in-flight runs finish --------------------------
log "draining in-flight Dagster runs (timeout ${DRAIN_TIMEOUT}s)"
in_flight() {
  curl -fsS "$LOCAL_GQL" -H 'Content-Type: application/json' \
    --data '{"query":"{ runsOrError(filter:{statuses:[STARTED]}, limit:1){ __typename ... on Runs { results { runId } } } }"}' 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(len((d.get('data',{}).get('runsOrError',{}) or {}).get('results',[])))" 2>/dev/null || echo 0
}
waited=0
while [ "$(in_flight)" != "0" ] && [ "$waited" -lt "$DRAIN_TIMEOUT" ]; do
  log "  in-flight run(s) active — waiting…"; sleep 20; waited=$((waited+20))
done
[ "$(in_flight)" != "0" ] && log "  WARN: drain timed out — proceeding (runs may retry)"

# --- 4. rebuild + redeploy (core + capture profile) -------------------------
log "rebuild + redeploy core services"
$COMPOSE up -d --build || rollback "core build/up failed"
log "rebuild capture-profile images"
$COMPOSE --profile capture build || rollback "capture build failed"

# --- 5. reinstall host crontab IFF capture.crontab changed ------------------
if git diff --name-only "${OLD_HEAD}..${NEW_HEAD}" | grep -q 'services/dagster/aws/capture.crontab'; then
  log "capture.crontab changed → reinstalling host crontab"
  crontab "$CRONTAB" || log "  WARN: crontab reinstall failed (check cronie installed)"
else
  log "capture.crontab unchanged — no crontab reinstall"
fi

# --- 6. post-deploy verify --------------------------------------------------
log "post-deploy verification"
sleep 8   # let containers settle

$COMPOSE exec -T dagster-codeloc python -c "import pipeline" \
  || rollback "defs failed to import in codeloc"
$COMPOSE ps --status running 2>/dev/null | grep -q dagster-daemon \
  || rollback "dagster-daemon not running"
$COMPOSE exec -T dagster-codeloc curl -fsS http://dbt-runner:8080/health | grep -q '"ok"' \
  || rollback "dbt-runner /health not ok"
$COMPOSE exec -T dagster-codeloc head -1 /tmp/snowflake_rsa_key.pem | grep -q 'BEGIN' \
  || rollback "Snowflake PEM not materialized (normalize bug?)"
# instance role reachable from inside a container ⇒ IMDSv2 hop-limit>=2 + region ok
$COMPOSE exec -T dagster-codeloc python -c "import boto3; boto3.client('sts').get_caller_identity()" \
  || rollback "container cannot reach instance role (IMDS hop-limit / region?)"

# --- success ----------------------------------------------------------------
for img in "${ROLLBACK_IMAGES[@]}"; do docker image inspect "${img}:rollback" >/dev/null 2>&1 && docker rmi "${img}:rollback" >/dev/null 2>&1 || true; done
log "✅ deploy OK — main (${NEW_HEAD:0:8}) live on the box; all checks passed"
