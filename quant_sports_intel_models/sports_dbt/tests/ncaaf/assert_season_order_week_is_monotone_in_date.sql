-- ⭐ THE ORDERING GATE for dim_ncaaf_game.season_order_week (NCAAF-P1.1).
--
-- Asserts: `season_order_week` orders a season the same way the CALENDAR does.
--
-- This is the root-cause guard for the postseason-collision bug. CFBD restarts `week` at 1 for
-- the postseason, so raw `week` places January's national championship before September's week 2.
-- `season_order_week` offsets the postseason past the last regular-season week to fix that, and
-- every point-in-time model in this layer orders on it. If that offset ever breaks — a new
-- season_type appears, a season's regular-season week count shifts, the offset is dropped — the
-- ordering silently reverts to nonsense and every as-of rollup starts leaking again.
--
-- The assertion: within a season, a LATER season_order_week must not start EARLIER on the
-- calendar than an earlier one. Compare each week's first kickoff against the previous week's;
-- any inversion is returned and fails the build.
--
-- ⚠️ Compares FIRST kickoff to FIRST kickoff, not max to min: college weeks legitimately overlap
-- at the edges (a Tuesday MACtion game, a Friday opener), so requiring strict non-overlap would
-- produce false failures. An INVERTED START is the real defect and is what this catches.

with week_start as (
    select
        season,
        season_order_week,
        min(game_date) as first_kickoff
    from {{ ref('dim_ncaaf_game') }}
    where is_fbs_matchup
      and season_order_week is not null
      and game_date is not null
    group by 1, 2
),

sequenced as (
    select
        season,
        season_order_week,
        first_kickoff,
        lag(season_order_week) over (partition by season order by season_order_week) as prev_order_week,
        lag(first_kickoff)     over (partition by season order by season_order_week) as prev_first_kickoff
    from week_start
)

select
    season,
    prev_order_week,
    prev_first_kickoff,
    season_order_week,
    first_kickoff
from sequenced
where prev_first_kickoff is not null
  and first_kickoff < prev_first_kickoff
