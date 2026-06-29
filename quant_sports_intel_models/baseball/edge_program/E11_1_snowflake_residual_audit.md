# E11.1 — Snowflake RESIDUAL / TAIL audit → the W8+ wave plan

**Date:** 2026-06-29 · **Type:** READ-ONLY audit (no code changed) · **Snapshot:** `dev` branch (~`main`) · **Tooling:** grep/codebase + Snowflake MCP (read-only `information_schema`)

**Why this exists:** W7a's handoff revealed *"Cortex-only is NOT one wave away."* There's a real tail still on Snowflake that was only loosely listed. This is the authoritative inventory — every remaining Snowflake read, write, and import-time coupling, status-tagged — plus a sequenced W8+ wave plan with dependencies, effort/risk, and the honest *"true Cortex-only is N more waves"* picture.

> **Concurrency note:** W7b (feature/serving reader repoint) is migrating in parallel. Items it owns are tagged **🔵 W7b-in-scope** so they are *not* double-counted in the W8+ waves below. E9.36 (team page) and E9.37 (line-movement series) are app-only and touch no Snowflake migration.

**Status legend:** ✅ already-S3 · 🔵 W7b-in-scope · 🔴 TAIL (still Snowflake, not yet migrated) · 🟢 Cortex-sanctioned

---

## 0. Executive summary

| Metric | Value |
|---|---|
| Top-level `scripts/` using `snowflake.connector` | **47** |
| Central read helper | `betting_ml.utils.data_loader.get_snowflake_connection()` (lazy; env-with-defaults) |
| dbt models total | **128** |
| dbt models already S3-backed (carry a `w*_lakehouse` tag) | **74** |
| dbt models with a DuckDB/`read_parquet` branch | **77** |
| dbt models still **native** Snowflake (no lakehouse branch) | **~54** |
| `feature_pregame_*` models (the serving feature layer) | **21** — only **2** migrated → **19 native = W7b+ tail** |
| Live Snowflake external tables (`lakehouse_ext`, S3-backed) | **76** |
| Live native `betting_features` tables (feature layer) | **33 tables + 1 view** (almost entirely native) |
| Genuinely Cortex-sanctioned scripts | **1** (`generate_pick_narratives.py`, two copies) |

**Headline:** The lakehouse migration so far (W1–W7a) moved the **pitch-derived marts, odds/CLV marts, and cluster assignments** to S3 (76 external tables, 74 tagged dbt models). What remains is everything *upstream and downstream of those marts*: the **raw-ingestion substrate** the lakehouse is built FROM, the **feature layer** (`betting_features`, ~19 native `feature_pregame_*` + signal tables), the **sub-model signal generators**, the **EB / sequential-Bayes / Elo stateful builders**, the **monitoring sensors**, and the **serving-state table** (`daily_model_predictions`). True Cortex-only is **~6 substantive waves** out, and the raw-ingestion-→-S3-native rewrite is the long pole.

---

## 1. READS — Snowflake consumers

### 1a. Serving / request path (HALT-tier) — 🔵 W7b-in-scope

| Component | Reads (Snowflake) | Status | Note |
|---|---|---|---|
| `scripts/predict_today.py` | feature store `betting_features.feature_pregame_game_features`, EB dbt posteriors, `betting_ml.daily_model_predictions` | 🔵 W7b | Primary scoring; reads feature matrix at serve time. **Writes** `daily_model_predictions` (§2). |
| `scripts/write_serving_store.py` | `daily_model_predictions`, `mart_game_results`, `mart_odds_outcomes`, `mart_odds_line_movement`, `prediction_log` | 🔵 W7b | Populates Railway PG + S3 serving store. **Import-time SF coupling** (§4). |
| `scripts/write_api_cache.py` | `daily_model_predictions`, `mart_game_results`, `mart_odds_outcomes`, `prediction_log` | 🔵 W7b | Post-predict S3 JSON cache writer. |
| `app/backend/routers/picks.py` | `daily_model_predictions`, `mart_clv_labeled_games`, `stg_statsapi_games`/`_lineups_wide`/`_probable_pitchers`, `mart_odds_outcomes`/`_line_movement`, several `feature_pregame_*` | 🔵 W7b (last-resort) | **Fallback tier only**: DynamoDB → S3 → Snowflake. INC-18 keep+flag for the `stg_*` game-state reads (no clean post-game mart equiv). W7b converts last-resort → direct-S3. |
| `app/backend/routers/performance.py` | `mart_bankroll_state` (primary), `mart_clv_labeled_games` (fallback) | 🔵 W7b (last-resort) | Behind DynamoDB/S3 cache. |
| `app/backend/routers/bets.py` | `stg_statsapi_games` (auto-void game-state) | 🔵 W7b (last-resort) | INC-18 keep+flag. |
| `app/backend/routers/admin.py` | `betting_ml.model_registry` (metadata) | 🔴 TAIL | Non-critical admin read. |
| `app/backend/services/snowflake.py` | connection service (role `CREDENCE_API_RO`) | 🔵 W7b | Lazy-instantiated; **no import-time SF coupling** in backend. |

