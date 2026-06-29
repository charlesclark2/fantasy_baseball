# Session Recap — E11.1-W3-main (Lakehouse Wave 3, main) — for PM Claude

**Date:** 2026-06-28 · **Status:** ✅ COMPLETE — code merged to main, cutover live, post-deploy verified healthy.

## What shipped
Migrated **11 pitch-derived batch marts** off Snowflake → DuckDB/S3 (dual-branch, `tags=['w3_lakehouse']`, `materialized='view'` over `baseball_data.lakehouse_ext.*`), same machinery as W1/W2:
`mart_pitcher_pitch_archetype`, `mart_batter_vs_pitch_archetype`, `mart_batter_vs_handedness_splits`, `mart_pitcher_vs_handedness_splits`, `mart_starter_tto_splits`, `mart_team_base_state_splits`, `mart_team_vs_pitcher_hand`, `mart_bullpen_handedness_splits`, `mart_bullpen_leverage`, `mart_bullpen_workload`, `mart_reliever_top3_availability`.

New/changed infra: `scripts/run_w1_lakehouse.py` (W3_MART_MODELS + `_build_w3` + `--w3-only`), `scripts/refresh_w1_external_tables.py` (W3_TABLES, HALT), `scripts/ddl/generate_w3_external_tables.py` (+ generated DDL), `scripts/parity_check_w3.py`, `pipeline/ops/daily_ingestion_ops.py` (comments). W3 builds default-on after W2 on `run_w1_lakehouse_op`; refreshed on `refresh_w1_external_tables_op`.

Gates at handoff: `dbtf compile` 1771/1771 ✅ · fast pytest 683 ✅ · `parity_check_w3` GREEN (operator) ✅. Post-cutover SF spot-checks healthy (views resolve; TTO xwOBA non-zero; team_vs_pitcher_hand consumed `_std` cols non-null).

## ⚠️ Scope decision PM must propagate (the prompt was wrong)
The story prompt told us to "migrate SAFE/EVAL marts FIRST" naming 4 odds/CLV marts (`mart_prediction_clv`, `mart_derivative_closes`, `mart_clv_label_count`, `mart_bookmaker_disagreement`). **All 4 are mechanically BLOCKED** — each reads a serving-coupled mart not yet in S3, and the DuckDB build needs every upstream in S3. They are deferred to **Wsv**. We instead migrated the genuinely-unblocked pitch-derived set (the 11 above). User approved this scope.

## ❗ Closeout items still open (NOT blocking the merge — for PM tracking)

1. **Roadmap/story-prompt framing is now stale.** `build_roadmap.md` + `story_prompts.md` call W3-main "the July-1 all-batch-off-Snowflake finish." **That finish was NOT achieved.** W3-main only cleared the pitch-derived leftovers. Update the docs to: (a) mark W3-main DONE, (b) redefine the residual + name the precursors each remaining wave needs (below).

2. **Snowflake residual is 35 marts — NOT serving-only yet.** Breaks into:
   - **Odds/CLV eval marts (4)** → **Wsv** (blocked on serving parents `mart_game_odds_bridge`/`mart_odds_outcomes`/`mart_closing_line_value`/`mart_clv_labeled_games`/`mart_game_results`/`daily_model_predictions` getting an S3 read-path).
   - **Serving/odds path (~9)**: `mart_odds_outcomes`, `mart_game_odds_bridge`, `mart_odds_line_movement`, `mart_closing_line_value`, `mart_odds_consensus`, `mart_odds_events`, `mart_clv_labeled_games`, `mart_game_results`, `mart_game_spine` → **Wsv** (read at/near request time).
   - **Blocked on non-S3 sources needing their own export precursor (the rest)** — each is a future wave:
     - **`odds_snapshots_historical` (2021–25)** S3 export → unblocks `mart_closing_line_value` + `mart_odds_line_movement` (read it directly, not via staging).
     - **FanGraphs facts** (`fct_fangraphs_*`) → `mart_batter_profile_summary`, `mart_pitcher_arsenal_summary`, `mart_pitcher_profile_summary`.
     - **Posteriors/cluster Snowflake tables** (`eb_park_factors_raw`, `eb_park_factors_granular_raw`, `mart_player_archetype_posteriors`, `pitcher_clusters`, `eb_bullpen_team_posteriors`) → `mart_eb_park_factors`, `mart_park_factors_granular`, `mart_batter_archetype_vs_pitcher_cluster`, `mart_batter_woba_vs_cluster`, `mart_bullpen_effectiveness`.
     - **Seeds** (`ref_teams`, `dim_team_name_lookup`) + **`mart_game_results` chain** → `mart_head_to_head_team_history`, `mart_home_away_splits`, `mart_park_run_factors`, `mart_team_pythagorean_rolling`, `mart_team_rolling_offense`, `mart_team_rolling_pitching`, `mart_team_season_record`, `mart_team_schedule_context`, `mart_player_game_starts`, `mart_player_profile_identity`.
     - **Raw savant/external** (`catcher_framing_raw`, `oaa_team_season_raw`, `stg_batter_sprint_speed`) → `mart_catcher_framing`, `mart_team_fielding_oaa`, `mart_team_defense_quality_rolling`.

3. **Measured Snowflake cost delta (AC item, observable later).** Daily build now runs **11 fewer table CTAS**. Confirm the credit-trend drop over the next billing window; record the number when available.

4. **Parity is now tautological** for these 11 (`betting.*` = view over the same parquet). Re-run `parity_check_w3` only before a *future* change to one of these marts.

## Notes for whoever picks up Wsv / the precursor waves
- One parity subtlety baked in: `mart_team_vs_pitcher_hand` single-game `woba`/`xwoba` are **zeroed by design** (reproduces a latent Snowflake scale-0 `::numeric` bug via `::numeric(38,0)`; those columns are consumed by nothing — features/serving read only `_7d/_30d/_std`). Don't "fix" them without checking consumers.
- Cutover order is load-bearing: **create external tables BEFORE the PR merges** (CI `state:modified+` build + CD auto-deploy on `dbt/**`+`scripts/**`).
- Memory: `project_e11_1_w3main_lakehouse.md`.
