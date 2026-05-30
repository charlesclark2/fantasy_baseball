{{ config(materialized='table') }}

-- Grain: game_pk
-- For each game, computes the expected wOBA advantage based on each lineup's batter
-- archetype composition facing the opposing starter's pitcher cluster (Card 7.K2).
--
-- Leakage guards:
--   - Starter pitcher cluster: prior-season assignment (pc.season = game_year - 1);
--     PK on pitcher_clusters is (pitcher_id, season) — one row per pair, no deduplication.
--   - Batter cluster assignments: game_year - 1 = season (prior-season batter archetype).
--   - Matchup mart lookup: game_date strictly before anchor game_date in
--     mart_batter_archetype_vs_pitcher_cluster.
--
-- Output columns (8 total, integrated into feature_pregame_game_features):
--   home_lineup_archetype_avg_woba        -- avg expected wOBA across home lineup slots
--   home_lineup_archetype_avg_xwoba
--   home_lineup_archetype_slot_coverage   -- how many of 9 slots had archetype matchup data
--   away_lineup_archetype_avg_woba
--   away_lineup_archetype_avg_xwoba
--   away_lineup_archetype_slot_coverage
--   home_batter_cluster_mode              -- most common batter archetype in home lineup
--   away_batter_cluster_mode
--
-- Availability: null before 2021 (cluster data begins 2020, prior-season lag).

with games as (
    select
        game_pk,
        game_date::date    as game_date,
        game_year::integer as game_year
    from {{ ref('mart_game_results') }}
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
        pc.cluster_label as pitcher_cluster_label
    from games g
    join starters s
        on  s.game_pk = g.game_pk
    left join {{ source('statsapi', 'pitcher_clusters') }} pc
        on  pc.pitcher_id = s.pitcher_id
        and pc.season     = g.game_year - 1
),

lineups as (
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

-- Map each lineup batter to their prior-season batter cluster (leakage guard: game_year - 1)
batter_cluster_joined as (
    select
        ls.game_pk,
        ls.side,
        ls.slot,
        ls.batter_id,
        bc.cluster_label as batter_cluster_label
    from lineup_slots ls
    join games g
        on  g.game_pk = ls.game_pk
    left join {{ source('statsapi', 'batter_clusters') }} bc
        on  bc.batter_id = ls.batter_id
        and bc.season    = g.game_year - 1
    where ls.batter_id is not null
),

-- For each lineup slot, identify the opposing starter's pitcher cluster
slot_opp_cluster as (
    select
        bcj.game_pk,
        bcj.side,
        bcj.slot,
        bcj.batter_id,
        bcj.batter_cluster_label,
        -- Each side's lineup faces the OPPOSING side's starter
        opp_sc.pitcher_cluster_label as opp_pitcher_cluster_label
    from batter_cluster_joined bcj
    left join starter_cluster opp_sc
        on  opp_sc.game_pk = bcj.game_pk
        and opp_sc.side    = case when bcj.side = 'home' then 'away' else 'home' end
),

-- Look up population-level adj_woba for (batter_cluster_label, opp_pitcher_cluster_label)
-- from mart_batter_archetype_vs_pitcher_cluster using most recent prior record.
slot_matchup_stats as (
    select
        soc.game_pk,
        soc.side,
        soc.slot,
        soc.batter_cluster_label,
        soc.opp_pitcher_cluster_label,
        bam.adj_woba,
        bam.adj_xwoba
    from slot_opp_cluster soc
    join games g
        on  g.game_pk = soc.game_pk
    left join {{ ref('mart_batter_archetype_vs_pitcher_cluster') }} bam
        on  bam.batter_cluster_label  = soc.batter_cluster_label
        and bam.pitcher_cluster_label = soc.opp_pitcher_cluster_label
        and bam.game_date             < g.game_date
    qualify row_number() over (
        partition by soc.game_pk, soc.side, soc.slot
        order by bam.game_date desc nulls last
    ) = 1
),

-- Aggregate across 9 slots per game × side
side_agg as (
    select
        game_pk,
        side,
        avg(adj_woba)                          as archetype_avg_woba,
        avg(adj_xwoba)                         as archetype_avg_xwoba,
        count(adj_woba)                        as archetype_slot_coverage
    from slot_matchup_stats
    group by game_pk, side
),

-- Most common batter archetype in each lineup (batter_cluster_mode)
cluster_mode_ranked as (
    select
        game_pk,
        side,
        batter_cluster_label,
        count(batter_cluster_label) as label_count
    from slot_matchup_stats
    where batter_cluster_label is not null
    group by game_pk, side, batter_cluster_label
    qualify row_number() over (
        partition by game_pk, side
        order by count(batter_cluster_label) desc
    ) = 1
),

home_agg as (select * from side_agg where side = 'home'),
away_agg as (select * from side_agg where side = 'away'),
home_mode as (select game_pk, batter_cluster_label as home_batter_cluster_mode from cluster_mode_ranked where side = 'home'),
away_mode as (select game_pk, batter_cluster_label as away_batter_cluster_mode from cluster_mode_ranked where side = 'away')

select
    g.game_pk,

    -- Home lineup archetype matchup signals
    h.archetype_avg_woba               as home_lineup_archetype_avg_woba,
    h.archetype_avg_xwoba              as home_lineup_archetype_avg_xwoba,
    h.archetype_slot_coverage          as home_lineup_archetype_slot_coverage,

    -- Away lineup archetype matchup signals
    a.archetype_avg_woba               as away_lineup_archetype_avg_woba,
    a.archetype_avg_xwoba              as away_lineup_archetype_avg_xwoba,
    a.archetype_slot_coverage          as away_lineup_archetype_slot_coverage,

    -- Dominant batter archetype in each lineup
    hm.home_batter_cluster_mode,
    am.away_batter_cluster_mode

from games g
left join home_agg h   on  h.game_pk = g.game_pk
left join away_agg a   on  a.game_pk = g.game_pk
left join home_mode hm on  hm.game_pk = g.game_pk
left join away_mode am on  am.game_pk = g.game_pk