> Backend finding: **no genuine request-time Snowflake-only dependency** — every hot path is DynamoDB→S3 cached, Snowflake is the last-resort tier. W7b removes the last-resort by pointing the fallback at S3 directly.

### 1b. dbt `source()` resolution

| Source | DB.schema | Backing | Status |
|---|---|---|---|
| `lakehouse_clusters` | `baseball_data.lakehouse_ext` | **S3 external tables** | ✅ (W7a) — `batter_clusters`, `pitcher_clusters` |
| `savant` | `baseball_data.savant` | Snowflake native | 🔴 TAIL — `stg_batter_pitches`/`ref_players` already exported to S3 (W1); native raw retained (raw-ingestion wave) |
| `statsapi` | `baseball_data.statsapi` | Snowflake native | 🔴 TAIL — games/lineups/venues/umpires/weather/profiles/transactions raw |
| `oddsapi` | `baseball_data.oddsapi` | Snowflake native | 🔴 TAIL — live; W6 marts S3-backed but raw still native |
| `parlayapi` | `baseball_data.parlayapi` | Snowflake native | 🔴 TAIL — decommissioned feed (E11.6), cold archive |
| `fangraphs` | `baseball_data.fangraphs` | Snowflake native | 🔴 TAIL — append-only raw |
| `actionnetwork` | `baseball_data.actionnetwork` | Snowflake native | 🔴 TAIL — public-betting raw |
| `external` | `baseball_data.external` | Snowflake native | 🔴 TAIL — `oaa_team_season_raw` (static) |
| `betting` / `betting_ml` / `betting_features` | `baseball_data.*` | Snowflake native (mixed) | 🔴 TAIL — marts/features/serving-state; 74/128 models now `lakehouse_ext` views |

### 1c. Monitoring sensors (Dagster) — all read via `get_snowflake_connection()` — 🔴 TAIL

`statcast_freshness_sensor`, `lineup_monitor_sensor`, `odds_freshness_alert_sensor`, `odds_current_rebuild_sensor` (direct `snowflake.connector`), `pregame_alert_sensor`, `clv_alert_sensor`, `schedule_freshness_alert_sensor`, `morning_watchdog_sensor`, `conviction_pick_alert_sensor`, `model_health_alert_sensor`. They read `stg_statsapi_games`, `daily_model_predictions`, `mart_odds_outcomes`, `mart_game_results`, `oddsapi.*` for freshness/alert decisions. **Plus** the inline op `pipeline/ops/intraday_ops.py::check_games_today` opens its own `snowflake.connector` connection to count today's games (gates the odds-snapshot job).

### 1d. Offline training / research reads (the broad, low-priority class) — 🔴 TAIL

~180 files under `betting_ml/scripts/**` read the warehouse via `data_loader`/`load_features`. These are operator-run training/ablation/bake-off scripts — **not on any recurring or serving path**. They migrate opportunistically (lowest risk/priority); most simply need their `load_*` calls to accept the S3/DuckDB feature parquet once the feature layer is on S3 (Wave 8). Not enumerated individually here — they are a single class that resolves for free once `data_loader` gains an S3 read mode.

---

## 2. WRITES — Snowflake materializers

### 2a. Raw-ingestion writers (⭐ the deep one — the substrate the lakehouse is built FROM) — 🔴 TAIL

