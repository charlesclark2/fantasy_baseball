{{ config(materialized='table') }}

-- Grain: game_pk × side (home / away)
-- Aggregates mart_batter_woba_vs_cluster across lineup slots given the
-- scheduled starter's cluster for each side.
--
-- Leakage guard:
--   - Pitcher cluster joined on prior-season assignment (pc.season = game_year - 1).
--     PK on pitcher_clusters is (pitcher_id, season) — one row per pair, no deduplication.
--   - Batter wOBA stats come from mart_batter_woba_vs_cluster which itself
--     enforces a game_date < anchor_date strict-prior window.
--
-- Availability: cluster data begins 2015; effective coverage begins for games in 2016+
-- (prior-season lag: game_year - 1 = 2015 is the minimum season in pitcher_clusters).

with games as (
    select
        game_pk,
        game_date::date    as game_date,
        game_year::integer as game_year
    -- A2.4: spine on mart_game_spine (completed + today's scheduled games) instead of
    -- completed-only mart_game_results, so lineup-vs-cluster matchups exist for today's
    -- slate once lineups post. Downstream leakage guards stay game_date < anchor_date.
    from {{ ref('mart_game_spine') }}
    where game_type = 'R'
),

-- Probable starters per side
starters as (
    select
        game_pk,
        side,
        probable_pitcher_id as pitcher_id
    from {{ ref('stg_statsapi_probable_pitchers') }}
    where probable_pitcher_id is not null
),

-- Prior-season pitcher cluster (no leakage): season = game_year - 1.
-- PK is (pitcher_id, season) — one row per pair, no deduplication needed.
starter_cluster as (
    select
        g.game_pk,
        s.side,
        s.pitcher_id,
        pc.cluster_id
    from games g
    join starters s
        on  s.game_pk = g.game_pk
    left join {{ source('lakehouse_clusters', 'pitcher_clusters') }} pc
        on  pc.pitcher_id = s.pitcher_id
        and pc.season     = g.game_year - 1
),

lineups as (
    -- SCD-2 lineup state (2026+): most-recent confirmed lineup per game-side.
    -- INC-17 P2: 2026 games are not in stg_statsapi_lineups_wide; without this
    -- source all slot_*_player_id are NULL → cluster matchup is null → model sees
    -- imputed constants and loses all lineup-gated discrimination.
    select
        game_pk,
        home_away,
        slot_1_player_id,
        slot_2_player_id,
        slot_3_player_id,
        slot_4_player_id,
        slot_5_player_id,
        slot_6_player_id,
        slot_7_player_id,
        slot_8_player_id,
        slot_9_player_id
    from {{ source('betting_features', 'feature_pregame_lineup_state') }}
    where is_current = true
    qualify row_number() over (partition by game_pk, home_away order by valid_from desc) = 1

    union all

    -- Historical lineups (2015–2025): confirmed post-game lineups not covered by
    -- the SCD-2 state above.
    select
        game_pk,
        home_away,
        slot_1_player_id,
        slot_2_player_id,
        slot_3_player_id,
        slot_4_player_id,
        slot_5_player_id,
        slot_6_player_id,
        slot_7_player_id,
        slot_8_player_id,
        slot_9_player_id
    from {{ ref('stg_statsapi_lineups_wide') }}
    where game_pk not in (
        select distinct game_pk
        from {{ source('betting_features', 'feature_pregame_lineup_state') }}
        where is_current = true
    )
),

-- Unpivot lineup slots: one row per game_pk × side × slot × batter_id
lineup_slots as (
    select game_pk, home_away as side, 1 as slot, slot_1_player_id as batter_id from lineups
    union all
    select game_pk, home_away, 2, slot_2_player_id from lineups
    union all
    select game_pk, home_away, 3, slot_3_player_id from lineups
    union all
    select game_pk, home_away, 4, slot_4_player_id from lineups
    union all
    select game_pk, home_away, 5, slot_5_player_id from lineups
    union all
    select game_pk, home_away, 6, slot_6_player_id from lineups
    union all
    select game_pk, home_away, 7, slot_7_player_id from lineups
    union all
    select game_pk, home_away, 8, slot_8_player_id from lineups
    union all
    select game_pk, home_away, 9, slot_9_player_id from lineups
),

-- Map each lineup batter to the opposing starter's cluster
slot_with_cluster as (
    select
        ls.game_pk,
        ls.side,
        ls.slot,
        ls.batter_id,
        -- Each side's lineup faces the OPPOSING side's starter
        case when ls.side = 'home' then 'away' else 'home' end as opp_side
    from lineup_slots ls
    where ls.batter_id is not null
),

slot_opp_cluster as (
    select
        sc.game_pk,
        sc.side,
        sc.slot,
        sc.batter_id,
        opp_sc.cluster_id as opp_starter_cluster_id
    from slot_with_cluster sc
    left join starter_cluster opp_sc
        on  opp_sc.game_pk = sc.game_pk
        and opp_sc.side    = sc.opp_side
),

-- Join each batter to their career-cumulative wOBA vs. the opposing starter's cluster.
-- LEFT JOIN on game_date < game_date picks all prior records; QUALIFY keeps the most recent.
-- Handles off-days correctly without requiring an exact date match.
slot_cluster_stats as (
    select
        soc.game_pk,
        soc.side,
        soc.slot,
        soc.batter_id,
        soc.opp_starter_cluster_id,
        bwc.adj_woba,
        bwc.adj_xwoba,
        bwc.pa_count
    from slot_opp_cluster soc
    join games g
        on  g.game_pk = soc.game_pk
    left join {{ ref('mart_batter_woba_vs_cluster') }} bwc
        on  bwc.batter_id  = soc.batter_id
        and bwc.cluster_id = soc.opp_starter_cluster_id
        and bwc.game_date  < g.game_date
    qualify row_number() over (
        partition by soc.game_pk, soc.side, soc.slot
        order by bwc.game_date desc nulls last
    ) = 1
),

-- Aggregate across 9 slots per game × side
cluster_agg as (
    select
        game_pk,
        side,
        avg(adj_woba)                 as avg_woba_vs_cluster,
        avg(adj_xwoba)                as avg_xwoba_vs_cluster,
        count(adj_woba)               as slot_coverage
    from slot_cluster_stats
    group by game_pk, side
),

-- Combine home and away sides into one game row
home_agg as (
    select * from cluster_agg where side = 'home'
),
away_agg as (
    select * from cluster_agg where side = 'away'
),

home_starter_cl as (
    select game_pk, cluster_id as home_starter_cluster_id
    from starter_cluster where side = 'home'
),
away_starter_cl as (
    select game_pk, cluster_id as away_starter_cluster_id
    from starter_cluster where side = 'away'
)

select
    g.game_pk,

    -- Home lineup vs. away starter's cluster
    h_agg.avg_woba_vs_cluster         as home_lineup_avg_woba_vs_cluster,
    h_agg.avg_xwoba_vs_cluster        as home_lineup_avg_xwoba_vs_cluster,
    h_agg.slot_coverage               as home_lineup_cluster_slot_coverage,

    -- Away lineup vs. home starter's cluster
    a_agg.avg_woba_vs_cluster         as away_lineup_avg_woba_vs_cluster,
    a_agg.avg_xwoba_vs_cluster        as away_lineup_avg_xwoba_vs_cluster,
    a_agg.slot_coverage               as away_lineup_cluster_slot_coverage,

    -- Starter cluster IDs (from prior season, for downstream filtering)
    h_sc.home_starter_cluster_id,
    a_sc.away_starter_cluster_id

from games g
left join home_agg h_agg      on  h_agg.game_pk = g.game_pk
left join away_agg a_agg      on  a_agg.game_pk = g.game_pk
left join home_starter_cl h_sc on  h_sc.game_pk = g.game_pk
left join away_starter_cl a_sc on  a_sc.game_pk = g.game_pk
