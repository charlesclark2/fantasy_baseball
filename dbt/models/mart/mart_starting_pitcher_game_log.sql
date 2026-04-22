{{
    config(
        materialized='table'
    )
}}

-- Starter definition: the pitcher who threw the first pitch for their team in
-- the game, AND who meets at least one of these thresholds:
--   • threw ≥ 20 pitches, OR
--   • appeared in ≥ 3 distinct innings
-- The thresholds distinguish true starters from openers used for one- or
-- two-batter platoon matchups before handing to a bulk reliever.

with pitches as (
    select *
    from {{ ref('stg_batter_pitches') }}
    where game_type = 'R'
),

pitches_tagged as (
    select
        *,
        -- Pitching team is the one in the field
        case when inning_half = 'Top' then home_team else away_team end as pitching_team,
        case when inning_half = 'Top' then away_team else home_team end as batting_team_tag
    from pitches
),

-- Identify which pitcher appeared first for each team in each game
game_first_pitcher as (
    select game_pk, pitching_team, pitcher_id as first_pitcher_id
    from (
        select
            game_pk,
            pitching_team,
            pitcher_id,
            row_number() over (
                partition by game_pk, pitching_team
                order by at_bat_number, pitch_number
            ) as pitch_seq
        from pitches_tagged
    )
    where pitch_seq = 1
),

-- Aggregate per-pitcher per-game stats
pitcher_game as (
    select
        p.game_pk,
        p.game_date,
        p.game_year,
        p.pitcher_id,
        p.pitching_team,
        p.batting_team_tag                                          as batting_team,
        p.home_team,
        p.away_team,
        p.pitching_team = p.home_team                               as is_home_team,

        count(*)                                                    as total_pitches,
        count(distinct p.at_bat_number)                             as batters_faced,

        -- Outs recorded drives innings pitched
        sum(case when p.plate_appearance_event in (
            'strikeout', 'strikeout_double_play',
            'field_out', 'force_out',
            'grounded_into_double_play', 'double_play', 'triple_play',
            'sac_fly', 'sac_fly_double_play',
            'sac_bunt', 'sac_bunt_double_play',
            'fielders_choice_out',
            'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
            'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
            'other_out'
        ) then 1 else 0 end)                                        as outs_recorded,

        sum(case when p.plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ) then 1 else 0 end)                                        as strikeouts,

        sum(case when p.plate_appearance_event in (
            'walk', 'intent_walk'
        ) then 1 else 0 end)                                        as walks,

        sum(case when p.plate_appearance_event = 'hit_by_pitch'
            then 1 else 0 end)                                      as hit_by_pitch,

        sum(case when p.plate_appearance_event = 'home_run'
            then 1 else 0 end)                                      as home_runs_allowed,

        sum(case when p.plate_appearance_event in (
            'single', 'double', 'triple', 'home_run'
        ) then 1 else 0 end)                                        as hits_allowed,

        -- xwOBA against: expected value for batted balls, actual wOBA value for
        -- non-contact events (strikeouts, walks) where xwOBA equals wOBA
        sum(case when p.woba_denom = 1
            then coalesce(p.xwoba, p.woba_value)
            else 0
        end)                                                        as xwoba_numerator,
        sum(p.woba_denom)                                           as xwoba_denom,

        -- Average fastball velocity: 4-seam (FF), sinker (SI), cutter (FC)
        avg(case when p.pitch_type in ('FF', 'SI', 'FC')
            then p.release_speed_mph
        end)                                                        as avg_fastball_velo,

        -- Used for starter threshold check; not surfaced as a final column
        count(distinct p.inning)                                    as distinct_innings_count

    from pitches_tagged p
    group by
        p.game_pk, p.game_date, p.game_year, p.pitcher_id,
        p.pitching_team, p.batting_team_tag, p.home_team, p.away_team
),

starters as (
    select pg.*
    from pitcher_game pg
    inner join game_first_pitcher gfp
        on  pg.game_pk       = gfp.game_pk
        and pg.pitching_team = gfp.pitching_team
        and pg.pitcher_id    = gfp.first_pitcher_id
    where
        pg.total_pitches      >= 20
        or pg.distinct_innings_count >= 3
)

select
    game_pk,
    game_date,
    game_year,
    pitcher_id,
    pitching_team,
    batting_team,
    home_team,
    away_team,
    is_home_team,

    total_pitches,
    batters_faced,
    outs_recorded,
    -- Traditional innings pitched format: 6 outs = 2.0, 7 outs = 2.1, 8 outs = 2.2
    floor(outs_recorded / 3) + (mod(outs_recorded, 3) * 0.1)       as innings_pitched,

    strikeouts,
    walks,
    hit_by_pitch,
    home_runs_allowed,
    hits_allowed,

    round(
        xwoba_numerator / nullif(xwoba_denom, 0),
        4
    )                                                               as xwoba_against,

    round(avg_fastball_velo, 1)                                     as avg_fastball_velo

from starters