Recurring (Dagster-wired) ingestion → **writes Snowflake raw** → a separate `export_*_to_s3.py` bridge copies it to S3 → DuckDB builds the marts. So the lakehouse is *downstream* of Snowflake raw. S3-native ingestion = make each ingester write parquet directly (deleting both the Snowflake raw schema AND the export bridge).

| Script | Writes (Snowflake) | Recurring? |
|---|---|---|
| `savant_ingestion.py` | `savant.batter_pitches` | daily + catchup |
| `ingest_statsapi.py` | `statsapi.monthly_schedule`, `statsapi.venues_raw` | daily + intraday |
| `odds_api_ingestion.py` | `oddsapi.mlb_events_raw`, `oddsapi.mlb_odds_raw` | Railway cron (30 min) |
| `parlayapi_ingestion.py` | `parlayapi.mlb_{events,odds,matches,line_movement}_raw` | intraday (feed decommissioned) |
| `ingest_weather.py` | `statsapi.weather_raw` | daily + intraday |
| `ingest_umpires.py` / `ingest_umpire_scorecards.py` | `statsapi.umpire_game_log` | daily + lineup path |
| `ingest_oaa.py` | `external.oaa_team_season_raw` | daily (soft) |
| `ingest_sprint_speed.py` | `savant.sprint_speed_raw` | daily |
| `ingest_catcher_framing.py` | `savant.catcher_framing_raw` | daily |
| `ingest_fangraphs_stuff_plus.py` / `ingest_fangraphs_hitting_leaderboard.py` | `fangraphs.fg_*_raw` | Sunday |
| `ingest_transactions.py` | `statsapi.player_transactions` | daily |
| `ingest_player_profiles.py` | `statsapi.player_profiles_raw` | weekly |
| `ingest_actionnetwork_betting.py` | `actionnetwork.public_betting_raw` | daily |
| *(one-shot backfills)* `ingest_umpires_historical.py`, `backfill_historical_odds_snapshots.py`, `backfill_observed_weather.py`, `backfill_umpire_assignments.py` | various raw | one-off |

**S3-export bridge** (reads Snowflake raw → writes S3 parquet; ✅ they are the migration glue, but they exist *because* ingestion still lands in Snowflake first): `export_odds_raw_to_s3.py`, `export_statcast_to_s3.py`, `export_ref_players_to_s3.py`, `export_w4_raw_to_s3.py`, `export_w5_raw_to_s3.py`, `export_w6_raw_to_s3.py`. **The S3-native exception that proves the pattern:** `ingest_statcast_to_s3.py` already writes Savant → S3 parquet directly with no Snowflake hop (✅). It is the template for the rest.

### 2b. dbt models materializing to Snowflake — 🔴 TAIL / 🔵 W7b

The daily/intraday/sensor `dbt run` ops all target `baseball_betting_and_fantasy` (Snowflake). ~54 of 128 models still materialize native. Two clusters matter:

- **Feature layer (W7b + Wave 8):** 19 of 21 `feature_pregame_*` models still native — `feature_pregame_game_features(_raw)`, `_team_features`, `_starter_features`, `_lineup_features`, `_umpire_features`, `_odds_features`, `_market_features`, `_weather_features`, `_park_features`, `_public_betting_features`, `_meta_model_features`, `_sub_model_signals`, the `*_status` SCD-2 promotions, plus `feature_batter_archetype_matchups` / `feature_pitcher_cluster_matchups` (these last two already read `lakehouse_clusters` for inputs but still **materialize** to Snowflake). Only 2 carry a lakehouse branch.
- **EB posterior dbt models (Wave 8/10):** `eb_starter_posteriors`, `eb_batter_posteriors_raw`, `eb_bullpen_posteriors`, `eb_bullpen_team_posteriors`, `int_bullpen_ali_by_season` (all in `dbt/models/eb_posteriors/`). **Correction to W7a's tail list:** these are now **dbt models**, not the Python `compute_*_posteriors.py` scripts (those were superseded by Story A2.11 and are unwired/research-only — see §3).

### 2c. Sub-model signal generators (MERGE/SCD-2 to Snowflake) — 🔴 TAIL (except matchup 🔵)

Daily Dagster ops; each scores `_recent_completed_dates()` and writes via `betting_ml/scripts/scd2_writer.py` (a Snowflake-coupled SCD-2 helper) into `betting.mart_sub_model_signals` or the `betting_features.*_signals` tables.

