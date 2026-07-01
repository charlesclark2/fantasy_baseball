#!/usr/bin/env bash
# =============================================================================
# INC-16-P5 — on-box deploy (the CD payload; invoked by SSM Run Command on merge
# to main, or run manually on the box).
#
#   bash services/dagster/aws/deploy.sh
#
# Does, in order:
#   1. git pull origin main (records the range for change-detection). MUST be first
#      so env-parity below validates the env.required we're DEPLOYING, not the stale
#      copy already on the box — otherwise removing/adding a required key never takes
#      effect via CD without a manual pull. A pull touches only the working tree, not
#      running containers/images, so nothing serving is mutated yet.
#   2. env-parity: every key in (the just-pulled) env.required is present AND
#      non-empty in .env (empty SHADOWS code defaults — the P4 trap). die() on fail —
#      no images touched yet, so no rollback needed.
#   3. snapshot current images → :rollback (for auto-revert on a bad deploy)
#   4. graceful drain — wait for in-flight Dagster runs to finish before recreate
#   5. rebuild + redeploy: `up -d --build` (core) AND `--profile capture build`
#      ⭐ the WHOLE point — a git pull does NOT update a running container; the code
#         is COPY'd into the image, so it must be rebuilt (P4 baked-image drift).
#   6. reinstall the host crontab IFF capture.crontab changed in the pull
#   7. post-deploy verify (defs load, daemon up, dbt-runner health, PEM, instance
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

# INC-16-P6: source the shared notifier so an auto-rollback pages (best-effort).
# shellcheck source=/dev/null
source "${APP_DIR}/services/dagster/aws/notify.sh" 2>/dev/null || notify() { :; }

# INC-16-P6a: deploy lock — tells healthcheck.sh containers may be transiently
# restarting during `up -d --build`; it skips checks + resets its fail counter
# while this file exists. Trap removes it on any exit (normal, die, rollback).
DEPLOY_LOCK="/tmp/credence_deploy_in_progress"
touch "$DEPLOY_LOCK"
trap 'rm -f "$DEPLOY_LOCK"' EXIT
log "deploy lock acquired (${DEPLOY_LOCK})"

# --- 1. pull (FIRST — so env-parity validates the env.required being deployed) --
OLD_HEAD="$(git rev-parse HEAD)"
# The host crontab is hand-editable on the box (operators toggle capture crons for Odds-API
# credit windows), but the COMMITTED capture.crontab is the single source of truth — the
# reconcile step (§6) re-installs it every deploy regardless. A local edit otherwise makes
# `git pull --ff-only` ABORT ("Your local changes would be overwritten by merge") and fails
# the WHOLE CD deploy (recurring 2026-06-30/07-01). Discard drift on JUST capture.crontab
# before the pull — LOUD so the log shows it — restoring it to HEAD (the pull then brings the
# committed version). Untracked files (.env, backups) are never touched; OTHER tracked-file
# drift still (correctly) aborts the pull so a real on-box edit gets investigated, not eaten.
if ! git diff --quiet -- services/dagster/aws/capture.crontab; then
  log "WARN: discarding local edits to capture.crontab (committed version is source of truth):"
  git --no-pager diff --stat -- services/dagster/aws/capture.crontab | sed 's/^/    /' || true
  git checkout HEAD -- services/dagster/aws/capture.crontab || true
fi
log "git pull origin main (from ${OLD_HEAD:0:8})"
git pull --ff-only origin main || die "git pull failed"
NEW_HEAD="$(git rev-parse HEAD)"
log "now at ${NEW_HEAD:0:8}"

# --- 2. env-parity: required keys present AND non-empty (KEY= counts as MISSING)
# Runs against the JUST-PULLED env.required. die() on fail — no images touched yet.
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

# --- 3. snapshot current images for rollback --------------------------------
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
  notify CRITICAL "CD auto-rollback on box" \
    "A deploy to the orchestration box FAILED verification and was auto-rolled-back to the previous images. Reason: $1. Box is serving on the PREVIOUS image — investigate the failed deploy (Actions log + Dagit) before the next merge." 2>/dev/null || true
  die "$1"
}

# --- 4. graceful drain — let in-flight runs finish --------------------------
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

# --- 5. rebuild + redeploy (core + capture profile) -------------------------
log "rebuild + redeploy core services"
$COMPOSE up -d --build || rollback "core build/up failed"
log "rebuild capture-profile images"
$COMPOSE --profile capture build || rollback "capture build failed"

# --- 6. reconcile host crontab to the committed source of truth (ALWAYS) ----
# INC-23 (2026-06-30): this used to reinstall ONLY IFF capture.crontab changed in the
# pull. That let a resize / reprovision / on-box `crontab -e` mistake silently DROP the
# capture crons (incl. odds-capture) — a deploy that didn't touch capture.crontab would
# report success with NO host crontab installed → the 5.6h odds-capture stall (mlb_odds_raw
# went 336 min stale). The committed capture.crontab is the SINGLE SOURCE OF TRUTH; reconcile
# to it on EVERY deploy (`crontab <file>` idempotently replaces the whole table) and ALERT
# LOUDLY if the install fails or the odds-capture line is absent afterward — never a silent skip.
if git diff --name-only "${OLD_HEAD}..${NEW_HEAD}" | grep -q 'services/dagster/aws/capture.crontab'; then
  log "reconciling host crontab (capture.crontab CHANGED in this pull)"
