"""Guards the daily forward props cron's market scoping (E5.1b).

`backfill_multisport_props_to_s3.py --player-props-only` keys the daily catch-up
off `_filter_player_props`. If a derivative/spread key ever leaked through that
filter the cron would silently multiply its credit burn, so we pin:
  - only batter_*/pitcher_*/player_* survive (derivatives/spreads are dropped),
  - input order is preserved,
  - the MLB canonical set resolves to exactly the 8 player props we capture,
    including the 3 batter markets added 2026-06-30.
Pure, no IO — stays in the fast gate.
"""

import scripts.backfill_multisport_props_to_s3 as bf


def test_filter_keeps_only_player_props_and_preserves_order():
    markets = [
        "pitcher_strikeouts",
        "h2h_1st_5_innings",      # derivative — drop
        "batter_runs_scored",
        "spreads",                # game-level — drop
        "player_points",
        "alternate_totals_1st_5_innings",  # derivative — drop
    ]
    assert bf._filter_player_props(markets) == [
        "pitcher_strikeouts",
        "batter_runs_scored",
        "player_points",
    ]


def test_no_derivative_or_spread_key_survives():
    derivative_keys = [
        "spreads",
        "alternate_spreads",
        "team_totals",
        "alternate_team_totals",
        "h2h_1st_5_innings",
        "totals_1st_1_innings",
        "spreads_1st_5_innings",
    ]
    assert bf._filter_player_props(derivative_keys) == []


def test_mlb_canonical_set_is_the_eight_player_props():
    resolved = bf._filter_player_props(bf.SPORTS_CONFIG["baseball_mlb"]["markets"])
    assert set(resolved) == {
        "pitcher_strikeouts",
        "pitcher_outs",
        "batter_total_bases",
        "batter_hits",
        "batter_home_runs",
        "batter_runs_scored",
        "batter_rbis",
        "batter_hits_runs_rbis",
    }
    # single-region us cost driver the cron budgets against
    assert bf._credits_per_event(resolved, ["us"]) == 80