| Generator | Writes | S3 branch? | Status |
|---|---|---|---|
| `generate_run_env_signals.py` | `mart_sub_model_signals` | no | 🔴 TAIL |
| `offense_v2/generate_offense_signals.py` | `betting_features.offense_v2_signals` | no | 🔴 TAIL |
| `starter_v1/generate_starter_signals.py` | `betting_features.starter_suppression_signals` | no | 🔴 TAIL |
| `starter_v1/generate_starter_ip_signals.py` | `betting_features.starter_ip_signals` | no | 🔴 TAIL |
| `generate_bullpen_signals.py` | `mart_sub_model_signals` | no | 🔴 TAIL |
| `generate_env_state_signals.py` | `mart_sub_model_signals` | no | 🔴 TAIL |
| `generate_defense_quality_signals.py` | `mart_sub_model_signals` | no | 🔴 TAIL |
| `eb_priors/generate_matchup_signals.py` | `mart_sub_model_signals` | **yes** (`--s3`, W7a, gated OFF) | 🔵 W7b — reads cluster/posterior/pitch substrate from S3; **write still Snowflake** |

### 2d. EB / sequential / Elo stateful builders — 🔴 TAIL (except archetype + matchup-cell 🔵)

| Builder | Writes (Snowflake MERGE) | S3 branch? | Wired? | Status |
|---|---|---|---|---|
| `eb_priors/compute_archetype_posteriors.py` | `mart_player_archetype_posteriors` | **yes** (`--s3`, W5b/W7a, gated) | daily (`update_archetype_posteriors_op`) | 🔵 W7b |
| `sequential_bayes/update_matchup_cell_posteriors.py` | `matchup_cell_sequential_posteriors` | **yes** (`--s3`, W7a, gated) | daily | 🔵 W7b |
| `sequential_bayes/update_player_posteriors.py` | `player_sequential_posteriors` | no | daily | 🔴 TAIL — stateful sequential chain |
| `sequential_bayes/update_team_posteriors.py` | `team_sequential_posteriors` | no | daily | 🔴 TAIL — stateful sequential chain |
| `betting_ml/scripts/compute_elo.py` | `betting.team_elo_history` | no | daily + catchup | 🔴 TAIL — direct `snowflake.connector`; stateful MERGE |
| `eb_priors/fit_granular_park_priors.py` | `mart_park_factors_granular` (→ S3) | **yes** (`--s3`, W4) | opt-in | ✅/🔵 |
| `clustering/*` + `batter_clustering/cluster_batters.py` + `pitcher_clustering/cluster_pitchers.py` | `batter_clusters`/`pitcher_clusters` | **yes** (`--s3`/`--seed`, W4/W5b) | daily (gated) | 🔵 W7b |

### 2e. SCD-2 / state / settlement / monitoring writers — 🔴 TAIL

`backfill_lineup_state_scd2.py` → `betting_features.feature_pregame_lineup_state`; `backfill_market_features_scd2.py` → `betting_features.feature_pregame_market_features`; `backfill_prediction_log.py` → `betting.prediction_log`; `update_pipeline_status.py` → `betting_ml.pipeline_status`; `compute_model_health.py` → `betting_ml.model_health_log`; `lineup_monitor.py` → `config.lineup_monitor_state`; `settle_user_bets.py` (reads `stg_statsapi_games`, writes DynamoDB); `generate_pick_narratives.py` UPDATE `daily_model_predictions.pick_narrative` (Cortex — §5).

### 2f. The serving-state table — `daily_model_predictions` (`betting_ml`) — 🔴 TAIL (serving-coupled)

The hub of the serving path: `predict_today.py` **writes** it, Cortex narratives **UPDATE** it, `write_serving_store.py`/`write_api_cache.py`/`mart_prediction_clv` **read** it. Migrating it off Snowflake is coupled to both the serving wave AND the Cortex pin (§5) — it cannot simply become an S3 parquet because Cortex must read it in-warehouse.

---

## 3. Validating / expanding W7a's flagged tail

