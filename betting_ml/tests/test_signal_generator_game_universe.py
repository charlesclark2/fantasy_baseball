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

Guard (offense/starter/starter_ip): source the `game_type='R'` filter from `stg_statsapi_games`,
never the lagging completed-only `mart_game_results`. These three read NO result column — their
universe is a SUPERSET of the gate's completed slate (offense's is lineup'd games), so they always
cover the gate's demand. That is still correct and pinned below.

`run_env` IS DIFFERENT and does the OPPOSITE (2026-07-24 reconciliation): it consumes realized
scores (`total_runs`) and MUST read `mart_game_results` — the EXACT table + completed-only filter
the signal_freshness gate anchors on (`max(game_date) from mart_game_results where game_type='R'
and home_final_score is not null`; coverage denominator = games in mart_game_results). INC-34 had
moved run_env to `stg_statsapi_games.home_score` for freshness, but that DE-SYNCED it from the gate:
the two "is this game Final + its runs" signals are INDEPENDENT pipelines (Statcast pitch data via
stg_batter_pitches vs the StatsAPI monthly_schedule capture) that can disagree at generator time —
on 2026-07-24 mart_game_results had the 7/23 finals while stg_statsapi_games.home_score lagged, so
run_env emitted 0/10 → BLOCKING HALT. Re-unifying run_env onto the gate's own source makes a false
HALT structurally impossible in EITHER lag direction. So the run_env guard below is INVERTED vs the
other three: run_env must read mart_game_results, they must not.
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


class TestRunEnvIsAlignedToTheGateSource:
    """run_env's guard is INVERTED vs offense/starter: it MUST read mart_game_results (the gate's
    own source), because it consumes realized total_runs and the gate demands exactly the games in
    mart_game_results (2026-07-24 reconciliation — see module docstring)."""

    def test_run_env_query_reads_mart_game_results(self):
        q = _score_query_run_env(RUN_ENV)
        assert "baseball_data.betting.mart_game_results" in _sql_code_only(q), (
            "run_env must source its game universe + total_runs from mart_game_results — the EXACT "
            "table the signal_freshness gate anchors on — or a false HALT is possible when the "
            "StatsAPI schedule pipeline and the Statcast-derived mart disagree on which games are "
            "Final (the 2026-07-24 0/10 run_env HALT)."
        )

    def test_run_env_does_not_read_stg_statsapi_games(self):
        # The whole point of the reconciliation: run_env must NOT source its universe from a
        # SEPARATE pipeline than the gate. stg_statsapi_games.home_score is that separate pipeline.
        assert "stg_statsapi_games" not in _sql_code_only(_score_query_run_env(RUN_ENV)), (
            "run_env regressed to stg_statsapi_games — re-de-syncs it from the gate (mart_game_results)."
        )

    def test_run_env_gets_total_runs_from_mart_finals_completed_only(self):
        q = _sql_code_only(_score_query_run_env(RUN_ENV))
        assert "home_final_score + g.away_final_score" in q or \
               "home_final_score+g.away_final_score" in q.replace(" ", ""), (
            "run_env total_runs must come from mart_game_results home_final_score+away_final_score."
        )
        assert "home_final_score is not null" in q.lower(), (
            "run_env must keep completed-only semantics via mart_game_results.home_final_score IS NOT "
            "NULL — the gate's exact completed-slate filter."
        )

    def test_run_env_filters_on_date_typed_game_date(self):
        # mart_game_results.game_date is a real DATE (cast ::date in the model) — NOT the INC-23
        # VARCHAR game_date on stg_statsapi_games — so a DATE range filter is binder-safe.
        q = _sql_code_only(_score_query_run_env(RUN_ENV))
        assert "g.game_date >= " in q and "g.game_date <= " in q


class TestPrecedent:
    def test_starter_ip_is_the_precedent(self):
        # starter_ip already joins stg_statsapi_games — the pattern the other three now match.
        assert "stg_statsapi_games" in STARTER_IP
