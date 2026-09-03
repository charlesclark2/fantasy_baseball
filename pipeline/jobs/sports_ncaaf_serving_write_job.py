"""NCAAF-P3.1 — the box Dagster job that puts the NCAAF lake output onto the SERVING store.

Runs `scripts/write_ncaaf_serving_store.py`: reads the latest NCAAF-PS pre-kickoff per-game
snapshots + the P1.5 futures-board snapshot from the lake, and writes the manifest / per-day slates
/ per-game blobs / futures board to **DynamoDB (primary) + S3 (fallback)** under the `ncaaf/` key
namespace — the store the FastAPI NCAAF routers read. NCAAF-P3.3 adds the per-TEAM stats pages to
the same write, at a strictly lower tier (see below).

🚦 TIER: **HALT.** This is the serving-critical write. If it fails, the app has no NCAAF board, and
a run that goes red is exactly what an operator needs to see. The op does NOT swallow: the writer
raises when neither store took a single blob, and everything below that (a market-line read, the
futures board) is already degraded-but-continue INSIDE the writer at its own tier.

⭐ "NOTHING TO WRITE" IS A NO-OP, NOT A FAILURE — and the two are reported DISTINCTLY. Before the
opener (or on a week nothing has been snapshotted) the snapshot table legitimately has no rows;
that returns `status="no_snapshots"` and logs a no-op. A lake we could not READ raises instead
(`query_or_missing`), because a write that "succeeded" over an unreadable input is the 19-green-runs
class (NF-FRESH1, INC-38).

🖥️ BOX PREREQUISITES — AWS FOR THE SERVING-CRITICAL PATH, AND NOTHING ELSE. The predictions write
is lake-only: no Snowflake, no CFBD key, no Odds-API credits, no gitignored parquet (NF-INFRA1 — an
op that quietly depends on a deploy-ephemeral file is how a schedule runs green over a frozen
table). The market-line join is WARN-tier and reads the same S3 lake.

⚠️ NCAAF-P3.3 ADDED ONE MORE DEPENDENCY, AND DELIBERATELY BELOW THE HALT LINE. The team pages read
the P1.1 dbt marts, which live in the sports DuckDB rather than the lake. That is heavier than this
job's original contract, so it sits at ALERT tier: the team page's LEAD number (the P1.2 strength
rating and its band) comes from the LAKE and never touches the DuckDB, the mart-backed blocks
degrade to STATED absences (`reason=source_marts_unavailable`) when it cannot be read, and no
failure in that half can reach the manifest / slate / per-game / futures write. The NF-FRESH1
hazard the original line names — a HALT-tier op depending on a deploy-EPHEMERAL file and running
green over a frozen table — is answered on both counts: NF-INFRA1 moved the DuckDB onto a persistent
named volume with `SPORTS_DUCKDB_PATH` deploy-gated, and this read is loud when it cannot run.
⛔ Do not move the predictions path onto the DuckDB.

⛔ NOTHING HERE KEYS ON A WEEK. CFBD restarts `week` at 1 for the postseason and
`game_prediction_snapshot.py`'s `season_order_week` is a verbatim alias of that raw week (the
recorded alias landmine). The serving grain is the America/Los_Angeles kickoff DAY (INC-22).
"""

import os

from dagster import In, Nothing, Out, in_process_executor, job, op

#: The writer is a lake read + a few hundred small key writes; a finite cap so a wedged S3/DynamoDB
#: call can never park a Dagster worker forever (INC-32 — the rule holds even for a short job).
SERVING_WRITE_TIMEOUT_S = int(os.environ.get("NCAAF_SERVING_WRITE_TIMEOUT_S", "900"))


