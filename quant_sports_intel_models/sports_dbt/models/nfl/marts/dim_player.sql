-- dim_player — the player ID/bio dimension (N0.3 port of jaffle `dim_player`).
--
-- One current row per player (latest season/week wins). The cross-ID rosetta (espn / sportradar
-- / yahoo / rotowire / pff / pfr / sleeper / gsis_it / smart) every fact joins to, plus bio. The
-- old Snowflake `md5_number_upper64` surrogate is replaced by an MD5 string key (DuckDB has no
-- md5_number_upper64) — value is opaque, only used as a stable player_surrogate_key. ⭐ sport-tag.
-- 🐛 GRAIN FIX (2026-07-24): the dedup previously partitioned by (player_id, player_name), so a
-- player whose NAME spelling drifts across roster weeks (Cedrick Wilson / Ced Wilson / … Jr.;
-- De'Von vs DeVon) survived as MULTIPLE rows → the `left join dim_player` in fct_player_week
-- fanned out ×N (83 players doubled/tripled every stat line → the "36-game season" corruption).
-- The dimension grain is one row PER player_id; partition on player_id ALONE, latest name wins.
with weekly_rosters as (
    select *
    from {{ ref('stg_nfl_weekly_rosters') }}
),
transformed as (
    select
        'nfl'                                         as sport,
        md5(concat(player_id::varchar, player_name::varchar)) as player_surrogate_key,
        player_id,
        player_name,
        height_inches,
        weight,
        college,
        birth_date,
        draft_club,
        draft_number,
        first_pro_year,
        rookie_year,
        upper(trim(espn_id))                          as espn_id,
        upper(trim(sportradar_id))                    as sportradar_id,
        upper(trim(yahoo_id))                         as yahoo_id,
        upper(trim(rotowire_id))                      as rotowire_id,
        upper(trim(pff_id))                           as pff_id,
        upper(trim(pfr_id))                           as pfr_id,
        upper(trim(fantasy_data_id))                  as fantasy_data_id,
        upper(trim(sleeper_id))                       as sleeper_id,
        upper(trim(esb_id))                           as esb_id,
        upper(trim(gsis_it_id))                       as gsis_it_id,
        upper(trim(smart_id))                         as smart_id
    from weekly_rosters
    qualify row_number() over (partition by player_id order by season desc, week desc) = 1
)
select *
from transformed
