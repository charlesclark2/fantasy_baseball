"""test_signal_generator_game_universe.py — the 2026-07-21 signal_freshness HALT fix.

ROOT CAUSE: the offense (and starter) sub-model signal generators JOINed
`mart_game_results` — a COMPLETED-games mart whose S3 parquet lands a slate's rows only
after that slate finishes AND the mart is rebuilt — PURELY to filter `game_type = 'R'`.
Its lag behind `feature_pregame_lineup_features` (rows exist as soon as lineups are set)
raced the generator: a run during the lag dropped the newest completed slate, so offense
wrote 0 rows for it → `feature_pregame_sub_model_signals.pred_runs_mu_v2` NULL →
`check_signal_freshness` BLOCKING HALT (a false positive — the data was fine).

CURE: source the `game_type='R'` filter from `stg_statsapi_games` (one row per game_pk,
refreshed intraday, so it never lags for a scheduled/completed slate). The R game-set is
identical to `mart_game_results` for every completed slate (verified), and neither offense
nor starter reads any RESULT column — only `game_type`. `starter_ip` already does this.

Guard: these two generators must NOT regress to `mart_game_results` for the game universe.
`run_env` is intentionally EXEMPT — it genuinely consumes `home_final_score`/`away_final_score`
(`total_runs`), a real completed-games dependency, so it legitimately keeps `mart_game_results`.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OFFENSE = (REPO / "betting_ml" / "scripts" / "offense_v2" / "generate_offense_signals.py").read_text()
STARTER = (REPO / "betting_ml" / "scripts" / "starter_v1" / "generate_starter_signals.py").read_text()
STARTER_IP = (REPO / "betting_ml" / "scripts" / "starter_v1" / "generate_starter_ip_signals.py").read_text()
RUN_ENV = (REPO / "betting_ml" / "scripts" / "generate_run_env_signals.py").read_text()


def _score_query(src: str) -> str:
    """The generator's main feature query (the _SCORE_QUERY triple-quoted block)."""
    i = src.find("_SCORE_QUERY")
    assert i != -1, "no _SCORE_QUERY in generator"
    start = src.find('"""', i)
    end = src.find('"""', start + 3)
    return src[start:end]


class TestOffenseUsesFreshGameUniverse:
    def test_offense_joins_stg_not_mart_game_results(self):
        q = _score_query(OFFENSE)
        assert "stg_statsapi_games" in q, (
            "offense must source game_type='R' from stg_statsapi_games (intraday-fresh), not the "
            "lagging completed-only mart_game_results — the 2026-07-21 signal_freshness HALT race."
        )
        assert "JOIN baseball_data.betting.mart_game_results" not in q, (
            "offense regressed to JOINing mart_game_results — re-introduces the freshness-HALT race."
        )

    def test_offense_still_filters_regular_season(self):
        assert "game_type = 'R'" in _score_query(OFFENSE)


class TestStarterUsesFreshGameUniverse:
    def test_starter_joins_stg_not_mart_game_results(self):
        q = _score_query(STARTER)
        assert "stg_statsapi_games" in q
        assert "JOIN baseball_data.betting.mart_game_results" not in q, (
            "starter regressed to JOINing mart_game_results for the game_type filter — same race."
        )


class TestPrecedentAndExemption:
    def test_starter_ip_is_the_precedent(self):
        # starter_ip already joins stg_statsapi_games — the pattern offense/starter now match.
        assert "stg_statsapi_games" in STARTER_IP

    def test_run_env_keeps_mart_game_results_because_it_needs_results(self):
        # run_env legitimately consumes final scores (total_runs) — it is EXEMPT from the swap.
        assert "mart_game_results" in RUN_ENV
        assert "final_score" in RUN_ENV, (
            "run_env's mart_game_results dependency is only justified while it reads a result column; "
            "if final_score usage is gone, run_env should also move to stg_statsapi_games."
        )