def _run_serving_write(context) -> None:
    """The write itself. ONE implementation behind both ops below — a second copy would be a second
    rule set free to drift (the E9.61 two-renderers class), and these two ops differ ONLY in where
    they sit in a graph."""
    from quant_sports_intel_models.football.ncaaf.ingest.sources import current_season
    from scripts.write_ncaaf_serving_store import write_serving_store

    season = current_season()
    context.log.info("NCAAF serving write: season=%s (clock-derived)", season)
    manifest = write_serving_store(season)

    if manifest.get("status") == "no_snapshots":
        context.log.info(
            "NCAAF serving write: the prediction-snapshot table holds NO rows for season %s — a "
            "genuine no-op (pre-opener / nothing snapshotted yet), NOT a failure and NOT a write. "
            "Nothing in the serving store was touched; run "
            "`sports_ncaaf_prediction_snapshot_job` first.", season)
        return

    context.log.info(
        "NCAAF serving write: %s game(s) across %s LA game-day(s) %s → %s blob(s) "
        "(%s DynamoDB / %s S3). Futures board: %s team(s). Market lines attached: %s by source %s "
        "(read_failed=%s); market nulls by reason %s. Model %s, snapshot vintage %s. "
        "best_alpha=0 — market-blind projections, no pick or edge claim is served.",
        manifest.get("n_games"), manifest.get("n_game_days"), manifest.get("game_days"),
        manifest.get("n_blobs"), manifest.get("dynamo_writes"), manifest.get("s3_writes"),
        manifest.get("futures_teams"), manifest.get("market_lines_attached"),
        # NCAAF-P3.1b: WHICH line, per key shape. "12 lines attached" cannot answer "did the T-1
        # leg fire?", which is the only question this story's runtime gate asks — and a REFUSED
        # line (a leakage-guard refusal = a defect in our odds join) must be legible here rather
        # than looking like a kickoff nobody priced.
        manifest.get("market_lines_by_source"),
        manifest.get("market_read_failed"), manifest.get("market_reasons"),
        manifest.get("model_version"), manifest.get("snapshot_ts"))

    # NCAAF-P3.3 — the team pages, reported PER BLOCK rather than as one coverage number.
    # ⭐ A POOLED "n% populated" CANNOT TELL THE TWO STATES APART that an operator most needs to
    # distinguish here: a week-1 slate whose efficiency/pace blocks are CORRECTLY empty (nobody has
    # played) versus a mart build that did not run at all (MH2.1 (c) — report per-column absence,
    # never a pooled mean). The reasons are machine-readable on the payload for the same purpose.
    teams = manifest.get("team_pages") or {}
    if teams.get("skipped"):
        context.log.info("NCAAF team pages: SKIPPED this run (--no-teams).")
    elif teams.get("error"):
        context.log.warning(
            "[ALERT] NCAAF team pages FAILED to build (%s) — the game board and futures were "
            "written and are unaffected; the previously-published team pages are untouched.",
            teams["error"])
    else:
        context.log.info(
            "NCAAF team pages: %s team(s). P1.1 marts available: %s. P1.2 strength read ok: %s. "
            "Blocks by status — strength %s, efficiency %s, splits %s, schedule %s. "
            "New to FBS this season: %s.",
            teams.get("n_teams"), teams.get("marts_available"), teams.get("strength_read_ok"),
            teams.get("strength_blocks"), teams.get("efficiency_blocks"),
            teams.get("splits_blocks"), teams.get("schedule_blocks"),
            teams.get("teams_new_to_fbs"))
        if not teams.get("marts_available"):
            context.log.warning(
                "[ALERT] NCAAF team pages: the P1.1 marts were UNREADABLE, so every team's "
                "efficiency / trench-pace / schedule block is served as a stated absence "
                "(reason=source_marts_unavailable). The strength rating and its band are "
                "unaffected — they come from the lake. Run `sports_ncaaf_dbt_build_job` on the box "
                "and confirm SPORTS_DUCKDB_PATH.")
        if teams.get("conference_mismatches"):
            # ⭐ NOT a display problem. The SCD-2 dim and the P1.2 pooling level are independently
            # derived; a disagreement means the posterior was shrunk toward a conference the team
            # does not play in, which is a finding about the model's INPUTS.
            context.log.warning(
                "[ALERT] NCAAF team pages: %d team(s) whose SCD-2 conference DISAGREES with the "
                "conference the P1.2 strength row was pooled under: %s. The dim's answer is "
                "served; the disagreement is recorded on each payload as "
                "`team.conference_matches_model_input = false`.",
                len(teams["conference_mismatches"]), teams["conference_mismatches"])

    if manifest.get("market_read_failed"):
        context.log.warning(
            "[ALERT] NCAAF serving write: the market-line join FAILED — every game is served with "
            "market.status=unavailable, reason=market_read_failed. The projections themselves are "
            "unaffected (the market line is transparency beside the model line, never an input).")


