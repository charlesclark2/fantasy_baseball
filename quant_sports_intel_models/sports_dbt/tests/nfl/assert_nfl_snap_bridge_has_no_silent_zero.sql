-- ⭐ THE NF-W0b SILENT-ZERO GATE for fct_player_week (v3 §12A).
--
-- WHAT IT DEFENDS. `fct_player_week` used to `coalesce(offense_pct, 0.0)` after a LEFT join on the
-- sparse `pfr_id` key. A snap share is a rate in [0, 1] where 0.0 is a LEGAL observation ("dressed,
-- played no offensive snaps"), so an unresolved identity became a value indistinguishable from a
-- real one: no error, no NULL, invisible to every coverage check, trained on as fact. Measured on
-- the live lake, that served Michael Woods II a 0.00 snap share for a week in which he played 100%
-- of CLE's offensive snaps.
--
-- ⚠️ WHY THIS TEST IS NOT "assert offense_pct IS NOT NULL". That would be the exact inversion —
-- it would demand the fabricated zero back. The invariant is the OPPOSITE: a row with no snap
-- observation must carry NULL, and only a row WITH one may carry a number. So this asserts the
-- BICONDITIONAL between `snap_source_tier` and the value's presence, which is what makes the two
-- kinds of zero tellable apart:
--
--     snap_source_tier = 'observed'  ⟺  offense_pct IS NOT NULL
--
-- Both directions are checked, and each catches a different regression: a re-introduced
-- `coalesce(..., 0)` trips the RIGHT direction (a value present on a non-observed row), while a
-- broken bridge that loses genuinely-matched rows trips the LEFT (a tier claiming an observation
-- that carries no value). A one-directional test would pass through the coalesce it exists to stop.
--
-- Returns violating rows; dbt fails the build if any are returned.

with fct as (
    select
        season,
        week,
        player_id,
        snap_source_tier,
        offense_pct,
        offense_snaps
    from {{ ref('fct_player_week') }}
)

select
    season,
    week,
    player_id,
    snap_source_tier,
    offense_pct,
    case
        when snap_source_tier <> 'observed' and offense_pct is not null
            then 'a NON-observed row carries a snap value — a join miss was coalesced to a number'
        else 'an OBSERVED row carries no snap value — the bridge lost a matched row'
    end as violation
from fct
where (snap_source_tier <> 'observed' and offense_pct is not null)
   or (snap_source_tier =  'observed' and offense_pct is null)
