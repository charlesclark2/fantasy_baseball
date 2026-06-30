"""test_lineup_intraday_s3_rebuild.py — guards lineup_intraday_s3_feature_rebuild,
the fix for the 824819 post-lineup restart loop.

Post-W8b-cutover the served lineup/matchup/aggregator features are a COPY of a
daily-frozen S3 parquet; lineup_dbt_feature_rebuild only re-copies the ext table, so an
intraday lineup confirmation never reached the post_lineup re-score and the game looped
forever. The new op regenerates the S3 chain (SCD-2 write → precursor mirror → --w8b
build → ext refresh) before the copy. These tests lock its three contracts:
  1. GATED default-OFF — no shell-outs unless LINEUP_INTRADAY_S3_REBUILD=1.
  2. Correct chain + args when enabled (the daily order, scoped to the lineup precursor).
  3. MIRROR-tier ALERT-continue — a build failure is swallowed (logged), never raised,
     so the post_lineup re-score still runs on the last-good S3 features.

No S3/SF IO — _run_script is monkeypatched. Fast gate (well under 5s).
"""
from __future__ import annotations

from dagster import build_op_context

import pipeline.ops.sensor_ops as so


def _capture(calls):
    def _fake(_ctx, script, args=None, timeout=so._SUBPROCESS_TIMEOUT):
        calls.append((script, tuple(args or ())))
    return _fake


def test_gated_off_is_noop(monkeypatch):
    monkeypatch.delenv("LINEUP_INTRADAY_S3_REBUILD", raising=False)
    calls: list = []
    monkeypatch.setattr(so, "_run_script", _capture(calls))
    so.lineup_intraday_s3_feature_rebuild(build_op_context())
    assert calls == [], "op must NOT shell out when the flag is unset (default-OFF no-op)"


def test_enabled_runs_full_chain_in_daily_order(monkeypatch):
    monkeypatch.setenv("LINEUP_INTRADAY_S3_REBUILD", "1")
    calls: list = []
    monkeypatch.setattr(so, "_run_script", _capture(calls))
    so.lineup_intraday_s3_feature_rebuild(build_op_context())

    scripts = [c[0] for c in calls]
    assert scripts == [
        "backfill_lineup_state_scd2.py",     # SCD-2 ← fresh staging (else intraday change is invisible)
        "export_w8b_precursors_to_s3.py",    # mirror SCD-2 lineup state → S3
        "run_w1_lakehouse.py",               # rebuild the W8b feature/matchup/aggregator parquet
        "refresh_w1_external_tables.py",     # point lakehouse_ext at the new parquet
    ], "the S3-regeneration chain must run in the daily mirror order, before the feature copy"

    by_script = dict(calls)
    # the parquet MUST actually be regenerated + the ext table refreshed
    assert by_script["run_w1_lakehouse.py"] == ("--w8b-only",)
    assert by_script["refresh_w1_external_tables.py"] == ("--w8b",)
    # intraday-light: only the lineup_state precursor is re-mirrored (the rest are reused)
    assert by_script["export_w8b_precursors_to_s3.py"] == ("--table", "feature_pregame_lineup_state")
    # SCD-2 write is scoped to a date window (not a full-history backfill on every tick)
    assert by_script["backfill_lineup_state_scd2.py"][0] == "--since"


def test_mirror_tier_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("LINEUP_INTRADAY_S3_REBUILD", "1")

    def _boom(_ctx, script, args=None, timeout=so._SUBPROCESS_TIMEOUT):
        raise Exception("simulated --w8b build failure")

    monkeypatch.setattr(so, "_run_script", _boom)
    # MUST NOT raise — a rebuild failure must never block the whole slate's post_lineup
    # re-score (predict runs on the last-good S3 features; the next tick retries).
    so.lineup_intraday_s3_feature_rebuild(build_op_context())
