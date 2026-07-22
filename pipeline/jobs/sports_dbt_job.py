"""
NFL-N0.3 — the box Dagster job that builds the `sports_dbt` NFL DAG (dbt-duckdb over the
S3/Delta lake).

This is the FIRST sports-dbt (DuckDB-native) build wired into Dagster — the MLB dbt path
(`_dbt_exec` → the remote dbt-fusion/Snowflake runner) does NOT apply here. `sports_dbt` is a
disjoint DuckDB project (NCAAF + NFL): it reads the raw Delta lake via DuckDB and materializes
tables into a LOCAL DuckDB file (no warehouse, no remote runner). So this job just invokes
dbt-duckdb in-process on the box.

Tier: standalone job, NOT in the MLB daily serving DAG → it fails ITS OWN run on a build error
(so the operator is alerted) and blocks nothing MLB-serving. INC-32 discipline: the subprocess
carries a finite `timeout=` so a wedged dbt can never hang the Dagster worker forever.

⚠️ DEPLOY PREREQUISITES (operator — dbt-duckdb is not on the box image yet, per the NCAAF-P0.2
flag): the box image must install `dbt-core` + `dbt-duckdb` (already in this repo's uv lock), and
the container needs S3 read on `credence-sports-lakehouse` via the instance role (the same chain
the MLB writers use — no inline keys). Region is pinned to us-east-2 for the DuckDB S3 secret.
"""

import os
import subprocess
import sys

from dagster import In, Nothing, Out, in_process_executor, job, op

# The repo is copied to /app on the box; the shared sports project lives here.
SPORTS_DBT_DIR = os.environ.get(
    "SPORTS_DBT_DIR", "/app/quant_sports_intel_models/sports_dbt"
)
# 40 min ceiling — the full NFL build is ~1–2 min over the lake; this is a generous wedge-guard.
DBT_TIMEOUT_SECONDS = int(os.environ.get("SPORTS_DBT_TIMEOUT_SECONDS", "2400"))


@op(out=Out(Nothing))
def sports_nfl_dbt_build_op(context):
    """Build the NFL staging + refined marts in sports_dbt over the S3/Delta lake."""
    cmd = [
        sys.executable,
        "-m",
        "dbt.cli.main",
        "build",  # run models + run their data tests in one pass
        "--select",
        "nfl.staging",
        "nfl.marts+",
        "--project-dir",
        SPORTS_DBT_DIR,
        "--profiles-dir",
        SPORTS_DBT_DIR,
    ]
    env = {
        **os.environ,
        "DAGSTER_JOB_NAME": context.job_name,
        # DuckDB needs an explicit region for the S3 lake bucket (boto3 is region-less).
        "SPORTS_LAKE_REGION": os.environ.get("SPORTS_LAKE_REGION", "us-east-2"),
        "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-2"),
        # Materialize into a writable local DuckDB file (rebuilt each run).
        "SPORTS_DUCKDB_PATH": os.environ.get("SPORTS_DUCKDB_PATH", "/tmp/sports_nfl.duckdb"),
    }
    context.log.info(f"Building sports_dbt NFL DAG: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            cwd=SPORTS_DBT_DIR,
            timeout=DBT_TIMEOUT_SECONDS,  # INC-32: never an un-timed-out subprocess on a worker
        )
    except subprocess.TimeoutExpired as exc:
        raise Exception(
            f"sports_dbt NFL build TIMED OUT after {DBT_TIMEOUT_SECONDS}s — dbt wedged."
        ) from exc

    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(
            f"sports_dbt NFL build FAILED (exit {result.returncode}). See logs above."
        )
    context.log.info("sports_dbt NFL build PASSED — staging + refined marts materialized.")


@job(executor_def=in_process_executor)
def sports_nfl_dbt_build_job():
    sports_nfl_dbt_build_op()


