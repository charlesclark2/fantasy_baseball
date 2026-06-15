-- =============================================================================
-- assert_eb_starter_posteriors_covers_today.sql  —  Story 30.6 freshness guard
--
-- Fails (WARN) if any of TODAY's announced probable starters is MISSING from
-- eb_starter_posteriors. Catches the 2026-06-15 regression class where the
-- incremental watermark `game_date >= max(game_date) - 7` was poisoned by a few
-- far-future spine games (stg_statsapi_probable_pitchers carries marquee starters
-- announced months ahead) → max(game_date) ran to September → every incremental
-- run skipped today's slate → the table silently collapsed to 12 stray future
-- rows → home/away_starter_eb_xwoba_against served 100% NULL → live home_win
-- re-collapsed to a coinflip (undercutting Story 30.6's serving fix).
--
-- A non-empty result = the starter-EB serving block is (about to be) null for
-- today's bet. severity=warn surfaces it in build logs / Dagster without hard-
-- blocking the build (matches the source-scoped alert-only freshness pattern;
-- escalate to error, or attach a Dagster alert policy, for paging).
--
-- NOTE: runs only under `dbtf build` (not `dbtf run`), so on the current cadence
-- it gates the periodic full build. A higher-frequency check (Dagster freshness
-- sensor on eb_starter_posteriors vs today's probables) is the stronger follow-up.
-- =============================================================================
{{ config(severity='warn') }}

with todays_probables as (
    select distinct
        game_pk::varchar             as game_pk,
        probable_pitcher_id::varchar as pitcher_id
    from {{ ref('stg_statsapi_probable_pitchers') }}
    where probable_pitcher_id is not null
      and game_date::date = current_date()
)

select
    p.game_pk,
    p.pitcher_id
from todays_probables p
left join {{ ref('eb_starter_posteriors') }} e
    on  e.game_pk::varchar    = p.game_pk
    and e.pitcher_id::varchar = p.pitcher_id
where e.pitcher_id is null
