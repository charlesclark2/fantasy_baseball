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

import sys

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
    ctx = src.Ctx(cfbd=object())
    manifest = orc.run_recurring_capture(2025, ctx=ctx)
    assert manifest == {
        "season": 2025, "new_kickoffs": 0, "new_kickoffs_t1": None,
        "forced_weeks": None, "rows_written": 0,
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

    def fake_fetch(ctx, kicks, **kw):
        fetch_calls.append(kicks)
        return [{"id": "e1", "commence_time": src._iso(kickoff),
                 "_requested_snapshot": src._iso(kickoff - timedelta(minutes=5))}]

    monkeypatch.setattr(orc, "_odds_historical_for_kickoffs", fake_fetch)
    monkeypatch.setattr(orc, "_merge_and_write", lambda season, records, **kw: len(records))
    ctx = src.Ctx(cfbd=object())
    manifest = orc.run_recurring_capture(2025, ctx=ctx, now=now)
    assert fetch_calls == [[kickoff]]
    assert manifest["new_kickoffs"] == 1
    assert manifest["new_kickoffs_t1"] is None  # capture_t1 defaults False — unaffected (P0.6c)
    assert manifest["rows_written"] == 1


def test_run_recurring_capture_weeks_bypasses_the_auto_detect_diff(monkeypatch):
    """--weeks sources its candidate kickoffs from the EXPLICIT week list (_season_kickoffs),
    never the whole-season auto-detect diff (_new_kickoffs_to_capture stays untouched)."""
    monkeypatch.setattr(orc, "_captured_commence_times", lambda season, **kw: set())

    def _boom(*a, **kw):
        raise AssertionError("--weeks must not go through the whole-season auto-detect diff")

    monkeypatch.setattr(orc, "_new_kickoffs_to_capture", _boom)
    seen = {}
    kickoff = datetime(2025, 8, 21, 16, 0, tzinfo=timezone.utc)

    def fake_season_kickoffs(ctx, season, weeks=None):
        seen["weeks"] = weeks
        return [kickoff]

    monkeypatch.setattr(orc, "_season_kickoffs", fake_season_kickoffs)
    monkeypatch.setattr(
        orc, "_odds_historical_for_kickoffs",
        lambda ctx, kicks, **kw: [{"id": "e1", "commence_time": src._iso(kickoff),
                                    "_requested_snapshot": src._iso(kickoff - timedelta(minutes=5))}],
    )
    monkeypatch.setattr(orc, "_merge_and_write", lambda season, records, **kw: len(records))
    ctx = src.Ctx(cfbd=object())
    manifest = orc.run_recurring_capture(2025, ctx=ctx, weeks=[1])
    assert seen["weeks"] == [1]
    assert manifest["forced_weeks"] == [1]
    assert manifest["rows_written"] == 1


# ── the actual fix requested: --weeks no longer silently re-buys credits for already-captured
# kickoffs (the original P0.6b "operator override" bypassed the dedup check unconditionally) ──
def test_run_recurring_capture_weeks_skips_already_captured_by_default(monkeypatch):
    already_captured = datetime(2025, 8, 21, 16, 0, tzinfo=timezone.utc)
    still_needed = datetime(2025, 8, 22, 19, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        orc, "_season_kickoffs", lambda ctx, season, weeks=None: [already_captured, still_needed]
    )
    monkeypatch.setattr(
        orc, "_captured_commence_times", lambda season, **kw: {src._iso(already_captured)}
    )
    fetch_calls = []

    def fake_fetch(ctx, kicks, **kw):
        fetch_calls.append(kicks)
        return [{"id": f"e-{i}", "commence_time": src._iso(k),
                 "_requested_snapshot": src._iso(k - timedelta(minutes=5))}
                for i, k in enumerate(kicks)]

    monkeypatch.setattr(orc, "_odds_historical_for_kickoffs", fake_fetch)
    monkeypatch.setattr(orc, "_merge_and_write", lambda season, records, **kw: len(records))
    ctx = src.Ctx(cfbd=object())
    manifest = orc.run_recurring_capture(2025, ctx=ctx, weeks=[1])
    assert fetch_calls == [[still_needed]]  # already_captured was SKIPPED, not re-fetched
    assert manifest["new_kickoffs"] == 1
    assert manifest["forced_weeks"] == [1]


def test_run_recurring_capture_weeks_fully_captured_makes_no_paid_calls(monkeypatch):
    """The concrete AC this fix targets: a --weeks re-run against a fully-already-captured week
    makes ZERO paid calls (0 credits), instead of unconditionally re-pulling everything."""
    already_captured = datetime(2025, 8, 21, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(orc, "_season_kickoffs", lambda ctx, season, weeks=None: [already_captured])
    monkeypatch.setattr(
        orc, "_captured_commence_times", lambda season, **kw: {src._iso(already_captured)}
    )

    def _boom(*a, **kw):
        raise AssertionError("must not fetch odds when everything targeted is already captured")

    monkeypatch.setattr(orc, "_odds_historical_for_kickoffs", _boom)
    ctx = src.Ctx(cfbd=object())
    manifest = orc.run_recurring_capture(2025, ctx=ctx, weeks=[1])
    assert manifest["rows_written"] == 0
    assert manifest["new_kickoffs"] == 0
    assert manifest["forced_weeks"] == [1]


def test_run_recurring_capture_weeks_force_refetches_already_captured(monkeypatch):
    """force=True is the escape hatch for genuinely re-pulling a known-BAD existing capture —
    it bypasses the per-kind skip and re-fetches every kickoff --weeks selects regardless."""
    already_captured = datetime(2025, 8, 21, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(orc, "_season_kickoffs", lambda ctx, season, weeks=None: [already_captured])
    monkeypatch.setattr(
        orc, "_captured_commence_times", lambda season, **kw: {src._iso(already_captured)}
    )
    fetch_calls = []

    def fake_fetch(ctx, kicks, **kw):
        fetch_calls.append(kicks)
        return [{"id": "e1", "commence_time": src._iso(already_captured),
                 "_requested_snapshot": src._iso(already_captured - timedelta(minutes=5))}]

    monkeypatch.setattr(orc, "_odds_historical_for_kickoffs", fake_fetch)
    monkeypatch.setattr(orc, "_merge_and_write", lambda season, records, **kw: len(records))
    ctx = src.Ctx(cfbd=object())
    manifest = orc.run_recurring_capture(2025, ctx=ctx, weeks=[1], force=True)
    assert fetch_calls == [[already_captured]]  # re-fetched DESPITE already being captured
    assert manifest["new_kickoffs"] == 1


# ── NCAAF-P0.6c: T-1 day-prior snapshot capture ───────────────────────────────────────────────
def test_run_recurring_capture_default_does_not_fetch_t1(monkeypatch):
    """P0.6c ships default OFF (capture_t1=False) — a plain call must fetch ONLY the close
    snapshot, zero extra Odds-API calls, exactly like P0.6b, until an operator opts in."""
    now = datetime(2025, 9, 10, tzinfo=timezone.utc)
    kickoff = now - timedelta(days=1)
    captured_kind_calls = []

    def fake_captured(season, *, kind=orc.SNAPSHOT_KIND_CLOSE, **kw):
        captured_kind_calls.append(kind)
        return set()

    monkeypatch.setattr(orc, "_captured_commence_times", fake_captured)
    monkeypatch.setattr(orc, "_new_kickoffs_to_capture", lambda *a, **kw: [kickoff])
    fetch_buffers = []

    def fake_fetch(ctx, kicks, *, buffer_min=None):
        fetch_buffers.append(buffer_min)
        return [{"id": "e1", "commence_time": src._iso(kickoff),
                 "_requested_snapshot": src._iso(kickoff - timedelta(minutes=buffer_min))}]

    monkeypatch.setattr(orc, "_odds_historical_for_kickoffs", fake_fetch)
    monkeypatch.setattr(orc, "_merge_and_write", lambda season, records, **kw: len(records))
    ctx = src.Ctx(cfbd=object())
    manifest = orc.run_recurring_capture(2025, ctx=ctx, now=now)
    assert fetch_buffers == [5]  # ONE fetch, close buffer only — no T-1 call at all
    assert captured_kind_calls == [orc.SNAPSHOT_KIND_CLOSE]  # never diffed against T-1 coverage
    assert manifest["new_kickoffs_t1"] is None


def test_run_recurring_capture_with_capture_t1_fetches_both_kinds(monkeypatch):
    """capture_t1=True fetches BOTH the close (5min) and T-1 (T1_BUFFER_MIN) snapshots for the
    same kickoff, tags each record's `_snapshot_kind`, and merges both into one write."""
    now = datetime(2025, 9, 10, tzinfo=timezone.utc)
    kickoff = now - timedelta(days=1)
    monkeypatch.setattr(orc, "_captured_commence_times", lambda season, **kw: set())
    monkeypatch.setattr(orc, "_new_kickoffs_to_capture", lambda *a, **kw: [kickoff])
    fetch_buffers = []

    def fake_fetch(ctx, kicks, *, buffer_min=None):
        fetch_buffers.append(buffer_min)
        return [{"id": "e1", "commence_time": src._iso(kickoff),
                 "_requested_snapshot": src._iso(kickoff - timedelta(minutes=buffer_min))}]

    monkeypatch.setattr(orc, "_odds_historical_for_kickoffs", fake_fetch)
    written = {}

    def fake_merge(season, records, **kw):
        written["records"] = records
        return len(records)

    monkeypatch.setattr(orc, "_merge_and_write", fake_merge)
    ctx = src.Ctx(cfbd=object())
    manifest = orc.run_recurring_capture(2025, ctx=ctx, now=now, capture_t1=True)
    assert sorted(fetch_buffers) == sorted([5, orc.T1_BUFFER_MIN])
    assert manifest["new_kickoffs"] == 1
    assert manifest["new_kickoffs_t1"] == 1
    assert manifest["rows_written"] == 2
    kinds = {r["_snapshot_kind"] for r in written["records"]}
    assert kinds == {orc.SNAPSHOT_KIND_CLOSE, orc.SNAPSHOT_KIND_T1}
    # distinguishable by _requested_snapshot / _snapshot_ts (the AC) — different buffers ⇒
    # different requested snapshots for the SAME kickoff/event.
    requested = {r["_requested_snapshot"] for r in written["records"]}
    assert len(requested) == 2


def test_captured_commence_times_filters_by_snapshot_kind(tmp_path):
    close_row = {"id": "e1", "commence_time": "2025-09-06T16:00:00Z",
                "_requested_snapshot": "2025-09-06T15:55:00Z",
                "_snapshot_kind": orc.SNAPSHOT_KIND_CLOSE, "bookmakers": []}
    t1_row = {"id": "e2", "commence_time": "2025-09-06T19:00:00Z",
             "_requested_snapshot": "2025-09-05T19:00:00Z",
             "_snapshot_kind": orc.SNAPSHOT_KIND_T1, "bookmakers": []}
    # A P0.6b LEGACY row with no _snapshot_kind field at all — must be treated as "close".
    legacy_row = {"id": "e3", "commence_time": "2025-09-06T23:00:00Z",
                 "_requested_snapshot": "2025-09-06T22:55:00Z", "bookmakers": []}
    s3io.write_records([close_row, t1_row, legacy_row], sport="ncaaf",
                       source=orc.ODDS_HISTORICAL_SOURCE, season=2025, local_root=str(tmp_path))

    close_ct = orc._captured_commence_times(
        2025, kind=orc.SNAPSHOT_KIND_CLOSE, local_root=str(tmp_path)
    )
    t1_ct = orc._captured_commence_times(2025, kind=orc.SNAPSHOT_KIND_T1, local_root=str(tmp_path))
    assert close_ct == {"2025-09-06T16:00:00Z", "2025-09-06T23:00:00Z"}  # legacy row ⇒ close
    assert t1_ct == {"2025-09-06T19:00:00Z"}


def test_merge_and_write_never_loses_a_prior_snapshot_of_a_different_kind(tmp_path):
    """NCAAF-P0.6c AC — the never-lose-prior-snapshot regression test at the SNAPSHOT grain: a
    CLOSE snapshot and a T-1 snapshot of the SAME event must both survive a merge, in either
    order, and re-running either capture must never clobber the other. The dedup key is (event
    id, `_requested_snapshot`), which the two kinds always differ on by construction (5min vs
    T1_BUFFER_MIN buffers) — this is a REUSE of the P0.6b merge guard at the snapshot grain, not
    a new mechanism; this test proves that reuse actually holds end-to-end."""
    close_row = {
        "id": "e1", "commence_time": "2025-09-06T16:00:00Z",
        "_requested_snapshot": "2025-09-06T15:55:00Z", "_snapshot_ts": "2025-09-06T15:55:00Z",
        "_snapshot_kind": orc.SNAPSHOT_KIND_CLOSE, "bookmakers": [],
    }
    n = s3io.write_records([close_row], sport="ncaaf", source=orc.ODDS_HISTORICAL_SOURCE,
                           season=2025, local_root=str(tmp_path))
    assert n == 1

    # A LATER run captures the T-1 snapshot of the SAME event — must ADD, not clobber the close.
    t1_row = {
        "id": "e1", "commence_time": "2025-09-06T16:00:00Z",
        "_requested_snapshot": "2025-09-05T16:00:00Z", "_snapshot_ts": "2025-09-05T16:00:00Z",
        "_snapshot_kind": orc.SNAPSHOT_KIND_T1, "bookmakers": [],
    }
    rows_written = orc._merge_and_write(2025, [t1_row], local_root=str(tmp_path))
    assert rows_written == 2  # close preserved + t_minus_1 added

    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL delta; LOAD delta")
    uri = s3io.local_table_uri(str(tmp_path), "ncaaf", orc.ODDS_HISTORICAL_SOURCE)
    rows = con.execute(f"SELECT raw_json FROM delta_scan('{uri}')").fetchall()
    parsed = [json.loads(r[0]) for r in rows]
    kinds = {p["_snapshot_kind"] for p in parsed}
    assert kinds == {orc.SNAPSHOT_KIND_CLOSE, orc.SNAPSHOT_KIND_T1}
    snap_ts = {p["_snapshot_ts"] for p in parsed}
    assert len(snap_ts) == 2  # distinguishable by _snapshot_ts — the AC

    # Re-running the CLOSE capture again (an idempotent re-fetch) must not clobber the T-1 row.
    rows_written_again = orc._merge_and_write(2025, [dict(close_row)], local_root=str(tmp_path))
    assert rows_written_again == 2
    rows2 = con.execute(f"SELECT raw_json FROM delta_scan('{uri}')").fetchall()
    kinds2 = {json.loads(r[0])["_snapshot_kind"] for r in rows2}
    assert kinds2 == {orc.SNAPSHOT_KIND_CLOSE, orc.SNAPSHOT_KIND_T1}


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


# ── _table_is_absent / _q_or_missing: distinguish an absent table from a transient failure ────
#
# 🩹 NCAAF-LAKE1 RE-ANCHORED these onto the listing check. They used to assert that a specific
# ERROR STRING was classified as "missing" — which is a restatement of the classifier's own
# assumption, and it is exactly why the defect survived: the string those tests used is the one a
# LOCAL directory emits, and production reads S3, where a never-written table says something else
# entirely. The properties pinned are unchanged; what they are asked OF is now the store.
def test_table_is_absent_answers_from_the_store_not_from_the_error_text():
    """The whole point of the fix: absence is a fact about the STORE. An engine message — in either
    direction — must not be able to decide it."""
    absent, present = [], []

    def fake_has_commits(uri):
        return False if "never-written" in uri else True

    import quant_sports_intel_models.football.ncaaf.ingest.query_lake as ql
    orig = ql._table_has_commits
    ql._table_has_commits = fake_has_commits
    try:
        assert orc._table_is_absent("select 1 from delta_scan('s3://b/never-written') limit 1") is True
        assert orc._table_is_absent("select 1 from delta_scan('s3://b/real-table') limit 1") is False
    finally:
        ql._table_has_commits = orig


def test_an_undeterminable_listing_is_never_reported_as_absent(monkeypatch):
    """The load-bearing direction. If we cannot ASK the store (no boto3, a denied listing), the only
    safe answer is "not absent" — which sends the caller down the RAISE path. Reporting absence
    here is what would let `_merge_and_write` overwrite a season of PAID odds."""
    import quant_sports_intel_models.football.ncaaf.ingest.query_lake as ql
    monkeypatch.setattr(ql, "_table_has_commits", lambda uri: None)
    assert orc._table_is_absent("select 1 from delta_scan('s3://b/whatever') limit 1") is False


def test_sql_whose_tables_cannot_be_identified_is_never_reported_as_absent():
    """A SELECT we cannot parse a `delta_scan` target out of tells us nothing about the store."""
    assert orc._table_is_absent("select 1") is False


# ── _table_has_commits: the STORE PROBE itself ────────────────────────────────────────────────
#
# The tests above monkeypatch `_table_has_commits` to drive the policy, which means NOTHING was
# asking whether the probe itself is right — the NCAAF-LAKE1 red proof found exactly that hole, by
# breaking the probe and watching every guard stay green. These close it. The probe is the piece
# that must be substrate-correct: it is the whole reason the classifier no longer reads messages.

class _FakeS3:
    """A boto3 stub shaped like `list_objects_v2`'s real response (or a client that explodes)."""

    def __init__(self, key_count: int | None = 0, boom: bool = False):
        self.key_count, self.boom, self.calls = key_count, boom, []

    def list_objects_v2(self, **kw):
        self.calls.append(kw)
        if self.boom:
            raise RuntimeError("AccessDenied: not authorized to perform s3:ListBucket")
        return {"KeyCount": self.key_count}


def _patch_boto3(monkeypatch, fake):
    import types
    monkeypatch.setitem(sys.modules, "boto3",
                        types.SimpleNamespace(client=lambda *a, **k: fake))


def test_the_s3_probe_reports_absent_only_when_the_log_prefix_is_empty(monkeypatch):
    import quant_sports_intel_models.football.ncaaf.ingest.query_lake as ql

    empty = _FakeS3(key_count=0)
    _patch_boto3(monkeypatch, empty)
    assert ql._table_has_commits("s3://bucket/ncaaf/derived/thing") is False
    # It must ask about the _delta_log PREFIX specifically — a bucket-wide listing would report
    # "present" for any table sharing the bucket, which is every table we have.
    assert empty.calls[0]["Prefix"] == "ncaaf/derived/thing/_delta_log/"
    assert empty.calls[0]["Bucket"] == "bucket"

    _patch_boto3(monkeypatch, _FakeS3(key_count=1))
    assert ql._table_has_commits("s3://bucket/ncaaf/derived/thing") is True


def test_a_listing_that_fails_is_UNDETERMINED_never_absent(monkeypatch):
    """⭐ THE DESTRUCTIVE DIRECTION, at the probe. A denied or failed listing tells us NOTHING about
    the store; answering `False` would hand a merge writer a licence to overwrite on an IAM change."""
    import quant_sports_intel_models.football.ncaaf.ingest.query_lake as ql

    _patch_boto3(monkeypatch, _FakeS3(boom=True))
    assert ql._table_has_commits("s3://bucket/ncaaf/derived/thing") is None
    # and the policy layer must turn that into "not absent" -> the caller raises
    assert ql.table_is_absent("select 1 from delta_scan('s3://bucket/ncaaf/derived/thing')") is False


def test_a_malformed_s3_uri_is_undetermined_not_absent(monkeypatch):
    import quant_sports_intel_models.football.ncaaf.ingest.query_lake as ql

    _patch_boto3(monkeypatch, _FakeS3(key_count=0))
    assert ql._table_has_commits("s3://") is None


def test_the_local_probe_reads_the_real_filesystem(tmp_path):
    """The other substrate, unmocked. A never-created path and a directory with no `_delta_log` are
    BOTH absent — the second is the case the retired message match could not see."""
    import quant_sports_intel_models.football.ncaaf.ingest.query_lake as ql

    assert ql._table_has_commits(str(tmp_path / "never-created")) is False
    assert ql._table_has_commits(str(tmp_path)) is False          # exists, but no _delta_log
    (tmp_path / "_delta_log").mkdir()
    assert ql._table_has_commits(str(tmp_path)) is False          # log dir, but no commit in it
    (tmp_path / "_delta_log" / "00000000000000000000.json").write_text("{}")
    assert ql._table_has_commits(str(tmp_path)) is True


def test_q_or_missing_returns_none_only_for_a_genuinely_missing_table(monkeypatch):
    def fake_q(sql):
        raise Exception("IO Error: DeltaKernel GenericError (5): No files in log segment")

    monkeypatch.setattr(query_lake, "q", fake_q)
    monkeypatch.setattr(query_lake, "_table_has_commits", lambda uri: False)
    assert orc._q_or_missing("select 1 from delta_scan('s3://b/t')") is None


def test_q_or_missing_raises_when_the_table_exists_however_the_engine_worded_it(monkeypatch):
    """⭐ THE REGRESSION TEST FOR THIS INCIDENT, FACING THE DANGEROUS WAY. The old classifier keyed
    on the message; if a future engine emitted the ABSENT wording for a table that is really there,
    the old code would have reported absence and a merge writer would have deleted the season. The
    listing decides, so the wording is irrelevant."""
    def fake_q(sql):
        raise Exception('IO Error: DeltaKernel InvalidTableLocationError (28): Path does not exist')

    monkeypatch.setattr(query_lake, "q", fake_q)
    monkeypatch.setattr(query_lake, "_table_has_commits", lambda uri: True)
    monkeypatch.setattr(query_lake, "_connect", lambda: _NoopConn())
    with pytest.raises(RuntimeError, match="refusing to treat this as a missing table"):
        orc._q_or_missing("select 1 from delta_scan('s3://b/t')", retries=0, retry_sleep=0)


def test_q_or_missing_raises_after_bounded_retries_on_a_transient_error(monkeypatch):
    # The exact CI flake this guards against: a read failure that is NOT "table missing" (e.g. a
    # read-after-write delta_scan hiccup) must be retried, then RAISED — never treated as absent.
    calls = {"n": 0}

    def fake_q(sql):
        calls["n"] += 1
        raise Exception("IO Error: transient read hiccup")

    monkeypatch.setattr(query_lake, "q", fake_q)
    monkeypatch.setattr(query_lake, "_connect", lambda: _NoopConn())
    with pytest.raises(RuntimeError, match="refusing to treat this as a missing table"):
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
