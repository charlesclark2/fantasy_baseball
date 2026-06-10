{{
    config(
        materialized='table'
    )
}}

-- Grain: one row per game_pk × team_abbrev (home and away).
-- Pre-game bullpen state for each team entering a given game.
-- Designed to be joined to feature_pregame_game_features on (game_pk + team side)
-- or used standalone by selecting the home/away row.
--
-- Column definitions:
--   bullpen_leverage_pitches_prev_1d   — bullpen pitch count in prior 1 calendar day
--   bullpen_leverage_pitches_prev_3d   — bullpen pitch count in prior 3 calendar days
--   high_leverage_arms_used_prev_2d    — 1/0: any reliever in inning 7+ in prior 2 days
--   closer_availability_proxy          — 1 = closer not used yesterday (rested); 0 = was used
--   bullpen_lhb_xwoba_against          — rolling 30d xwOBA against left-handed batters
--   bullpen_rhb_xwoba_against          — rolling 30d xwOBA against right-handed batters
--   bullpen_matchup_quality_vs_lineup  — xwOBA this bullpen is expected to allow given the
--                                        opposing lineup's actual LHB/RHB composition
--
-- Leakage guard: all rolling windows in source marts use an upper bound of 1 day
-- preceding. No current-game data leaks into any feature.
--
-- NULL handling: NULLs are preserved (not coalesced). Impute to 0.0 in
-- betting_ml/utils/preprocessing.py for workload/availability columns and to
-- league-average xwOBA for quality columns.

with

-- Spine: both teams per regular-season game
games as (

    select
        game_pk,
        game_date,
        game_year,
        home_team    as team_abbrev,
        'home'       as side,
        away_team    as opposing_team
    from {{ ref('mart_game_spine') }}   -- A1.11: completed + today's scheduled
    where game_type = 'R'

    union all

    select
        game_pk,
        game_date,
        game_year,
        away_team    as team_abbrev,
        'away'       as side,
        home_team    as opposing_team
    from {{ ref('mart_game_spine') }}   -- A1.11: completed + today's scheduled
    where game_type = 'R'

),

-- Opposing lineup handedness: home team's lineup
home_lineup as (

    select
        game_pk,
        coalesce(lhb_count, 0)                          as lhb_count,
        coalesce(rhb_count, 0)                          as rhb_count,
        coalesce(lhb_count, 0) + coalesce(rhb_count, 0) as total_batters
    from {{ ref('feature_pregame_lineup_features') }}
    where side = 'home'

),

-- Opposing lineup handedness: away team's lineup
away_lineup as (

    select
        game_pk,
        coalesce(lhb_count, 0)                          as lhb_count,
        coalesce(rhb_count, 0)                          as rhb_count,
        coalesce(lhb_count, 0) + coalesce(rhb_count, 0) as total_batters
    from {{ ref('feature_pregame_lineup_features') }}
    where side = 'away'

),

final as (

    select

        -- ── Identifiers ──────────────────────────────────────────────────────
        g.game_pk,
        g.game_date,
        g.game_year,
        g.team_abbrev,
        g.side,
        g.opposing_team,

        -- ── Workload and availability ────────────────────────────────────────
        -- "leverage" in column names reflects that these pitches occurred in
        -- meaningful game contexts, not just total pitch volume.
        bw.bullpen_pitches_prev_1d              as bullpen_leverage_pitches_prev_1d,
        bw.bullpen_pitches_prev_3d              as bullpen_leverage_pitches_prev_3d,
        bw.high_leverage_used_prev_2d           as high_leverage_arms_used_prev_2d,

        -- Closer availability proxy: 1 = closer rested (not used yesterday),
        -- 0 = closer was used yesterday. NULL when workload data unavailable.
        case
            when bw.closer_used_prev_1d is null then null
            else 1 - bw.closer_used_prev_1d
        end                                     as closer_availability_proxy,

        -- ── Handedness-split effectiveness ───────────────────────────────────
        hs.bp_xwoba_vs_lhb_30d                  as bullpen_lhb_xwoba_against,
        hs.bp_xwoba_vs_rhb_30d                  as bullpen_rhb_xwoba_against,

        -- ── Matchup-adjusted quality vs opposing lineup ───────────────────────
        -- This team's bullpen xwOBA weighted by the opposing lineup's actual
        -- LHB/RHB composition. Higher = more permissive bullpen for that lineup.
        -- NULL when handedness splits or lineup data are unavailable.
        case
            when hs.bp_xwoba_vs_rhb_30d is null
              or hs.bp_xwoba_vs_lhb_30d is null
            then null

            when g.side = 'home' then
                -- Home team pitching → batters are the away lineup
                case
                    when coalesce(aln.total_batters, 0) = 0 then null
                    else round(
                        hs.bp_xwoba_vs_rhb_30d
                            * (aln.rhb_count / aln.total_batters::float)
                        + hs.bp_xwoba_vs_lhb_30d
                            * (aln.lhb_count / aln.total_batters::float),
                        4
                    )
                end

            else
                -- Away team pitching → batters are the home lineup
                case
                    when coalesce(hln.total_batters, 0) = 0 then null
                    else round(
                        hs.bp_xwoba_vs_rhb_30d
                            * (hln.rhb_count / hln.total_batters::float)
                        + hs.bp_xwoba_vs_lhb_30d
                            * (hln.lhb_count / hln.total_batters::float),
                        4
                    )
                end

        end                                     as bullpen_matchup_quality_vs_lineup

    from games g

    left join {{ ref('mart_bullpen_workload') }} bw
        on  bw.pitching_team = g.team_abbrev
        and bw.game_pk       = g.game_pk

    left join {{ ref('mart_bullpen_handedness_splits') }} hs
        on  hs.team_abbrev = g.team_abbrev
        and hs.game_pk     = g.game_pk

    left join home_lineup hln
        on  hln.game_pk = g.game_pk

    left join away_lineup aln
        on  aln.game_pk = g.game_pk

)

select * from final
