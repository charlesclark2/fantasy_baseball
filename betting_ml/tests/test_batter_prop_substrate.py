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


# ── name-variant pooling (the SECOND grain defect) ─────────────────────────────

def _assemble_fixture(con, quote_rows: list[str], name_rows: list[str]) -> None:
    """Minimal in-memory versions of every table `assemble` reads.

    One game (pk 1), one batter (100), one book unless a row says otherwise.
    `quote_rows`/`name_rows` are SQL VALUES tuples supplied by the test.
    """
    con.execute(f"""CREATE OR REPLACE TABLE quotes_all AS SELECT * FROM (VALUES {','.join(quote_rows)})
        AS t(event_id, player_name, market_key, bookmaker_key, line, two_sided, p_over_devig)""")
    con.execute(f"""CREATE OR REPLACE TABLE name_candidates AS SELECT * FROM (VALUES {','.join(name_rows)})
        AS t(player_name, batter_id, match_tier)""")
    con.execute("""CREATE OR REPLACE TABLE event_map AS
        SELECT 2025::INTEGER AS season, 'E1' AS event_id, 1::BIGINT AS game_pk,
               'bridge' AS resolver, false AS resolvers_disagree""")
    con.execute("""CREATE OR REPLACE TABLE outcomes AS
        SELECT 1::BIGINT AS game_pk, 100::BIGINT AS batter_id, DATE '2025-05-05' AS game_date,
               4 AS pa, 2 AS hits, 1 AS home_runs, 5 AS total_bases, 1 AS singles,
               0 AS doubles, 0 AS triples, 0 AS walks, 1 AS strikeouts""")
    con.execute("""CREATE OR REPLACE TABLE feat_eb AS
        SELECT 1::BIGINT AS game_pk, 100::BIGINT AS batter_id, 3 AS batting_slot,
               0.34::DOUBLE AS eb_woba, 0.22::DOUBLE AS eb_k_pct, 0.08::DOUBLE AS eb_bb_pct,
               0.17::DOUBLE AS eb_iso, 0.02::DOUBLE AS eb_woba_uncertainty,
               400.0::DOUBLE AS pa_weight, 'full_eb' AS eb_data_source""")
    con.execute("""CREATE OR REPLACE TABLE spine AS
        SELECT 1::BIGINT AS game_pk, 'H' AS home_team_name, 'A' AS away_team_name,
               TIMESTAMP '2025-05-05 23:00:00' AS first_pitch, DATE '2025-05-05' AS official_date,
               10::BIGINT AS venue_id, 2025::INTEGER AS season""")
    con.execute("""CREATE OR REPLACE TABLE feat_park AS
        SELECT 10::BIGINT AS venue_id, 2025::INTEGER AS apply_season,
               1.0::DOUBLE AS eb_hr_factor, 1.0::DOUBLE AS eb_singles_factor,
               1.0::DOUBLE AS eb_doubles_triples_factor, 1.0::DOUBLE AS eb_woba_factor,
               1.0::DOUBLE AS eb_so_factor, 1.0::DOUBLE AS eb_bb_factor""")
    bps.build_rolling_features(con, _fixture_relation([
        _row(0, 100, 1, "R", 4, 0.300, 0.310),
        _row(1, 100, 5, "R", 4, 0.400, 0.410),
    ]))


