# Temporal Audit — baseball_data Platform

**Completed:** 2026-05-28  
**Rolling window SQL audit completed:** 2026-05-28  
**Weather infrastructure audit completed:** 2026-05-28  
**Weather observation_type bug fixed:** 2026-05-28 — `feature_pregame_weather_features.sql` patched; `mart_sub_model_signals` backfilled (50,114 rows corrected)  
**Schemas audited:** `baseball_data.betting_features`, `baseball_data.betting`, `baseball_data.betting_ml`  
**Purpose:** Story 13.1 — Identify leakage risk, SCD-2 gaps, and remediation priority for all feature marts before Phase 9 sub-model work adds more consumers.  
**Author:** Generated from live Snowflake schema + column inspection.

---

## Summary of Key Findings

| Finding | Detail |
|---|---|
| Tables audited | 107 total (13 betting_features, 76 betting, 14 betting_ml + 4 reference/staging) |
| Tables with SCD-2 already | **2** — `mart_sub_model_signals`, `feature_pregame_lineup_features` |
| Tables with `computed_at` | **2** (same as above) |
| High leakage risk, high downstream use | **5** — see priority list below |
| Outcome tables (never features) | **7** — `mart_game_results`, `mart_closing_line_value`, `mart_prediction_clv`, `daily_model_predictions`, `placed_bets`, `mart_odds_outcomes`, `mart_pitch_play_event` |
| Tables needing no SCD-2 (stable/reference) | **8** — park factors, ref_teams, ref_venues, EB park factors, CV result tables, model registry, probability outputs |

**Top priority gap:** `feature_pregame_odds_features` has no SCD-2 and no `computed_at`. The single-row-per-game design means every time odds change intraday the previous snapshot is overwritten. If odds were updated after game start (or even after the game), the mart silently reflects post-market information for any prediction replay.

**Positive finding:** `feature_pregame_lineup_features` already has full SCD-2 (`valid_from`, `valid_to`, `is_current`, `computed_at`, `record_hash`). Epic 15 can treat this table as the reference implementation for all other migrations.

---

## Remediation Priority Order

Ordered by **leakage risk × downstream consumer count**. This is the input to Epic 15's story sequencing.

| Priority | Table | Schema | Risk | SCD-2? | Notes |
|---|---|---|---|---|---|
| 1 | `feature_pregame_odds_features` | betting_features | HIGH | ✗ | Intraday odds shift; no snapshot timestamp; single row per game silently overwrites |
| 2 | `feature_pregame_starter_features` | betting_features | HIGH | ✗ | Pitcher identity changes (scratches); no intraday tracking post-Epic-T |
| 3 | `feature_pregame_weather_features` | betting_features | HIGH | ✗ | Intraday temperature/wind/humidity shifts; only 12,483 rows for 25,599 games |
| 4 | `feature_pregame_team_features` | betting_features | MEDIUM-HIGH | ✗ | Rolling win%, Pythagorean, wOBA windows may include game-day results if not strictly lagged |
| 5 | `feature_pregame_game_features` | betting_features | MEDIUM-HIGH | ✗ | Mega-feature aggregation; inherits leakage from all source tables; fix sources first |
| 6 | `feature_pregame_bullpen_state_features` | betting_features | MEDIUM | ✗ | Prev-N-day usage stats; legitimate pre-game but no audit trail for intraday changes |
| 7 | `stg_statsapi_probable_pitchers` | betting | MEDIUM | ✗ | Has `ingestion_ts`; can replay who the probable pitcher was at any point — but no formal SCD-2 |
| 8 | `stg_statsapi_lineups` | betting | MEDIUM | ✗ | Has `ingestion_ts`; 468k rows (multiple snapshots per game); raw source for 15.2 |
| 9 | `feature_pregame_umpire_features` | betting_features | LOW | ✗ | Umpire stats are stable batch data; rare intraday changes |
| 10 | `feature_pregame_park_features` | betting_features | LOW | ✗ | Annual batch; park dimensions and EB factors don't change mid-season |
| 11 | `eb_batter_posteriors_raw` | betting | LOW-MEDIUM | ✗ | Has `fit_date`; verify fit_date is always < game_date |
| 12 | `mart_bookmaker_disagreement` | betting | MEDIUM | ✗ | No timestamp; sharp/soft disagreement is intraday — may reflect post-market state |
| — | `feature_pregame_lineup_features` | betting_features | — | ✓ | **Already SCD-2.** Reference implementation for all other migrations. |
| — | `mart_sub_model_signals` | betting | — | ✓ | **Already SCD-2.** `scd2_writer.py` pattern established in Story 2.4. |

