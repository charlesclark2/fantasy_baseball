"""NCAAF-P3.1 — the box Dagster job that puts the NCAAF lake output onto the SERVING store.

Runs `scripts/write_ncaaf_serving_store.py`: reads the latest NCAAF-PS pre-kickoff per-game
snapshots + the P1.5 futures-board snapshot from the lake, and writes the manifest / per-day slates
/ per-game blobs / futures board to **DynamoDB (primary) + S3 (fallback)** under the `ncaaf/` key
namespace — the store the FastAPI NCAAF routers read.

🚦 TIER: **HALT.** This is the serving-critical write. If it fails, the app has no NCAAF board, and
a run that goes red is exactly what an operator needs to see. The op does NOT swallow: the writer
raises when neither store took a single blob, and everything below that (a market-line read, the
futures board) is already degraded-but-continue INSIDE the writer at its own tier.

⭐ "NOTHING TO WRITE" IS A NO-OP, NOT A FAILURE — and the two are reported DISTINCTLY. Before the
opener (or on a week nothing has been snapshotted) the snapshot table legitimately has no rows;
that returns `status="no_snapshots"` and logs a no-op. A lake we could not READ raises instead
(`query_or_missing`), because a write that "succeeded" over an unreadable input is the 19-green-runs
class (NF-FRESH1, INC-38).

🖥️ NO BOX PREREQUISITES BEYOND AWS. Lake-only + the serving store: no Snowflake, no CFBD key, no
Odds-API credits, no `sports.duckdb` and no gitignored parquet (NF-INFRA1 — an op that quietly
depends on a deploy-ephemeral file is how a schedule runs green over a frozen table). The one
optional read that touches anything else is the market-line join, which is WARN-tier and reads the
same S3 lake.

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

    if manifest.get("market_read_failed"):
        context.log.warning(
            "[ALERT] NCAAF serving write: the market-line join FAILED — every game is served with "
            "market.status=unavailable, reason=market_read_failed. The projections themselves are "
            "unaffected (the market line is transparency beside the model line, never an input).")


@op(out=Out(Nothing))
def ncaaf_serving_write_op(context):
    """Lake → serving store, standalone. HALT tier: raises on a failed write."""
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