W7a's handoff listed: *"sub-model signal generators (bullpen/run_env/defense/env_state/starter/offense), EB posterior builders (compute_starter/bullpen/lineup_posteriors, fit_park_priors), compute_elo, raw ingestion, monitoring sensors."* Validation:

| W7a claim | Verdict | Correction / expansion |
|---|---|---|
| 6 sub-model generators on Snowflake | ✅ confirmed | Actually **7** no-S3 generators (run_env, offense_v2, **starter**, **starter_ip**, bullpen, env_state, defense_quality); matchup has gated `--s3`. All write via `scd2_writer.py`. |
| EB builders `compute_{starter,lineup,bullpen}_posteriors.py` | ⚠️ **stale** | These **Python scripts are unwired/superseded** (Story A2.11). The live EB posteriors are **dbt models** (`eb_starter_posteriors`, `eb_batter_posteriors_raw`, `eb_bullpen_posteriors`, `eb_bullpen_team_posteriors`, `int_bullpen_ali_by_season`) built in `dbt_build_bullpen_posteriors_op` / `dbt_umpire_feature_rebuild`. ⇒ this tail is a **dbt-materialization** problem (Wave 8), not a Python-script one. |
| `fit_park_priors` | partial | `fit_granular_park_priors.py` already has `--s3` (W4). `fit_park_priors.py` and the other `fit_*_priors.py` are unwired/research. |
| `compute_elo` | ✅ confirmed | Wired daily + sensor; direct `snowflake.connector`; no S3 branch. |
| raw ingestion | ✅ confirmed | ~20 writers (§2a); the deepest item. |
| monitoring sensors | ✅ confirmed | 10 sensors + `check_games_today` inline op (§1c). |
| **MISSED by W7a** | ➕ new | **(1)** `sequential_bayes/update_player_posteriors.py` + `update_team_posteriors.py` (stateful chains, no S3). **(2)** SCD-2 state writers `backfill_lineup_state_scd2.py` / `backfill_market_features_scd2.py`. **(3)** the serving-state table `daily_model_predictions` itself (§2f) + `prediction_log`, `pipeline_status`, `model_health_log`, `team_elo_history`, `*_sequential_posteriors` — the **Snowflake-resident model STATE tables**. **(4)** `settle_user_bets.py`. **(5)** the **import-time `pipeline.resources` ENV coupling** (§4). **(6)** the ~180 offline training scripts (low-pri class, §1d). |

---

## 4. Import-time Snowflake coupling (a separate cleanup class)

The **only true import-time ENV coupling**: `pipeline/resources/__init__.py` line 42-48 constructs `SnowflakeResource(account=os.environ["SNOWFLAKE_ACCOUNT"], ...)` at **module import** (bracket access → `KeyError` if unset). `pipeline/__init__.py` imports it to build the Dagster `Definitions`, so **importing any `pipeline.*` submodule executes it** and requires the full Snowflake env to be present.

- **Confirmed instance (E9.37/W7a):** `scripts/write_serving_store.py` must `load_dotenv()` **before** `from pipeline.utils.alerting import send_alert` and wrap it in a broad `try/except` precisely because the transitive `pipeline.resources` import reads `os.environ["SNOWFLAKE_ACCOUNT"]` at import (its own comment, lines 58-67).
- **Scope:** narrow — no `scripts/**` module imports `pipeline.resources` directly; the coupling bites only modules that import the `pipeline` package (Dagster code-location load + the few scripts that import `pipeline.utils.*`).
- **Distinct, softer class:** ~all ingestion/serving scripts + `betting_ml.utils.data_loader` + `scd2_writer.py` `import snowflake.connector` at module top. That needs the **package installed**, not the **env** — `data_loader._connect()` uses `os.environ.get(..., default)` lazily, so importing it is safe. Not a blocker; noted for completeness.
- **Cleanup:** make `pipeline.resources` lazy (build the `SnowflakeResource` inside a factory / use `EnvVar` instead of eager `os.environ[...]`) so importing `pipeline` never requires Snowflake env. Cheap; can ride any wave.

---

## 5. Cortex — the only sanctioned Snowflake use (and the pin it leaves)

`generate_pick_narratives.py` (two copies: `scripts/` and the wired `betting_ml/scripts/`) is the **sole genuinely Snowflake-only** dependency — it calls **Snowflake Cortex `COMPLETE()`** (a warehouse-native LLM) to write `pick_narrative`. Nothing else claims Cortex. Confirmed: only these two files reference `CORTEX`/`COMPLETE(`.