---

## Schema Detail: `baseball_data.betting_features`

### FEATURE_PREGAME_GAME_FEATURES
- **Grain:** `game_pk` (25,599 rows)
- **Leakage risk:** MEDIUM-HIGH
- **SCD-2:** ✗ No `computed_at`, `valid_from`, or `valid_to`
- **Leakage vectors:**
  - `HOME_WINS`, `HOME_LOSSES`, `HOME_WIN_PCT`, `HOME_PYTHAGOREAN_WIN_EXP` — season-to-date counts; must be computed strictly from `game_date < current_game_date`. If the dbt model includes the current game's result in these aggregates, it leaks.
  - `HOME_OFF_WOBA_30D`, `HOME_PIT_XWOBA_AGAINST_30D` etc. — 30-day rolling windows; same strict-lag requirement.
  - `HOME_ML_MONEY_PCT`, `HOME_ML_TICKET_PCT`, `ML_SHARP_SIGNAL`, `TOTAL_SHARP_SIGNAL` — public betting data; highly intraday. Reflects current snapshot, not prediction-time snapshot.
  - `HOME_WIN_PROB_CONSENSUS`, `SHARP_SOFT_ML_DELTA`, `TOTAL_LINE` — odds at time of last ingest; may reflect post-market odds if table was refreshed after game start.
- **Note:** This is the aggregation mart that denormalizes `feature_pregame_team_features`, `feature_pregame_odds_features`, `feature_pregame_starter_features`, etc. Fixing the source marts effectively fixes this table. SCD-2'ing this mart directly is lower priority than fixing its sources.
- **Downstream consumers:** Primary feature table for all three main models (H2H, totals, run diff). Highest consumer count in the system.
- **Recommended action:** Fix source marts first (odds, starter, weather, team). Once sources have SCD-2, this mart's AS-OF behavior is inherited. Add `computed_at` now as 13.2 compliance.

---

### FEATURE_PREGAME_LINEUP_FEATURES ✅ SCD-2 COMPLETE
- **Grain:** `(game_pk, side)` (52,058 rows)
- **Leakage risk:** LOW
- **SCD-2:** ✓ Has `valid_from`, `valid_to`, `is_current`, `computed_at`, `record_hash`
- **Notes:** Reference implementation. `avg_eb_woba`, `avg_eb_k_pct` etc. pulled from `eb_batter_posteriors_raw` which has `fit_date` — verify fit_date < game_date in the dbt model. ZiPS projections (`avg_zips_wrc_plus`, `avg_zips_woba_proxy`) are season-start batch data; no intraday risk.
- **Action:** None required for SCD-2. Verify EB join uses `fit_date <= game_date` strictly.

---

### FEATURE_PREGAME_ODDS_FEATURES
- **Grain:** `game_pk` (25,599 rows)
- **Leakage risk:** HIGH
- **SCD-2:** ✗ No temporal columns
- **Leakage vectors:**
  - Single row per game; overwrites with each odds ingest run. If the daily pipeline runs post-game, the "pregame odds" mart silently reflects post-game or closing-line values.
  - `HOME_WIN_PROB_CONSENSUS`, `TOTAL_LINE`, `SHARP_SOFT_ML_DELTA` — consensus values at last ingest; may be closing-line equivalent.
  - `ODDS_INGESTION_TS` is present but is a single scalar — it records only the most recent ingest, not the ingest at prediction time.
- **Downstream consumers:** H2H model, totals model, probability layer, `feature_pregame_game_features`.
- **Priority 1 for Epic 15.** Natural key for SCD-2: `(game_pk, odds_bookmaker_key)`. Change-detection hash: moneyline, total line, juice.
- **Backfill strategy:** Full historical replay via `stg_oddsapi_odds` (append-only, 2021+) and `stg_parlayapi_odds` (2026-05-26+). The raw tables are append-only so full timeline reconstruction is possible for Odds API coverage.

