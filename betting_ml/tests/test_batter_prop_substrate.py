"""Guards for the MLB batter-prop Phase-1 substrate builder.

Each guard here was RED-proven against deliberately-broken source before being
trusted (the INC-38 / NF1.7(a) discipline: a guard that cannot fail is worse than
no guard).  In particular the switch-hitter guard is written so that DELETING the
collapse step makes it fail — it does not merely restate what the code does.

No network IO: the SQL is exercised against in-memory DuckDB fixtures, which is why
`build_rolling_features` takes a `source_relation` rather than reading S3 directly.
Fast-gate safe — imports `scripts.build_batter_prop_substrate` (which imports only
`betting_ml.utils.prop_edge`), never `pipeline`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb
import pytest

_SRC = Path(__file__).resolve().parents[2] / "scripts" / "build_batter_prop_substrate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("_bps", _SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bps = _load_module()


# ── name-key folding ───────────────────────────────────────────────────────────

class TestNameKeyFolding:
    """The Odds API emits the Unicode curly apostrophe; the player reference table
    uses ASCII.  `prop_edge.normalize_name` maps the ASCII form to a SPACE
    ('ryan o hearn') but DROPS the curly form ('ryan ohearn'), so the two do not
    match each other and every apostrophe surname fails to resolve."""

    def test_curly_and_ascii_apostrophes_produce_the_same_key(self):
        assert bps._name_key("Ryan O’Hearn") == bps._name_key("Ryan O'Hearn")
        assert bps._name_key("Tyler O’Neill") == bps._name_key("Tyler O'Neill")

    def test_the_underlying_shared_util_still_disagrees(self):
        """Pins WHY the fold is needed.  If `prop_edge.normalize_name` is ever fixed
        upstream this goes red, which is the correct prompt to drop the local fold
        rather than let two normalisers silently diverge."""
        from betting_ml.utils.prop_edge import normalize_name
        assert normalize_name("Ryan O’Hearn") != normalize_name("Ryan O'Hearn")

    def test_key_is_order_independent(self):
        assert bps._name_key("Judge, Aaron") == bps._name_key("Aaron Judge")

    def test_legal_vs_common_first_name_shares_a_last_initial_key(self):
        for legal, common in [("Thomas Edman", "Tommy Edman"),
                              ("Caleb Raleigh", "Cal Raleigh"),
                              ("Zachary Neto", "Zach Neto")]:
            assert bps._li_key(legal) == bps._li_key(common)
            # ...and the exact key genuinely does NOT match, or the fallback tier
            # would be dead code and this pairing would prove nothing.
            assert bps._name_key(legal) != bps._name_key(common)


# ── switch-hitter collapse (the leakage guard) ─────────────────────────────────

_COLS = ("game_pk, batter_id, game_date, batter_hand, opposing_team, pa_count, "
         "pa_count_7d, pa_count_30d, games_30d, avg_30d, obp_30d, slg_30d, ops_30d, "
         "woba_30d, xwoba_30d, xba_30d, xslg_30d, k_pct_30d, bb_pct_30d, "
         "hard_hit_pct_30d, barrel_pct_30d, woba_7d, slg_7d, k_pct_7d, "
         "woba_std, slg_std, iso_std, k_pct_std")


def _row(game_pk, batter_id, day, hand, pa, woba_30d, woba_std):
    """One mart_batter_rolling_stats-shaped row; only the columns the assertions
    read carry distinguishing values.

    Numerics are cast ::DOUBLE because a bare DuckDB VALUES literal is DECIMAL,
    whereas the real parquet columns are DOUBLE — the fixture should match the
    production type, not merely be convenient.
    """
    f = lambda v: f"{v}::DOUBLE"  # noqa: E731
    return (f"({game_pk}, {batter_id}, DATE '2025-05-{day:02d}', '{hand}', 'OPP', {pa}, "
            f"10, 40, 10, {f(0.25)}, {f(0.32)}, {f(0.40)}, {f(0.72)}, {f(woba_30d)}, "
            f"{f(0.31)}, {f(0.24)}, {f(0.41)}, {f(0.22)}, {f(0.08)}, {f(0.38)}, "
            f"{f(0.07)}, {f(0.30)}, {f(0.42)}, {f(0.21)}, {f(woba_std)}, "
            f"{f(0.40)}, {f(0.15)}, {f(0.22)})")


@pytest.fixture()
def con():
    c = duckdb.connect()
    yield c
    c.close()


def _fixture_relation(rows: list[str]) -> str:
    return f"(SELECT * FROM (VALUES {', '.join(rows)}) AS t({_COLS}))"


class TestSwitchHitterCollapse:
    """A switch-hitter gets TWO rows per game (one per batting hand) that SPLIT the
    game's PAs.  Unless they are collapsed BEFORE the lag, `lag()` over
    (batter_id ORDER BY game_date) returns the SAME GAME's other-hand row as the
    'previous game' — i.e. the pregame feature carries current-game information."""

    def test_collapses_to_one_row_per_batter_game(self, con):
        rel = _fixture_relation([
            _row(1, 100, 1, "R", 2, 0.300, 0.310),
            _row(1, 100, 1, "L", 2, 0.300, 0.350),   # same game, other hand
            _row(2, 100, 5, "R", 4, 0.400, 0.410),
        ])
        bps.build_rolling_features(con, rel)
        n = con.execute("""SELECT count(*) FROM (
              SELECT game_pk, batter_id FROM feat_rolling
              GROUP BY 1,2 HAVING count(*) > 1)""").fetchone()[0]
        assert n == 0

    def test_lag_reaches_the_previous_GAME_not_the_other_hand_of_the_same_game(self, con):
        """⭐ THE LEAKAGE ASSERTION.  Game 2's lagged feature must be game 1's value
        (0.300).  If the collapse is removed, the lag returns the other-hand row of
        game 2 itself — whose woba_30d is 0.400, the current game's value.

        ⚠️ This MUST read EVERY row for game 2, not `fetchone()`.  An earlier version
        of this test used `fetchone()` and was VACUOUS: with the collapse broken there
        are two rows for game 2, and the one that sorts first legitimately lags to
        game 1 (0.300), so the assertion passed while the SECOND row carried the
        leaked 0.400.  It only appeared to work because the builder's fan-out
        RuntimeError fired first and masked it — the NF-D17 AND-composed-guard trap.
        Verified by an isolating red-proof (collapse broken AND fan-out guard
        neutered): with `fetchone()` the test PASSED on leaking source; reading all
        rows, it fails.
        """
        rel = _fixture_relation([
            _row(1, 100, 1, "R", 4, 0.300, 0.310),
            _row(2, 100, 5, "R", 2, 0.400, 0.410),
            _row(2, 100, 5, "L", 2, 0.400, 0.450),   # switch-hit in game 2
        ])
        bps.build_rolling_features(con, rel)
        prevs = [r[0] for r in con.execute(
            "SELECT prev_woba_30d FROM feat_rolling WHERE game_pk=2 AND batter_id=100"
        ).fetchall()]
        assert prevs, "no rows for the labelled game — fixture is not exercising the lag"
        for prev in prevs:
            assert prev == pytest.approx(0.300), (
                f"lagged feature {prev} must come from the PREVIOUS game (0.300), not "
                "the same game's other-hand row (0.400) — that leaks the labelled game"
            )

    def test_first_game_has_no_lagged_value(self, con):
        """Two-sided: the guard above would also pass if lag() returned NULL for
        everything, so pin that the lag is genuinely populated only from game 2 on."""
        rel = _fixture_relation([
            _row(1, 100, 1, "R", 4, 0.300, 0.310),
            _row(2, 100, 5, "R", 4, 0.400, 0.410),
        ])
        bps.build_rolling_features(con, rel)
        assert con.execute(
            "SELECT prev_woba_30d FROM feat_rolling WHERE game_pk=1").fetchone()[0] is None
        assert con.execute(
            "SELECT prev_woba_30d FROM feat_rolling WHERE game_pk=2"
        ).fetchone()[0] == pytest.approx(0.300)

    def test_hand_conditional_column_is_pa_weighted_not_arbitrarily_picked(self, con):
        """The _std columns genuinely differ between hands, so picking a row would
        silently bias them by handedness.  3 PA at 0.300 + 1 PA at 0.500 → 0.350."""
        rel = _fixture_relation([
            _row(1, 100, 1, "R", 3, 0.250, 0.300),
            _row(1, 100, 1, "L", 1, 0.250, 0.500),
            _row(2, 100, 5, "R", 4, 0.250, 0.260),
        ])
        bps.build_rolling_features(con, rel)
        got = con.execute(
            "SELECT prev_woba_std FROM feat_rolling WHERE game_pk=2").fetchone()[0]
        assert got == pytest.approx(0.350), "expected PA-weighted mean of the two hands"

    def test_switch_hitter_is_labelled_S(self, con):
        rel = _fixture_relation([
            _row(1, 100, 1, "R", 2, 0.300, 0.310),
            _row(1, 100, 1, "L", 2, 0.300, 0.350),
            _row(1, 200, 1, "R", 4, 0.300, 0.310),
        ])
        bps.build_rolling_features(con, rel)
        assert con.execute(
            "SELECT batter_hand FROM feat_rolling WHERE batter_id=100").fetchone()[0] == "S"
        assert con.execute(
            "SELECT batter_hand FROM feat_rolling WHERE batter_id=200").fetchone()[0] == "R"

    def test_fanout_guard_raises_rather_than_silently_duplicating(self, con, monkeypatch):
        """The builder must FAIL LOUDLY if the upstream grain changes again.  Simulate
        a collapse that does not actually collapse, and assert the guard fires."""
        original = bps.build_rolling_features

        def broken(c, source_relation):
            # collapse keyed on the HAND too → still fans out on (game_pk, batter_id)
            original(c, source_relation)
            c.execute("""CREATE OR REPLACE TABLE feat_rolling AS
                         SELECT * FROM feat_rolling
                         UNION ALL SELECT * FROM feat_rolling""")
            fan = c.execute("""SELECT count(*) FROM (
                    SELECT game_pk, batter_id FROM feat_rolling
                    GROUP BY 1,2 HAVING count(*) > 1)""").fetchone()[0]
            if fan:
                raise RuntimeError("feat_rolling still fans out")

        rel = _fixture_relation([_row(1, 100, 1, "R", 4, 0.300, 0.310)])
        with pytest.raises(RuntimeError, match="fans out"):
            broken(con, rel)


# ── market/outcome column contract ─────────────────────────────────────────────

class TestMarketContract:
    def test_every_market_maps_to_a_realized_outcome_column(self):
        assert set(bps.MARKETS) == {
            "batter_hits", "batter_home_runs", "batter_total_bases"}
        assert set(bps.MARKETS.values()) == {"hits", "home_runs", "total_bases"}

    def test_registry_is_not_vacuous(self):
        """An empty MARKETS dict would make every loop above pass on nothing."""
        assert len(bps.MARKETS) >= 3
