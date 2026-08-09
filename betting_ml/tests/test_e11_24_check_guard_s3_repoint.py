"""E11.24 target 3 — guards for the `check_*` cluster's Snowflake → S3/DuckDB repoint.

WHAT WAS REPOINTED (each ran at ~100% wake — essentially every execution RESUMED COMPUTE_WH):
  • ``check_odds_coverage.py``          (ALERT→HALT tier)  — fully S3
  • ``check_prediction_coverage.py``    (HALT tier, UNCONDITIONAL) — fully S3
  • ``check_data_freshness.py``         (WARN tier) — ``_is_game_day`` + the archetype entry

WHY THESE TESTS EXIST — the bar for a guard repoint is VERDICT PARITY, not "it runs". A guard
that reads different or staler data fails in two directions and both are silent:
  • false PASS  → a real outage is missed and serving degrades unnoticed;
  • false FAIL  → the daily job HALTs on a healthy slate (check_prediction_coverage has no
                  --strict gate and no try/except in its op, so its verdict IS the job's).
Live SF-vs-S3 parity over real slates was measured before the repoint (see the module
docstrings); it cannot be re-measured in CI, which mocks all IO. What CI *can* prove — and what
a live parity run structurally CANNOT, because the pipeline is healthy and no recent slate is
degraded — is the NEGATIVE half: that each guard still TRIPS on a degraded slate. A guard that
can only ever pass has been defeated (NF1.7 (a)).

Every test drives the REAL query text through a seeded in-memory DuckDB, injected via the
``conn=`` seam each script exposes. That is deliberate: the most dangerous defect in this
repoint lives in the SQL itself (the VARCHAR date predicate below), so a test that only
exercised the pure classifier would be a restatement of the classifier, not a test of the
repoint (the "a test reading back the key the code wrote" class).
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _PROJECT_ROOT / "scripts"


def _load(alias: str, filename: str):
    spec = importlib.util.spec_from_file_location(alias, _SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


odds = _load("_e1124_check_odds_coverage", "check_odds_coverage.py")
pred = _load("_e1124_check_prediction_coverage", "check_prediction_coverage.py")
fresh = _load("_e1124_check_data_freshness", "check_data_freshness.py")


# ══════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — seeded to match the REAL parquet column types, which is the whole point.
# ══════════════════════════════════════════════════════════════════════════════════════════
# ⚠️ `game_date` is VARCHAR on BOTH mart_game_spine and mart_game_odds_bridge in the live
# lakehouse (verified 2026-08-08 via DESCRIBE) — the INC-23 string-wrapped-timestamp cure.
# `commence_date` on mart_odds_outcomes is a real DATE. Seeding the wrong types here would
# make these tests vacuous, so they mirror the measured reality exactly.
_SPINE_TS = "{d} 00:00:00"


def _seed_odds(conn, days: dict[str, dict]) -> None:
    """days: {iso_date: {"spine": n, "events": n, "bridge_with_odds": n}}"""
    conn.execute("CREATE TABLE mart_game_spine (game_date VARCHAR, game_type VARCHAR)")
    conn.execute("CREATE TABLE mart_odds_outcomes (commence_date DATE, event_id VARCHAR)")
    conn.execute("CREATE TABLE mart_game_odds_bridge (game_date VARCHAR, has_odds BOOLEAN)")
    for d, spec in days.items():
        ts = _SPINE_TS.format(d=d)
        for _ in range(spec.get("spine", 0)):
            conn.execute("INSERT INTO mart_game_spine VALUES (?, 'R')", [ts])
        for i in range(spec.get("events", 0)):
            conn.execute("INSERT INTO mart_odds_outcomes VALUES (?::date, ?)", [d, f"{d}-e{i}"])
        n_bridge = spec.get("bridge", spec.get("spine", 0))
        n_attached = spec.get("bridge_with_odds", 0)
        for i in range(n_bridge):
            conn.execute("INSERT INTO mart_game_odds_bridge VALUES (?, ?)",
                         [ts, i < n_attached])


def _seed_predictions(conn, *, scheduled: dict[str, int], scored: dict[str, list[dict]]) -> None:
    conn.execute("CREATE TABLE stg_statsapi_games "
                 "(game_pk BIGINT, official_date DATE, game_type VARCHAR)")
    conn.execute("CREATE TABLE daily_model_predictions "
                 "(game_pk BIGINT, game_date DATE, data_source VARCHAR, "
                 " feature_coverage_score DOUBLE, inserted_at TIMESTAMP)")
    pk = 1000
    for d, n in scheduled.items():
        for i in range(n):
            conn.execute("INSERT INTO stg_statsapi_games VALUES (?, ?::date, 'R')", [pk + i, d])
    for d, rows in scored.items():
        for r in rows:
            conn.execute(
                "INSERT INTO daily_model_predictions VALUES (?, ?::date, ?, ?, ?::timestamp)",
                [r["game_pk"], d, r.get("data_source", "feature_store"),
                 r.get("coverage", 1.0), r.get("inserted_at", f"{d} 12:00:00")],
            )


@pytest.fixture
def conn():
    c = duckdb.connect()
    yield c
    c.close()


# ══════════════════════════════════════════════════════════════════════════════════════════
# 1. THE LOAD-BEARING CAST — the defect a naive repoint ships
# ══════════════════════════════════════════════════════════════════════════════════════════
# `game_date <= '2026-08-08'` against a stored `'2026-08-08 00:00:00'` is a STRING compare:
# the stored value is lexicographically GREATER, so the window's LAST day vanishes with no
# error at all (the E9.52 silent-empty class — an equality/range predicate on a wrapped
# timestamp does not raise, it matches nothing). Measured on the live parquet over
# 2026-08-06..08-08: un-cast 26 rows vs cast 41. In a FREEZE detector that is a 15-game hole.
# This test fails if any ::date cast is dropped from the coverage SQL.

def test_the_window_includes_its_last_day_despite_varchar_game_dates(conn):
    _seed_odds(conn, {
        "2026-08-06": {"spine": 5, "events": 5, "bridge_with_odds": 5},
        "2026-08-07": {"spine": 5, "events": 5, "bridge_with_odds": 5},
        "2026-08-08": {"spine": 5, "events": 5, "bridge_with_odds": 5},  # the end day
    })
    rows = odds.fetch_coverage_rows(date(2026, 8, 6), date(2026, 8, 8), conn=conn)
    by_date = {str(r["d"]): r for r in rows}
    assert "2026-08-08" in by_date, (
        "the window's LAST day is missing — a ::date cast was dropped and the VARCHAR "
        "game_date predicate is doing a string comparison (INC-23 / E9.52)"
    )
    assert sum(int(r["spine_games"]) for r in rows) == 15
    assert sum(int(r["bridge_games"]) for r in rows) == 15


def test_the_uncast_predicate_really_does_truncate_so_the_cast_is_not_cosmetic(conn):
    """Two-sided proof: the same fixture read with the OLD un-cast predicate loses the end day.

    Without this, "the cast test passes" would be consistent with the cast being irrelevant.
    """
    _seed_odds(conn, {
        "2026-08-06": {"spine": 5, "events": 5, "bridge_with_odds": 5},
        "2026-08-07": {"spine": 5, "events": 5, "bridge_with_odds": 5},
        "2026-08-08": {"spine": 5, "events": 5, "bridge_with_odds": 5},
    })
    uncast = conn.execute(
        "SELECT count(*) FROM mart_game_spine WHERE game_type='R' "
        "AND game_date >= '2026-08-06' AND game_date <= '2026-08-08'"
    ).fetchone()[0]
    cast = conn.execute(
        "SELECT count(*) FROM mart_game_spine WHERE game_type='R' "
        "AND game_date::date >= '2026-08-06'::date AND game_date::date <= '2026-08-08'::date"
    ).fetchone()[0]
    assert uncast == 10 and cast == 15, (
        f"expected the un-cast string predicate to silently drop the end day "
        f"(got uncast={uncast}, cast={cast})"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════
# 2. check_odds_coverage — the S3 read must still produce every verdict, including FREEZE
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_a_frozen_bridge_is_still_detected_through_the_s3_read(conn):
    """The incident this guard exists for: games AND odds both present, ZERO attached."""
    _seed_odds(conn, {"2026-08-08": {"spine": 15, "events": 15, "bridge_with_odds": 0}})
    r = odds.fetch_coverage_rows(date(2026, 8, 8), date(2026, 8, 8), conn=conn)[0]
    assert odds._classify(int(r["spine_games"]), int(r["odds_events"]),
                          int(r["bridge_with_odds"])) == "FREEZE"


def test_a_partial_attach_is_still_detected_through_the_s3_read(conn):
    _seed_odds(conn, {"2026-08-08": {"spine": 15, "events": 15, "bridge_with_odds": 4}})
    r = odds.fetch_coverage_rows(date(2026, 8, 8), date(2026, 8, 8), conn=conn)[0]
    assert odds._classify(int(r["spine_games"]), int(r["odds_events"]),
                          int(r["bridge_with_odds"])) == "PARTIAL"


def test_books_not_posted_yet_is_never_reported_as_a_freeze(conn):
    """The property that makes this guard safe at HALT tier: FREEZE keys off odds_events>0,
    so an early-morning / forward-date slate with no odds can never trip it."""
    _seed_odds(conn, {"2026-08-08": {"spine": 15, "events": 0, "bridge_with_odds": 0}})
    r = odds.fetch_coverage_rows(date(2026, 8, 8), date(2026, 8, 8), conn=conn)[0]
    assert odds._classify(int(r["spine_games"]), int(r["odds_events"]),
                          int(r["bridge_with_odds"])) == "NO_ODDS_YET"


def test_a_healthy_slate_reads_ok_through_the_s3_read(conn):
    _seed_odds(conn, {"2026-08-08": {"spine": 15, "events": 15, "bridge_with_odds": 15}})
    r = odds.fetch_coverage_rows(date(2026, 8, 8), date(2026, 8, 8), conn=conn)[0]
    assert odds._classify(int(r["spine_games"]), int(r["odds_events"]),
                          int(r["bridge_with_odds"])) == "OK"


def test_a_date_outside_the_window_is_not_pulled_in(conn):
    """The mirror-image of the truncation bug: the cast must not WIDEN the window either."""
    _seed_odds(conn, {
        "2026-08-08": {"spine": 15, "events": 15, "bridge_with_odds": 15},
        "2026-08-09": {"spine": 15, "events": 15, "bridge_with_odds": 15},
    })
    rows = odds.fetch_coverage_rows(date(2026, 8, 8), date(2026, 8, 8), conn=conn)
    assert [str(r["d"]) for r in rows] == ["2026-08-08"]


# ══════════════════════════════════════════════════════════════════════════════════════════
# 3. check_prediction_coverage — HALT tier: it must still EXIT 1 on an under-covered slate
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_an_under_covered_slate_still_exits_nonzero(conn):
    """8 of 15 games scored = 53% — well under the 90% gate. This is the whole reason the op
    is HALT-tier, so it is the single most important negative test in this file."""
    _seed_predictions(
        conn,
        scheduled={"2026-08-08": 15},
        scored={"2026-08-08": [{"game_pk": 1000 + i} for i in range(8)]},
    )
    with pytest.raises(SystemExit) as e:
        pred.run(date(2026, 8, 8), conn=conn)
    assert e.value.code == 1


def test_a_zero_prediction_slate_still_exits_nonzero(conn):
    _seed_predictions(conn, scheduled={"2026-08-08": 15}, scored={})
    with pytest.raises(SystemExit) as e:
        pred.run(date(2026, 8, 8), conn=conn)
    assert e.value.code == 1


def test_a_fully_covered_slate_passes(conn):
    _seed_predictions(
        conn,
        scheduled={"2026-08-08": 15},
        scored={"2026-08-08": [{"game_pk": 1000 + i} for i in range(15)]},
    )
    pred.run(date(2026, 8, 8), conn=conn)  # must not raise


def test_an_off_day_is_skipped_not_failed(conn):
    """expected_games == 0 must SKIP. Reading it as 0% coverage would HALT the daily job on
    every All-Star break / off day."""
    _seed_predictions(conn, scheduled={}, scored={})
    pred.run(date(2026, 12, 25), conn=conn)  # must not raise


def test_only_the_latest_row_per_game_feeds_the_feature_summary(conn, capsys):
    """predict re-runs across the day WITHOUT superseding earlier rows, so a naive AVG would
    mix a morning intraday_fallback into a healthy post_lineup slate. The QUALIFY must survive
    the DuckDB translation."""
    rows = []
    for i in range(3):
        rows.append({"game_pk": 1000 + i, "data_source": "intraday_fallback",
                     "coverage": 0.40, "inserted_at": "2026-08-08 10:00:00"})
        rows.append({"game_pk": 1000 + i, "data_source": "feature_store",
                     "coverage": 1.00, "inserted_at": "2026-08-08 18:00:00"})
    _seed_predictions(conn, scheduled={"2026-08-08": 3}, scored={"2026-08-08": rows})
    pred.run(date(2026, 8, 8), conn=conn)
    out = capsys.readouterr().out
    assert "feature_store=3" in out and "intraday_fallback=0" in out
    assert "[METRIC] feature_coverage_score=1.0000" in out


def test_a_degraded_feature_set_still_warns_without_failing(conn, capsys):
    """Coverage is fine (all games scored) but the feature set is degraded — the check must
    still PASS (this half is deliberately non-blocking) while emitting the metric."""
    _seed_predictions(
        conn,
        scheduled={"2026-08-08": 5},
        scored={"2026-08-08": [{"game_pk": 1000 + i, "data_source": "intraday_fallback",
                                "coverage": 0.35} for i in range(5)]},
    )
    pred.run(date(2026, 8, 8), conn=conn)  # non-blocking: must not raise
    assert "[METRIC] feature_coverage_score=0.3500" in capsys.readouterr().out


# ══════════════════════════════════════════════════════════════════════════════════════════
# 4. check_data_freshness — the source registry + the lazy Snowflake connection
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_is_game_day_discriminates_through_the_s3_read(conn):
    conn.execute("CREATE TABLE stg_statsapi_games "
                 "(game_pk BIGINT, official_date DATE, game_type VARCHAR)")
    conn.execute("INSERT INTO stg_statsapi_games VALUES (1, '2026-08-08'::date, 'R')")
    # A spring-training game on an otherwise empty date must NOT make it a game day.
    conn.execute("INSERT INTO stg_statsapi_games VALUES (2, '2026-03-01'::date, 'S')")
    assert fresh._is_game_day(date(2026, 8, 8), conn) is True
    assert fresh._is_game_day(date(2026, 8, 9), conn) is False
    assert fresh._is_game_day(date(2026, 3, 1), conn) is False


def test_the_s3_max_timestamp_reader_labels_a_naive_value_utc(conn):
    """Same UTC-labelling contract as the Snowflake twin — the E11.20 phase-2b tz defect cost
    six days of false abstains by getting exactly this wrong on the other side."""
    conn.execute("CREATE TABLE some_posteriors (update_ts TIMESTAMP)")
    conn.execute("INSERT INTO some_posteriors VALUES ('2026-08-08 13:02:31'::timestamp)")
    ts = fresh._max_ingestion_timestamp_s3(
        "baseball_data.betting.some_posteriors", "update_ts", conn)
    assert ts is not None and ts.tzinfo is not None
    assert ts.utcoffset().total_seconds() == 0
    assert ts.isoformat() == "2026-08-08T13:02:31+00:00"


def test_an_empty_table_reads_as_no_data_not_as_fresh(conn):
    """NO DATA must stay distinguishable from OK — an unevaluable check is never a pass."""
    conn.execute("CREATE TABLE some_posteriors (update_ts TIMESTAMP)")
    assert fresh._max_ingestion_timestamp_s3(
        "baseball_data.betting.some_posteriors", "update_ts", conn) is None


def test_the_archetype_entry_reads_s3_because_its_snowflake_table_is_frozen():
    """The FOURTH retired-Snowflake-writer instance: update_archetype_posteriors_op went
    S3-only at W7a, so the Snowflake table froze 2026-07-05 and this entry had been printing a
    false STALE every game day for a month."""
    cfg = fresh.FRESHNESS_THRESHOLDS[
        "baseball_data.betting.mart_player_archetype_posteriors"]
    assert fresh.entry_source(cfg) == "s3"


def test_every_entry_declares_a_source_explicitly():
    """No silent defaults in the registry: a reader must be able to tell, per entry, which
    store it is trusting — that ambiguity is what let the archetype freeze hide."""
    missing = [t for t, c in fresh.FRESHNESS_THRESHOLDS.items() if "source" not in c]
    assert not missing, f"entries with no explicit source: {missing}"
    bad = {t: c["source"] for t, c in fresh.FRESHNESS_THRESHOLDS.items()
           if c["source"] not in ("s3", "snowflake")}
    assert not bad, f"unknown source values: {bad}"


def test_needs_snowflake_is_true_while_any_entry_is_still_snowflake_resident():
    assert fresh.needs_snowflake() is True, (
        "expected some entries to still be Snowflake-resident — if this flipped, the "
        "blockers were cleared and the module docstring's blocked-entry list is now stale"
    )


def test_needs_snowflake_goes_false_once_every_entry_is_s3():
    """The self-closing property: the day the last blocker clears, `run()` stops opening a
    Snowflake connection with no further code edit. Proven, not asserted in a comment."""
    all_s3 = {k: {**v, "source": "s3"} for k, v in fresh.FRESHNESS_THRESHOLDS.items()}
    assert fresh.needs_snowflake(all_s3) is False


def test_lakehouse_name_strips_the_snowflake_schema():
    assert fresh.lakehouse_name(
        "baseball_data.betting.team_sequential_posteriors") == "team_sequential_posteriors"
    assert fresh.lakehouse_name(
        "baseball_data.statsapi.player_profiles_raw") == "player_profiles_raw"
    assert fresh.lakehouse_name("already_bare") == "already_bare"


# ══════════════════════════════════════════════════════════════════════════════════════════
# 5. The repoint must not silently REGROW a Snowflake read
# ══════════════════════════════════════════════════════════════════════════════════════════
# A future edit re-adding `get_snowflake_connection()` to either fully-repointed script would
# quietly restore a COMPUTE_WH resume on every run and nothing would fail. This is an AST scan,
# not a text grep — so it is immune BY CONSTRUCTION to the "prose satisfies the guard" defect
# (INC-38): these files' docstrings discuss Snowflake at length, and a substring check would
# either fire on the prose or have to be weakened until it tested nothing.

def _snowflake_names_in_code(path: Path) -> set[str]:
    import ast

    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] == "snowflake":
                    found.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                if a.name in ("get_snowflake_connection", "get_monitoring_connection"):
                    found.add(f"{mod}.{a.name}")
                if mod.split(".")[0] == "snowflake":
                    found.add(f"{mod}.{a.name}")
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (
                fn.attr if isinstance(fn, ast.Attribute) else None)
            if name in ("get_snowflake_connection", "get_monitoring_connection"):
                found.add(f"call:{name}")
    return found


@pytest.mark.parametrize("filename", ["check_odds_coverage.py", "check_prediction_coverage.py"])
def test_a_fully_repointed_guard_has_no_snowflake_code_path(filename):
    found = _snowflake_names_in_code(_SCRIPTS / filename)
    assert not found, (
        f"{filename} regrew a Snowflake dependency ({sorted(found)}) — it was repointed to "
        f"S3/DuckDB by E11.24 target 3 precisely because it resumed COMPUTE_WH on ~every run"
    )


def test_the_partially_repointed_guard_still_declares_its_remaining_snowflake_use():
    """The counterpart assertion, so the test above cannot be satisfied by simply deleting the
    Snowflake code from a script that legitimately still needs it. check_data_freshness KEEPS a
    Snowflake path for the five blocked entries; the day those clear, this test is what tells
    the next session the docstring's blocked list needs rewriting too."""
    found = _snowflake_names_in_code(_SCRIPTS / "check_data_freshness.py")
    assert any("get_snowflake_connection" in f for f in found), (
        "check_data_freshness no longer imports get_snowflake_connection — if every entry is "
        "now source='s3', delete the Snowflake branch AND the blocked-entry list in its "
        "docstring, then update this test"
    )
