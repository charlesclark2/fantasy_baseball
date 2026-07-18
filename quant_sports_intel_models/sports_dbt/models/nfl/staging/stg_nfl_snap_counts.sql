-- stg_nfl_snap_counts — player game-level snap usage (nflverse snap_counts), NFL-N0.2.
--
-- ⭐ the all-position usage feed NCAAF has no free equivalent for (`nfl_data_inventory.md` §4).
-- Typed Delta → plain renames. Keyed pfr_player_id + game_id (join snaps onto the player-week
-- fact via the schedules game-key rosetta). Offense/defense/ST snap counts + pct. 2012+.
select
    'nfl'                          as sport,
    game_id,
    pfr_game_id,
    season,
    game_type                      as season_type,
    week,
    player,
    pfr_player_id,
    position,
    team,
    opponent,
    offense_snaps,
    offense_pct,
    defense_snaps,
    defense_pct,
    st_snaps,
    st_pct
from {{ nfl_delta('snap_counts') }}
where pfr_player_id is not null
