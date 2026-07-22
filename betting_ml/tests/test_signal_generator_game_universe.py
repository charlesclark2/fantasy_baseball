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

Guard: none of the four floor/blocking signal generators may regress to `mart_game_results`
for the game universe. `run_env` ALSO consumes realized scores (`total_runs`) but takes them
from `stg_statsapi_games.home_score + away_score` (EXACT parity with mart_game_results' finals,
populated the moment a game goes Final) with `home_score IS NOT NULL` to keep completed-only
semantics — so it is race-free too, without depending on the heavy daily --w5 mart rebuild.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OFFENSE = (REPO / "betting_ml" / "scripts" / "offense_v2" / "generate_offense_signals.py").read_text()
STARTER = (REPO / "betting_ml" / "scripts" / "starter_v1" / "generate_starter_signals.py").read_text()
STARTER_IP = (REPO / "betting_ml" / "scripts" / "starter_v1" / "generate_starter_ip_signals.py").read_text()
RUN_ENV = (REPO / "betting_ml" / "scripts" / "generate_run_env_signals.py").read_text()


def _triple_quoted_after(src: str, var: str) -> str:
    """The triple-quoted block assigned to `var` in the generator source."""
    i = src.find(var)
    assert i != -1, f"no {var} in generator"
    start = src.find('"""', i)
    end = src.find('"""', start + 3)
    return src[start:end]


def _score_query(src: str) -> str:
    """The offense/starter feature query (the _SCORE_QUERY block)."""
    return _triple_quoted_after(src, "_SCORE_QUERY")


def _score_query_run_env(src: str) -> str:
    """run_env's feature query (the _SIGNAL_QUERY_TEMPLATE block)."""
    return _triple_quoted_after(src, "_SIGNAL_QUERY_TEMPLATE")


def _sql_code_only(q: str) -> str:
    """Strip `--` SQL comments so a banned-table check can't trip on the prose that
    DOCUMENTS why the table was avoided (the E9.26 disclaimer-scan trap)."""
    return "\n".join(line.split("--", 1)[0] for line in q.splitlines())


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


class TestRunEnvUsesFreshGameUniverse:
    def test_run_env_query_uses_stg_not_mart_game_results(self):
        q = _score_query_run_env(RUN_ENV)
        assert "stg_statsapi_games" in q, (
            "run_env must source its game universe + total_runs from stg_statsapi_games (intraday-"
            "fresh) so it can't race the lagging --w5 mart_game_results rebuild (the blocking-floor "
            "recurrence of the 2026-07-21 HALT)."
        )
        assert "mart_game_results" not in _sql_code_only(q), (
            "run_env query regressed to mart_game_results (checked on comment-stripped SQL)."
        )

    def test_run_env_gets_total_runs_from_stg_scores_completed_only(self):
        q = _score_query_run_env(RUN_ENV)
        assert "home_score + g.away_score" in q or "home_score+g.away_score" in q.replace(" ", ""), (
            "run_env total_runs must come from stg_statsapi_games home_score+away_score (parity with "
            "mart_game_results finals)."
        )
        assert "home_score is not null" in q.lower(), (
            "run_env must keep completed-only semantics (home_score IS NOT NULL) — else it would emit "
            "rows for scheduled/postponed games mart_game_results excluded."
        )

    def test_run_env_filters_on_official_date_not_varchar_game_date(self):
        # official_date is a DATE; stg_statsapi_games.game_date is the INC-23 VARCHAR — filtering/
        # selecting the VARCHAR would reintroduce the year(VARCHAR) binder bite.
        q = _score_query_run_env(RUN_ENV)
        assert "g.official_date >= " in q and "g.official_date <= " in q


class TestPrecedent:
    def test_starter_ip_is_the_precedent(self):
        # starter_ip already joins stg_statsapi_games — the pattern the other three now match.
        assert "stg_statsapi_games" in STARTER_IP
