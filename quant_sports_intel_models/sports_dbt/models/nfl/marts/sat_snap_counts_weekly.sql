-- sat_snap_counts_weekly — snap-usage satellite on the fct spine (N0.3 port of jaffle
-- `sat_snap_counts_weekly`). Left-joins offense/ST snap counts+pct onto every fct player-week
-- row. ⭐ sport-tagged.
--
-- 🐛 NF-W0b (v3 §12A): this model used to key on `weekly_rosters.pfr_id` and then
-- `coalesce(offense_pct, 0.0)` — so an unresolved IDENTITY became an observed 0.0 snap share,
-- indistinguishable from a real "dressed, played no offensive snaps". It now reads the already-
-- resolved snap columns straight off `fct_player_week` (which owns the cross-season pfr bridge),
-- so there is ONE bridge in the project rather than two copies that can drift apart, and the
-- satellite cannot silently re-introduce the zero. `snap_source_tier` distinguishes a real 0.0
-- ('observed') from an unknown ('no_snap_row' / 'bye').
select
    'nfl' as sport,
    season,
    week,
    player_id,
    pfr_id,
    gsis_it_id,
    player_name,
    team_id,
    position,
    status,
    depth_chart_position_rank,
    is_bye,
    week_start_et,
    week_end_et,
    offense_snaps,
    offense_pct,
    special_teams_snaps,
    special_teams_pct,
    snap_source_tier
from {{ ref('fct_player_week') }}
