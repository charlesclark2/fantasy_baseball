-- stg_ncaab_schedule — the NCAAB game spine (NCAAB-P0).
--
-- hoopR lands TYPED parquet (not CFBD-style raw_json), so this staging layer SELECTS and
-- renames rather than flattening JSON. Materialized as a TABLE, not a view: the raw tier is
-- Delta and DuckDB's delta extension cannot serialize a DeltaScan inside a complex plan, so a
-- mart joining several staging views over delta_scan fails with "DeltaScan serialization not
-- implemented" (the NCAAF-P1.1 / NFL-N0.3 cure, inherited rather than rediscovered).
--
-- ⭐ `capture_timestamp` is carried through deliberately. hoopR overwrites the current season's
-- file in place and publishes no as-of, so OUR capture stamp is the only vintage that exists;
-- dropping it here would discard the point-in-time property the ingest exists to create.
select
    'ncaab'                                         as sport,
    game_id::bigint                                 as game_id,
    season::int                                     as season,
    season_type::int                                as season_type,
    game_date::date                                 as game_date,
    game_date_time                                  as game_datetime_raw,
    coalesce(neutral_site, false)                   as neutral_site,
    coalesce(conference_competition, false)         as conference_game,
    coalesce(status_type_completed, false)          as completed,
    home_id::bigint                                 as home_team_id,
    home_display_name                               as home_team,
    home_conference_id::int                         as home_conference_id,
    home_score::int                                 as home_score,
    coalesce(home_winner, false)                    as home_winner,
    away_id::bigint                                 as away_team_id,
    away_display_name                               as away_team,
    away_conference_id::int                         as away_conference_id,
    away_score::int                                 as away_score,
    venue_id::bigint                                as venue_id,
    venue_full_name                                 as venue_name,
    attendance::int                                 as attendance,
    tournament_id::int                              as tournament_id,
    -- ⚠️ `neutral_site` is identically FALSE for every season before 2008 in the source — an
    -- ABSENCE, not "no neutral games were played". Exposed as an explicit trust flag so a
    -- training window reaching that far back cannot silently read missing as False
    -- (the per-column-absence lesson: "missing" and "never existed" are different findings).
    (season >= 2008)                                as neutral_site_is_trustworthy,
    -- Both sides carrying a D-I conference id is the modelling universe. coalesce → FALSE:
    -- an UNKNOWN side is not D-I, and a NULL flag would propagate three-valued logic into
    -- every downstream `where is_di_matchup`.
    coalesce(home_conference_id is not null
             and away_conference_id is not null, false) as is_di_matchup,
    capture_timestamp,
    source_url
from {{ ncaab_delta('schedules') }}
where game_id is not null