**The honest pin:** Cortex reads `pick_explanation` and writes `pick_narrative` **on `daily_model_predictions` inside Snowflake**. So "Cortex-only" is not "zero data in Snowflake" — it requires that predictions slice to be query-able in-warehouse. Two end-state options:

1. **Pragmatic Cortex-only:** keep a *minimal* `daily_model_predictions` in Snowflake purely as the Cortex I/O surface; everything else (raw, marts, features, signals, state) lives in S3. The warehouse runs only the narrative step.
2. **Zero-Snowflake:** replace Cortex with the **Anthropic API** (Claude) for narratives. Then `daily_model_predictions` can be S3/PG and Snowflake is fully decommissioned. (Aligns with the house default of using Claude for AI features; removes the last warehouse cost line.)

Recommendation: treat the Cortex→Claude swap as its own small wave (Wave 14) — it is the literal precondition for *full* decommission, independent of all the data waves.

---

## 6. Proposed W8+ wave plan

> **W7b boundary (in flight, not counted below):** `feature_pregame_*` DuckDB branches + `predict_today`/`write_serving_store`/`write_api_cache` reader repoint + backend last-resort → direct-S3 + `mart_player_profile_identity` + the 2 staging (`stg_statsapi_probable_pitchers`, `stg_statsapi_lineups_wide`) → S3 + flipping the gated `--s3` paths ON (matchup signals, archetype/matchup-cell posteriors, clusters). Everything 🔵 above completes with W7b.

| Wave | Scope | Depends on | Effort | Risk |
|---|---|---|---|---|
| **W8 — Feature-layer dbt → S3** | The 19 native `feature_pregame_*` + the EB-posterior dbt models (`eb_*`, `int_bullpen_ali_by_season`) + the signal tables → DuckDB build + `lakehouse_ext` views (the W6 dual-branch pattern). This is the serving feature store. | W7b (feature reads on S3); upstream marts (W1–W6 ✅) | **HIGH** | **HIGH** (serving-critical; SCD-2 `*_status` promotions are fiddly) |
| **W9 — Sub-model signal generators → S3** | The 7 no-S3 generators + `scd2_writer.py`: add the W7a `--s3` read pattern AND an **S3-native SCD-2 write** target for `mart_sub_model_signals` / `*_signals`. | W8 (read feature marts from S3) | **HIGH** | **MED-HIGH** (W7a lesson: `--s3` *write/accumulate* paths are bug-prone — exercise before trusting) |
| **W10 — Stateful builders (sequential / Elo)** | `update_player_posteriors`, `update_team_posteriors` (sequential chains), `compute_elo` (`team_elo_history`): migrate the accumulating MERGE state to S3/DuckDB (or Railway PG). The hardest *write* semantics. | W8 (read `mart_game_results`/pitch from S3 ✅ already) | **MED-HIGH** | **HIGH** (stateful accumulate = the W7a posterior-wipe bug class; consider PG for mutable state) |
| **W11 — Raw-ingestion → S3-native** ⭐ | The ~20 ingestion writers write parquet **directly to S3** (template: `ingest_statcast_to_s3.py`), retiring the Snowflake raw schemas (`savant`/`statsapi`/`oddsapi`/`parlayapi`/`fangraphs`/`actionnetwork`/`external`) **and** the `export_*_to_s3.py` bridges; repoint the `stg_*` source models to DuckDB over the new raw parquet. Per-source, independently shippable. | per-source `stg_*` DuckDB branches | **VERY HIGH** | **HIGH** (changes the foundation; dedup/idempotency + the W2 stale-year-parquet dupe class per source) |
| **W12 — Monitoring sensors + freshness ops → S3** | 10 sensors + `check_games_today` inline op + freshness/health scripts (`check_data_freshness`, `check_prediction_coverage`, `check_signal_freshness`, `compute_model_health`, `update_pipeline_status`, `lineup_monitor`, `pregame_snapshot`) repoint reads to S3/DuckDB. | W8–W11 (the objects they watch on S3) | **MED** | **LOW-MED** (read-only; many touch points, simple) |
| **W13 — Serving-state + settlement + import-coupling** | `daily_model_predictions` + `prediction_log`/`pipeline_status`/`model_health_log` to S3/PG; `settle_user_bets`; the SCD-2 state writers; the `pipeline.resources` lazy-init cleanup. (Gated by the Cortex pin — see W14.) | W8–W12 | **MED-HIGH** | **HIGH** (serving state; Cortex coupling on `daily_model_predictions`) |
| **W14 — Cortex → Claude (full-decommission precondition)** | Swap Cortex `COMPLETE()` for the Anthropic API in `generate_pick_narratives.py`, freeing `daily_model_predictions` from the warehouse. Then decommission the Snowflake account/warehouse. | W13 (predictions off Snowflake) | **LOW-MED** | **LOW** (isolated; one script + a model call) |

