"""INC-25 regression — lock the sub-model-signal DAG ordering in daily_ingestion_job.

The P0 (2026-07-01): after the W8a cutover the Snowflake consumer
`feature_pregame_sub_model_signals` reads an S3 parquet built from the W9 signal
stores. That parquet MUST be (re)built AFTER the day's generators write the stores
and AFTER export_w9_signals_to_s3_op mirrors them to S3 — otherwise the consumer
serves a slate-stale pivot and signal_freshness_check HALTs the whole daily job.

The required chain:
    all 8 generators
        → export_w9_signals_to_s3_op        (fan-in; SF stores → S3 parquet)
        → rebuild_sub_model_signals_consumer_op  (consumer parquet from fresh stores)
        → dbt_sub_model_signals_rebuild     (SF materialize)
        → signal_freshness_check            (HALT gate)

This test is pure DAG introspection (no IO) so it stays in the fast gate.
"""
from __future__ import annotations

from pipeline.jobs.daily_ingestion_job import daily_ingestion_job

_GENERATORS = {
    "generate_run_env_signals_op",
    "generate_offense_signals_op",
    "generate_starter_signals_op",
    "generate_starter_ip_signals_op",
    "generate_bullpen_signals_op",
    "generate_matchup_signals_op",
    "generate_env_state_signals_op",
    "generate_defense_quality_signals_op",
}


def _deps() -> dict[str, dict[str, str]]:
    return {
        node.name: {inp: dep.node for inp, dep in ins.items()}
        for node, ins in daily_ingestion_job.graph.dependencies.items()
    }


def test_export_w9_is_the_fan_in_of_all_eight_generators():
    deps = _deps()
    assert set(deps["export_w9_signals_to_s3_op"].values()) == _GENERATORS


def test_consumer_rebuild_runs_between_export_and_pivot_materialize():
    deps = _deps()
    # consumer parquet rebuild depends on the store export (fresh stores first)
    assert deps["rebuild_sub_model_signals_consumer_op"]["start"] == "export_w9_signals_to_s3_op"
    # the SF materialize depends on the fresh consumer parquet
    assert deps["dbt_sub_model_signals_rebuild"]["start"] == "rebuild_sub_model_signals_consumer_op"


def test_freshness_gate_runs_after_the_materialize():
    deps = _deps()
    assert deps["signal_freshness_check"]["start"] == "dbt_sub_model_signals_rebuild"
