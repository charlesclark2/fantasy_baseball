-- stg_nfl_weekly_rosters — per-week roster (N0.3 port of jaffle `stg_weekly_rosters`).
--
-- Feeds dim_player (the ID/bio dimension) + dim_player_role (the SCD-2 role). Lake asset:
-- `weekly_rosters`. ⚠️ nflverse column-drift vs the old Snowflake table: the key is `gsis_id`
-- (not `player_id`), the name lives in `full_name` (not `player_name`), and there is NO `age`
-- column → age is derived from birth_date (season − birth-year). `jersey_number`/`draft_number`
-- are VARCHAR-PINNED (N0.2 flag) — passed through as-is (no numeric use downstream).
-- Typed Delta → plain renames. ⭐ sport-tagged.
select
    'nfl'                                             as sport,
    trim(gsis_id)                                     as player_id,
    season,
    week,
    case when full_name is null then trim(concat(first_name, ' ', last_name)) else trim(full_name) end as player_name,
    case
        when team in ('ARI', 'ARZ') then 'ARI'
        when team in ('CLE', 'CLV') then 'CLE'
        when team in ('HOU', 'HST') then 'HOU'
        when team in ('LA', 'SL')   then 'LAR'
        when team in ('SD', 'LAC')  then 'LAC'
        when team in ('OAK', 'LV')  then 'LV'
        when team in ('BAL', 'BLT') then 'BAL'
        else team
    end                                               as team,
    position,
    depth_chart_position,
    jersey_number,                                    -- VARCHAR-pinned (N0.2)
    status,
    status_description_abbr,
    height                                            as height_inches,
    weight,
    college,
    years_exp,
    ngs_position                                      as next_gen_stats_position,
    entry_year                                        as first_pro_year,
    rookie_year,
    draft_club,
    draft_number,                                     -- VARCHAR-pinned (N0.2)
    -- old table carried `age`; the lake `weekly_rosters` does not → derive it season-relative
    (season - year(birth_date))                       as age,
    birth_date,
    espn_id,
    sportradar_id,
    yahoo_id,
    rotowire_id,
    pff_id,
    pfr_id,
    fantasy_data_id,
    sleeper_id,
    esb_id,
    gsis_it_id,
    smart_id
from {{ nfl_delta('weekly_rosters') }}
where position in ('FB', 'K', 'QB', 'RB', 'TE', 'WR')
  and game_type ilike 'reg'
  and gsis_id is not null
