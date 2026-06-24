"""E9.27 — regression guard: book-odds serving query must not expose post-game-start prices.

Root cause: _BOOK_ODDS_BATCH selects MAX(ingestion_ts) with no filter on game start.
The odds-capture cron keeps ingesting after first pitch, so the 'latest complete snapshot'
becomes a post-start price and is displayed in the Book Comparison — un-bettable to users.

Fix: the bridge CTE left-joins stg_statsapi_games to get game_start_ts and the all_odds
CTE filters ingestion_ts < game_start_ts, so only pre-game snapshots survive.

These tests parse the SQL as text (no Snowflake / no package import required).
"""
from __future__ import annotations

import re
from pathlib import Path

_SERVING_SRC = (Path(__file__).resolve().parents[2] / "scripts" / "write_serving_store.py").read_text()


def _extract_sql(src: str, var_name: str) -> str:
    """Pull the triple-quoted string assigned to var_name."""
    pattern = rf'{re.escape(var_name)}\s*=\s*"""(.*?)"""'
    m = re.search(pattern, src, re.DOTALL)
    assert m, f"{var_name} not found in write_serving_store.py"
    return m.group(1)


class TestBookOddsLeakageGuard:
    def test_bridge_cte_joins_statsapi_for_game_start(self):
        sql = _extract_sql(_SERVING_SRC, "_BOOK_ODDS_BATCH")
        assert "stg_statsapi_games" in sql, (
            "_BOOK_ODDS_BATCH must join stg_statsapi_games to obtain game_start_ts "
            "for the pre-game-start leakage guard (E9.27)."
        )

    def test_all_odds_filters_to_pre_game_start(self):
        sql = _extract_sql(_SERVING_SRC, "_BOOK_ODDS_BATCH")
        assert "game_start_ts" in sql, (
            "_BOOK_ODDS_BATCH missing game_start_ts — the pre-game leakage guard is absent."
        )
        # Guard must be inside the WHERE clause that filters mart_odds_outcomes rows.
        assert "ingestion_ts < b.game_start_ts" in sql, (
            "_BOOK_ODDS_BATCH has game_start_ts but does not filter "
            "'ingestion_ts < b.game_start_ts'. Post-game-start odds will leak through."
        )

    def test_bovada_batch_still_has_pre_game_guard(self):
        """Regression: the existing _BOVADA_BATCH guard must not have been removed."""
        sql = _extract_sql(_SERVING_SRC, "_BOVADA_BATCH")
        assert "ingestion_ts" in sql and "game_date" in sql, (
            "_BOVADA_BATCH has lost its pre-game leakage guard "
            "(ingestion_ts < game_date::TIMESTAMP_NTZ)."
        )
        assert "game_date::TIMESTAMP_NTZ" in sql, (
            "_BOVADA_BATCH guard changed — verify the timestamp cast is still correct."
        )
