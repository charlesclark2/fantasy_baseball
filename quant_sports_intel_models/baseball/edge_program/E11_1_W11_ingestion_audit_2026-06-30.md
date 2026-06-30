# E11.1-W11 — Ingestion Audit + Decommission-Finish Plan (Task 0)

**Wave:** W11 — "all ingestion strictly to S3" (the FINISH wave).
**Date:** 2026-06-30. **Sibling wave running in parallel:** W9-tail (signal generators → S3) — see Ownership at bottom.
**Goal:** EVERY raw-ingestion writer writes strictly to S3, not Snowflake. After W11 the ONLY Snowflake left is the by-decision minimal (Cortex `daily_model_predictions` + the stateful model-state tables).

This is the authoritative **HAVE / MIGRATE / STAY** table. It is the shared baseline every per-source sub-session should work from (the migrations are per-source, independent, and each needs its own serialized box run — the runtime gate).

---

## §1 — TASK-0 INGESTION AUDIT (have / migrate / stay)

Legend — **WRITE**: `conn` = `snowflake.connector` execute/executemany INSERT/MERGE; `wp` = `write_pandas`; `araw` = `append_raw_rows` (Snowflake VARIANT, NOT yet the S3 dispatcher); `araw_lh` = `append_raw_rows_lakehouse` (the S3-capable dispatcher, env-gated); `s3` = native S3 parquet. **INC-20**: does it write accumulating growing-history snapshots each run.

### ✅ HAVE — already S3-native (no W11 action)

| Writer | S3 target | Notes |
|---|---|---|
| `ingest_statcast_to_s3.py` | `mart_pitch_*` parquet (W1d) | the canonical template; HALT-tier in daily job |
| `run_w1_lakehouse.py` (W1–W8b builds) | `lakehouse/<model>/` parquet | DuckDB build, no Snowflake write |
| E5.1b prop/odds capture → `mlb/props/` | S3 | already S3-native (operator confirmed) |
| `export_odds_raw_to_s3.py --source monthly_schedule` | `lakehouse_raw/monthly_schedule/` | the recurring bridge (daily op) + INC-20 `latest_dt_per_month` retention already applied |

### 🟡 PARTIAL — S3-capable but Snowflake leg still live (flip + retire the SF leg)

| Writer | SF target(s) | Mechanism | Downstream stg | What's left |
|---|---|---|---|---|
| `odds_api_ingestion.py` | `oddsapi.mlb_odds_raw`, `mlb_events_raw` | `conn` + **`write_raw_rows_s3` dual-write gated by `LAKEHOUSE_RAW_WRITE_MODE`** | `stg_oddsapi_odds` (⚠serving), `stg_oddsapi_events` | flip env `snowflake`→`s3` after W6 fully cut over; retire the SF temp-table/PARSE_JSON leg |
| `ingest_player_profiles.py` | `statsapi.player_profiles_raw` | `conn` (SF write); S3 `player_profiles_raw` parquet read by `stg_statsapi_player_profiles` (W4 dual-branch) | `stg_statsapi_player_profiles` | the **read** is S3 already; the **writer** still SF-only + an export bridge feeds the parquet → flip writer to `araw_lh`, drop bridge |

### ❌ MIGRATE — still Snowflake-native RAW ingestion (the W11 work-list)

