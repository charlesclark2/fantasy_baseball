"""MLB-LAKE2 — the W3pre intraday tier: compaction reader sign-off + the tier's scope.

Two levers, guarded here.

LEVER ① — `derivative_odds_raw` joins `COMPACTABLE_SOURCES`.
`compact_lakehouse_raw.py` writes promote-then-delete, so a reader binding the glob inside the
window sees a partition's rows TWICE. That order is safe only as a property of the READERS, and
this source's chain is NOT the same shape as `mlb_odds_raw`'s, so its rationale cannot be
borrowed (the script refuses one on purpose):

    derivative_odds_raw  ──(1)──>  stg_derivative_odds  ──(2)──>  mart_derivative_closes
                                   (NO dedup)                     eval_cross_market.py

  (1) the ONLY reader of the raw glob is the flatten, and it does NOT dedup — so unlike
      mlb_odds_raw the duplication is NOT absorbed at the first hop. It is a pure
      unnest chain (no join), so it propagates EXACTLY 2x rather than squaring.
  (2) both readers of the flattened output do their OWN closing selection
      (`row_number() ... = 1` over a key that includes the snapshot), which collapses an exact
      duplicate to the same row.

MEASURED 2026-09-14 against LIVE S3 (real partition `derivative_odds_raw/dt=2026-08-16`, 42 real
files, the real flatten SQL and the real reader SQL, clean vs. the duplicate window):

    L1  real flatten                      24,942 -> 49,884 rows   EXACTLY 2.00x
    L2a eval_cross_market closing          390 ->    390 rows     IDENTICAL
    L2b mart_derivative_closes closing   7,412 ->  7,412 rows     IDENTICAL

L1 is the two-sided control: it proves the duplicate genuinely REACHED the readers, so L2's
"identical" is a measurement and not a vacuous pass (NF1.7 (a)). The tests below re-run that
measurement OFFLINE, on a committed slice of REAL `stg_derivative_odds` rows, so it stays true.

⭐ A property the RED proof turned up and the rationale now records: `eval_cross_market` is
duplicate-idempotent REDUNDANTLY. `rn = 1` keeps exactly one row per key however many copies
exist, and the outer `max()` is invariant over a doubled multiset — breaking either ALONE leaves
the output identical (both measured). So the sign-off does not hang on a single line of SQL, and
only defeating both makes this reader see a duplicate at all.

LEVER ② — the intraday tick builds only what a consumer reads intraday.
`--w3pre-only` is one 480 s leg of a 30-min tick. Three of its four models are daily-cadence odds
staging with NO intraday consumer; the fourth (`stg_statsapi_games`) carries a 90-min freshness
SLA. MLB-INC-0904 put the serving-critical one FIRST so a timeout could not starve it; this goes
the rest of the way and stops the tick paying for the other three at all. The DAILY build
(`lakehouse_w3pre_flatten_op`, `timeout=1800`) keeps building the full tier, so nothing is
orphaned — see `test_the_daily_build_still_owns_every_model_the_tick_drops`.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURE = Path(__file__).parent / "fixtures" / "mlb_lake2_stg_derivative_odds_team_totals.csv"

#: The PRODUCTION column types of `stg_derivative_odds`, read from the live parquet 2026-09-14.
#: Pinned, not inferred: every TIMESTAMP column of this table is stored as ISO VARCHAR (the W8a
#: string-timestamp pin, INC-23) and both readers cast `::timestamp` at the use site. Letting the
#: CSV loader infer types would materialise TIMESTAMP columns and run the measurement against a
#: schema production never serves — the cast would then be a no-op and the fixture would stop
#: resembling the thing under test.
_PRODUCTION_TYPES: dict[str, str] = {
    "ingestion_ts": "VARCHAR", "load_id": "VARCHAR", "requested_snapshot_ts": "VARCHAR",
    "actual_snapshot_ts": "VARCHAR", "previous_snapshot_ts": "VARCHAR",
    "next_snapshot_ts": "VARCHAR", "markets_requested": "VARCHAR",
    "regions_requested": "VARCHAR", "x_requests_remaining": "VARCHAR",
    "x_requests_last": "VARCHAR", "event_id": "VARCHAR", "sport_key": "VARCHAR",
    "commence_time": "VARCHAR", "home_team": "VARCHAR", "away_team": "VARCHAR",
    "bookmaker_key": "VARCHAR", "bookmaker_title": "VARCHAR",
    "bookmaker_last_update": "VARCHAR", "market_key": "VARCHAR",
    "market_last_update": "VARCHAR", "outcome_name": "VARCHAR",
    "outcome_description": "VARCHAR", "outcome_price_american": "INTEGER",
    "outcome_price_decimal": "DOUBLE", "outcome_point": "DOUBLE",
}

pytest.importorskip("duckdb")


# ────────────────────────────────────────────────────────────────────────────────
# Fixture plumbing — real rows, production types
# ────────────────────────────────────────────────────────────────────────────────
def _fixture_rows() -> list[dict]:
    with FIXTURE.open() as fh:
        return list(csv.DictReader(fh))


def _select_list() -> str:
    return ", ".join(f"CAST({c} AS {_PRODUCTION_TYPES[c]}) AS {c}" for c in _fixture_rows()[0])


def _materialise(tmp_path: Path, *, duplicated: bool) -> str:
    """Write the fixture as `<lakehouse>/stg_derivative_odds/data.parquet`.

    ``duplicated=True`` models the compaction's promote-then-delete window: the raw partition's
    rows are visible twice, and the flatten (which does not dedup — L1 above) carries that
    straight through into the single staging parquet its readers bind.
    """
    import duckdb

    lake = tmp_path / ("dup" if duplicated else "clean")
    (lake / "stg_derivative_odds").mkdir(parents=True)
    con = duckdb.connect()
    body = f"SELECT {_select_list()} FROM read_csv('{FIXTURE}', header=true, all_varchar=true)"
    if duplicated:
        body = f"{body} UNION ALL {body}"
    con.execute(f"COPY ({body}) TO '{lake / 'stg_derivative_odds' / 'data.parquet'}' (FORMAT PARQUET)")
    con.close()
    return str(lake)


def _bridge():
    """event_id -> game_pk. Not under test: the bridge is a join input the dup window cannot
    touch, so synthetic game_pks are honest here — what is REAL is the odds rows."""
    import pandas as pd

    ids = sorted({r["event_id"] for r in _fixture_rows()})
    return pd.DataFrame({"event_id": ids,
                         "game_pk": list(range(700001, 700001 + len(ids))),
                         "game_date": ["2026-08-16"] * len(ids)})


# ────────────────────────────────────────────────────────────────────────────────
# 0. Non-vacuity — the fixture must be able to SHOW a perturbed selection
# ────────────────────────────────────────────────────────────────────────────────
def test_the_fixture_is_real_and_its_closing_selection_is_load_bearing():
    """If every snapshot of a key agreed, "identical under duplication" would prove nothing.

    The readers pick the LATEST snapshot per key. That choice only has consequences where the
    snapshots of a key DISAGREE on price or point — so the fixture has to contain such keys, or
    the whole measurement is satisfied by a constant.
    """
    rows = [r for r in _fixture_rows()
            if r["market_key"] == "team_totals" and r["outcome_point"] != ""
            and r["actual_snapshot_ts"] <= r["commence_time"]]
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r["event_id"], r["bookmaker_key"], r["outcome_description"], r["outcome_name"])
        groups.setdefault(key, []).append(r)

    assert len(groups) >= 8, f"fixture has only {len(groups)} selection groups"
    multi = [v for v in groups.values() if len(v) > 1]
    assert len(multi) == len(groups), "every group must carry >1 snapshot, or ORDER BY is untested"
    disagree = [v for v in multi
                if len({x["outcome_price_american"] for x in v}) > 1
                or len({x["outcome_point"] for x in v}) > 1]
    assert len(disagree) >= 5, (
        f"only {len(disagree)} groups have snapshots that DISAGREE on price/point. A perturbed "
        f"closing selection would be invisible in this fixture — re-cut it from real data."
    )
    # real data, not hand-written: several books, both sides, both teams of a game
    assert len({r["bookmaker_key"] for r in rows}) >= 2
    assert {r["outcome_name"] for r in rows} >= {"Over", "Under"}
    assert len({r["outcome_description"] for r in rows}) >= 3

    # the slice must carry the FULL production schema: mart_derivative_closes selects columns
    # (bookmaker_title, market_last_update, ...) that the eval reader never touches, so a fixture
    # cut to one reader's columns silently stops exercising the other.
    assert set(_fixture_rows()[0]) == set(_PRODUCTION_TYPES), (
        f"fixture columns drifted from the production schema of stg_derivative_odds: "
        f"missing {sorted(set(_PRODUCTION_TYPES) - set(_fixture_rows()[0]))}, "
        f"unexpected {sorted(set(_fixture_rows()[0]) - set(_PRODUCTION_TYPES))}"
    )


# ────────────────────────────────────────────────────────────────────────────────
# 1. THE CONTROL — the duplicate window must actually reach the readers
# ────────────────────────────────────────────────────────────────────────────────
def test_the_duplicate_window_actually_reaches_the_readers(tmp_path):
    """Two-sided control for the two tests below.

    Without this, "the reader's output is identical" is indistinguishable from "the duplication
    never happened" — the vacuous-anchor bug (NF1.7 (a)). A read with NO dedup must double.
    """
    import duckdb

    con = duckdb.connect()
    counts = {}
    for dup in (False, True):
        lake = _materialise(tmp_path, duplicated=dup)
        counts[dup] = con.execute(
            f"SELECT count(*) FROM read_parquet('{lake}/stg_derivative_odds/**/*.parquet', "
            f"union_by_name=true)").fetchone()[0]
    con.close()
    assert counts[True] == 2 * counts[False] > 0, (
        f"the simulated window did not double the rows a reader binds ({counts}) — every "
        f"'unchanged under duplication' result below would then be passing on nothing."
    )


# ────────────────────────────────────────────────────────────────────────────────
# 2. LEVER ① — the two readers of the flattened output, driven for real
# ────────────────────────────────────────────────────────────────────────────────
def test_eval_cross_market_closing_selection_is_unchanged_by_the_duplicate_window(tmp_path):
    """The reader MLB-INC-0904 §7 named as the sign-off gate, driven as it actually ships.

    ⭐ This calls the REAL `_read_team_totals` rather than re-typing its SQL: a test that
    restates the code cannot catch the code being wrong (the NF-C0e class).
    """
    import duckdb

    from betting_ml.scripts.cross_market_eval.eval_cross_market import _read_team_totals

    bridge = _bridge()
    out = {}
    for dup in (False, True):
        con = duckdb.connect()
        out[dup] = _read_team_totals(con, _materialise(tmp_path, duplicated=dup), bridge, "2026")
        con.close()
        out[dup] = out[dup].sort_values(list(out[dup].columns)).reset_index(drop=True)

    assert not out[False].empty, "the reader returned nothing — the fixture misses its filters"
    assert out[False].equals(out[True]), (
        "eval_cross_market's closing selection CHANGED under the compaction's duplicate window.\n"
        "promote-then-delete is then NOT safe for derivative_odds_raw and the source must leave "
        "COMPACTABLE_SOURCES — do not weaken this test.\n"
        f"{out[False].compare(out[True]) if out[False].shape == out[True].shape else 'row counts differ'}"
    )


def test_mart_derivative_closes_is_unchanged_by_the_duplicate_window(tmp_path):
    """The other reader of the flattened output — its REAL dbt SQL, not a paraphrase."""
    import duckdb

    from scripts.run_w1_lakehouse import extract_duckdb_sql

    sql = extract_duckdb_sql("mart_derivative_closes")
    # The dup window can only perturb the CLOSING selection; everything after it is a join to the
    # bridge, which this source's duplication does not touch. Cut the real SQL at that seam so the
    # assertion is on the stage under test rather than on a stubbed join.
    seam = sql.lower().index("game_bridge as (")
    closing_sql = sql[:seam].rstrip().rstrip(",") + "\nselect * from closing"

    out = {}
    for dup in (False, True):
        con = duckdb.connect()
        lake = _materialise(tmp_path, duplicated=dup)
        con.execute(f"CREATE VIEW stg_derivative_odds AS SELECT * FROM read_parquet("
                    f"'{lake}/stg_derivative_odds/**/*.parquet', union_by_name=true)")
        df = con.execute(closing_sql).fetchdf()
        con.close()
        out[dup] = df.sort_values(list(df.columns)).reset_index(drop=True)

    assert not out[False].empty
    assert out[False].equals(out[True]), (
        "mart_derivative_closes' closing selection CHANGED under the duplicate window — "
        "derivative_odds_raw must leave COMPACTABLE_SOURCES."
    )


def test_the_flatten_cannot_absorb_or_amplify_the_duplication(tmp_path):
    """Pins the (1) link of the chain in the module docstring.

    Two claims, both structural and both load-bearing for the rationale:
      * NO dedup construct  => duplication is NOT absorbed here, so the L2 readers are what make
        promote-then-delete safe. If a dedup is ever added the rationale gets *safer*, but it
        would no longer describe the code, so it must be restated.
      * NO join             => duplication propagates linearly (measured 2.00x), not squared.
    """
    from scripts.run_w1_lakehouse import extract_duckdb_sql

    sql = extract_duckdb_sql("stg_derivative_odds")
    stripped = re.sub(r"^\s*--.*$", "", sql, flags=re.MULTILINE)

    for construct in ("qualify", "distinct", "row_number", "group by"):
        assert not re.search(rf"\b{construct}\b", stripped, re.IGNORECASE), (
            f"stg_derivative_odds now contains `{construct}` — it used to be a pure "
            f"row-preserving flatten, which is the premise of derivative_odds_raw's entry in "
            f"COMPACTABLE_SOURCES. Re-state that rationale against the new code."
        )
    assert not re.search(r"\bjoin\b", stripped, re.IGNORECASE), (
        "stg_derivative_odds now contains a join — duplication may no longer propagate linearly, "
        "so the measured 2.00x in this module's docstring no longer bounds the blast radius."
    )


# ────────────────────────────────────────────────────────────────────────────────
# 3. LEVER ② — the tick's scope, and the anti-orphan guards that make it safe
# ────────────────────────────────────────────────────────────────────────────────
#: A model the tick drops must still be BUILT by something, and — if its content is live — be
#: WATCHED, or the move trades a timeout for a silent freeze. Each moved model is therefore
#: either in the INC-41 registry or carries a stated, measured exemption here.
_MOVED_WITHOUT_FRESHNESS_COVERAGE: dict[str, str] = {
    "stg_oddsapi_events": (
        "its raw source mlb_events_raw is RETIRED — last partition dt=2026-06-04, no object "
        "written since 2026-06-28 — so max(ingestion_ts) reads 2026-06-04T23:25:12 on a healthy "
        "system (~102 days). An SLA would be red forever and would say nothing about the builder."
    ),
}


def _src(rel: str) -> str:
    """Comment-stripped source. INC-38: a guard a COMMENT can satisfy is not a guard, and every
    file touched here carries explanatory comments that name the very flags being asserted."""
    text = (REPO_ROOT / rel).read_text()
    if rel.endswith(".sql"):
        return re.sub(r"^\s*--.*$", "", text, flags=re.MULTILINE)
    return re.sub(r"^\s*#.*$", "", text, flags=re.MULTILINE)


def test_the_intraday_scope_is_a_subset_that_keeps_the_serving_critical_model():
    from scripts.run_w1_lakehouse import W3PRE_INTRADAY_MODELS, W3PRE_STG_MODELS

    assert set(W3PRE_INTRADAY_MODELS) <= set(W3PRE_STG_MODELS), (
        "the tick cannot build a model the full tier does not contain"
    )
    assert "stg_statsapi_games" in W3PRE_INTRADAY_MODELS, (
        "stg_statsapi_games carries the 90-min freshness SLA and is the ONLY member of this tier "
        "with an intraday consumer — dropping it from the tick is the MLB-INC-0904 outage."
    )
    assert set(W3PRE_INTRADAY_MODELS) != set(W3PRE_STG_MODELS), (
        "the tick is building the full tier again — MLB-LAKE2 moved the daily-cadence odds "
        "staging off the 30-min leg because it no longer fit inside the 480 s cap."
    )


def test_the_tick_asks_for_the_scoped_build_and_the_daily_asks_for_the_full_tier():
    """Pins BOTH owners. The two callers pass different flags to the same script, and it is the
    difference between them that makes the move safe rather than a silent freeze."""
    tick = _src("pipeline/ops/intraday_ops.py")
    assert '"--w3pre-serving-only"' in tick, (
        "the 30-min tick no longer requests the scoped W3pre build — it is back to paying ~163 s "
        "for daily-cadence odds staging inside a 480 s leg."
    )
    assert '"--w3pre-only"' not in tick, (
        "the tick requests the FULL W3pre tier again (--w3pre-only)."
    )
    daily = _src("pipeline/ops/daily_ingestion_ops.py")
    assert '"--w3pre-only"' in daily, (
        "the DAILY build no longer requests the full W3pre tier. It is the sole builder of the "
        "three models the tick drops — without this the move ORPHANS them."
    )


def test_the_daily_build_still_owns_every_model_the_tick_drops():
    """The anti-orphan invariant, stated as the thing that must not become false.

    The tick drops a model only because a DAILY builder still builds it. If the daily op ever
    narrows its scope the same way the tick just did, these tables lose their last builder — the
    exact silent-freeze class this repo keeps paying for (INC-25, INC-27, E5.10).
    """
    from scripts.run_w1_lakehouse import W3PRE_INTRADAY_MODELS, W3PRE_STG_MODELS

    dropped = set(W3PRE_STG_MODELS) - set(W3PRE_INTRADAY_MODELS)
    assert dropped, "nothing was moved — the rest of this guard is vacuous"

    daily = _src("pipeline/ops/daily_ingestion_ops.py")
    # the daily op must ask for the UNSCOPED build, which is what builds the full tier
    assert re.search(r'"run_w1_lakehouse\.py",\s*\["--w3pre-only"\]', daily), (
        f"lakehouse_w3pre_flatten_op no longer runs `--w3pre-only`, so the models the tick "
        f"dropped ({sorted(dropped)}) may have NO builder left."
    )


@pytest.mark.parametrize("model", ["stg_oddsapi_odds", "stg_oddsapi_events", "stg_derivative_odds"])
def test_every_moved_model_is_watched_or_has_a_stated_exemption(model):
    """A dropped model with live content must PAGE if the daily builder stops.

    The daily op is gated on W11_W3PRE_DAILY — default-OFF and not in env.required — so "the
    daily build runs" is an assumption about a box's live env, not a property of this repo. A
    freshness SLA is what turns that assumption into something that announces itself when it
    stops being true.
    """
    from scripts.run_w1_lakehouse import W3PRE_INTRADAY_MODELS, W3PRE_STG_MODELS
    from betting_ml.monitoring.artifact_freshness import REGISTRY

    dropped = set(W3PRE_STG_MODELS) - set(W3PRE_INTRADAY_MODELS)
    if model not in dropped:
        pytest.skip(f"{model} is still built by the tick")

    watched = {c.name for c in REGISTRY}
    if model in _MOVED_WITHOUT_FRESHNESS_COVERAGE:
        why = _MOVED_WITHOUT_FRESHNESS_COVERAGE[model]
        assert model not in watched, (
            f"{model} is listed as exempt from freshness coverage AND registered in INC-41 — "
            f"one of the two is wrong. Exemption on record: {why}"
        )
        # the reason must live in the module a future reader will actually open, not only here
        assert model in (REPO_ROOT / "betting_ml/monitoring/artifact_freshness.py").read_text(), (
            f"{model} is exempt from an SLA but artifact_freshness.py does not say so — an "
            f"absence with no stated reason reads as an oversight (NF1.7 (a))."
        )
        return
    assert model in watched, (
        f"{model} was moved off the 30-min tick, so the once-daily (and env-gated) "
        f"lakehouse_w3pre_flatten_op is its ONLY builder — but nothing watches it. Register an "
        f"INC-41 FreshnessContract at its daily cadence, or record a measured exemption in "
        f"_MOVED_WITHOUT_FRESHNESS_COVERAGE."
    )


def test_the_daily_cap_matches_the_timeout_the_daily_op_actually_passes():
    """One logical quantity, two owners (INC-30 crontab, INC-36 concurrency, INC-38 per-caller
    flags). The tier is graded against this number; the op enforces that one."""
    from betting_ml.monitoring.intraday_tick_budget import W3PRE_DAILY_TIMEOUT_SECONDS

    daily = _src("pipeline/ops/daily_ingestion_ops.py")
    m = re.search(r'"run_w1_lakehouse\.py",\s*\["--w3pre-only"\],\s*timeout=(\d+)', daily)
    assert m, "could not find lakehouse_w3pre_flatten_op's run_w1_lakehouse invocation"
    assert int(m.group(1)) == W3PRE_DAILY_TIMEOUT_SECONDS, (
        f"the W3pre tier is graded against {W3PRE_DAILY_TIMEOUT_SECONDS}s but the daily op now "
        f"enforces {m.group(1)}s — the budget and the thing it budgets have drifted apart."
    )


def test_the_full_tier_is_graded_against_the_daily_cap_unless_the_tick_asks_otherwise():
    """A default that grades the full tier against the 480 s TICK cap would report OVER on every
    daily and manual run — a permanently-wrong verdict, which is how a monitor gets ignored."""
    import inspect

    from betting_ml.monitoring.intraday_tick_budget import (
        LEG_TIMEOUT_SECONDS, W3PRE_DAILY_TIMEOUT_SECONDS, w3pre_tier_verdict)
    from scripts.run_w1_lakehouse import _build_w3pre

    default = inspect.signature(_build_w3pre).parameters["leg_timeout_seconds"].default
    assert default == W3PRE_DAILY_TIMEOUT_SECONDS, (
        f"_build_w3pre defaults to grading against {default}s; the full tier runs under the "
        f"daily cap ({W3PRE_DAILY_TIMEOUT_SECONDS}s), not the tick's {LEG_TIMEOUT_SECONDS}s."
    )
    # and the tick's scope must land comfortably inside the tick's own cap
    measured_games_seconds = 12.0          # MLB-INC-0904 / re-measured 2026-09-14: unchanged
    v = w3pre_tier_verdict({"stg_statsapi_games": measured_games_seconds},
                           leg_timeout_seconds=LEG_TIMEOUT_SECONDS)
    assert v.verdict == "OK" and v.fraction < 0.30, (
        f"the scoped tick tier does not sit comfortably inside its cap: {v.verdict} at "
        f"{v.fraction:.0%}"
    )