**Sequencing logic:** W8→W9→W10 follow the data-flow downstream (marts→features→signals→state). **W11 (raw ingestion) is independent and can run in parallel** with W8–W10 per-source, but it is the long pole and the only thing that lets the **raw schemas + warehouse** actually go away. W12 (sensors) and W13 (serving state) come last because they observe/serve everything above. W14 is the literal switch for *full* Cortex-only/zero-Snowflake.

**Quick-win cleanup (any time, no dependency):** the `pipeline.resources` lazy-init fix (§4) and retiring the one-shot backfill/parity scripts as each wave lands.

---

## 7. The honest "true Cortex-only is N more waves" picture

- **After W7b:** the marts + clusters + the gated `--s3` consumers are on S3, but the **feature layer, signal generators, stateful builders, raw ingestion, sensors, and serving-state are all still Snowflake.** Cortex-only is **not** one wave away.
- **Realistic count:** **~6 substantive waves (W8–W13)** of data/compute migration, **plus W14** (Cortex→Claude) to reach *zero*-Snowflake. If the house accepts **pragmatic Cortex-only** (a minimal `daily_model_predictions` kept in-warehouse purely for the narrative step), the data side finishes at **W12–W13** and W11 (raw-ingestion S3-native) becomes the cost-decision gate: it's the wave that lets the raw schemas + a chunk of warehouse spend retire.
- **The long pole is W11 (raw ingestion).** Until ingestion writes S3 first, every `stg_*` and the export-bridge keep Snowflake on the critical path, and the raw schemas can't drop. It is also the most parallelizable (per-source) and the most decoupled from serving — a good candidate to start early alongside W8.
- **Biggest hidden risk** is **stateful writes** (W9 SCD-2, W10 sequential/Elo accumulate, W13 serving-state): parity checks validate *reads*, not *accumulate semantics* — the W7a posterior-wipe incident is the cautionary tale. For mutable model state, **Railway PG is likely a better target than S3 parquet** (S3 has no in-place update).

---

## 8. Operator handoff

- **AC met:** complete reads+writes+import-coupling inventory (status-tagged) ✅; W7a tail validated + expanded (stale EB-Python→dbt correction, +sequential posteriors, +SCD-2 state writers, +serving-state tables, +import-coupling) ✅; sequenced W8+ plan with dependencies/effort/risk ✅; raw-ingestion S3-native question scoped (W11, the long pole) ✅; report committed ✅.
- **No code changed, no changelog** (read-only audit, per the story).
- **`git add`:** `quant_sports_intel_models/baseball/edge_program/E11_1_snowflake_residual_audit.md`
- **Recommended next-wave order:** start **W11 (raw-ingestion → S3-native, per-source)** in parallel with **W8 (feature-layer dbt → S3)** after W7b cuts over — W8 unblocks the downstream serving chain (W9→W10→W13), W11 is the independent long pole that actually retires the Snowflake raw schemas + warehouse spend. Defer the **Cortex→Claude swap (W14)** until predictions are off Snowflake; do the cheap **`pipeline.resources` lazy-init** cleanup opportunistically.
- **Verification notes:** counts are from live `information_schema` (MCP, read-only) on 2026-06-29: `lakehouse_ext` = 76 external tables; `betting_features` = 33 tables + 1 view (feature layer ~all native); dbt = 128 models, 74 lakehouse-tagged, 77 with a DuckDB branch, 19/21 `feature_pregame_*` still native.