def _tier_decision(context):
    """`(re-serve?, why)` for THIS tick — the NCAAF-ODDS-LIVE followUp ⑦ tier.

    ⭐ FAILS OPEN, and that direction is the whole design. The gate exists to SKIP cheap redundant
    writes, so an unevaluable gate must never withhold the serving write itself: a check that could
    not run is not a reason to stop publishing (NF1.7 (a) says an unevaluable check is never scored
    healthy — here "healthy" would be "skip", so the safe verdict is to serve). A gate that failed
    closed would turn a transient lake read into a silently frozen board, which is precisely the
    NF-FRESH1 outage this tier is meant to make less likely, not more.
    """
    from quant_sports_intel_models.football.ncaaf.ingest.sources import current_season
    from scripts.write_ncaaf_serving_store import should_reserve, upcoming_kickoffs

    try:
        kickoffs = upcoming_kickoffs(current_season())
    except Exception as exc:  # noqa: BLE001 — see the fail-open note above
        context.log.warning(
            "ALERT NCAAF serving write: the re-serve TIER could not be evaluated (%s) — serving "
            "anyway. The tier only ever suppresses a redundant refresh, so an unevaluable gate "
            "must fall through to the write, never withhold it.", exc)
        return True, f"tier unevaluable ({exc}) — failing open to a write"
    return should_reserve(kickoffs)


@op(out=Out(Nothing))
def ncaaf_serving_write_op(context):
    """Lake → serving store, standalone, TIER-GATED. HALT tier: raises on a failed write.

    ⏱️ The schedule now ticks HOURLY and this op decides whether the tick publishes — one logical
    job with ONE execution owner, the same shape the live odds capture uses. Two crons for one job
    is this repo's most-repeated operational defect (INC-30, INC-36, INC-38), so the alternative —
    a second "dense" schedule beside the daily one — was deliberately not built.

    ⭐ A SKIPPED TICK IS A NO-OP, NOT A FAILURE, AND IT SAYS WHY. This op is cheap and almost
    always succeeds, which is exactly the shape that produces 19 green runs over a frozen store
    (NF-FRESH1); the reason is logged on BOTH branches so "skipped on purpose" can never be read
    off the same silence as "stopped firing".
    """
    serve, why = _tier_decision(context)
    if not serve:
        context.log.info("NCAAF serving write: no re-serve this tick — %s", why)
        return
    context.log.info("NCAAF serving write: publishing — %s", why)
    _run_serving_write(context)


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ncaaf_serving_write_after_snapshot_op(context):
    """The SAME write, chained downstream of the week's snapshot ops.

    ⭐ INC-25: the serving store is a CONSUMER of the snapshot tables, so it must be rebuilt
    DOWNSTREAM of the write that feeds it IN THE SAME RUN. A serving write that merely ran on its
    own schedule would publish whatever vintage happened to be in the lake when it fired — which,
    on the morning the week's snapshot lands, is last week's.

    HALT tier, and deliberately placed LAST: by the time it runs, the deadline-critical pre-kickoff
    snapshot is already in the lake, so a red run here costs a serving refresh (re-fireable in
    seconds via `sports_ncaaf_serving_write_job`) and never the immutable row that could not have
    been written later.
    """
    _run_serving_write(context)


@job(executor_def=in_process_executor)
def sports_ncaaf_serving_write_job():
    """Refresh the NCAAF serving store from the lake."""
    ncaaf_serving_write_op()
