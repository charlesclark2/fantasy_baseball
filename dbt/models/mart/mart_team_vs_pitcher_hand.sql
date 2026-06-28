-- =============================================================================
-- mart_team_vs_pitcher_hand.sql
-- Grain: one row per batting team × opposing starter hand × game (game_pk).
--        Rolling windows are computed over 7/14/30-day and season-to-date spans.
-- Purpose: Team-level offensive production split by the opposing starting
--          pitcher's handedness. Provides a fast team-level platoon signal:
--          "against tonight's LHP/RHP starter, how has this team been hitting?"
-- Join keys: team, opp_starter_hand, game_date, game_pk
-- Source: stg_batter_pitches only. Runs scored is derived from the maximum
--         post-pitch batting-team score recorded across all PAs in the game.
-- =============================================================================
--
-- Starter identification: the opposing starting pitcher is the first pitcher
-- to appear (lowest at_bat_number, then pitch_number) for each pitching side
-- in the game. All PAs in the game count toward the batting team's metrics —
-- not only PAs against the starter — so the metrics reflect full-game offensive
-- context when the opposing starter was of a given handedness.
--
-- Rolling window semantics: windows are partitioned by (team, opp_starter_hand)
-- so that LHP-game and RHP-game windows are maintained separately. A 7-day
-- window covers only games against that starter type in the prior 7 days.
-- Season-to-date restarts at game_year = 1 using ROWS UNBOUNDED PRECEDING.

{{
    config(
        materialized = 'view',
        tags         = ['w3_lakehouse']
    )
}}

-- E11.1-W3: dual-branch lakehouse model. Upstream stg_batter_pitches is the W1
-- S3 parquet (registered as a view by run_w1_lakehouse.py); the Snowflake branch
-- is a thin view over the lakehouse_ext external table. game_date is cast to
-- ::date in plate_appearances so the RANGE-interval rolling windows operate on the
-- VARCHAR game_date the parquet carries.
--
-- ⚠️ ::numeric parity: the single-game `woba` / `xwoba` columns use a RESULT-cast
-- `(ratio)::numeric` which in Snowflake is scale-0 → those two columns are ZEROED
-- in the retired Snowflake build (a latent bare-::numeric bug; consumed by NOTHING
-- — feature_pregame_team_features + write_serving_store read only the _7d/_30d/_std
-- rolling columns, which carry no result-cast). The DuckDB branch reproduces that
-- exactly via ::numeric(38,0) so the migration is value-PRESERVING. The single-game
-- k_pct/bb_pct/slugging/hard_hit_pct/barrel_pct use a NUMERATOR-cast (int::numeric /
-- int) which is NOT zeroed in either engine, so those keep the bare ::numeric.

{% if target.name == 'duckdb' %}

with

