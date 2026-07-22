-- mart_nfl_clv_game_lines — the leakage-safe CLOSING game line + CLV scoreboard (NFL-N1.0).
--
-- ⭐ THE MARKET BENCHMARK for all three verticals. GRAIN: one row per (game_id, bookmaker, market,
--   side) — the CLOSING price/point each book offered, paired with the realized game outcome so
--   CLV and settlement are directly computable.
--
-- ⭐⭐ THE CLOSING LINE IS LEAKAGE-SAFE BY CONSTRUCTION. N0.4 captured each historical snapshot a
--   few minutes BEFORE kickoff, and this mart keeps ONLY rows with `snapshot_ts < commence_time`
--   (belt-and-suspenders, per N0.4), then takes the LATEST such snapshot per (event, book, market,
--   side) = the true closing line. `assert_nfl_clv_is_pre_kickoff` HALTs the build if any served
--   row's snapshot is at/after kickoff.
--
-- ⭐ THE ODDS↔SCHEDULE JOIN (the readiness-flagged cross-source join): the Odds feed keys on
--   (commence_time, full team names) and the schedule on game_id — DIFFERENT number spaces.
--   Bridged by (season, home_code, away_code) [names→codes via stg_nfl_team_geo] then disambiguated
--   to a single game by the SMALLEST kickoff-date gap — because a division pair can meet twice in a
--   season (a regular game + a playoff rematch at the same site: 65 such events measured on the real
--   lake). The rematch is months away, so nearest-date resolves it 1:1.
--
-- Coverage EXPECTED: game lines 2020–2024 (the N0.4 vendor floor). 25 books incl. Bovada
--   (reference_target_bookmaker). Realized outcome is NULL for an unplayed game (kept honest).
{{ config(materialized='table') }}

with odds as (
    select * from {{ ref('stg_nfl_historical_odds') }}
    where is_leakage_safe                                    -- snapshot_ts < commence_time
      and home_team is not null and away_team is not null    -- name→code resolved
),

-- the CLOSING line: latest leakage-safe snapshot per (event, book, market, side)
closing as (
    select
        event_id, season, commence_time, snapshot_ts,
        home_name, away_name, home_team, away_team,
        bookmaker, market,
        -- side: home / away for h2h & spreads, over / under for totals
        case when outcome_name = home_name then 'home'
             when outcome_name = away_name then 'away'
             when lower(outcome_name) = 'over'  then 'over'
             when lower(outcome_name) = 'under' then 'under'
             else lower(outcome_name) end                    as side,
        outcome_name,
        price,
        point
    from odds
    qualify row_number() over (
        partition by event_id, bookmaker, market,
            case when outcome_name = home_name then 'home'
                 when outcome_name = away_name then 'away'
                 when lower(outcome_name) = 'over'  then 'over'
                 when lower(outcome_name) = 'under' then 'under'
                 else lower(outcome_name) end
        order by snapshot_ts desc
    ) = 1
),

games as (
    select game_id, season, home_team, away_team, game_date, game_datetime,
           is_completed, home_score, away_score, home_margin, total_points, home_win
    from {{ ref('dim_nfl_game') }}
),

-- bridge odds → game_id on (season, codes), disambiguating a same-season rematch by nearest date.
-- odds commence_time is UTC; the ET kickoff date ≈ (commence − 5h)::date (kickoffs never cross the
-- ET midnight under a uniform −5h, and a rematch is months away so exactness is unnecessary).
bridged as (
    select
        c.*,
        g.game_id, g.game_date, g.is_completed, g.home_score, g.away_score,
        g.home_margin, g.total_points, g.home_win,
        row_number() over (
            partition by c.event_id, c.bookmaker, c.market, c.side
            order by abs(date_diff('day', (c.commence_time - interval 5 hour)::date, g.game_date::date))
        ) as game_match_rank
    from closing c
    left join games g
      on g.season = c.season and g.home_team = c.home_team and g.away_team = c.away_team
)

select
    'nfl'                                                    as sport,
    game_id,
    event_id,
    season,
    commence_time,
    snapshot_ts,
    date_diff('minute', snapshot_ts, commence_time)         as minutes_before_kickoff,
    home_team,
    away_team,
    bookmaker,
    (bookmaker = 'bovada')                                  as is_target_book,
    market,
    side,
    point                                                   as closing_point,
    price                                                   as closing_price,

    -- ── realized outcome (for CLV / settlement; NULL when unplayed) ──────────────────
    is_completed,
    home_score,
    away_score,
    home_margin,
    total_points,
    home_win
from bridged
where game_match_rank = 1
  and game_id is not null            -- keep only odds events that resolved to a scheduled game