---

### FEATURE_PREGAME_PARK_FEATURES
- **Grain:** `game_pk` (25,599 rows)
- **Leakage risk:** LOW
- **SCD-2:** ✗
- **Notes:** Physical park dimensions and EB park run factor. Park factors update annually. `EB_PARK_RUN_FACTOR` is updated when `compute_eb_park_factors.py` runs (has `fit_date` in source `mart_eb_park_factors`). No intraday volatility. Stadium dimensions are effectively permanent.
- **Action:** Add `computed_at` (13.2 compliance). SCD-2 migration is low value — annual batch. Story 15.8 is a 1-hour task.

---

### FEATURE_PREGAME_STARTER_FEATURES
- **Grain:** `(game_pk, side)` (51,966 rows)
- **Leakage risk:** HIGH
- **SCD-2:** ✗ No temporal columns
- **Leakage vectors:**
  - `PITCHER_ID`, `PITCHER_NAME` — identity of the starting pitcher. If a starter is scratched post-publication, this table reflects the replacement. Any prediction made before the scratch used the original pitcher's stats.
  - Rolling stats (`K_PCT_7D`, `XWOBA_AGAINST_30D` etc.) are based on the identified pitcher — if pitcher identity changes, all these stats change with it. No audit trail.
  - `STARTER_PROJ_FIP`, `STARTER_PROJ_XFIP` — ZiPS projections; stable, but attached to whoever `PITCHER_ID` currently points to.
- **Downstream consumers:** All three models; starter features are among the highest SHAP-value inputs for H2H and totals.
- **Priority 2 for Epic 15.** Raw source: `stg_statsapi_probable_pitchers` (has `ingestion_ts`; multiple rows per game_pk per side for scratches). Full historical replay from Epic T date forward.
- **Backfill:** Forward-only from Epic T conversion date (~2026-05-12). Pre-T probable pitcher history is lost (MERGE-pattern on `monthly_schedule`).

---

### FEATURE_PREGAME_SUB_MODEL_SIGNALS
- **Grain:** `game_pk` (25,693 rows)
- **Leakage risk:** LOW
- **SCD-2:** ✗ (but source `mart_sub_model_signals` IS SCD-2)
- **Notes:** Pivoted view of `mart_sub_model_signals` filtered to `is_current = TRUE`. Since the source is SCD-2, the signals themselves are temporally anchored. This mart doesn't need independent SCD-2 — it will be correct if the join always uses `is_current = TRUE`.
- **Action:** None for SCD-2. Add `computed_at` (13.2 compliance).

---

### FEATURE_PREGAME_TEAM_FEATURES
- **Grain:** `(game_pk, side)` (51,198 rows)
- **Leakage risk:** MEDIUM (rolling window guards confirmed present)
- **SCD-2:** ✗
- **Rolling window audit (2026-05-28) — CLEAN ✅:**
  - `OFF_WOBA_7D`, `OFF_WOBA_30D`, `PIT_XWOBA_AGAINST_30D` etc. — rolling stats are joined from `mart_team_rolling_offense` and `mart_team_rolling_pitching` using a strict `ro.game_date::date < g.game_date::date` guard (`LEAKAGE GUARD` comment in model). The `ROW_NUMBER() ... ORDER BY ro.game_date DESC` pattern selects the most recent completed game's row — current game's data is never accessible.
  - `WINS`, `LOSSES`, `WIN_PCT`, `PYTHAGOREAN_WIN_EXP` — joined from `mart_team_season_record` on `record_date = dateadd('day', -1, game_date)`. Uses yesterday's record only. Already SCD-2 internally.
  - `PYTHAGOREAN_RESIDUAL_30D` — joined from `mart_team_pythagorean_rolling` which has its own `interval '1 day' preceding` guard inside the mart.
  - Bullpen workload/effectiveness — both source marts use preceding-day upper bounds internally.
- **Remaining leakage risk:** Intraday only — this mart is materialized as a table, so any intraday changes to `feature_pregame_odds_features` or starter identity after the daily dbt run aren't captured. This is the SCD-2 motivation, not a rolling-window correctness issue.
- **Downstream consumers:** All models via `feature_pregame_game_features`. High consumer count.
- **Action:** Add `computed_at` (13.2 compliance). Lower SCD-2 priority than odds/starter — rolling stats are confirmed correct at daily run time, just not tracked intraday.

