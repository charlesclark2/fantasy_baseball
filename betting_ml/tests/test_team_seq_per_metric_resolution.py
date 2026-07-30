"""E9.53 — the CONSUMER must resolve each team-sequential metric INDEPENDENTLY.

feature_pregame_game_features_raw used to pivot the three metrics to one row per
(game_pk, team, game_date) and THEN pick exactly ONE such row per (game_pk, side). All three
metrics were therefore forced to come from a single source row, so any metric missing from that
one row read NULL — even when a perfectly good posterior for it existed on an earlier date.

Live consequence (the reason this story exists): the producer wrote off_xwoba + win_prob but not
bullpen_xwoba for 2026-07-22/23/24/27/28, and `*_team_sequential_bullpen_xwoba` went NULL for
EVERY game on those dates, plus for today's scheduled slate whenever a team's latest prior row
happened to be one of the holed ones. team_sequential_* is unconditional-core DISCRIMINATIVE, so
that set is_degraded on served picks (discriminative_coverage 0.854-0.997, erratic).

These are real DuckDB executions of the two SQL shapes against a fixture reproducing that data,
so the fix is PROVEN, not asserted — including the two-sided requirement that the post-fix shape
is byte-identical to the pre-fix one whenever the exact row exists (it may only ADD coverage).
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MODEL = _PROJECT_ROOT / "dbt" / "models" / "feature" / "feature_pregame_game_features_raw.sql"
_PUBLIC = _PROJECT_ROOT / "dbt" / "models" / "feature" / "feature_pregame_game_features.sql"

# ── Fixture: NYY plays 07-23 (completed) and 07-29 (today, scheduled). ────────────────────
#   07-21  all three metrics written        → the last COMPLETE row
#   07-23  off + win only (bullpen HOLE)    → the E9.53 producer skip
# Pre-fix, the 07-23 completed game reads bullpen NULL (only the exact game_pk row was
# eligible, and it has no bullpen), and the 07-29 scheduled game ALSO reads bullpen NULL
# (the carry-forward picked 07-23, the holed row).
_FIXTURE = """
create table team_sequential_posteriors as
select * from (values
    -- (team, metric, game_pk, game_date, prior_mu, update_ts)
    ('NYY','off_xwoba',     101, date '2026-07-21', 0.330, timestamp '2026-07-22 06:00:00'),
    ('NYY','bullpen_xwoba', 101, date '2026-07-21', 0.300, timestamp '2026-07-22 06:00:00'),
    ('NYY','win_prob',      101, date '2026-07-21', 0.550, timestamp '2026-07-22 06:00:00'),
    ('NYY','off_xwoba',     102, date '2026-07-23', 0.335, timestamp '2026-07-24 06:00:00'),
    ('NYY','win_prob',      102, date '2026-07-23', 0.560, timestamp '2026-07-24 06:00:00')
) as t(team, metric, game_pk, game_date, prior_mu, update_ts);

