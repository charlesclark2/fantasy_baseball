-- mart_nfl_fantasy_season_projection — the NF-FASTPATH output (the 2026 draft-tool content base).
--
-- GRAIN: one row per draft-relevant offensive player (`player_id` = gsis_id) — their projected
-- UPCOMING-season RAW STAT LINE (season totals) + a playing-time (`proj_games`) estimate + an 80%
-- PPR interval. This is the input contract MVP-2 / NF-C1 (the league-config/scoring engine) reads:
-- the RAW line is scored per league downstream; the `proj_fp_*` columns are a CONVENIENCE (standard
-- nflverse scoring) for ranking/validation only.
--
-- ⚠️ NOT COMPUTED IN dbt. A read-only view over the parquet that
-- `football/nfl/fantasy/run_season_projection.py` writes to the lake
-- (`nfl/fantasy/derived/season_projections`). The model is a veteran per-game line shrunk by sample
-- size × an expected-games role estimate, plus an incoming rookie class anchored on a draft-slot
-- production curve and nudged by the NCAAF-P1A residual — Python, not SQL, and should not be.
--
-- 🚨 BUILD ORDER: the NFL marts (fct_player_week etc.) + the NCAAF-P1A rookie parquet must exist,
-- THEN run_season_projection.py lands the derived Delta, THEN this view. Building it in the same
-- pass that produces its input serves the previous run. Excluded from the default build via the
-- `nfl_fantasy` tag until the script has run once.
--
-- ⚖️ EDGE-INDEPENDENT — a PROJECTION product, no best_alpha/PBO/DSR/CLV gate (that is the betting
-- posture). The gate is face-validity + coverage + a holdout rank-correlation sanity check.
-- ⚠️ UNCERTAINTY: veteran intervals are EMPIRICAL (realized game-to-game variance); rookie intervals
-- are PARAMETER uncertainty (slot-curve + P1A) → recalibrate before pricing. NULL = unknown kept NULL.
{{ config(materialized='view', tags=['nfl_fantasy']) }}

select * from {{ nfl_delta('season_projections', tier='fantasy/derived') }}