---

### FEATURE_PREGAME_UMPIRE_FEATURES
- **Grain:** `game_pk` (25,584 rows — ~15 fewer than games, likely games with no umpire assignment)
- **Leakage risk:** LOW
- **SCD-2:** ✗
- **Notes:** `UMP_K_PCT_ZSCORE`, `UMP_RUNS_PER_GAME_ZSCORE` etc. are trailing career stats — batch-computed, rarely updated. Umpire assignment changes are rare (injury substitutions). `UMPIRE_NAME` identity is the only volatile field. Epic T.4 captures umpire assignment intraday.
- **Action:** Add `computed_at` (13.2 compliance). SCD-2 migration is Story 15.7 — low value, batch at end.

---

### FEATURE_PREGAME_WEATHER_FEATURES
- **Grain:** `game_pk` (only 12,483 rows — outdoor games only; dome games excluded)
- **Leakage risk:** HIGH
- **SCD-2:** ✗
- **Weather infrastructure audit (2026-05-28):**
  - **Raw ingestion (`ingest_weather.py`):** Three `observation_type` values: `forecast_pregame` (fetched ~6-12h before first pitch), `forecast_intraday` (T-24h/6h/3h/1h snapshots; captured hourly by Dagster/GH Actions since Epic T.2 ~2026-05-12), `observed_at_first_pitch` (archive fetch for yesterday's completed games). Raw table is **append-only** — full replay possible for all post-Epic-T.2 games.
  - **Staging (`stg_weather_raw`):** Deduplicates to latest row per `(game_pk, venue_id, observation_type, hours_to_first_pitch)`. Passes `weather_observation_type` through.
  - **Feature mart (`feature_pregame_weather_features`) — BUG FIXED 2026-05-28:** Was using `ORDER BY abs(fetch_offset_hours) ASC` with no `WHERE weather_observation_type = 'forecast_pregame'` filter. `fetch_offset_hours = (fetch_time − game_time)`. This meant `forecast_intraday T-1h` (abs ≈ 1) beat `forecast_pregame` (abs ≈ 6-12) whenever both exist. Since Epic T.2, the mart silently switched from `forecast_pregame` to `forecast_intraday T-1h` for games that have intraday captures — with no `observation_type` column in the output. **Fix applied:** `WHERE weather_observation_type = 'forecast_pregame'` added to the CTE; `weather_observation_type` column added to output. `mart_sub_model_signals` backfilled (50,114 rows corrected, 49,626 prior SCD-2 records closed).
- **Leakage vectors:**
  - **Train/inference distribution shift (confirmed):** Models trained on `forecast_pregame` weather; live inference has used `forecast_intraday T-1h` since Epic T.2. T-1h forecasts are more accurate (smaller error), so the model's implicit "forecast uncertainty" calibration is mismatched.
  - **No `observation_type` column in output:** Downstream consumers and training scripts cannot detect which observation type was used for a given game.
  - **`observed_at_first_pitch` protection:** Correctly protected by `abs(fetch_offset_hours)` ordering — post-game observed rows (abs ~15+) always lose to pre-game rows.
- **Fix applied 2026-05-28:** `WHERE weather_observation_type = 'forecast_pregame'` added; `weather_observation_type` column added to output. Training/inference consistency restored. `mart_sub_model_signals` backfilled for all affected games.
- **Action:** SCD-2 migration is still pending (Priority 3 for Epic 15.5). Forward-only backfill from Epic T.2 conversion date.

---

### FEATURE_BATTER_ARCHETYPE_MATCHUPS
- **Grain:** `game_pk` (25,599 rows)
- **Leakage risk:** LOW-MEDIUM
- **SCD-2:** ✗
- **Notes:** Historical aggregate wOBA by lineup archetype vs pitcher archetype. Based on `mart_batter_archetype_vs_pitcher_cluster`. These are historical aggregates — stable batch data. Changes only when lineup composition changes (which flows through `feature_pregame_lineup_features`, already SCD-2'd).
- **Action:** Low priority. Add `computed_at` (13.2 compliance).

---

### FEATURE_PITCHER_BATTER_H2H_MATCHUPS
- **Grain:** `game_pk` (25,599 rows)
- **Leakage risk:** LOW
- **SCD-2:** ✗
- **Notes:** Historical H2H wOBA and xwOBA for the active lineup vs the opposing starter. Stable batch data from `mart_pitcher_batter_history`. Dependent on lineup composition (via SCD-2'd `feature_pregame_lineup_features`).
- **Action:** Add `computed_at`. No SCD-2 needed.

---

### FEATURE_PITCHER_CLUSTER_MATCHUPS
- **Grain:** `game_pk` (25,599 rows)
- **Leakage risk:** LOW
- **SCD-2:** ✗
- **Notes:** Historical average wOBA/xwOBA for each lineup vs pitcher cluster assignment. Cluster labels are stable (updated seasonally). Dependent on lineup composition.
- **Action:** Add `computed_at`. No SCD-2 needed.

---

## Schema Detail: `baseball_data.betting` (selected tables)

### MART_GAME_RESULTS ⛔ OUTCOME TABLE — NEVER A FEATURE INPUT
- **Grain:** `game_pk` (25,599 rows)
- **Leakage risk:** CRITICAL if joined to feature marts without date filter
- **Columns that leak:** `HOME_FINAL_SCORE`, `AWAY_FINAL_SCORE`, `RUN_DIFFERENTIAL`, `HOME_TEAM_WON`, `WINNING_TEAM`
- **Assessment:** This is the outcome table. It must only be used as (a) a training target, (b) a rolling window source where `game_date < current_game_date` is strictly enforced in SQL. Any feature mart that joins this table without a strict date lag is a leakage source.
- **Action:** Audit every dbt model that joins `mart_game_results` to confirm it uses `game_date < {{ current_game_date }}` (or `game_date < game_pk_game_date`) in the join predicate. Document findings in Epic 15.

---

### MART_CLOSING_LINE_VALUE ⛔ EVALUATION TABLE — NEVER A FEATURE INPUT
- **Grain:** `game_pk` (8,931 rows)
- **Leakage risk:** CRITICAL if used as a feature
- **Notes:** Contains `CLV_HOME_ML`, `CLV_TOTAL`, `CLOSE_VF_HOME` — all computed using the closing line, which is post-market (available only after the game begins). No SCD-2 needed because this is purely an evaluation output.

---

### MART_PREDICTION_CLV ⛔ EVALUATION TABLE — NEVER A FEATURE INPUT
- **Grain:** `(score_date, game_pk, model_version, prediction_type)` (43,513 rows)
- **Leakage risk:** CRITICAL if used as a feature
- **Notes:** Joins `daily_model_predictions` with `mart_closing_line_value`. Contains CLV outcome columns. Correct use: CLV monitoring dashboard and promotion gates. Never a feature for any model.

---

### MART_ODDS_CONSENSUS
- **Grain:** `event_id` (9,948 rows) — note: uses `event_id`, not `game_pk`
- **Leakage risk:** MEDIUM
- **SCD-2:** ✗ No timestamp columns
- **Notes:** Consensus win probability, sharp vs soft split, bookmaker count. No ingestion timestamp means we cannot determine when this snapshot was taken. If the daily pipeline refreshes this after game start, the consensus reflects post-game market movement. This feeds `feature_pregame_odds_features`.
- **Action:** Part of Epic 15.1 (odds SCD-2). Add `ingestion_ts` and `valid_from`/`valid_to`.

---

### MART_ODDS_LINE_MOVEMENT
- **Grain:** `game_pk` (9,073 rows)
- **Leakage risk:** MEDIUM
- **Notes:** `OPEN_HOME_WIN_PROB`, `PREGAME_HOME_WIN_PROB`, `H2H_LINE_MOVEMENT` — open-to-pregame movement summary. The `PREGAME_HOME_WIN_PROB` should be the last pre-game snapshot, but without SCD-2 we can't verify this for historical replays.
- **Action:** Part of Epic 15.1. Derivable from `stg_oddsapi_odds` or `stg_parlayapi_line_movement` (6M rows) with timestamp-bounded queries.

---

### MART_BOOKMAKER_DISAGREEMENT
- **Grain:** `game_pk` (8,731 rows)
- **Leakage risk:** MEDIUM
- **Notes:** `SHARP_SOFT_ML_SPREAD`, `N_BOOKS_AVAILABLE`, `ML_IMPLIED_PROB_STD` — disagreement among bookmakers. Highly time-sensitive (narrows as game approaches). No timestamp. Part of Epic 15.1 or treated as a downstream of odds SCD-2.

---

### STG_STATSAPI_PROBABLE_PITCHERS
- **Grain:** `(game_pk, side, ingestion_ts)` implicitly (52,186 rows)
- **SCD-2:** ✗ (but has `ingestion_ts` — already temporal)
- **Notes:** 52,186 rows for ~25,599 games × 2 sides = ~51,198 expected unique (game_pk, side) slots. Slight excess suggests multiple probable pitcher rows per slot from intraday re-ingestion. This is the raw source for 15.4 — `ingestion_ts` enables replay without needing to add columns.
- **Action:** Add formal `valid_from`/`valid_to` in the mart that consumes this staging table.

---

### STG_STATSAPI_LINEUPS
- **Grain:** `(game_pk, home_away, batting_order, player_id, ingestion_ts)` implicitly (468,540 rows)
- **SCD-2:** ✗ (but has `ingestion_ts`)
- **Notes:** 468k rows for ~26k games. Approximately 18 batter-slots per game × 2 sides = 52k expected unique slots. Extra rows are from intraday re-ingestion snapshots capturing lineup changes. Already has `ingestion_ts` — usable for SCD-2 backfill.
- **Action:** Raw source for 15.2. `ingestion_ts` is the key for temporal reconstruction.

---

### STG_STATSAPI_TRANSACTIONS
- **Grain:** `transaction_id` (66,897 rows)
- **Already append-only:** ✓ Each transaction is immutable.
- **Notes:** Full historical IL placement/activation timeline. `transaction_date`, `effective_date`, `resolution_date` provide rich temporal metadata. Source for 15.3 injury status SCD-2.
- **Action:** Primary raw source for 15.3. No changes needed to this staging table.

---

### STG_STATSAPI_PLAYER_INJURY_STATUS
- **Grain:** `player_id` (9,340 rows) — current state only
- **Leakage risk:** MEDIUM
- **Notes:** Current-state injury snapshot. `STATUS_START_DATE` and `STATUS_END_DATE` are present but this table reflects current state, not a full history. For historical SCD-2 work, use `stg_statsapi_transactions` instead.
- **Action:** This table feeds the current-day injury flag in `feature_pregame_lineup_features`. For SCD-2, reconstruct history from `stg_statsapi_transactions`.

---

### EB_BATTER_POSTERIORS_RAW
- **Grain:** `(game_pk, batting_slot, batter_id, fit_date)` (233,460 rows)
- **Leakage risk:** LOW-MEDIUM
- **Notes:** Has `fit_date` and `ingestion_ts`. Multiple `fit_date` values per batter indicate the EB model has been re-run. **Leakage check required:** Verify that the dbt model joining these posteriors to `feature_pregame_lineup_features` uses `fit_date <= game_date` strictly. If `fit_date` equals `game_date`, the EB estimate may incorporate that day's plate appearances (depending on when the fit ran relative to first pitch).
- **Action:** Add explicit assertion in the dbt model: `eb_batter_posteriors_raw.fit_date < feature_pregame_lineup_features.game_date`. This is a training-data leakage check, not an SCD-2 gap.

---

### MART_EB_PARK_FACTORS
- **Grain:** `(venue_id, season)` (362 rows)
- **Leakage risk:** LOW
- **Has `fit_date`:** ✓
- **Notes:** Annual batch EB park factor computation. `FIT_DATE` records when it was computed. 362 rows ≈ 30 parks × ~12 seasons. No intraday volatility. Source for `feature_pregame_park_features.eb_park_run_factor`.
- **Action:** None. Already has sufficient temporal metadata via `fit_date`.

---

### MART_SUB_MODEL_SIGNALS ✅ SCD-2 COMPLETE
- **Grain:** `(game_pk, side, signal_name, sub_model_name)` + SCD-2 (102,769 rows)
- **SCD-2:** ✓ `valid_from`, `valid_to`, `is_current`, `computed_at`, `record_hash`
- **Notes:** Established in Story 2.4 via `scd2_writer.py`. Reference implementation alongside `feature_pregame_lineup_features`.

---

### MART_TEAM_PYTHAGOREAN_ROLLING
- **Grain:** `(team_id, game_pk)` (49,693 rows)
- **Leakage risk:** LOW (audit complete, guard confirmed)
- **Rolling window audit (2026-05-28) — CLEAN ✅:**
  - Window spec: `range between interval '30 days' preceding and interval '1 day' preceding` — the guard is **inside the mart itself**, not deferred to the consumer. The row for `game_pk=X` on 2026-05-28 contains rolling stats from games strictly before 2026-05-28. This is the gold standard pattern.
  - `game_pk` is the predicted game, and the mart's daily totals are aggregated at the calendar-date level first before joining back — both legs of a doubleheader inherit the same pre-game rolling stats.
  - The comment in the model explicitly documents: "LEAKAGE GUARD: the rolling window upper bound is `interval '1 day' preceding` so the row's own game day is excluded."
  - Consumer (`feature_pregame_team_features`) joins directly on `game_pk` without any additional date guard — correct, because the guard is already inside the mart.
- **Minimum game gate:** `NULL` when fewer than 10 games in the 30d window (correct early-season handling).
- **Action:** None required for correctness. Add `computed_at` (13.2 compliance).

---

## Schema Detail: `baseball_data.betting_ml`

### DAILY_MODEL_PREDICTIONS ⛔ OUTPUT TABLE
- **Grain:** `(score_date, game_pk, model_version, prediction_type)` (44,873 rows)
- **Notes:** Model output. Never a feature input. This is the source table for the 13.4 `prediction_snapshots` backfill. Does NOT currently store a `feature_snapshot` VARIANT — that's what 13.4 adds. Has `inserted_at` timestamp.

### PLACED_BETS ⛔ OUTPUT TABLE
- **Notes:** Actual bet records with outcomes. Never a feature. Contains `OUTCOME` and `PROFIT_LOSS`.

### CV_* tables ⛔ EVALUATION / METADATA
- **Notes:** Cross-validation results per model. Never feature inputs.

### MODEL_REGISTRY ⛔ METADATA
- **Notes:** Model version tracking. Never a feature input. Correctly tracks `is_current`, `promoted_date`, `deprecated_date`.

### PROBABILITY_OUTPUTS / PROBABILITY_LAYER_SUMMARY ⛔ OUTPUT TABLES
- **Notes:** Intermediate probability computation outputs. Small tables (108 and 1 row). Not feature inputs.

---

## `computed_at` Compliance Status (Story 13.2)

Tables that are **missing `computed_at`** and will need it added as new Phase 9 models are created or existing ones are touched:

| Table | Schema | Has `computed_at`? |
|---|---|---|
| feature_pregame_game_features | betting_features | ✗ |
| feature_pregame_lineup_features | betting_features | ✓ |
| feature_pregame_odds_features | betting_features | ✗ |
| feature_pregame_park_features | betting_features | ✗ |
| feature_pregame_starter_features | betting_features | ✗ |
| feature_pregame_sub_model_signals | betting_features | ✗ |
| feature_pregame_team_features | betting_features | ✗ |
| feature_pregame_umpire_features | betting_features | ✗ |
| feature_pregame_weather_features | betting_features | ✗ |
| feature_batter_archetype_matchups | betting_features | ✗ |
| feature_pitcher_batter_h2h_matchups | betting_features | ✗ |
| feature_pitcher_cluster_matchups | betting_features | ✗ |
| mart_sub_model_signals | betting | ✓ |
| mart_game_results | betting | ✗ |
| mart_closing_line_value | betting | ✗ |
| mart_odds_consensus | betting | ✗ |
| mart_odds_line_movement | betting | ✗ |

Rule per Story 13.2: all **new** dbt models created in Phase 9 must have `computed_at`. Existing models get `computed_at` added when they are touched by Epic 15 SCD-2 work.

---

## Action Items for Epic 15 Sequencing

This audit confirms the Epic 15 story order is correct. Additional sequencing notes:

1. **15.1 (Odds)** — highest priority and fully replayable (2021+ Odds API raw is append-only; Parlay API from 2026-05-26). Start here.
2. **15.2 (Lineup)** — forward-only from ~2026-05-12 (Epic T.1 conversion date); raw `stg_statsapi_lineups` has `ingestion_ts` for replay.
3. **15.3 (Injury)** — fully replayable via `stg_statsapi_transactions` (append-only, full history). Can run in parallel with 15.2.
4. **15.4 (Starter)** — forward-only from ~2026-05-12 (Epic T conversion date); raw `stg_statsapi_probable_pitchers` has `ingestion_ts`.
5. **15.5 (Weather)** — forward-only from Epic T.2 conversion date; need to add `observation_type` column to distinguish forecast types.
6. **15.6 (Public betting)** — forward-only from Epic T.3 date; also gated by Action Network data gap (data starts 2024-02-22 only).
7. **15.7 (Umpire)** — low value, batch at end.
8. **15.8 (Park)** — trivial (annual batch); add `valid_from`/`valid_to` from season start/end dates.

**Additional table to consider for Epic 15 (not in original list):**
- `mart_bookmaker_disagreement` — no timestamp; should be treated as part of 15.1 (odds SCD-2 bundle)
- `mart_odds_line_movement` — derivable from raw odds snapshots; also part of 15.1
- `mart_team_pythagorean_rolling` — rolling win stats; audit SQL immediately for date-lag correctness before adding to 15 scope

---

## Rolling Window SQL Audit — COMPLETE (2026-05-28)

All 6 rolling window dbt models pass temporal correctness. Epic 15 may proceed.

| Model | Window Bound | Leakage Guard Location | Verdict |
|---|---|---|---|
| `mart_team_rolling_offense` | `current row` | Consumer (`feature_pregame_team_features`): `ro.game_date::date < g.game_date::date` | ✅ CLEAN |
| `mart_team_rolling_pitching` | `current row` | Consumer: `rp.game_date::date < g.game_date::date` | ✅ CLEAN |
| `mart_pitcher_rolling_stats` | `current row` | Consumer (`feature_pregame_starter_features`): `rs.game_date::date < pp.game_date` | ✅ CLEAN |
| `mart_batter_rolling_stats` | `current row` | Consumer (`feature_pregame_lineup_features`): `rs.game_date::date < ls.official_date` | ✅ CLEAN |
| `mart_team_pythagorean_rolling` | `interval '1 day' preceding` | **Inside the mart itself** — self-contained | ✅ CLEAN (gold standard) |
| `mart_team_season_record` | (SCD-2 date spine) | Consumer: `record_date = dateadd('day', -1, game_date)` | ✅ CLEAN (already SCD-2) |

**Design note on models 1–4:** The `current row` window bound means each mart row includes the current game's stats in the rolling averages. This is intentional — the row is only created after the game completes, and consumers enforce `< game_date` at join time via `ROW_NUMBER() ORDER BY game_date DESC` + `rn = 1`. The risk is that any **future consumer** that forgets the date guard would silently get leakage. `mart_team_pythagorean_rolling` avoids this by building the guard into the mart — that pattern should be the standard for new rolling marts.

**Weather bug found (separate from rolling window audit):** `feature_pregame_weather_features` has a train/inference distribution mismatch — see the `FEATURE_PREGAME_WEATHER_FEATURES` section above. This must be fixed before the next model retrain. Epic 15.5 should include the observation_type filter fix as its first deliverable.

---

## Remediation Priority Updates Post-Audit

| Priority | Table | Change from pre-audit |
|---|---|---|
| 1 | `feature_pregame_weather_features` — **observation_type bug fix** | **FIXED 2026-05-28** — `WHERE weather_observation_type = 'forecast_pregame'` applied; signals backfilled. |
| 2 | `feature_pregame_odds_features` | Unchanged (was #1) |
| 3 | `feature_pregame_starter_features` | Unchanged (was #2) |
| 4 | `feature_pregame_weather_features` — SCD-2 migration | Unchanged (was #3); observation_type bug fix is separate pre-work |
| 5 | `feature_pregame_team_features` | **Downgraded** — rolling window guards confirmed correct; only intraday SCD-2 gap remains |
| 6 | `mart_team_pythagorean_rolling` | **Cleared** — was flagged HIGH risk; guard is inside the mart; no action needed |
