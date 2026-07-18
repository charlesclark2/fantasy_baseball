-- stg_nfl_players — the NFL player ID universe (nflverse players), NFL-N0.2.
--
-- The dimension every fact joins to, and the cross-ID rosetta (gsis / esb / pfr / pff / espn /
-- otc / smart / nfl_id). NOT season-grained (landed under season=0). Typed Delta → plain
-- renames. ⚠️ N0.1 §1 column-drift: `players` uses rookie_season / draft_year / draft_round /
-- draft_pick (the `rosters` table uses rookie_year / draft_number for the same concepts — do
-- not assume across assets). Also the props name→gsis resolver's bridge (N0.4, §8 gap 4).
select
    'nfl'                          as sport,
    gsis_id,
    display_name,
    first_name,
    last_name,
    football_name,
    -- cross-IDs
    esb_id,
    nfl_id,
    pfr_id,
    pff_id,
    otc_id,
    espn_id,
    smart_id,
    -- bio / role
    position_group,
    position,
    ngs_position,
    college_name,
    college_conference,
    height,
    weight,
    jersey_number,
    status,
    years_of_experience,
    -- draft (players-table naming — see header)
    rookie_season,
    draft_year,
    draft_round,
    draft_pick,
    draft_team
from {{ nfl_delta('nflverse_players') }}
where gsis_id is not null
