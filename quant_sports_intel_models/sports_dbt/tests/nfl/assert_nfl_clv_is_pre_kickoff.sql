-- ⭐⭐ THE LEAKAGE GATE for the CLV marts (NFL-N1.0) — mart_nfl_clv_game_lines + mart_nfl_clv_props.
--
-- Asserts the belt-and-suspenders close mechanic (N0.4): EVERY served closing line was captured
-- STRICTLY BEFORE its game kicked off. A closing "line" whose snapshot is at/after commence_time is
-- post-kickoff information — using it as the market benchmark would leak the very thing CLV measures
-- against. N0.4's ±30-min discovery windows produce harmless post-kickoff over-captures in the RAW
-- feed; the marts must have dropped every one (`where is_leakage_safe` + latest pre-kickoff
-- snapshot). This HALTs the build if any survived.
--
-- Returns violating rows (snapshot at/after kickoff, or a non-positive minutes_before_kickoff).

select 'game_lines' as mart, event_id, bookmaker, market, side, snapshot_ts, commence_time,
       minutes_before_kickoff
from {{ ref('mart_nfl_clv_game_lines') }}
where snapshot_ts >= commence_time or minutes_before_kickoff <= 0

union all

select 'props' as mart, event_id, bookmaker, market, side, snapshot_ts, commence_time,
       minutes_before_kickoff
from {{ ref('mart_nfl_clv_props') }}
where snapshot_ts >= commence_time or minutes_before_kickoff <= 0