else
  log "reconciling host crontab (capture.crontab unchanged — reinstalled idempotently anyway)"
fi
if ! crontab "$CRONTAB"; then
  notify CRITICAL "host crontab reinstall FAILED on box" \
    "deploy.sh could not install ${CRONTAB} (cronie missing / crond down / spool not writable). The capture crons (odds/derivative/weather/schedule) are NOT scheduled — odds WILL go stale. Fix on the box: 'sudo dnf install -y cronie && sudo systemctl enable --now crond', then re-run deploy." 2>/dev/null || true
  die "crontab reinstall failed — capture crons not scheduled (see CRITICAL alert)"
fi
# A `crontab <file>` can return 0 yet leave an empty/partial table on some minimal AMIs;
# verify the odds-capture line actually landed (the line whose absence == the INC-23 stall).
# 2026-07-01: this verify false-failed 3 CONSECUTIVE CD deploys while a standalone repro of
# the SAME commands (same user + `sudo -u ec2-user -H` env) passed with the line present —
# the install DID land, but `crontab -l` read EMPTY in the tiny window while crond reloads
# the just-written spool. The reconcile runs right after a container-recreation storm, which
# widens that race, and the old `2>/dev/null` hid the transient read error so it looked
# "absent" and die()'d the whole deploy (auto-rollback). Retry the read, RE-ASSERTING the
# install each round, and dump the real crontab + stderr before ever giving up.
_odds_seen=0
for _try in 1 2 3 4 5; do
  if crontab -l 2>/tmp/credence_crontab_err | grep -q 'run --rm odds-capture'; then
    _odds_seen=1; break
  fi
  log "  crontab verify ${_try}/5: odds-capture not visible yet (crond reload race?); stderr: $(tr '\n' ' ' < /tmp/credence_crontab_err 2>/dev/null)"
  sleep 2
  crontab "$CRONTAB" >/dev/null 2>&1 || true   # re-assert the install before the next read
done
if [ "$_odds_seen" != "1" ]; then
  log "  odds-capture GENUINELY absent after 5 tries — FINAL crontab -l dump:"
  crontab -l 2>&1 | sed 's/^/    /' || true
  notify CRITICAL "odds-capture cron MISSING after reinstall on box" \
    "crontab installed but 'crontab -l' had no odds-capture line after 5 retries — live odds capture will go stale. Investigate crond/spool on the box (SSM)." 2>/dev/null || true
  die "odds-capture cron absent after reinstall (see CRITICAL alert)"
fi
log "  host crontab reconciled — odds-capture line present"

# --- 7. post-deploy verify --------------------------------------------------
log "post-deploy verification"

# The daemon waits on postgres + the codeloc gRPC server before it reports 'running',
# so a single check after a fixed `sleep 8` is racy — it false-rolled-back a HEALTHY
# W3pre deploy on 2026-06-28 (daemon just wasn't 'running' yet at the 8s mark; the
# build + `import pipeline` had both passed). Poll readiness instead; a genuine crash
# still rolls back after the timeout (and we dump the daemon logs to show why).
VERIFY_TIMEOUT="${VERIFY_TIMEOUT:-120}"
waited=0
until $COMPOSE ps --status running 2>/dev/null | grep -q dagster-daemon; do
  if [ "$waited" -ge "$VERIFY_TIMEOUT" ]; then
    log "dagster-daemon still not running after ${VERIFY_TIMEOUT}s — recent logs:"
    $COMPOSE logs --tail 40 dagster-daemon 2>&1 | sed 's/^/    /' || true
    rollback "dagster-daemon not running after ${VERIFY_TIMEOUT}s"
  fi
  sleep 5; waited=$((waited+5))
done
log "  dagster-daemon running (after ${waited}s)"

# Daemon up ⇒ codeloc gRPC is up; the codeloc-exec checks below can run.
$COMPOSE exec -T dagster-codeloc python -c "import pipeline" \
  || rollback "defs failed to import in codeloc"
# dbt-runner can also lag its first /health — poll it the same way.
waited=0
until $COMPOSE exec -T dagster-codeloc curl -fsS http://dbt-runner:8080/health 2>/dev/null | grep -q '"ok"'; do
  if [ "$waited" -ge "$VERIFY_TIMEOUT" ]; then
    log "dbt-runner /health not ok after ${VERIFY_TIMEOUT}s — recent logs:"
    $COMPOSE logs --tail 40 dbt-runner 2>&1 | sed 's/^/    /' || true
    rollback "dbt-runner /health not ok after ${VERIFY_TIMEOUT}s"
  fi
  sleep 5; waited=$((waited+5))
done
log "  dbt-runner /health ok"
$COMPOSE exec -T dagster-codeloc head -1 /tmp/snowflake_rsa_key.pem | grep -q 'BEGIN' \
  || rollback "Snowflake PEM not materialized (normalize bug?)"
# instance role reachable from inside a container ⇒ IMDSv2 hop-limit>=2 + region ok
$COMPOSE exec -T dagster-codeloc python -c "import boto3; boto3.client('sts').get_caller_identity()" \
  || rollback "container cannot reach instance role (IMDS hop-limit / region?)"

# --- success ----------------------------------------------------------------
for img in "${ROLLBACK_IMAGES[@]}"; do docker image inspect "${img}:rollback" >/dev/null 2>&1 && docker rmi "${img}:rollback" >/dev/null 2>&1 || true; done
log "✅ deploy OK — main (${NEW_HEAD:0:8}) live on the box; all checks passed"
