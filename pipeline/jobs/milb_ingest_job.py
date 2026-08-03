"""E7.1/E7.2 — the isolated daily MiLB incremental-ingest job.

A standalone job (like settle_user_bets_job / the sports jobs) so MiLB ingestion runs on its own
daily cadence and, crucially, in its OWN run — a MiLB Stats-API/Savant/S3 failure fails only this
job and can never touch the MLB serving-critical daily_ingestion_job. Two independent ops
(game-log boxscores + AAA Statcast leaderboards) run here rather than two separate jobs — both
are WARN-tier and catch their own exceptions internally, so one failing never blocks the other;
splitting them into separate jobs would just double the Dagster scaffolding for what is
operationally one "keep MiLB data topped up" duty. MiLB data feeds E7.3 (MLE) + E8 (Dynasty),
never the MLB predict path.
"""
from dagster import in_process_executor, job

from pipeline.ops.milb_ops import (
    dim_player_xref_build_op,
    fangraphs_milb_leaderboards_ingest_op,
    fangraphs_prospects_ingest_op,
    milb_coverage_sla_op,
    milb_incremental_ingest_op,
    milb_leakage_screen_op,
    statcast_aaa_incremental_ingest_op,
)


@job(executor_def=in_process_executor)
def milb_ingest_job():
    # Four independent WARN-tier ingest ops in one isolated run (E7.1/E7.2/E7.7). Each catches its
    # own exceptions internally, so one failing never blocks the others or fails the run — one
    # operational duty ("keep the MiLB + prospect research data topped up"), no extra scaffolding.
    logs = milb_incremental_ingest_op()
    statcast = statcast_aaa_incremental_ingest_op()
    board = fangraphs_prospects_ingest_op()
    leaderboards = fangraphs_milb_leaderboards_ingest_op()

    # E7.4 — the identity spine is a CONSUMER of all four, so it is a downstream fan-in, never a
    # fifth peer. Built at job start it would crosswalk the PREVIOUS cycle's board against the
    # previous cycle's leaderboards and silently miss every newly-listed prospect (the INC-25
    # "consumer parquet lags the stores" class). The ingests are WARN-tier and always succeed, so
    # this edge orders the work without letting an ingest hiccup skip the rebuild.
    dim_player_xref_build_op(start=[logs, statcast, board, leaderboards])

    # E7.6 — the coverage/SLA report + leakage screen are ALSO downstream fan-ins of the four
    # ingests (same INC-25 ordering reason: reading the FRESHEST game-log/statcast/board data,
    # not the previous cycle's). Both run in parallel with dim_player_xref_build_op — neither
    # depends on the identity spine. Both are pure READERS (no writes), so they carry no ordering
    # relationship to each other either.
    milb_coverage_sla_op(start=[logs, statcast, board, leaderboards])
    milb_leakage_screen_op(start=[logs, statcast, board, leaderboards])