| # | Writer | SF target | WRITE | INC-20? | Downstream stg | Daily-op / cron | Risk tier |
|---|---|---|---|---|---|---|---|
| 1 | `derivative_odds_backfill.py` + derivative capture | `oddsapi.derivative_odds_raw` | parquet→PUT/COPY/MERGE | no (per-event) | `stg_derivative_odds` → `mart_derivative_closes` | derivative capture (was Railway cron) | **eval/CLV** — INC-23 bridge wired this session (§3) |
| 2 | `backfill_historical_odds_snapshots.py` | `oddsapi.odds_snapshots_historical` | `conn`/parquet→MERGE | mild (date×ts re-upsert, idempotent) | `stg_odds_snapshots_historical`; read direct by `mart_closing_line_value`, `mart_odds_line_movement` | manual/intraday | non-serving eval |
| 3 | `ingest_actionnetwork_betting.py` | `actionnetwork.public_betting_raw` | `conn` per-row | no (idempotent by date) | `stg_actionnetwork_public_betting(_snapshots)` | daily op `ingest_action_network` | peripheral |
| 4 | `parlay_api_ingestion.py` | `parlayapi.mlb_{events,odds,matches,line_movement,canonical_events}_raw` (5) | `conn` per-event | no | `stg_parlayapi_*` | intraday `odds_snapshot_ingest` + crontab `odds-capture` | ⚠ **serving-adjacent** (live odds) |
| 5 | `ingest_statsapi.py schedule` | `statsapi.monthly_schedule` | `conn` INSERT | **YES** (append per month) | `stg_statsapi_games/_lineups/_starter_snapshots/_probable_pitchers` | daily `ingest_statsapi_schedule` + crontab `schedule-capture` | ⚠ **serving** (lineups). Export-bridge + retention already exist; flip the **writer** to `araw_lh` to retire the bridge |
| 6 | `ingest_statsapi.py venues` | `statsapi.venues_raw` | `conn` INSERT | YES (append) | `stg_statsapi_venues` | manual | low |
| 7 | `ingest_umpires.py` | `statsapi.umpire_game_log` (statsapi) | `conn` DELETE+INSERT | no (idempotent) | `stg_statsapi_umpire_game_log/_snapshots` | `ingest_umpires_early/late`, `lineup_ingest_umpires` | peripheral. ⚠ 4 writers share ONE table — migrate together |
| 8 | `ingest_umpire_scorecards.py` | `statsapi.umpire_game_log` (umpscorecards) | `wp` DELETE+INSERT | no | same | `ingest_umpire_scorecards` (WARN) | peripheral |
| 9 | `ingest_umpires_historical.py` | `statsapi.umpire_game_log` (umpscorecards) | `wp`/`conn` | YES (append) | same | manual | peripheral |
| 10 | `backfill_umpire_assignments.py` | `statsapi.umpire_game_log` (statsapi_backfill) | `conn` (guarded skip) | no | same | manual | peripheral |
| 11 | `ingest_weather.py` | `statsapi.weather_raw` | `conn` INSERT | no (dedup) | `stg_weather_raw(_snapshots)`, `feature_pregame_weather_features` | daily `ingest_weather` + crontab `weather-capture` + intraday | peripheral |
| 12 | `backfill_observed_weather.py` | `statsapi.weather_raw` | `conn` INSERT | no | same | manual | peripheral |
| 13 | `ingest_oaa.py` | `external.oaa_team_season_raw` | `conn` executemany | no (dedup downstream) | `mart_team_fielding_oaa` (direct) | daily `ingest_oaa` (WARN) | peripheral |
| 14 | `ingest_sprint_speed.py` | `savant.sprint_speed_raw` | `wp` DELETE+INSERT | no | `stg_batter_sprint_speed` | weekly `ingest_sprint_speed` | peripheral |
| 15 | `ingest_catcher_framing.py` | `savant.catcher_framing_raw` | `conn` executemany | no | (no stg; feature builders) | weekly `ingest_fangraphs_catcher_framing` | peripheral |
| 16 | `ingest_transactions.py` | `statsapi.player_transactions` | `conn` DELETE+INSERT | no | `stg_statsapi_transactions` | daily `ingest_transactions` | peripheral |
| 17 | `savant_ingestion.py batter_pitches` | `savant.batter_pitches` | `wp` DELETE+INSERT | no | `stg_batter_pitches` (dual-branch; **read already S3**) | daily `ingest_statcast`, `catchup_ingest_statcast` | ⚠ **VERIFY**: likely shadowed by `ingest_statcast_to_s3.py`. If the S3 path fully feeds `stg_batter_pitches`, the SF write is redundant → retire. Confirm coverage parity first |
| 18 | `ingest_savant_park_factors.py` | `fangraphs.savant_park_factors_raw` | `conn` executemany | no | (park-factor builders) | manual | low |
| 19 | `score_playing_time.py` | `betting.mart_player_start_probability` | `wp` CREATE OR REPLACE | no (full rebuild) | `feature_expected_lineup_*` | manual (Story 33.1) | ⚠ **AMBIGUOUS** — derived model output, not raw ingest. Treat as a dbt/serving artifact decision, not a raw-ingest migration (flag to operator) |
| 20 | `ingest_fangraphs_stuff_plus.py` | `fangraphs.fg_stuff_plus_raw` | `araw` (SF VARIANT) | no (append) | `stg_fangraphs__stuff_plus` | Sunday `ingest_fangraphs_stuff_plus` (WARN) | flip `araw`→`araw_lh` (cheapest class) |
| 21 | `ingest_fangraphs_hitting_leaderboard.py` | `fangraphs.fg_hitting_leaderboard_raw` | `araw` (SF VARIANT) | no | `stg_fangraphs__hitting_leaderboard` | daily `ingest_fangraphs_hitting_leaderboard` (WARN) | flip `araw`→`araw_lh` |

### 🔒 STAY — model-STATE on minimal Snowflake (NOT ingestion; by the pragmatic-Cortex-only decision)

