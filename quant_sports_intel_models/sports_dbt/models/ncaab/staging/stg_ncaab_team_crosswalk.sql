-- stg_ncaab_team_crosswalk — the D-I team universe with conference NAMES and external keys.
--
-- The per-game feed carries conference only as a numeric ESPN id; this is where those ids get
-- names. It also carries `kp_*` / `bart_*` — ready join keys to KenPom and Bart Torvik — which
-- is why NCAAB does not need to buy an efficiency source to keep that door open.
--
-- ⚠️ CURRENT SEASON ONLY upstream (one published file, no history). So this resolves names for
-- the latest season and the id→name map is applied across history in dim_ncaab_conference;
-- ids are stable, names are not, and conflating the two is how a 2015 Big East game ends up
-- labelled with a 2027 conference name.
select
    'ncaab'                             as sport,
    season::int                         as season,
    espn_team_id::bigint                as team_id,
    espn_display_name                   as team,
    espn_location                       as team_location,
    espn_mascot                         as team_mascot,
    espn_abbreviation                   as team_abbreviation,
    espn_conference                     as conference_name,
    kp_team                             as kenpom_team,
    kp_conf                             as kenpom_conference,
    bart_team                           as torvik_team,
    bart_conf                           as torvik_conference,
    capture_timestamp
from {{ ncaab_delta('team_crosswalk') }}
where espn_team_id is not null
