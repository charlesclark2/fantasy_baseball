-- A1.11 — integrity / leakage guard for mart_game_spine's scheduled branch.
--
-- The whole non-destructive contract rests on two invariants for scheduled rows:
--   1. NO RESULT LEAKAGE — a scheduled (not-yet-played) game must carry NULL
--      scores. A non-null score on an is_scheduled row would mean a completed
--      game's outcome leaked into the forward-looking branch (and any feature
--      that reads it pre-game would be using post-game information).
--   2. NO DOUBLE-COUNT — a scheduled game_pk must NOT also exist in
--      mart_game_results. If it does, the NOT IN exclusion failed and the game
--      appears on both branches, double-counting it in every downstream feature.
--
-- Returns offending rows → the test fails. Expected result: zero rows.

select
    game_pk,
    'scheduled_row_has_result' as violation
from {{ ref('mart_game_spine') }}
where is_scheduled
  and (home_final_score is not null or away_final_score is not null)

union all

select
    s.game_pk,
    'scheduled_game_pk_also_completed' as violation
from {{ ref('mart_game_spine') }} s
where s.is_scheduled
  and exists (
      select 1 from {{ ref('mart_game_results') }} r
      where r.game_pk = s.game_pk
  )