| Writer | SF target | Why it stays |
|---|---|---|
| `predict_today.py` | `betting_ml.daily_model_predictions` | the Cortex decision carrier (serving output) |
| `generate_pick_narratives.py` | narrative col (Cortex `COMPLETE()`) | the ONLY sanctioned Snowflake use (Cortex) |
| `compute_elo.py` | `betting.team_elo_history` | rolling Elo state (sequential) |
| `sequential_bayes/update_{player,team,matchup_cell}_posteriors.py` | `betting.{player,team}_sequential_posteriors`, `matchup_cell_sequential_posteriors` | sequential-Bayes chains (not idempotent per date) |
| `eb_priors/compute_{bullpen,starter,lineup,archetype}_posteriors.py`, `fit_park_priors.py` | `betting.eb_*`, `mart_player_archetype_posteriors`, `eb_park_factors_raw` | EB prior state (Story A2.11 — mostly dbt now) |
| `scd2_writer.py`, `backfill_{lineup_state,market_features}_scd2.py` | SCD-2 state tables | SCD-2 state |

> Note: most EB posteriors are already dbt models (A2.11) and their **outputs** are S3-mirrored as W5/W8a precursors. The Snowflake STATE tables stay; their S3 read-mirrors already exist.

### 🚫 NOT W11 (owned by sibling W9-tail — do not touch)

The sub-model **signal generators** (`generate_{run_env,offense,starter,starter_ip,bullpen,matchup,env_state,defense_quality}_signals.py` → `betting_features.*_signals`, `mart_sub_model_signals`) are model-scoring exports, not raw ingestion. They are W9-tail's `--s3` source-repoint. Listed here only so they are not double-counted as W11 work.

### ⚪ READ-ONLY / N/A
`pregame_snapshot.py` (CI audit, no DB write), `write_serving_store.py` (READ SF/DuckDB → WRITE DynamoDB/S3 only, no SF write), `check_data_freshness.py`.

---

## §2 — FEATURE STRAGGLERS + 2 FANGRAPHS RESIDUALS (export-mirrored today → make NATIVE on S3)

These are dbt models the W8b aggregator reads. Today they are read from the **W7b-1 export mirror** (`export_features_to_s3.py` / `export_w8b_precursors_to_s3.py`), not built natively on S3. W11 makes each a dual-branch DuckDB model so the export bridge drops.

| Model | Reads today | W11 action |
|---|---|---|
| `feature_pregame_umpire_features` + `feature_pregame_umpire_status` | `stg_statsapi_umpire_game_log`/`_snapshots` (SF-native) | dual-branch over migrated `umpire_game_log` S3 raw (depends on writers 7–10) |
| `feature_pregame_weather_features` + `feature_pregame_weather_status` | `weather_raw` + SCD-2 status (SF-native) | dual-branch over migrated `weather_raw` S3 (depends on writers 11–12) |
| `feature_pregame_public_betting_features` + `feature_pregame_public_betting_status` | `stg_actionnetwork_public_betting_snapshots` (SF-native) | dual-branch over migrated `public_betting_raw` S3 (depends on writer 3) |
| `feature_pregame_meta_model_features` (W9 aggregator tail) | mix of W6 marts (dual-branch already) + SF stg | no direct action — inherits its parents' branches once they cut over |
| `stg_fangraphs__zips_pitching` | `source('fangraphs','fg_zips_pitching_raw')` — **SF-native** (S3 claim NOT confirmed) | add duckdb branch over `fg_zips_pitching_raw` S3 parquet (verify/export the raw first) |
| `fct_fangraphs_pitching_analytics` | `stg_fangraphs__stuff_plus` + `stg_fangraphs__zips_pitching` (both SF) | dual-branch once both stg parents are S3; currently W8b-export-mirrored |

> ⚠ **Discrepancy to resolve:** the story says `fg_zips_pitching_raw` is "already in S3," but the audit found `stg_fangraphs__zips_pitching` reads SF-native only and neither residual is in `W4_TABLES`. Confirm whether the raw parquet exists (export_w4_raw) before building the duckdb branch.

---

## §3 — INC-23 `--w3pre` WIRING — ✅ DONE THIS SESSION (gated default-OFF)

**Symptom:** `mart_derivative_closes` topped out at ~Apr-1 (E13.14 leans on it).
**Root cause:** the daily `run_w1_lakehouse_op` runs `run_w1_lakehouse.py --w6`, which **registers** `stg_derivative_odds` as a view over the existing parquet but never **rebuilds** it. Only `--w3pre` (`_build_w3pre`) rebuilds that parquet from `lakehouse_raw/derivative_odds_raw/`, and the daily op re-exports only `monthly_schedule`, never `derivative_odds_raw`, and never passes `--w3pre`.