create table games as
select * from (values
    (102, date '2026-07-23', false, 'NYY', 'BOS'),   -- completed, the holed date
    (109, date '2026-07-29', true,  'NYY', 'TOR')    -- today's slate, scheduled
) as g(game_pk, game_date, is_scheduled, home_team, away_team);
"""

_SPINE = """
spine_teams as (
    select game_pk, game_date, is_scheduled, home_team as team, 'home' as side from games
    union all
    select game_pk, game_date, is_scheduled, away_team as team, 'away' as side from games
)
"""

# The PRE-FIX shape, verbatim in structure: pivot first, then pick ONE row per (game_pk, side).
_PRE_FIX = f"""
with team_seq_pivot as (
    select
        game_pk, team, game_date::date as game_date,
        max(case when metric = 'off_xwoba'     then prior_mu end) as seq_off_xwoba,
        max(case when metric = 'bullpen_xwoba' then prior_mu end) as seq_bullpen_xwoba,
        max(case when metric = 'win_prob'      then prior_mu end) as seq_win_prob
    from (
        select game_pk, team, game_date, metric, prior_mu
        from team_sequential_posteriors
        qualify row_number() over (
            partition by team, metric, game_pk order by update_ts desc
        ) = 1
    )
    group by game_pk, team, game_date::date
),
{_SPINE},
team_seq as (
    select st.game_pk, st.side, ts.seq_off_xwoba, ts.seq_bullpen_xwoba, ts.seq_win_prob
    from spine_teams st
    left join team_seq_pivot ts
        on  ts.team = st.team
        and (
            (not st.is_scheduled and ts.game_pk = st.game_pk)
            or (st.is_scheduled and ts.game_date < st.game_date)
        )
    qualify row_number() over (
        partition by st.game_pk, st.side
        order by case when ts.game_pk = st.game_pk then 1 else 0 end desc,
                 ts.game_date desc nulls last
    ) = 1
)
select game_pk, side, seq_off_xwoba, seq_bullpen_xwoba, seq_win_prob
from team_seq where side = 'home' order by game_pk
"""

# The POST-FIX shape: resolve per metric, pivot LAST.
_POST_FIX = f"""
with team_seq_versions as (
    select game_pk, team, game_date::date as game_date, metric, prior_mu
    from team_sequential_posteriors
    qualify row_number() over (
        partition by team, metric, game_pk order by update_ts desc
    ) = 1
),
{_SPINE},
team_seq_metric as (
    select st.game_pk, st.side, v.metric, v.prior_mu
    from spine_teams st
    join team_seq_versions v
        on  v.team = st.team
        and (
            (not st.is_scheduled and v.game_pk = st.game_pk)
            or v.game_date < st.game_date
        )
    qualify row_number() over (
        partition by st.game_pk, st.side, v.metric
        order by case when v.game_pk = st.game_pk then 1 else 0 end desc,
                 v.game_date desc
    ) = 1
),
team_seq as (
    select
        game_pk, side,
        max(case when metric = 'off_xwoba'     then prior_mu end) as seq_off_xwoba,
        max(case when metric = 'bullpen_xwoba' then prior_mu end) as seq_bullpen_xwoba,
        max(case when metric = 'win_prob'      then prior_mu end) as seq_win_prob
    from team_seq_metric
    group by game_pk, side
)
select game_pk, side, seq_off_xwoba, seq_bullpen_xwoba, seq_win_prob
from team_seq where side = 'home' order by game_pk
"""


@pytest.fixture()
def con():
    c = duckdb.connect(":memory:")
    c.execute(_FIXTURE)
    yield c
    c.close()


def _rows(c, sql):
    """{game_pk: {off, pen, win}} — DuckDB hands DECIMAL back for the fixture literals, so
    coerce to float (None preserved: NULL is exactly what these tests are about)."""
    def f(v):
        return None if v is None else float(v)
    return {r[0]: {"off": f(r[2]), "pen": f(r[3]), "win": f(r[4])}
            for r in c.execute(sql).fetchall()}


class TestPreFixReproducesTheOutage:
    """Two-sided proof: the OLD shape must actually exhibit the bug on this fixture."""

    def test_completed_game_reads_bullpen_null(self, con):
        got = _rows(con, _PRE_FIX)
        assert got[102]["off"] == pytest.approx(0.335), "offense was fine — only bullpen holed"
        assert got[102]["win"] == pytest.approx(0.560)
        assert got[102]["pen"] is None, (
            "PRE-FIX: the completed 07-23 game must read bullpen NULL — this is the whole-block "
            "outage on a played date"
        )

    def test_todays_scheduled_game_also_reads_bullpen_null(self, con):
        got = _rows(con, _PRE_FIX)
        assert got[109]["pen"] is None, (
            "PRE-FIX: the carry-forward picked the HOLED 07-23 row, so today's live slate lost "
            "bullpen too — this is how the producer hole reached discriminative_coverage"
        )


class TestPostFixPopulatesEveryMetric:
    def test_completed_game_carries_the_metric_forward(self, con):
        got = _rows(con, _POST_FIX)
        assert got[102]["pen"] == pytest.approx(0.300), (
            "POST-FIX: the missing metric falls back to NYY's latest strictly-prior bullpen "
            "posterior (07-21), so the block populates on the played date"
        )
        # …and the metrics that DID have an exact row are untouched.
        assert got[102]["off"] == pytest.approx(0.335)
        assert got[102]["win"] == pytest.approx(0.560)

    def test_todays_scheduled_game_gets_every_metric(self, con):
        got = _rows(con, _POST_FIX)
        assert got[109]["off"] == pytest.approx(0.335), "latest prior off (07-23)"
        assert got[109]["win"] == pytest.approx(0.560), "latest prior win (07-23)"
        assert got[109]["pen"] == pytest.approx(0.300), (
            "POST-FIX: bullpen resolves independently to its OWN latest prior row (07-21) "
            "instead of being nulled by the holed 07-23 row"
        )

    def test_no_metric_is_null_anywhere(self, con):
        for game_pk, vals in _rows(con, _POST_FIX).items():
            assert all(v is not None for v in vals.values()), f"game {game_pk}: {vals}"


class TestPostFixIsANoOpWhenNothingIsMissing:
    """The fix may only ADD coverage — it must never change a value that was already served."""

    def test_identical_output_on_a_complete_history(self, con):
        # Give 07-23 its bullpen row, so every metric has an exact row for the completed game.
        con.execute(
            "insert into team_sequential_posteriors values "
            "('NYY','bullpen_xwoba',102,date '2026-07-23',0.305,timestamp '2026-07-24 06:00:00')"
        )
        assert _rows(con, _PRE_FIX) == _rows(con, _POST_FIX)

    def test_exact_row_still_wins_over_the_carry_forward(self, con):
        con.execute(
            "insert into team_sequential_posteriors values "
            "('NYY','bullpen_xwoba',102,date '2026-07-23',0.305,timestamp '2026-07-24 06:00:00')"
        )
        got = _rows(con, _POST_FIX)
        assert got[102]["pen"] == pytest.approx(0.305), (
            "the EXACT game_pk row must be preferred over the 07-21 carry-forward"
        )

    def test_scd2_latest_version_still_wins(self, con):
        # A re-backfill writes a second version of the same grain; the newest update_ts wins.
        con.execute(
            "insert into team_sequential_posteriors values "
            "('NYY','off_xwoba',102,date '2026-07-23',0.999,timestamp '2026-07-25 06:00:00')"
        )
        assert _rows(con, _POST_FIX)[102]["off"] == pytest.approx(0.999)


class TestLeakageSafety:
    def test_same_date_rows_are_never_eligible_as_a_fallback(self, con):
        # Doubleheader safety: game 2 on the SAME date must not read game 1's row. Only strictly
        # prior dates are eligible (`<`, not `<=`), so a same-date-only history yields NULL.
        con.execute("delete from team_sequential_posteriors")
        con.execute(
            "insert into team_sequential_posteriors values "
            "('NYY','bullpen_xwoba',101,date '2026-07-23',0.300,timestamp '2026-07-24 06:00:00')"
        )
        got = _rows(con, _POST_FIX)
        # No metric has an eligible row, so (102,'home') drops out of team_seq entirely. The model
        # consumes team_seq via `left join`, so an absent row and a NULL row are the same served
        # outcome: no value. Assert that contract rather than the intermediate row's presence.
        assert got.get(102, {}).get("pen") is None, (
            "a same-date row (doubleheader game 1) must NOT be carried into game 2 — that would "
            "be a within-day leak"
        )

    def test_future_rows_are_never_eligible(self, con):
        # A row dated AFTER the target game must never be selected (no forward leakage).
        con.execute(
            "insert into team_sequential_posteriors values "
            "('NYY','bullpen_xwoba',199,date '2026-07-28',0.111,timestamp '2026-07-29 06:00:00')"
        )
        got = _rows(con, _POST_FIX)
        assert got[102]["pen"] == pytest.approx(0.300), (
            "the 07-23 game must still read the 07-21 posterior, never the future 07-28 one"
        )
        # Today's scheduled 07-29 game legitimately MAY use 07-28 (it is strictly prior).
        assert got[109]["pen"] == pytest.approx(0.111)


class TestModelSourceCarriesTheFix:
    """Source-inspection backstop: the shipped model must actually use the per-metric shape."""

    def test_model_resolves_per_metric_before_pivoting(self):
        src = _MODEL.read_text()
        assert "team_seq_metric as (" in src, "the per-metric resolution CTE is missing"
        assert "partition by st.game_pk, st.side, v.metric" in src, (
            "the resolution must partition by METRIC — without it all three metrics are again "
            "forced to come from one source row (the E9.53 defect)"
        )
        assert "team_seq_pivot as (" not in src, (
            "the pivot-then-pick CTE is back — that is the defect this story fixed"
        )

    def test_seasonnorm_masking_is_documented_as_deferred_to_e1_12(self):
        # E9.53 diagnosed that a bare coalesce(...,0) serves a missing RAW feature as a fabricated
        # 0.0 ("exactly league average"), which is why the outage LOOKED like the raw and
        # _seasonnorm columns came from different paths. The FIX changes a served model input, so
        # it is deferred to the E1.12 retrain — but the finding must not be lost, or a future
        # session re-diagnoses it from scratch. Semantics + the two-copy parity invariant are
        # pinned by test_w8b_wrapper_seasonnorm_parity.py.
        src = _PUBLIC.read_text()
        assert "DEFERRED TO E1.12" in src, (
            "the deferred _seasonnorm masking defect must stay documented in the model"
        )
        # The INC-19 type pin must survive regardless.
        assert re.search(r"\)::double as \{\{ c \}\}_seasonnorm", src), (
            "the _seasonnorm ::double type pin was lost (INC-19)"
        )


class TestTheServedDuckdbBranchCarriesTheFix:
    """The DuckDB branch is the SERVED build path (run_w1_lakehouse extracts it → S3 parquet), and
    no local dbt target compiles it — `dbtf compile` only validates the Snowflake branch. So parse
    it explicitly here, or a syntax error in the branch that actually serves predictions ships
    green (the RUNTIME-GATE class: CI mocks all IO)."""

    def _extracted(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "run_w1_lakehouse", _PROJECT_ROOT / "scripts" / "run_w1_lakehouse.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.extract_duckdb_sql("feature_pregame_game_features_raw")

    def test_extracted_branch_parses_in_duckdb(self):
        import json
        sql = self._extracted()
        con = duckdb.connect(":memory:")
        try:
            parsed = json.loads(con.execute("select json_serialize_sql(?)", [sql]).fetchone()[0])
        finally:
            con.close()
        assert parsed.get("error") is False, (
            f"the served DuckDB branch does not parse: {parsed.get('error_message')}"
        )

    def test_extracted_branch_uses_the_per_metric_resolution(self):
        sql = self._extracted()
        assert "team_seq_metric" in sql and "team_seq_versions" in sql
        assert "partition by st.game_pk, st.side, v.metric" in sql
        assert "team_seq_pivot" not in sql, "the pre-fix pivot-then-pick shape is still served"