# ══════════════════════════════════════════════════════════════════════════════════════════
# NCAAF-P1.1 — the NCAAF dbt build
# ══════════════════════════════════════════════════════════════════════════════════════════
# 🚩 WHY THIS EXISTS AT ALL: before P1.1 there was NO Dagster job for ANY NCAAF dbt model.
# P0.4's `ncaaf_team_roster_continuity` and P0.5's `ncaaf_team_coaching_change` were HAND-BUILT on
# a laptop and could silently rot — nothing rebuilt them when the lake advanced, and nothing would
# have told anyone. So this job materializes the WHOLE NCAAF DAG (staging + every mart, those two
# included), not just P1.1's new dims/facts/rollups.
#
# ⚙️ THREE STEPS, TWO TIERS (the CLAUDE.md INC-6 contract, with leakage carved out):
#   1. `dbt run`        — HALT. The models are the deliverable; a failure fails the job.
#   2. leakage gates    — HALT. The three point-in-time contract tests. A pregame rollup absorbing
#      post-kickoff data is a correctness emergency; tiering it WARN would log it where nobody
#      reads it, which is exactly how the postseason week-1 collision survived to a shipped model.
#   3. the rest of `dbt test` — WARN-but-continue. Peripheral grain/not_null/accepted_values
#      assertions must never mask a successful build.
#
# 🧰 STAGING IS BUILT SERIALLY, ON PURPOSE — two independent reasons, both load-bearing:
#   • the P0.5 landmine: dbt-fusion preview-196 SEGFAULTS building 2+ delta_scan models in one
#     invocation. (This project runs dbt-core + dbt-duckdb, not fusion, but the serial build costs
#     ~85s and removes the whole class.)
#   • MEASURED on the real lake: `stg_ncaaf_game_player_stats` explodes ~13.8k records into ~5.2M
#     rows through four chained UNNESTs and OOMs a 4 GB DuckDB when threads compete for memory.
#     The model pins DuckDB itself to 1 thread; running dbt serially keeps peak RSS predictable.
#
# Marts then build in a second invocation — by then every staging model is a physical table, so no
# mart plan contains a delta_scan (the N0.3 "DeltaScan serialization not implemented" cure).


