{{
    config(
        materialized='table'
    )
}}

-- Wide lineup model: one row per game × home/away side.
-- Batting order positions 1–9 are spread into named columns.
-- Rows with no lineup data (lineup not yet confirmed) are excluded.

with lineups as (
    select * from {{ ref('stg_statsapi_lineups') }}
),

pivoted as (
    select
        game_pk,
        official_date,
        home_away,

        -- Batting order slot 1
        max(case when batting_order = 1 then player_id end)                 as slot_1_player_id,
        max(case when batting_order = 1 then full_name end)                 as slot_1_full_name,
        max(case when batting_order = 1 then position_abbreviation end)     as slot_1_position,

        -- Batting order slot 2
        max(case when batting_order = 2 then player_id end)                 as slot_2_player_id,
        max(case when batting_order = 2 then full_name end)                 as slot_2_full_name,
        max(case when batting_order = 2 then position_abbreviation end)     as slot_2_position,

        -- Batting order slot 3
        max(case when batting_order = 3 then player_id end)                 as slot_3_player_id,
        max(case when batting_order = 3 then full_name end)                 as slot_3_full_name,
        max(case when batting_order = 3 then position_abbreviation end)     as slot_3_position,

        -- Batting order slot 4
        max(case when batting_order = 4 then player_id end)                 as slot_4_player_id,
        max(case when batting_order = 4 then full_name end)                 as slot_4_full_name,
        max(case when batting_order = 4 then position_abbreviation end)     as slot_4_position,

        -- Batting order slot 5
        max(case when batting_order = 5 then player_id end)                 as slot_5_player_id,
        max(case when batting_order = 5 then full_name end)                 as slot_5_full_name,
        max(case when batting_order = 5 then position_abbreviation end)     as slot_5_position,

        -- Batting order slot 6
        max(case when batting_order = 6 then player_id end)                 as slot_6_player_id,
        max(case when batting_order = 6 then full_name end)                 as slot_6_full_name,
        max(case when batting_order = 6 then position_abbreviation end)     as slot_6_position,

        -- Batting order slot 7
        max(case when batting_order = 7 then player_id end)                 as slot_7_player_id,
        max(case when batting_order = 7 then full_name end)                 as slot_7_full_name,
        max(case when batting_order = 7 then position_abbreviation end)     as slot_7_position,

        -- Batting order slot 8
        max(case when batting_order = 8 then player_id end)                 as slot_8_player_id,
        max(case when batting_order = 8 then full_name end)                 as slot_8_full_name,
        max(case when batting_order = 8 then position_abbreviation end)     as slot_8_position,

        -- Batting order slot 9
        max(case when batting_order = 9 then player_id end)                 as slot_9_player_id,
        max(case when batting_order = 9 then full_name end)                 as slot_9_full_name,
        max(case when batting_order = 9 then position_abbreviation end)     as slot_9_position

    from lineups
    group by game_pk, official_date, home_away
)

select *
from pivoted
where slot_1_player_id is not null