pitches as (

    select * from stg_batter_pitches
    where game_type = 'R'
      and pitcher_hand in ('L', 'R')

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Identify the starting pitcher's hand for each pitching side per game.
--   home_starters: home team pitches in inning_half = 'Top'
--   away_starters: away team pitches in inning_half = 'Bot'
-- QUALIFY selects the first pitch seen for that side (= first PA of the game).
-- ─────────────────────────────────────────────────────────────────────────────
home_starters as (

    select
        game_pk,
        pitcher_hand as home_starter_hand
    from pitches
    where inning_half = 'Top'
    qualify row_number() over (
        partition by game_pk
        order by at_bat_number, pitch_number
    ) = 1

),

away_starters as (

    select
        game_pk,
        pitcher_hand as away_starter_hand
    from pitches
    where inning_half = 'Bot'
    qualify row_number() over (
        partition by game_pk
        order by at_bat_number, pitch_number
    ) = 1

),

-- One row per game with both sides' starter hands resolved
game_starters as (

    select
        hs.game_pk,
        hs.home_starter_hand,
        as_.away_starter_hand
    from home_starters hs
    left join away_starters as_
        on hs.game_pk = as_.game_pk

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Tag each terminal PA with the batting team and opposing starter's hand.
-- post_pitch_bat_score is retained to derive runs_scored at game level.
-- ─────────────────────────────────────────────────────────────────────────────
plate_appearances as (

    select
        p.game_pk,
        p.game_date::date as game_date,   -- VARCHAR (ISO) in parquet → DATE for RANGE windows [E11.1-W3]
        p.game_year,

        case
            when p.inning_half = 'Top' then p.away_team   -- away bats vs home starter
            else p.home_team                               -- home bats vs away starter
        end                                                     as batting_team,

        case
            when p.inning_half = 'Top' then gs.home_starter_hand
            else gs.away_starter_hand
        end                                                     as opp_starter_hand,

        p.woba_value,
        p.woba_denom,
        p.xwoba,

        (p.plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ))::boolean                                             as is_strikeout,

        (p.plate_appearance_event in (
            'walk', 'intent_walk'
        ))::boolean                                             as is_walk,

        case p.plate_appearance_event
            when 'single'   then 1
            when 'double'   then 2
            when 'triple'   then 3
            when 'home_run' then 4
            else 0
        end                                                     as total_bases,

        -- AT-bat excludes walks, HBP, sac flies, sac bunts
        (p.plate_appearance_event not in (
            'walk', 'intent_walk', 'hit_by_pitch',
            'sac_fly', 'sac_bunt', 'sac_fly_double_play'
        ) and p.plate_appearance_event is not null)::boolean    as is_at_bat,

        (p.exit_velocity_mph >= 95)::boolean                   as is_hard_hit,
        (p.launch_speed_angle_zone = 6)::boolean               as is_barrel,

        p.exit_velocity_mph,
        p.post_pitch_bat_score

    from pitches p
    inner join game_starters gs
        on p.game_pk = gs.game_pk
    where p.plate_appearance_event is not null
      and (
          case
              when p.inning_half = 'Top' then gs.home_starter_hand
              else gs.away_starter_hand
          end
      ) is not null   -- exclude games where the starter's hand can't be resolved

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Aggregate to game level: one row per team × opp_starter_hand × game
-- ─────────────────────────────────────────────────────────────────────────────
game_offense as (

    select
        game_pk,
        game_date,
        game_year,
        batting_team                                            as team,
        opp_starter_hand,

        count(*)                                                as pa_count,
        sum(woba_value)                                         as woba_value_sum,
        sum(woba_denom)                                         as woba_denom_sum,
        sum(xwoba)                                              as xwoba_sum,
        count(xwoba)                                            as xwoba_denom,
        sum(is_strikeout::integer)                              as strikeouts,
        sum(is_walk::integer)                                   as walks,
        sum(total_bases)                                        as total_bases,
        sum(is_at_bat::integer)                                 as at_bats,
        coalesce(sum(is_hard_hit::integer), 0)                  as hard_hit_balls,
        coalesce(sum(is_barrel::integer), 0)                    as barrels,
        count(case when exit_velocity_mph is not null
              then 1 end)                                       as batted_balls,
        -- Runs scored = batting team's final score for the game
        max(post_pitch_bat_score)                               as runs_scored

    from plate_appearances
    group by game_pk, game_date, game_year, batting_team, opp_starter_hand

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Rolling windows partitioned by (team, opp_starter_hand).
-- RANGE windows use date arithmetic; STD uses ROWS UNBOUNDED per season.
-- ─────────────────────────────────────────────────────────────────────────────
rolling as (

    select
        game_pk,
        game_date,
        game_year,
        team,
        opp_starter_hand,

        -- ── Single-game actuals ────────────────────────────────────────────────
        runs_scored,
        pa_count,
        strikeouts,
        walks,
        total_bases,
        at_bats,
        hard_hit_balls,
        barrels,
        batted_balls,
        round(
            case when woba_denom_sum  > 0
                 then (woba_value_sum  / woba_denom_sum)::numeric(38,0) else null end, 3
        )                                                       as woba,
        round(
            case when xwoba_denom     > 0
                 then (xwoba_sum      / xwoba_denom)::numeric(38,0)   else null end, 3
        )                                                       as xwoba,
        round(
            case when pa_count        > 0
                 then (strikeouts::numeric / pa_count)          else null end, 3
        )                                                       as k_pct,
        round(
            case when pa_count        > 0
                 then (walks::numeric / pa_count)               else null end, 3
        )                                                       as bb_pct,
        round(
            case when at_bats         > 0
                 then (total_bases::numeric / at_bats)          else null end, 3
        )                                                       as slugging,
        round(
            case when batted_balls    > 0
                 then (hard_hit_balls::numeric / batted_balls)  else null end, 3
        )                                                       as hard_hit_pct,
        round(
            case when batted_balls    > 0
                 then (barrels::numeric / batted_balls)         else null end, 3
        )                                                       as barrel_pct,

        -- ── Rolling 7-day ─────────────────────────────────────────────────────
        count(*) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row)  as games_7d,
        round(avg(runs_scored) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row), 3) as runs_per_game_7d,
        round(
            sum(woba_value_sum) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as woba_7d,
        round(
            sum(xwoba_sum) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as xwoba_7d,
        round(
            sum(strikeouts) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as k_pct_7d,
        round(
            sum(walks) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as bb_pct_7d,
        round(
            sum(total_bases) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as slugging_7d,
        round(
            sum(hard_hit_balls) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as hard_hit_pct_7d,
        round(
            sum(barrels) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, opp_starter_hand order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as barrel_pct_7d,

        -- ── Rolling 14-day ────────────────────────────────────────────────────
        count(*) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row) as games_14d,
        round(avg(runs_scored) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row), 3) as runs_per_game_14d,
        round(
            sum(woba_value_sum) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as woba_14d,
        round(
            sum(xwoba_sum) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as xwoba_14d,
        round(
            sum(strikeouts) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as k_pct_14d,
        round(
            sum(walks) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as bb_pct_14d,
        round(
            sum(total_bases) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as slugging_14d,
        round(
            sum(hard_hit_balls) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as hard_hit_pct_14d,
        round(
            sum(barrels) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, opp_starter_hand order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as barrel_pct_14d,

        -- ── Rolling 30-day ────────────────────────────────────────────────────
        count(*) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row) as games_30d,
        round(avg(runs_scored) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row), 3) as runs_per_game_30d,
        round(
            sum(woba_value_sum) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as woba_30d,
        round(
            sum(xwoba_sum) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as xwoba_30d,
        round(
            sum(strikeouts) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as k_pct_30d,
        round(
            sum(walks) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as bb_pct_30d,
        round(
            sum(total_bases) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as slugging_30d,
        round(
            sum(hard_hit_balls) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as hard_hit_pct_30d,
        round(
            sum(barrels) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, opp_starter_hand order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as barrel_pct_30d,

        -- ── Season-to-date ────────────────────────────────────────────────────
        count(*) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row) as games_std,
        round(avg(runs_scored) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row), 3) as runs_per_game_std,
        round(
            sum(woba_value_sum) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as woba_std,
        round(
            sum(xwoba_sum) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as xwoba_std,
        round(
            sum(strikeouts) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(pa_count) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as k_pct_std,
        round(
            sum(walks) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(pa_count) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as bb_pct_std,
        round(
            sum(total_bases) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(at_bats) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as slugging_std,
        round(
            sum(hard_hit_balls) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as hard_hit_pct_std,
        round(
            sum(barrels) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, opp_starter_hand, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as barrel_pct_std

    from game_offense

)

select * from rolling
order by team, opp_starter_hand, game_date

{% else %}

select * from baseball_data.lakehouse_ext.mart_team_vs_pitcher_hand

{% endif %}
