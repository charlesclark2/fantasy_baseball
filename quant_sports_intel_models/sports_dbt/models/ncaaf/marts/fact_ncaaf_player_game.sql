-- fact_ncaaf_player_game — the player-game fact (NCAAF-P1.1).
--
-- GRAIN: one row per (game_id, player_id). The long CFBD stat vocabulary
-- (stg_ncaaf_game_player_stats — 10 categories × 3–7 stat types) is PIVOTED here into the
-- modelled subset: passing / rushing / receiving / defensive / turnover lines.
--
-- ⭐ FBS-FILTERED (both sides FBS, via dim_ncaaf_game) + SPORT-TAGGED.
--
-- ⚠️ Only the ENUMERATED stat types are pivoted. Anything outside this set (CFBD's rare
-- `kicking.TOT`, future additions) stays reachable in the long staging table and is NOT silently
-- lost — that split is the whole reason staging stays long. If you need a new stat, add it here;
-- do not re-explode the raw JSON.
--
-- CFBD's wire format is strings, including the composite passing `C/ATT` ("27/39") which is split
-- into completions / pass_attempts. `try_cast` throughout: a non-numeric stat becomes NULL rather
-- than failing the build or, worse, coercing to 0.
--
-- ⚠️ The player's TEAM here is the name CFBD put on the box (there is no teamId on
-- /games/players). team_id is resolved through dim_ncaaf_team's SCD-2 season range — the
-- point-in-time lookup, so a 2021 row resolves to the 2021 conference, not today's.
--
-- ⚠️ POST-KICKOFF outcome fact — same rule as fact_ncaaf_team_game: never read into a pregame
-- row for the same game.
{{ config(materialized='table') }}

{# category → {stat_type: output column}. Composite C/ATT is handled separately below. #}
{% set pivots = {
    'passing':       {'YDS': 'passing_yards', 'TD': 'passing_tds', 'INT': 'interceptions_thrown',
                      'AVG': 'passing_yards_per_attempt', 'QBR': 'qbr'},
    'rushing':       {'CAR': 'rushing_attempts', 'YDS': 'rushing_yards', 'TD': 'rushing_tds',
                      'AVG': 'rushing_yards_per_carry', 'LONG': 'rushing_long'},
    'receiving':     {'REC': 'receptions', 'YDS': 'receiving_yards', 'TD': 'receiving_tds',
                      'AVG': 'receiving_yards_per_catch', 'LONG': 'receiving_long'},
    'defensive':     {'TOT': 'tackles_total', 'SOLO': 'tackles_solo', 'SACKS': 'sacks',
                      'TFL': 'tackles_for_loss', 'QB HUR': 'qb_hurries', 'PD': 'passes_defended',
                      'TD': 'defensive_tds'},
    'fumbles':       {'FUM': 'fumbles', 'LOST': 'fumbles_lost', 'REC': 'fumbles_recovered'},
    'interceptions': {'INT': 'interceptions_caught', 'YDS': 'interception_return_yards',
                      'TD': 'interception_return_tds'}
} %}

with games as (
    select game_id, season, week, season_order_week, season_type, game_date, home_team, away_team,
           home_conference, away_conference, is_neutral_site, is_conference_game, is_postseason
    from {{ ref('dim_ncaaf_game') }}
    where is_fbs_matchup            -- ⭐ the modelling universe
),

long as (
    select * from {{ ref('stg_ncaaf_game_player_stats') }}
),

teams as (
    select team_id, team, conference, valid_from_season, valid_to_season
    from {{ ref('dim_ncaaf_team') }}
),

pivoted as (
    select
        l.game_id,
        l.player_id,
        any_value(l.player_name)  as player_name,
        any_value(l.team)         as team,
        any_value(l.conference)   as conference,
        any_value(l.is_home)      as is_home,

        -- ── the enumerated numeric stat types ──────────────────────────────────────────
        {%- for category, types in pivots.items() %}
        {%- for stat_type, col in types.items() %}
        max(case when l.category = '{{ category }}' and l.stat_type = '{{ stat_type }}'
                 then try_cast(l.stat as double) end) as {{ col }},
        {%- endfor %}
        {%- endfor %}

        -- ── the composite passing line "C/ATT" → two columns ───────────────────────────
        max(case when l.category = 'passing' and l.stat_type = 'C/ATT'
                 then try_cast(split_part(l.stat, '/', 1) as integer) end) as completions,
        max(case when l.category = 'passing' and l.stat_type = 'C/ATT'
                 then try_cast(split_part(l.stat, '/', 2) as integer) end) as pass_attempts
    from long l
    group by 1, 2
)

select
    'ncaaf'                                              as sport,
    p.game_id,
    p.player_id,
    'ncaaf-' || p.game_id || '-' || p.player_id          as player_game_key,
    g.season,
    g.week,
    g.season_order_week,
    g.season_type,
    g.game_date,
    p.player_name,
    p.team,
    t.team_id,                                           -- point-in-time resolved (SCD-2 range)
    p.conference,
    p.is_home,
    case when p.is_home then g.away_team else g.home_team end as opponent_team,
    g.is_neutral_site,
    g.is_conference_game,
    g.is_postseason,

    -- ── the pivoted stat lines ────────────────────────────────────────────────────────
    p.completions,
    p.pass_attempts,
    {%- for category, types in pivots.items() %}
    {%- for stat_type, col in types.items() %}
    p.{{ col }},
    {%- endfor %}
    {%- endfor %}

    -- ── participation flags: which lines this player actually appeared on ─────────────
    (p.pass_attempts is not null)   as has_passing_line,
    (p.rushing_attempts is not null) as has_rushing_line,
    (p.receptions is not null)      as has_receiving_line,
    (p.tackles_total is not null)   as has_defensive_line
from pivoted p
join games g on g.game_id = p.game_id
left join teams t
    on t.team = p.team
   and g.season between t.valid_from_season and coalesce(t.valid_to_season, 9999)
