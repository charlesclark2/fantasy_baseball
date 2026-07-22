-- stg_nfl_team_week — the team-week box line (NFL-N1.0), from nflverse stats_team_week (133 cols).
--
-- One row per (game_id, team) from that team's OFFENSIVE perspective, plus the team's own defensive
-- counting stats (def_*). Typed nflverse Parquet → plain renames. This is the conventional box line
-- (yards, first downs, turnovers, third-down-ish, penalties); the EPA/success/explosiveness signal
-- comes from stg_nfl_pbp, not here. fct_nfl_team_game joins the two on (game_id, team).
--
-- ⚠️ POST-KICKOFF outcome data — an OUTCOME staging table. The as-of rollups are the pregame path.
select
    'nfl'                                               as sport,
    game_id,
    season,
    week,
    season_type,
    {{ nfl_team_norm('team') }}                         as team,
    {{ nfl_team_norm('opponent_team') }}                as opponent_team,

    -- passing box
    completions,
    attempts                                            as pass_attempts,
    passing_yards,
    passing_tds,
    passing_interceptions,
    sacks_suffered,
    sack_yards_lost,
    passing_first_downs,
    passing_epa,
    passing_air_yards,
    passing_yards_after_catch,

    -- rushing box
    carries                                             as rush_attempts,
    rushing_yards,
    rushing_tds,
    rushing_first_downs,
    rushing_epa,

    -- derived team totals (defined once)
    (coalesce(passing_yards, 0) + coalesce(rushing_yards, 0))            as total_yards,
    (coalesce(passing_first_downs, 0) + coalesce(rushing_first_downs, 0)) as offensive_first_downs,
    -- giveaways: interceptions thrown + fumbles lost (offense turning the ball over)
    (coalesce(passing_interceptions, 0) + coalesce(fumbles_lost_total, 0)) as turnovers,
    fumbles_lost_total,

    -- discipline
    penalties,
    penalty_yards,
    timeouts,

    -- defensive counting stats (this team's defense)
    def_sacks,
    def_interceptions,
    def_tds,
    def_tackles_for_loss,
    def_fumbles_forced,
    def_pass_defended
from {{ nfl_delta('stats_team_week') }}
where game_id is not null
  and team is not null
