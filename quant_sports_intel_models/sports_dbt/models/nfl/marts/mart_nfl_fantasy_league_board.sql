-- mart_nfl_fantasy_league_board — NF-C1-lite (MVP-2): per-league scored + ranked draft boards.
--
-- GRAIN: one row per (config_name, n_teams, player_id) — a player's league-specific fantasy points,
-- VOR (value-over-replacement), positional + overall rank, and a carried interval, for EACH shipped
-- preset (standard / half_ppr / full_ppr / superflex + the 3-WR roster variants) AT EACH league size.
-- League size is a NORMALIZED dimension (not part of the format name) because VOR replacement scales
-- with n_teams — each size is a genuinely different value board. This is MVP-3's (draft optimizer)
-- input contract: it ranks off `vor` / `overall_rank` for a chosen (config_name, n_teams).
--
-- ⚠️ NOT COMPUTED IN dbt. A read-only view over the parquet
-- `football/nfl/fantasy/run_league_board.py` writes to the lake
-- (`nfl/fantasy/derived/league_boards`). The board RESCORES the MVP-1 RAW stat line
-- (mart_nfl_fantasy_season_projection) per league config via the sport-agnostic `fantasy_engine`
-- (scoring rules + roster/flex/superflex slots + league size) → league points → positional scarcity
-- → VOR. Never the `proj_fp_*` convenience columns.
--
-- 🚨 BUILD ORDER: the season projection Delta must exist (run_season_projection.py), THEN
-- run_league_board.py lands this Delta, THEN this view. Tagged `nfl_fantasy` (opt-in until the
-- script has run).
--
-- ⚖️ EDGE-INDEPENDENT — a projection product, no best_alpha/PBO/DSR/CLV gate. The gate is scoring
-- correctness (hand-calc) + a transparent replacement-level definition + face-valid preset deltas
-- (superflex lifts QBs; full-PPR lifts pass-catchers). Uncertainty is a first-order CV rescale of the
-- MVP-1 interval; rookie intervals are PARAMETER uncertainty → recalibrate before pricing. NULL kept NULL.
{{ config(materialized='view', tags=['nfl_fantasy']) }}

select * from {{ nfl_delta('league_boards', tier='fantasy/derived') }}
