"""Fast-gate unit tests for the NCAAF-P0.6b recurring in-season closing-line catch-up.

Mirrors `test_ncaaf_roll_forward.py`'s conventions (import only from the ncaaf ingest package —
no `pipeline`, no dbt manifest — so this collects cleanly in the fast gate).

Guards:
  * `_new_kickoffs_to_capture` is KICKOFF-grain, not week-grain — CFBD's `week` field collides
    between regular-season and postseason numbering (verified live against real 2025 data while
    building this: a per-week check falsely flagged "week 1" as needing recapture because it
    silently mixed August season-openers with December bowl games). It only targets a kickoff
    once it has FULLY happened (kickoff − buffer ≤ now) AND isn't already in the lake.
  * `_merge_and_write` is a READ-MERGE-WRITE — the core regression test proves a weekly re-run
    can NEVER silently delete a previously-captured week (the landmine `s3io.write_season_partition`'s
    season-grained overwrite would otherwise cause).
  * `_q_or_missing`/`_existing_raw_rows`/`_captured_commence_times` distinguish a GENUINELY absent
    partition from a transient read failure — a CI-only flake (a read-after-write `delta_scan`
    hiccup on a partition the same test had just written) exposed a real data-loss bug where any
    read exception was swallowed into "nothing captured yet," which `_merge_and_write` then took
    as license for a destructive overwrite. A transient failure must now RAISE, never masquerade
    as an empty/fresh season.
  * `run_recurring_capture` makes ZERO paid Odds calls when nothing needs capture, and defaults
    the season to the clock-derived `current_season()`.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from quant_sports_intel_models.football.ncaaf.ingest import (
    odds_recurring_capture as orc,
    query_lake,
    s3io,
)
from quant_sports_intel_models.football.ncaaf.ingest import sources as src


# ── registry sanity — the recurring capture must target the SAME paid on_demand source P0.6 uses
def test_odds_historical_source_matches_the_registered_on_demand_source():
    assert orc.ODDS_HISTORICAL_SOURCE == "odds_ncaaf_historical"
    assert orc.ODDS_HISTORICAL_SOURCE in src.ODDS_ON_DEMAND
    assert src.SOURCES[orc.ODDS_HISTORICAL_SOURCE].on_demand is True


# ── _new_kickoffs_to_capture: kickoff-grain, past-only, diffed against the lake ───────────
def test_new_kickoffs_waits_for_the_kickoff_to_pass(monkeypatch):
    now = datetime(2025, 9, 1, 12, 0, tzinfo=timezone.utc)
    past = now - timedelta(hours=6)
    future = now + timedelta(days=4)
    monkeypatch.setattr(orc, "_season_kickoffs", lambda ctx, season: [past, future])
    new = orc._new_kickoffs_to_capture(object(), 2025, captured_commence=set(), now=now)
    assert new == [past]  # the future kickoff isn't captured yet — nothing to snapshot, wait


def test_new_kickoffs_excludes_already_captured(monkeypatch):
    now = datetime(2025, 9, 10, tzinfo=timezone.utc)
    k1 = datetime(2025, 8, 21, 16, 0, tzinfo=timezone.utc)
    k2 = datetime(2025, 8, 21, 19, 30, tzinfo=timezone.utc)
    captured = {src._iso(k1)}  # k1 already in the lake; k2 is not
    monkeypatch.setattr(orc, "_season_kickoffs", lambda ctx, season: [k1, k2])
    new = orc._new_kickoffs_to_capture(object(), 2025, captured, now=now)
    assert new == [k2]


def test_new_kickoffs_does_not_confuse_regular_and_postseason_week_numbers(monkeypatch):
    # The bug found live against real 2025 data: CFBD's `week` field collides between
    # regular-season week 1 and postseason (bowl) week 1. Kickoff-grain diffing must not care —
    # it just compares each individual kickoff's own commence_time against the lake.
    now = datetime(2026, 1, 5, tzinfo=timezone.utc)
    regular_week1 = datetime(2025, 8, 23, 16, 0, tzinfo=timezone.utc)
    bowl_week1 = datetime(2025, 12, 20, 20, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(orc, "_season_kickoffs", lambda ctx, season: [regular_week1, bowl_week1])
    captured = {src._iso(regular_week1)}  # only the regular-season game already captured
    new = orc._new_kickoffs_to_capture(object(), 2025, captured, now=now)
    assert new == [bowl_week1]  # only the genuinely-uncaptured bowl game is targeted


# ── run_recurring_capture: no work ⇒ zero paid calls; season defaults clock-derived ───────
def test_run_recurring_capture_no_kickoffs_needed_makes_no_paid_calls(monkeypatch):
    monkeypatch.setattr(orc, "_captured_commence_times", lambda season, **kw: set())
    monkeypatch.setattr(orc, "_new_kickoffs_to_capture", lambda *a, **kw: [])

    def _boom(*a, **kw):
        raise AssertionError("must not fetch odds when no kickoff needs capture")

    monkeypatch.setattr(orc, "_odds_historical_for_kickoffs", _boom)
    monkeypatch.setattr(orc, "_odds_ncaaf_historical", _boom)
    ctx = src.Ctx(cfbd=object())
    manifest = orc.run_recurring_capture(2025, ctx=ctx)
    assert manifest == {
        "season": 2025, "new_kickoffs": 0, "rows_written": 0,
        "credits_used": None, "credits_remaining": None,
    }


def test_run_recurring_capture_requires_cfbd_key():
    ctx = src.Ctx(cfbd=None)
    with pytest.raises(RuntimeError, match="CFBD_API_KEY"):
        orc.run_recurring_capture(2025, ctx=ctx)


def test_run_recurring_capture_defaults_to_current_season(monkeypatch):
    seen = {}
    monkeypatch.setattr(orc, "_captured_commence_times", lambda season, **kw: set())

    def fake_new_kickoffs(ctx, season, captured, **kw):
        seen["season"] = season
        return []

    monkeypatch.setattr(orc, "_new_kickoffs_to_capture", fake_new_kickoffs)
    ctx = src.Ctx(cfbd=object())
    orc.run_recurring_capture(ctx=ctx)
    assert seen["season"] == src.current_season()


def test_run_recurring_capture_fetches_and_merges_only_target_kickoffs(monkeypatch):
    now = datetime(2025, 9, 10, tzinfo=timezone.utc)
    kickoff = now - timedelta(days=1)
    monkeypatch.setattr(orc, "_captured_commence_times", lambda season, **kw: set())
    monkeypatch.setattr(orc, "_new_kickoffs_to_capture", lambda *a, **kw: [kickoff])
    fetch_calls = []

    def fake_fetch(ctx, kicks):
        fetch_calls.append(kicks)
        return [{"id": "e1", "commence_time": src._iso(kickoff),
                 "_requested_snapshot": src._iso(kickoff - timedelta(minutes=5))}]

    monkeypatch.setattr(orc, "_odds_historical_for_kickoffs", fake_fetch)
    monkeypatch.setattr(orc, "_merge_and_write", lambda season, records, **kw: len(records))
    ctx = src.Ctx(cfbd=object())
    manifest = orc.run_recurring_capture(2025, ctx=ctx, now=now)
    assert fetch_calls == [[kickoff]]
    assert manifest["new_kickoffs"] == 1
    assert manifest["rows_written"] == 1


def test_run_recurring_capture_forced_weeks_bypasses_the_diff(monkeypatch):
    monkeypatch.setattr(orc, "_captured_commence_times", lambda season, **kw: set())

    def _boom(*a, **kw):
        raise AssertionError("forced weeks must bypass the kickoff diff")

    monkeypatch.setattr(orc, "_new_kickoffs_to_capture", _boom)
    seen = {}

    def fake_ncaaf_historical(ctx, season, *, weeks=None):
        seen["weeks"] = weeks
        return [{"id": "e1", "commence_time": "2025-08-21T16:00:00Z",
                 "_requested_snapshot": "2025-08-21T15:55:00Z"}]

    monkeypatch.setattr(orc, "_odds_ncaaf_historical", fake_ncaaf_historical)
    monkeypatch.setattr(orc, "_merge_and_write", lambda season, records, **kw: len(records))
    ctx = src.Ctx(cfbd=object())
    manifest = orc.run_recurring_capture(2025, ctx=ctx, weeks=[1])
    assert seen["weeks"] == [1]
    assert manifest["forced_weeks"] == [1]
    assert manifest["rows_written"] == 1


# ── query_lake._connect(): must tolerate a credential-less sandbox for LOCAL-only reads ──────
def test_connect_tolerates_a_credential_chain_secret_failure(monkeypatch):
    # THE ACTUAL CI FAILURE (found after the swallow fix above stopped hiding it): a runner with
    # NO AWS credential source anywhere (no env, no profile, no IMDS role — the fast-gate sandbox
    # intentionally mocks all external IO) makes DuckDB's `credential_chain` secret VALIDATE
    # eagerly at CREATE-SECRET time and raise "Secret Validation Failure" — before any query even
    # runs, even one that only reads a LOCAL path via `local()`. `_connect()` must not let that
    # break local-only usage.
    monkeypatch.setattr(query_lake, "_con", None)

    class _FakeConn:
        def __init__(self):
            self.executed = []

        def execute(self, sql, *a, **kw):
            self.executed.append(sql)
            if "CREATE OR REPLACE SECRET" in sql:
                raise Exception(
                    "Secret Validation Failure: during `create` using the following: "
                    "Credential Chain: 'config'"
                )
            return self

    fake_conn = _FakeConn()
    import duckdb

    monkeypatch.setattr(duckdb, "connect", lambda: fake_conn)
    con = query_lake._connect()
    assert con is fake_conn  # _connect() succeeded despite the secret-creation failure
    assert any("CREATE OR REPLACE SECRET" in s for s in fake_conn.executed)  # it did try


# ── _is_missing_table_error / _q_or_missing: distinguish absent-partition from transient failure
def test_is_missing_table_error_distinguishes_missing_from_transient():
    missing = Exception(
        'IO Error: DeltaKernel InvalidTableLocationError (28): Invalid table location: '
        'Path does not exist: "s3://bucket/ncaaf/raw/odds_ncaaf_historical/".'
    )
    transient = Exception("IO Error: connection reset by peer")
    assert orc._is_missing_table_error(missing) is True
    assert orc._is_missing_table_error(transient) is False


def test_q_or_missing_returns_none_only_for_a_genuinely_missing_table(monkeypatch):
    def fake_q(sql):
        raise Exception(
            'IO Error: DeltaKernel InvalidTableLocationError (28): Invalid table location: '
            'Path does not exist: "x".'
        )

    monkeypatch.setattr(query_lake, "q", fake_q)
    assert orc._q_or_missing("select 1") is None


def test_q_or_missing_raises_after_bounded_retries_on_a_transient_error(monkeypatch):
    # The exact CI flake this guards against: a read failure that is NOT "table missing" (e.g. a
    # read-after-write delta_scan hiccup) must be retried, then RAISED — never treated as absent.
    calls = {"n": 0}

    def fake_q(sql):
        calls["n"] += 1
        raise Exception("IO Error: transient read hiccup")

    monkeypatch.setattr(query_lake, "q", fake_q)
    monkeypatch.setattr(query_lake, "_connect", lambda: _NoopConn())
    with pytest.raises(RuntimeError, match="NOT a missing-table error"):
        orc._q_or_missing("select 1", retries=2, retry_sleep=0)
    assert calls["n"] == 3  # initial attempt + 2 retries, all genuinely attempted


def test_q_or_missing_retries_transient_failure_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_q(sql):
        calls["n"] += 1
        if calls["n"] < 2:
            raise Exception("IO Error: transient read hiccup")
        return "the-dataframe"

    monkeypatch.setattr(query_lake, "q", fake_q)
    monkeypatch.setattr(query_lake, "_connect", lambda: _NoopConn())
    assert orc._q_or_missing("select 1", retries=2, retry_sleep=0) == "the-dataframe"
    assert calls["n"] == 2


class _NoopConn:
    def execute(self, *a, **kw):
        return None


# ── _existing_raw_rows / _captured_commence_times: raise on failure, None only when absent ────
def test_existing_raw_rows_raises_on_a_non_missing_read_failure(monkeypatch):
    def fake_q_or_missing(sql, **kw):
        raise RuntimeError("simulated non-missing read failure")

    monkeypatch.setattr(orc, "_q_or_missing", fake_q_or_missing)
    with pytest.raises(RuntimeError, match="simulated non-missing"):
        orc._existing_raw_rows(2025, local_root="/tmp/unused-for-this-test")


def test_captured_commence_times_raises_on_a_non_missing_read_failure(monkeypatch):
    def fake_q_or_missing(sql, **kw):
        raise RuntimeError("simulated non-missing read failure")

    monkeypatch.setattr(orc, "_q_or_missing", fake_q_or_missing)
    with pytest.raises(RuntimeError, match="simulated non-missing"):
        orc._captured_commence_times(2025, local_root="/tmp/unused-for-this-test")


def test_existing_raw_rows_returns_none_for_a_genuinely_absent_partition(tmp_path):
    # A real (unmocked) DuckDB delta_scan against a directory that was never written — proves
    # `_is_missing_table_error` recognizes the REAL exception shape, end-to-end.
    assert orc._existing_raw_rows(2099, local_root=str(tmp_path)) is None


def test_captured_commence_times_returns_empty_for_a_genuinely_absent_partition(tmp_path):
    assert orc._captured_commence_times(2099, local_root=str(tmp_path)) == set()


# ── _merge_and_write: the core landmine-guard — a weekly re-run must NEVER lose a prior week ──
def test_merge_and_write_raises_rather_than_silently_overwriting_on_a_read_failure(
    monkeypatch, tmp_path
):
    # Seed an existing partition the way a prior run would have left it.
    week1_row = {"id": "week1-e1", "commence_time": "2025-08-21T16:00:00Z",
                "_requested_snapshot": "2025-08-21T15:55:00Z", "bookmakers": []}
    s3io.write_records([week1_row], sport="ncaaf", source=orc.ODDS_HISTORICAL_SOURCE,
                       season=2025, local_root=str(tmp_path))

    # Simulate the exact CI flake: a transient failure reading back what's already captured.
    def _boom(season, **kw):
        raise RuntimeError("simulated transient delta_scan read failure")

    monkeypatch.setattr(orc, "_existing_raw_rows", _boom)
    week2_row = {"id": "week2-e1", "commence_time": "2025-08-28T16:00:00Z",
                "_requested_snapshot": "2025-08-28T15:55:00Z", "bookmakers": []}
    with pytest.raises(RuntimeError, match="simulated transient"):
        orc._merge_and_write(2025, [week2_row], local_root=str(tmp_path))

    # week1 must be UNCHANGED — the old bug would have silently overwritten it with week2 only.
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL delta; LOAD delta")
    uri = s3io.local_table_uri(str(tmp_path), "ncaaf", orc.ODDS_HISTORICAL_SOURCE)
    rows = con.execute(f"SELECT raw_json FROM delta_scan('{uri}')").fetchall()
    ids = {json.loads(r[0])["id"] for r in rows}
    assert ids == {"week1-e1"}  # week2 never written; week1 never dropped


def test_merge_and_write_never_loses_a_previously_captured_week(tmp_path):
    # Seed an "existing" partition the way a prior run would have left it.
    week1_row = {"id": "week1-e1", "commence_time": "2025-08-21T16:00:00Z",
                "_requested_snapshot": "2025-08-21T15:55:00Z", "bookmakers": []}
    n = s3io.write_records([week1_row], sport="ncaaf", source=orc.ODDS_HISTORICAL_SOURCE,
                           season=2025, local_root=str(tmp_path))
    assert n == 1

    # A new run captures a later week only — must NOT overwrite the earlier row away.
    week2_row = {"id": "week2-e1", "commence_time": "2025-08-28T16:00:00Z",
                "_requested_snapshot": "2025-08-28T15:55:00Z", "bookmakers": []}
    rows_written = orc._merge_and_write(2025, [week2_row], local_root=str(tmp_path))
    assert rows_written == 2  # week1 preserved + week2 added

    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL delta; LOAD delta")
    uri = s3io.local_table_uri(str(tmp_path), "ncaaf", orc.ODDS_HISTORICAL_SOURCE)
    rows = con.execute(f"SELECT raw_json FROM delta_scan('{uri}')").fetchall()
    ids = {json.loads(r[0])["id"] for r in rows}
    assert ids == {"week1-e1", "week2-e1"}


def test_merge_and_write_is_idempotent_on_rerun_of_the_same_kickoff(tmp_path):
    row = {"id": "e1", "commence_time": "2025-08-21T16:00:00Z",
          "_requested_snapshot": "2025-08-21T15:55:00Z", "bookmakers": []}
    orc._merge_and_write(2025, [row], local_root=str(tmp_path))
    # re-running the SAME kickoff's fetch must not accumulate a duplicate row.
    rows_written = orc._merge_and_write(2025, [dict(row)], local_root=str(tmp_path))
    assert rows_written == 1

    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL delta; LOAD delta")
    uri = s3io.local_table_uri(str(tmp_path), "ncaaf", orc.ODDS_HISTORICAL_SOURCE)
    cnt = con.execute(f"SELECT count(*) FROM delta_scan('{uri}')").fetchone()[0]
    assert cnt == 1
