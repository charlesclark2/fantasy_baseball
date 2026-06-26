#!/usr/bin/env bash
# =============================================================================
# scripts/dbt_state.sh  —  E11.16: honest, Platform-free `state:modified+` locally
# =============================================================================
# WHY THIS EXISTS
# ---------------
# dbt-fusion's `state:modified` selector, when run WITHOUT an explicit `--state`,
# auto-tries to DOWNLOAD a "deferral manifest" from dbt Platform for the active
# project in ~/.dbt/dbt_cloud.yml. This repo is self-managed (no dbt Platform
# deployment), so that download 404s:
#
#   [HttpError (dbt1203)]: Failed to download deferral manifest from the dbt
#   platform for project 441385, continuing without deferral. 404 Not Found:
#   No deferral environment defined for project with ID 441385
#
# It's "only a warning" — but it ALSO means `state:modified+` has lost its
# baseline, so the local selection is unreliable (and the operator burned a
# debugging session on it during W1d). Verified fix: passing `--state <dir>`
# suppresses the Platform call ENTIRELY and gives a correct, prod-relative diff
# — exactly what CI (dbt_build_ci.yml) already does on clean Ubuntu runners
# (which have no ~/.dbt/dbt_cloud.yml, so they never hit the 404).
#
# This wrapper mirrors CI locally: it fetches the SAME prod manifest baseline CI
# uses (the "Publish manifest baseline (main only)" artifact from dbt_build_ci.yml,
# 90-day retention) into dbt/state/, then runs your dbt command with
# `--state dbt/state --defer` so unbuilt upstreams resolve to the prod relations
# recorded in that manifest.
#
# USAGE (run from repo root):
#   scripts/dbt_state.sh ls   --select state:modified+ --target dev
#   scripts/dbt_state.sh build --select state:modified+ --target dev
#   scripts/dbt_state.sh build --select state:modified+ --target dev --target-path /tmp/run
#
# Anything after the subcommand is passed straight through to dbtf; this script
# only injects `--state dbt/state --defer --project-dir dbt --profiles-dir dbt`.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STATE_DIR="dbt/state"
mkdir -p "$STATE_DIR"

echo "── E11.16 dbt_state wrapper: fetching prod manifest baseline ──"
# gh fills {owner}/{repo} from the current repo's origin remote.
run_id="$(gh api \
  "repos/{owner}/{repo}/actions/artifacts?name=dbt-manifest&per_page=5" \
  --jq '[.artifacts[] | select(.expired == false)] | .[0].workflow_run.id' \
  2>/dev/null || true)"

if [ -n "${run_id:-}" ] && [ "$run_id" != "null" ]; then
  if gh run download "$run_id" --name dbt-manifest --dir "$STATE_DIR" 2>/dev/null; then
    echo "   manifest baseline ← prod run $run_id"
  else
    run_id=""
  fi
fi

if [ -z "${run_id:-}" ] || [ "$run_id" = "null" ] || [ ! -f "$STATE_DIR/manifest.json" ]; then
  # No artifact (producer hasn't run since this landed, or 90d expiry). Fall back to
  # a local PROD compile so the baseline is at least prod-relative, not tree-vs-tree.
  echo "   WARNING: no dbt-manifest artifact found — falling back to a local prod compile"
  echo "            (push to main to refresh the baseline producer; see dbt_build_ci.yml I.5)"
  dbtf compile --target baseball_betting_and_fantasy --project-dir dbt --profiles-dir dbt
  cp dbt/target/manifest.json "$STATE_DIR/manifest.json"
fi

echo "── running: dbtf $* --state $STATE_DIR --defer ──"
exec dbtf "$@" \
  --state "$STATE_DIR" \
  --defer \
  --project-dir dbt \
  --profiles-dir dbt
