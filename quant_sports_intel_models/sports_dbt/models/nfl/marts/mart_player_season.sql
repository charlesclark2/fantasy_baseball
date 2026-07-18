-- depends_on: {{ ref('fct_player_week') }}
--
-- mart_player_season — season rollup per player (N0.3 port of jaffle `mart_player_season`).
-- Per-game opportunity + efficiency means over played games, season totals, stability (SD), and
-- last-5 rolling form (the fantasy projection inputs). Snowflake `iff(cond, x, null)` → DuckDB
-- `case when cond then x end`; `count_if` is DuckDB-native. ⭐ sport-tagged.
with opportunity as (
    select * from {{ ref('mart_opportunity_player_week') }} where week > 0
),
efficiency as (
    select * from {{ ref('mart_efficiency_player_week') }} where week > 0
),
fact_player_week as (
    select
        season, week, player_id, team_id, position,
        fantasy_points_std, fantasy_points_ppr,
        the_league_fantasy_points, (played_flag and not is_bye) as played_game_flag
    from {{ ref('fct_player_week') }}
    where week > 0
),
joined as (
    select
        o.season,
        o.week,
        coalesce(o.player_name, e.player_name) as player_name,
        coalesce(o.player_id, e.player_id) as player_id,
        coalesce(o.team_id, e.team_id) as team_id,
        coalesce(o.position, e.position) as position,
        o.target_share,
        o.air_yards_share,
        o.weighted_opportunity_rating as wopr,
        o.carry_share,
        o.offense_pct,
        o.avg_intended_air_yards as wrte_adot,
        o.avg_separation as wrte_separation,
        o.avg_cushion as wrte_cushion,
        o.ngs_box_8plus_pct as rb_box_8plus_pct,
        o.dropback_share,
        e.completion_pct,
        e.yards_per_pass_attempt,
        e.passing_td_rate,
        e.expected_points_per_dropback,
        e.completion_percentage_above_expectation as cpoe,
        e.sack_rate,
        e.yards_per_carry,
        e.rush_touchdown_rate,
        e.expected_points_added_per_rush as epa_per_rush,
        e.rushing_yards_over_expected_per_attempt as ryoe_per_att,
        e.rush_efficiency as rb_path_efficiency,
        e.rec_catch_rate,
        e.yards_per_target,
        e.reception_touchdown_rate,
        e.rec_expected_points_added_per_target as epa_per_target,
        e.receiving_air_conversion_ratio as racr_proxy,
        e.avg_yards_after_catch_above_expectation as yac_oe,
        f.fantasy_points_std,
        f.fantasy_points_ppr,
        f.the_league_fantasy_points,
        f.played_game_flag
    from opportunity o
    full outer join efficiency e
        on e.season = o.season and e.week = o.week and e.player_id = o.player_id
    left join fact_player_week f
        on f.season = coalesce(o.season, e.season)
       and f.week = coalesce(o.week, e.week)
       and f.player_id = coalesce(o.player_id, e.player_id)
),
last_five as (
    select
        *,
        row_number() over (partition by player_id, season order by week) as rn,
        count_if(played_game_flag) over (partition by player_id, season) as played_games,
        avg(case when played_game_flag then target_share end) over (partition by player_id, season order by week rows between 4 preceding and current row) as ts_l5,
        avg(case when played_game_flag then carry_share  end) over (partition by player_id, season order by week rows between 4 preceding and current row) as cs_l5,
        avg(case when played_game_flag then wopr         end) over (partition by player_id, season order by week rows between 4 preceding and current row) as wopr_l5,
        avg(case when played_game_flag then offense_pct  end) over (partition by player_id, season order by week rows between 4 preceding and current row) as snap_pct_l5,
        avg(case when played_game_flag then cpoe         end) over (partition by player_id, season order by week rows between 4 preceding and current row) as cpoe_l5,
        avg(case when played_game_flag then ryoe_per_att end) over (partition by player_id, season order by week rows between 4 preceding and current row) as ryoe_pa_l5,
        avg(case when played_game_flag then yac_oe       end) over (partition by player_id, season order by week rows between 4 preceding and current row) as yac_oe_l5,
        avg(case when played_game_flag then fantasy_points_ppr end) over (partition by player_id, season order by week rows between 4 preceding and current row) as fp_ppr_l5
    from joined
),
agg as (
    select
        season,
        player_id,
        player_name,
        team_id     as team_id,
        position    as position,

        -- participation
        count_if(played_game_flag) as games_played,
        count(*)                    as rows_in_season,

        -- Per-game (over played games)
        avg(case when played_game_flag then fantasy_points_ppr end) as fp_ppr_pg,
        avg(case when played_game_flag then offense_pct       end) as offense_pct_pg,

        -- WR/TE opportunity per game
        avg(case when played_game_flag then target_share end) as target_share_pg,
        avg(case when played_game_flag then air_yards_share end) as air_yards_share_pg,
        avg(case when played_game_flag then wopr end)          as wopr_pg,
        avg(case when played_game_flag then wrte_adot end)     as wrte_adot_pg,

        -- RB opportunity per game
        avg(case when played_game_flag then carry_share end)       as carry_share_pg,
        avg(case when played_game_flag then rb_box_8plus_pct end)  as rb_box_8plus_pct_pg,

        -- QB opportunity per game
        avg(case when played_game_flag then dropback_share end)    as dropback_share_pg,

        -- Efficiency per game (rates averaged) — QB
        avg(case when played_game_flag then completion_pct end)         as completion_pct_pg,
        avg(case when played_game_flag then yards_per_pass_attempt end) as ypa_pg,
        avg(case when played_game_flag then passing_td_rate end)        as pass_td_rate_pg,
        avg(case when played_game_flag then expected_points_per_dropback end) as epa_per_dropback_pg,
        avg(case when played_game_flag then cpoe end)                   as cpoe_pg,
        avg(case when played_game_flag then sack_rate end)              as sack_rate_pg,

        -- RB
        avg(case when played_game_flag then yards_per_carry end)        as ypc_pg,
        avg(case when played_game_flag then rush_touchdown_rate end)    as rush_td_rate_pg,
        avg(case when played_game_flag then epa_per_rush end)           as epa_per_rush_pg,
        avg(case when played_game_flag then ryoe_per_att end)           as ryoe_pa_pg,
        avg(case when played_game_flag then rb_path_efficiency end)     as rb_path_efficiency_pg,

        -- WR/TE
        avg(case when played_game_flag then rec_catch_rate end)         as catch_rate_pg,
        avg(case when played_game_flag then yards_per_target end)       as ypt_pg,
        avg(case when played_game_flag then reception_touchdown_rate end) as rec_td_rate_pg,
        avg(case when played_game_flag then epa_per_target end)         as epa_per_target_pg,
        avg(case when played_game_flag then racr_proxy end)             as racr_pg,
        avg(case when played_game_flag then yac_oe end)                 as yac_oe_pg,

        -- Season totals
        sum(case when played_game_flag then fantasy_points_ppr else 0 end) as fp_ppr_total,

        -- Stability (variance)
        stddev_samp(case when played_game_flag then fantasy_points_ppr end) as fp_ppr_sd,

        -- Recent form (L5): last available rolling value in-season
        max(ts_l5)    as target_share_l5,
        max(cs_l5)    as carry_share_l5,
        max(wopr_l5)  as wopr_l5,
        max(snap_pct_l5) as snap_pct_l5,
        max(cpoe_l5)  as cpoe_l5,
        max(ryoe_pa_l5) as ryoe_pa_l5,
        max(yac_oe_l5)  as yac_oe_l5,
        max(fp_ppr_l5)  as fp_ppr_l5

    from last_five
    group by 1, 2, 3, 4, 5
)
select 'nfl' as sport, *
from agg
order by player_id, season