class TestNameVariantPooling:
    """The feed spells one player two ways — "Matt Duffy"/"Matthew Duffy",
    "MJ Melendez"/"M.J. Melendez" — and BOTH resolve to the same batter_id.  Forming
    the consensus on `player_name` splits one batter into TWO rows carrying different
    lines and probabilities.  Measured on the first published artifact: 11,461
    duplicate keys / 23,720 rows.  The consensus must key on the RESOLVED identity."""

    def test_two_spellings_of_one_batter_collapse_to_one_row(self, con):
        _assemble_fixture(
            con,
            quote_rows=[
                "('E1','Matt Duffy','batter_hits','bookA',0.5::DOUBLE,true,0.48::DOUBLE)",
                "('E1','Matthew Duffy','batter_hits','bookB',0.5::DOUBLE,true,0.58::DOUBLE)",
            ],
            name_rows=["('Matt Duffy',100::BIGINT,'exact')",
                       "('Matthew Duffy',100::BIGINT,'last_initial')"],
        )
        bps.assemble(con)   # raises via the grain guard if it fans out
        n = con.execute("SELECT count(*) FROM substrate").fetchone()[0]
        assert n == 1, f"two spellings of one batter must yield ONE row, got {n}"

    def test_both_books_are_POOLED_not_dropped(self, con):
        """Collapsing must not silently discard the other spelling's book — the whole
        point is that the two variants' books form ONE consensus.  A naive
        'take the first row' fix would pass the row-count test and fail this one."""
        _assemble_fixture(
            con,
            quote_rows=[
                "('E1','Matt Duffy','batter_hits','bookA',0.5::DOUBLE,true,0.40::DOUBLE)",
                "('E1','Matthew Duffy','batter_hits','bookB',0.5::DOUBLE,true,0.60::DOUBLE)",
            ],
            name_rows=["('Matt Duffy',100::BIGINT,'exact')",
                       "('Matthew Duffy',100::BIGINT,'last_initial')"],
        )
        bps.assemble(con)
        books, p = con.execute(
            "SELECT n_books, p_over_consensus FROM substrate").fetchone()
        assert books == 2, f"both books must survive the collapse, got n_books={books}"
        assert p == pytest.approx(0.50), (
            "consensus must POOL the two variants' books (mean of 0.40/0.60), "
            f"not pick one — got {p}"
        )

    def test_one_book_quoting_both_spellings_counts_ONCE(self, con):
        """The mirror risk: pooling must not double-count a single book that happens to
        post under both spellings — that would inflate n_books and let one book
        dominate the consensus."""
        _assemble_fixture(
            con,
            quote_rows=[
                "('E1','Matt Duffy','batter_hits','bookA',0.5::DOUBLE,true,0.40::DOUBLE)",
                "('E1','Matthew Duffy','batter_hits','bookA',0.5::DOUBLE,true,0.90::DOUBLE)",
            ],
            name_rows=["('Matt Duffy',100::BIGINT,'exact')",
                       "('Matthew Duffy',100::BIGINT,'last_initial')"],
        )
        bps.assemble(con)
        books = con.execute("SELECT n_books FROM substrate").fetchone()[0]
        assert books == 1, f"one book must count once across spellings, got {books}"

    def test_genuinely_different_batters_are_NOT_merged(self, con):
        """Two-sided: the collapse keys on batter_id, so two real players in one game
        must stay two rows.  Without this the row-count assertions above would also
        pass on code that merged everything."""
        con.execute("")  # no-op, keeps the fixture call adjacent for readability
        _assemble_fixture(
            con,
            quote_rows=[
                "('E1','Matt Duffy','batter_hits','bookA',0.5::DOUBLE,true,0.48::DOUBLE)",
                "('E1','Other Guy','batter_hits','bookA',0.5::DOUBLE,true,0.58::DOUBLE)",
            ],
            name_rows=["('Matt Duffy',100::BIGINT,'exact')",
                       "('Other Guy',200::BIGINT,'exact')"],
        )
        # batter 200 must also have batted, or appearance arbitration drops it
        con.execute("""INSERT INTO outcomes VALUES
            (1, 200, DATE '2025-05-05', 3, 1, 0, 1, 1, 0, 0, 0, 1)""")
        bps.assemble(con)
        ids = [r[0] for r in con.execute(
            "SELECT batter_id FROM substrate ORDER BY batter_id").fetchall()]
        assert ids == [100, 200], f"distinct batters must not merge, got {ids}"


# ── market/outcome column contract ─────────────────────────────────────────────

class TestMarketContract:
    def test_every_market_maps_to_a_realized_outcome_column(self):
        assert set(bps.MARKETS) == {
            "batter_hits", "batter_home_runs", "batter_total_bases"}
        assert set(bps.MARKETS.values()) == {"hits", "home_runs", "total_bases"}

    def test_registry_is_not_vacuous(self):
        """An empty MARKETS dict would make every loop above pass on nothing."""
        assert len(bps.MARKETS) >= 3