def _run_sports_dbt(context, args, label):
    """Invoke dbt-duckdb on the box for the sports project. Returns the CompletedProcess.

    INC-32 discipline: a finite `timeout=` on every subprocess that runs on a Dagster worker —
    an un-timed-out subprocess on a daemon path wedges the worker forever.
    """
    cmd = [
        sys.executable, "-m", "dbt.cli.main",
        *args,
        "--project-dir", SPORTS_DBT_DIR,
        "--profiles-dir", SPORTS_DBT_DIR,
    ]
    env = {
        **os.environ,
        "DAGSTER_JOB_NAME": context.job_name,
        # DuckDB needs an explicit region for the S3 lake bucket (boto3 is region-less).
        "SPORTS_LAKE_REGION": os.environ.get("SPORTS_LAKE_REGION", "us-east-2"),
        "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-2"),
        "SPORTS_DUCKDB_PATH": os.environ.get("SPORTS_DUCKDB_PATH", "/tmp/sports_ncaaf.duckdb"),
    }
    context.log.info(f"[{label}] {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True,
            cwd=SPORTS_DBT_DIR, timeout=DBT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise Exception(
            f"sports_dbt NCAAF {label} TIMED OUT after {DBT_TIMEOUT_SECONDS}s — dbt wedged."
        ) from exc
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    return result


@op(out=Out(Nothing))
def sports_ncaaf_dbt_run_op(context):
    """HALT tier — materialize the FULL NCAAF DAG (staging serially, then all marts)."""
    # Step 1: staging, ONE model at a time (see the serial-build rationale above).
    staging = _run_sports_dbt(
        context, ["run", "--select", "ncaaf.staging", "--threads", "1"], "ncaaf.staging (serial)"
    )
    if staging.returncode != 0:
        raise Exception(
            f"sports_dbt NCAAF STAGING build FAILED (exit {staging.returncode}). See logs above."
        )

    # Step 2: every NCAAF mart — P1.1's dims/facts/rollups AND P0.3's xref, P0.4's
    # roster-continuity, P0.5's coaching-change. `ncaaf.marts` selects the folder, so a mart added
    # by a later story is picked up automatically and cannot silently go un-built.
    marts = _run_sports_dbt(
        context, ["run", "--select", "ncaaf.marts", "--threads", "1"], "ncaaf.marts"
    )
    if marts.returncode != 0:
        raise Exception(
            f"sports_dbt NCAAF MARTS build FAILED (exit {marts.returncode}). See logs above."
        )
    context.log.info("sports_dbt NCAAF build PASSED — staging + all marts materialized.")


# The three P1.1 point-in-time contract gates. A failure here means a PREGAME rollup has started
# absorbing POST-KICKOFF data — a correctness emergency, not a data-quality nit — so they are the
# one part of the test suite that HALTs.
NCAAF_LEAKAGE_GATES = [
    "assert_asof_week_has_no_future_games",
    "assert_opponent_adjustment_is_point_in_time",
    "assert_season_order_week_is_monotone_in_date",
    # P1.2: the team-strength posterior is a serving-critical PREGAME feature that feeds the P1.3
    # matrix — a leak in it propagates to every P1.4 model, so its point-in-time gate HALTs too
    # (promoted from the WARN test suite to the HALT set, 2026-07-21).
    "assert_team_strength_is_point_in_time",
    # P1.3: the pregame feature matrix is THE input every P1.4 model trains on, so a leak here
    # contaminates all of it — its point-in-time gate HALTs like the P1.1 rollup gates.
    "assert_pregame_matrix_is_point_in_time",
]


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def sports_ncaaf_leakage_gate_op(context):
    """HALT tier — the three point-in-time leakage gates.

    ⚠️ These are deliberately NOT lumped in with the rest of the test suite. Tiering the whole
    suite as WARN (the INC-6 default for peripheral data-quality) would mean a silent pregame leak
    logs a warning nobody reads while the job stays green — which is precisely the failure mode
    that produced the postseason week-1 collision this model shipped with. Leakage fails the job.
    """
    result = _run_sports_dbt(
        context,
        ["test", "--select", *NCAAF_LEAKAGE_GATES, "--threads", "1"],
        "ncaaf leakage gates",
    )
    if result.returncode != 0:
        raise Exception(
            "🚨 NCAAF LEAKAGE GATE FAILED (exit "
            f"{result.returncode}) — a pregame rollup is absorbing post-kickoff data. "
            "Do NOT train or serve off these marts until it is resolved. See logs above."
        )
    context.log.info("NCAAF leakage gates PASSED — the point-in-time contract holds.")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def sports_ncaaf_dbt_test_op(context):
    """WARN tier — the rest of the NCAAF data tests (grain, not_null, accepted_values).

    The loud log is the whole point (the ALERT-continue contract): a silently-swallowed test
    failure is indistinguishable from a green run. Grep the run logs for 'NCAAF dbt TESTS FAILED'.

    Note `not_null_xref_college_nfl_players_gsis_id` (P0.3) is a RATCHET, not a plain assertion:
    the 8 known nulls (drafted players who never took an NFL snap, so nflverse issues no gsis_id)
    WARN, and a 9th ERRORS — so growth in that count fails this step rather than blending into an
    accepted background level.
    """
    result = _run_sports_dbt(context, ["test", "--select", "ncaaf", "--threads", "1"], "ncaaf tests")
    if result.returncode != 0:
        context.log.warning(
            "⚠️ NCAAF dbt TESTS FAILED (exit %s) — build kept, investigate above. "
            "If the failure is not_null_xref_college_nfl_players_gsis_id, the ratchet has been "
            "TRIPPED (>8 nulls) — that is a real regression, not the known background.",
            result.returncode,
        )
    else:
        context.log.info("sports_dbt NCAAF tests PASSED (warnings may still be present — see log).")


@job(executor_def=in_process_executor)
def sports_ncaaf_dbt_build_job():
    # run (HALT) → leakage gates (HALT) → the rest of the tests (WARN-continue).
    # The gates run BEFORE the broad suite so a leak surfaces even if a later peripheral test
    # is noisy, and they fail the job on their own.
    built = sports_ncaaf_dbt_run_op()
    sports_ncaaf_dbt_test_op(start=sports_ncaaf_leakage_gate_op(start=built))