**Fix (`pipeline/ops/daily_ingestion_ops.py`):** new gate `_w3pre_daily_on()` (env `W11_W3PRE_DAILY`, default OFF). When ON, `run_w1_lakehouse_op`:
1. `export_odds_raw_to_s3.py --source derivative_odds_raw --since <7d>` (recurring bridge; 7-day bounded `--since` = INC-20-safe per-day partitions, idempotent `overwrite_partition`).
2. `run_w1_lakehouse.py --w3pre --w6` (rebuild `stg_derivative_odds` from fresh raw → `--w6` builds `mart_derivative_closes` from it).
The downstream `refresh_w1_external_tables_op` (no-arg) already refreshes both `stg_derivative_odds` (W3PRE_TABLES) and `mart_derivative_closes` (W6_TABLES), so the chain is complete. Mirrors the proven `_schedule_lakehouse_intraday` pattern. `_build_w3pre` defensively SKIPs a source with no raw parquet → can't fail the HALT op.

**Operator must:** (a) one-time gap-fill `export_odds_raw_to_s3.py --source derivative_odds_raw` (full history, >1 min) to fill Apr→now, (b) verify derivative capture is actually running (was a Railway cron — INC-16 decommissioned Railway; confirm it's on the box), (c) set `W11_W3PRE_DAILY=1` after a box run validates `mart_derivative_closes` is fresh.

---

## §4 — PER-SOURCE MIGRATION PLAN (sequencing for parallel sub-sessions)

Each migrated source is an INDEPENDENT sub-session following the template (`ingest_statcast_to_s3.py` write pattern + the `append_raw_rows_lakehouse` dispatcher for VARIANT-JSON sources). Per-source steps:
1. Writer → S3 (use `araw_lh` for JSON-VARIANT sources / `make_s3_client()` + DuckDB COPY for typed; **never** `aws_access_key_id=os.environ.get(...)`).
2. Apply INC-20 retention at the source (latest-per-period, not unbounded snapshots).
3. Add a `stg_*` duckdb branch + external-table DDL (`generate_w11_external_tables.py`) + a `W11_TABLES` dict in `refresh_w1_external_tables.py` (own dict — do not clobber W9's).
4. `parity_check_w11_<source>.py` vs the Snowflake raw.
5. Per-source flag (default-OFF) + a **real box run** (serialized with the sibling).
6. Drop the Snowflake raw + the export bridge.

**Recommended wave order (cheapest/safest → serving-critical):**
- **Tier A (cheap, isolated):** #20–21 fangraphs (`araw`→`araw_lh`, one-line flip), #13 oaa, #14 sprint_speed, #15 catcher_framing, #18 savant_park_factors, #16 transactions. These are WARN-tier peripheral; lowest blast radius. Good first sub-sessions.
- **Tier B (umpire cluster — migrate the 4 writers together):** #7–10 all share `statsapi.umpire_game_log` → one S3 raw + one stg dual-branch + the `feature_pregame_umpire_*` straggler (§2) in the same sub-session.
- **Tier C (weather):** #11–12 + the `feature_pregame_weather_*` straggler.
- **Tier D (public betting):** #3 + the `feature_pregame_public_betting_*` straggler.
- **Tier E (serving-coupled — last, careful):** #5 statsapi `schedule`/#6 `venues` (lineups → matchup features; bridge already exists, flip the writer), #4 parlay_api (live odds), #2 odds_snapshots_historical, #1 derivative (bridge done §3; flip the live writer to retire the bridge). #17 savant_ingestion VERIFY-then-retire. Player-profiles (#PARTIAL) flip.
- **Defer / decide:** #19 score_playing_time (model output, not ingest — operator decision).

---

## §5 — WHAT STAYS ON MINIMAL SNOWFLAKE (so "complete" is unambiguous)

After W11, Snowflake retains ONLY:
- **Cortex** `betting_ml.daily_model_predictions` + the pick-narrative Cortex `COMPLETE()` path.
- **Stateful model-state:** `team_elo_history`; `{player,team}_sequential_posteriors` + `matchup_cell_sequential_posteriors`; the EB posterior state tables (`eb_*`, `mart_player_archetype_posteriors`, `eb_park_factors_raw`); SCD-2 state tables (`feature_pregame_lineup_state`, market-features SCD-2, `mart_sub_model_signals`).

Everything else (every raw feed) is S3. ⇒ The E11.1 decommission is COMPLETE modulo this deliberate keep.

---

## §7 — IMPLEMENTED THIS SESSION (Tier A end-to-end, code-complete + CI-green, default-OFF)

**All 7 Tier-A writers flipped** to a gated Snowflake→S3 dual-write — gated by the W11-SPECIFIC env
`W11_RAW_WRITE_MODE` (snowflake | both | s3; default `snowflake` = unchanged). ⚠️ This is a SEPARATE
env from the shared `LAKEHOUSE_RAW_WRITE_MODE` (which odds already runs at `s3`/`both`) — reusing the
shared one would have flipped these writers to S3-only on deploy, starving the still-SF-reading marts.
Guarded by `test_w11_write_mode_independent_of_shared_odds_env`.
- JSON-VARIANT (dispatcher `append_raw_rows_lakehouse`): `ingest_fangraphs_stuff_plus.py`,
  `ingest_fangraphs_hitting_leaderboard.py`.
- Typed/bespoke (leg-gated `lakehouse_write_legs(w11_write_mode())` + `write_raw_rows_s3`):
  `ingest_transactions.py`, `ingest_savant_park_factors.py`, `ingest_oaa.py` (mirror STAMPS `loaded_at`
  — the mart's dedup key, absent from the record dict), `ingest_sprint_speed.py` (mirror LOWERCASES the
  UPPERCASE df keys + stamps `ingestion_timestamp`), `ingest_catcher_framing.py` (mirror ADDS
  `snapshot_date`, passed separately to the SF write).

**Shared W11 infra (covers all 7):** `scripts/utils/lakehouse_raw_writer.py` (+7 RAW_SOURCES,
`lakehouse_write_legs`, `w11_write_mode`); `scripts/export_w11_raw_to_s3.py` (SF→lakehouse_raw bridge);
`scripts/parity_check_w11.py` (raw-tier parity); `scripts/tests/test_w11_ingestion_lakehouse.py` (5 tests).

**NOT done (deliberately deferred to the operator's box-gated CUTOVER — `extract_duckdb_sql` can't gate
a model jinja-conditionally, and the read repoint must follow a GREEN parity):** per-source repoint of
the stg/mart duckdb branch `lakehouse_loc → lakehouse_raw_loc`, the SF-leg retirement (`s3`), the SF raw
DROP, and the per-source export-bridge removal from `export_w4/w5_raw_to_s3.py`.

**Per-source CUTOVER sequence (operator, box, serialized with the W9-tail run):**
1. `export_w11_raw_to_s3.py [--source X]` (full history → lakehouse_raw/) — >1 min, operator.
2. `parity_check_w11.py [--source X]` → GREEN (raw mirror == Snowflake raw).
3. Repoint that source's stg/mart duckdb branch `lakehouse_loc("X") → lakehouse_raw_loc("X")`; rebuild
   `--w4`/`--w5`; verify the feature is non-null (per-ROW fetch, not just parity).
4. Set `W11_RAW_WRITE_MODE=both` → confirm the LIVE writer's mirror matches (re-run parity).
5. `W11_RAW_WRITE_MODE=s3` → DROP the SF raw table + remove the source from `export_w4/w5_raw_to_s3.py`.

## §6 — Shared-file touch list (for the sibling/operator to rebase onto)
- `pipeline/ops/daily_ingestion_ops.py` — **W11 touched**: added `_w3pre_daily_on()` helper + gated derivative export + `--w3pre` arg inside `run_w1_lakehouse_op` (W-series op, not a W9 op). No edits to W9's signal ops.
- `scripts/utils/lakehouse_raw_writer.py` — **W11 touched**: +7 RAW_SOURCES, `lakehouse_write_legs`, `w11_write_mode`/`W11_WRITE_MODE_ENV`. Additive; W9 doesn't touch this file.
- 7 ingestion writers (`ingest_fangraphs_*`, `ingest_transactions`, `ingest_savant_park_factors`, `ingest_oaa`, `ingest_sprint_speed`, `ingest_catcher_framing`) — gated dual-write (default-OFF).
- `scripts/export_w11_raw_to_s3.py`, `scripts/parity_check_w11.py`, `scripts/tests/test_w11_ingestion_lakehouse.py` — new (W11).
- `quant_sports_intel_models/baseball/edge_program/E11_1_W11_ingestion_audit_2026-06-30.md` — this doc (new).
- **NO dbt model files touched** (the repoints are the operator cutover) → the dbtf-Build CI gate is not triggered by this diff.
- (future sub-sessions for the model repoints will add: a `W11_TABLES` dict in `refresh_w1_external_tables.py` only where a source's stg OUTPUT isn't already a W4/W5 external table.)
