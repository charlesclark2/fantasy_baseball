# MLB Quantitative Intelligence — Implementation Guide

Version: Draft 0.2
Status: Planning
Companion to: `refined_architecture_proposal.md`

---

# Overview

This guide breaks the architecture proposal into epics and tasks suitable for sprint planning.

Each epic maps to a meaningful deliverable. Tasks within each epic are sequenced where dependencies exist. Epics themselves have sequencing dependencies documented in the **Sequencing** section at the end.

---

# Sequencing Summary

```
Epic 0   (Parlay API Migration)        — Immediate. Hard deadline: 2026-06-01.
Epic 0.5 (Dagster Orchestration)       — After Epic 0 cutover passes; before Epic 1 ships to production.
Epic 1   (Market-Blind Retrains)       — Immediate. Unblocked now (run in parallel with Epic 0).
Epic 2   (Sub-Model Infrastructure)    — Start in parallel with Epic 1.
Epic 3   (Run Environment Model)       — Can start after Epic 2.
Epic 4   (Offensive Quality Model)     — Can start after Epic 2.
Epic 5   (Starter Suppression Model)   — Can start after Epic 2.
Epic 6   (Bullpen State Model)         — Can start after Epic 2.
Epic 7   (Archetype Clustering)        — Prerequisite for Epic 8.
Epic 8   (Matchup Model)               — Requires Epic 7.
Epic 9   (Signal Integration & Ablation) — Requires Epics 3–6 to have at least one signal.
Epic 10  (Totals Distribution Model)   — Requires Epics 3–6 signals; builds on Epic 9.
Epic 11  (H2H Model Retrain w/ Signals) — Requires Epic 1 complete; builds on Epic 9.
Epic 12  (CLV Meta-Model)              — Gated on 500+ live CLV games.
Epic 13  (Temporal Data Platform)      — Long-horizon infrastructure; begin Phase 10.
```

---

# Epic 0 — Parlay API Migration (Phase 0)

**Goal:** Replace The Odds API as the primary live odds data source with Parlay API before June 1, 2026. Retain all historical Odds API data in place — no deletions or schema changes to existing tables.

**Hard deadline:** 2026-06-01. Odds API credits expire 2026-05-23; cease live ingestion by then but keep the pipeline runnable in case credits are extended.

**Docs:** https://parlay-api.com/docs

---

### 0.1 — Parlay API endpoint mapping ✅

**Goal:** Map every Odds API endpoint currently in use to its Parlay API equivalent. Identify any gaps or new capabilities available.

**Output:** `quant_sports_intel_models/parlay_api_endpoint_mapping.md`

Tasks:
- [x] Document current Odds API endpoint usage: `events` and `odds` run daily via GitHub Actions; `historical-events` and `historical-odds` are manual-only backfill subcommands
- [x] Review Parlay API docs and map each endpoint to its equivalent — URL-surface compatible; base URL change only for core live endpoints
- [x] Document Parlay API capabilities not in Odds API: `/consensus`, `/ev`, `/props`, `/arbitrage`, `/live` — see Section 4 of mapping doc
- [x] Document gaps: historical endpoint path unverified (assumed same); starter-key dual-key pattern not applicable; `commenceTimeFrom` params unverified on historical

**Key findings (updated after live endpoint testing 2026-05-09):**
- Migration scope is minimal: change base URL, swap API key env var, remove dual-key fallback, update `source_system` metadata — existing Snowflake write logic is unchanged
- **Tier selected: Business plan** (1,000,000 credits/month) — sufficient for daily automated use, historical backfills, and line-movement daily ingestion (~2,250 credits/month total with line-movement enabled)
- Live endpoints (`/events`, `/odds`) verified compatible — identical response schema; adds `canonical_event_id` field
- Historical `/events` path does not exist — replaced by `/matches` endpoint with a different flat schema (scores, results, `has_odds` flag)
- Historical `/odds` verified compatible — same bookmakers/markets structure; requires `oddsFormat=american`
- Credit headers (`x-requests-used`, `x-requests-remaining`) are not present in Parlay API responses — use call-count logging in ingestion script instead
- **`/line-movement` endpoint verified** — provides full opening-to-close price history per (event × book × market) in a single call; highest-value new capability for Epic 12 (CLV meta-model)
- `/ev` and `/consensus` worth evaluating post-migration as additional CLV inputs
- See `quant_sports_intel_models/parlay_api_endpoint_mapping.md` for full details

**Pipeline snapshot awareness note:**
Any pipeline consuming `parlayapi.mlb_line_movement_raw` must account for the nested `snapshots[]` array in `raw_json`. Each top-level record represents one (event × book × market) combination; `snapshots` is an arbitrary-length array of timestamped price changes. Decide before building any staging model whether to explode snapshots for time-series features or summarize to opening/closing price only. Do not assume a flat row-per-event schema.

---

### 0.2 — Parlay API raw table DDL ✅

**Goal:** Create new Snowflake raw tables for Parlay API data. Do NOT modify existing `baseball_data.oddsapi` tables — keep them append-only and intact.

**Output:** `scripts/ddl/parlayapi_raw_tables.sql`

Tasks:
- [x] Create new schema: `baseball_data.parlayapi` — provisioned manually 2026-05-09
- [x] Design DDL for raw events table: same observability columns as `mlb_events_raw`; adds `canonical_event_id` and `call_sequence`; `x_requests_used/remaining` retained as NULL-only columns for schema symmetry
- [x] Design DDL for raw odds table: same pattern as `mlb_odds_raw`; same adjustments as events table
- [x] Design DDL for `mlb_matches_raw`: new table for `/historical/matches` endpoint (flat schema with scores, results, `has_odds`)
- [x] Design DDL for `mlb_line_movement_raw`: new table for `/line-movement` endpoint; stores full snapshots array as VARIANT; includes snapshot awareness comment
- [x] Write DDL file at `scripts/ddl/parlayapi_raw_tables.sql`
- [x] Provision tables in Snowflake — all four tables created 2026-05-09

---

### 0.3 — Parlay API ingestion script

**Goal:** Build `scripts/parlay_api_ingestion.py` mirroring the structure of `odds_api_ingestion.py`.

**Output:** `scripts/parlay_api_ingestion.py`

Tasks:
- [x] Support `events` and `odds` subcommands (live daily ingestion)
- [x] Support `historical-odds` subcommand — iterates calendar days with `date=YYYY-MM-DD` param; idempotent by (game_date, market); `--force` to re-fetch
- [x] Support `historical-matches` subcommand — one row per date, full response as VARIANT; includes scores, results, `has_odds` flag
- [x] Support `line-movement` subcommand — one call per event_id; auto-resolves event IDs from mlb_events_raw or accepts `--event-ids`; stores full snapshots array as VARIANT
- [x] Preserve same append-only pattern: every run inserts new rows with shared `load_id`
- [x] Use same Snowflake auth pattern (private key preferred, password fallback)
- [x] Six env var overrides for target tables (PARLAY_TARGET_DATABASE, PARLAY_TARGET_SCHEMA, PARLAY_EVENTS_TABLE, PARLAY_ODDS_TABLE, PARLAY_MATCHES_TABLE, PARLAY_LINE_MOVEMENT_TABLE)
- [x] Single-key auth via `X-API-Key` header; no credit headers — call_sequence counter logged instead
- [x] Historical backfill defaults to 90 days prior to run date (Business plan data limit)
- [ ] **Run 90-day historical backfill** — execute `historical-odds` and `historical-matches` for 2026-02-08 → 2026-05-09 after script is tested
- [ ] Test against live tables before production cutover (per test-before-deploy protocol)

---

### 0.4 — dbt staging model for Parlay API odds

**Goal:** Add a `stg_parlayapi_odds` staging model that produces the same output schema as `stg_oddsapi_odds`, enabling all downstream dbt models and mart joins to consume both sources without changes.

Tasks:
- [ ] Create `dbt/models/staging/stg_parlayapi_odds.sql` — parse `raw_json` from `parlayapi.mlb_odds_raw` into normalized rows (one row per bookmaker per market per event per snapshot)
- [ ] Match column names and types to `stg_oddsapi_odds` exactly
- [ ] Add `source_system = 'parlay_api'` discriminator column so downstream models can filter by source if needed
- [ ] Add source entry to `dbt/models/sources.yml`
- [ ] Add schema tests (not null on `event_id`, `bookmaker_key`, `market_key`, `commence_time`)

**Blocking investigation — doubleheader disambiguation (RESOLVED 2026-05-10, support ticket open):**

**Finding: Parlay API collapses doubleheaders into a single odds line.** Both the `/events` endpoint and `/historical/odds` endpoint return only one event per (date, home_team, away_team) matchup regardless of how many games were played. The second game of a doubleheader does not appear as a separate event ID in any response.

Confirmed against three known 2026 doubleheader dates (sourced from `baseball_data.betting.stg_statsapi_games` where `double_header IN ('Y','S')`):
- 2026-04-05: Cleveland Guardians vs Chicago Cubs — StatsAPI: 2 games; Parlay API: 1 event (`id=607c7a2cc9eb6711`, `commence_time=19:00:00Z`)
- 2026-04-26: New York Mets vs Colorado Rockies — StatsAPI: 2 games; Parlay API: 1 event
- 2026-04-30: Baltimore Orioles vs Houston Astros — StatsAPI: 2 games; Parlay API: 1 event

Additional findings from live API testing 2026-05-10:
- `commence_time` is a slate placeholder (`19:00:00Z`) for every game on every date — not the actual scheduled start time. This applies to both `/events`, `/odds`, and `/historical/odds`.
- `dateFormat=unix` has no effect on historical endpoints — always returns ISO strings.
- `canonical_event_id` is `null` in historical odds responses; only populated in live `/events` responses.

**Impact on staging model design:**
- `(date, home_team, away_team)` cannot be a reliable join key to `stg_statsapi_games` — on doubleheader days it will produce a 1:2 fan-out (one Parlay odds row joining to two StatsAPI game rows).
- There is no field in the Parlay API response that distinguishes game 1 from game 2 of a doubleheader.
- Support ticket filed with Parlay API requesting: (1) separate event IDs for each game of a doubleheader, and (2) accurate per-game `commence_time` values. **Do not finalize staging model join key until ticket is resolved.**

**Interim approach until ticket is resolved:** In `stg_parlayapi_odds`, flag any (date, home_team, away_team) combination where `stg_statsapi_games` shows `double_header IN ('Y','S')` with a `doubleheader_ambiguous = true` column. Downstream mart joins should exclude or caveat these rows until the API issue is fixed.

---

### 0.5 — Update downstream mart joins to union both sources

**Goal:** Any mart that joins `stg_oddsapi_odds` should be able to consume `stg_parlayapi_odds` for dates after the cutover without breaking historical data.

Tasks:
- [ ] Audit which dbt marts currently join `stg_oddsapi_odds` or `mart_bookmaker_disagreement` (check `mart_bookmaker_disagreement.sql`, `feature_pregame_game_features.sql`, and any CLV-related models)
- [ ] Decide on union vs. coalesce strategy: option A = UNION ALL both staging models into a single intermediate `int_odds_combined`; option B = add Parlay API as a second branch in `mart_bookmaker_disagreement`
- [ ] Implement chosen strategy — preserve `source_system` column so historical Odds API rows are distinguishable from new Parlay API rows
- [ ] Verify no historical rows are dropped or duplicated after the change

---

### 0.6 — Update GitHub Actions workflow for daily ingestion

**Goal:** Wire the new Parlay API ingestion script into the daily GitHub Actions workflow that currently runs `odds_api_ingestion.py`.

Tasks:
- [ ] Add steps to `.github/workflows/daily_ingestion.yml` to call `parlay_api_ingestion.py events` and `parlay_api_ingestion.py odds` on the same schedule as the current Odds API steps
- [ ] Disable (comment out or condition-gate) the Odds API ingestion steps after 2026-05-23 — do not delete, retain for reference and potential reactivation
- [ ] Verify daily dbt refresh still completes correctly after the workflow change
- [ ] Add `PARLAY_API_KEY` (or equivalent) to GitHub Actions secrets

---

### 0.7 — Cutover validation and monitoring

Tasks:
- [ ] Run parallel ingestion for at least 3–5 days: ingest from both APIs simultaneously, compare event coverage and odds values
- [ ] Verify that `mart_bookmaker_disagreement` consensus line and bookmaker spread are consistent across sources for the overlap period
- [ ] Confirm `feature_pregame_game_features.has_odds` flag fires correctly from Parlay API data
- [ ] After validation: disable Odds API ingestion steps in GitHub Actions (2026-05-23 target, no later than 2026-06-01)
- [ ] Document which date range is covered by each source in `baseball_data_mart_inventory.md`

---

# Epic 0.5 — Orchestration: Decision Point (Revisit After Epic 3)

**Status: Deferred.** Do not build now.

**Context:** GitHub Actions is the current orchestrator and is working. A proper pipeline orchestrator (Dagster, Prefect) becomes genuinely useful once cross-epic asset dependencies materialize — i.e., once at least one sub-model (Epic 3+) is producing signals that downstream models consume. That complexity does not exist yet.

**Why deferred:** Dagster Cloud minimum cost is $10/month. Prefect Cloud has a functional free tier but weaker asset-lineage model. Self-hosted Dagster on a small VM (~$5–6/month Hetzner/DO) preserves the asset-centric model at low cost but adds maintenance burden. None of these trade-offs are worth taking on before the pipeline complexity that justifies them actually exists.

**Revisit trigger:** After Epic 3 (Run Environment Model) ships and the first sub-model signal is flowing into a downstream feature matrix. At that point, evaluate whether GitHub Actions dependency chaining is causing real pain. If yes, choose between:
- **Prefect Cloud free tier** — managed server/UI, no infra, weaker asset model
- **Self-hosted Dagster on Hetzner CX11** (~$5/mo) — stronger asset/lineage model, minor ops overhead

**Do not revisit sooner than Epic 3.**

---

# Epic 1 — Market-Blind Retrains

**Goal:** Remove market-derived features from all three production models and retrain. This is the single highest-priority improvement to live CLV performance and the direct fix for the market circularity problem identified in Phase 8.

**Target date:** ~2026-05-22 (waiting on in-season data accumulation).

---

### 1.1 — home_win market-blind retrain

**Status:** `_MARKET_COLS_TO_EXCLUDE` already populated in `train_elasticnet_prod.py`.

Tasks:
- [ ] Confirm `_MARKET_COLS_TO_EXCLUDE` list is complete (run feature importance analysis, verify all top market-correlated features are excluded)
- [ ] Run `train_elasticnet_prod.py` with exclusion list active
- [ ] Evaluate: CV Brier, ECE, calibration curve
- [ ] Gate: must beat or match current production Brier (0.2422)
- [ ] Update `model_registry.yaml` with new artifact path, feature columns, and wave gate results
- [ ] Update `.gitignore` exception if new `.pkl` artifact is to be tracked in git

---

### 1.2 — total_runs market-blind retrain

Tasks:
- [ ] Add `_MARKET_COLS_TO_EXCLUDE` equivalent to NGBoost training script (`train_ngboost_totals.py` or equivalent)
- [ ] Identify and drop the 4 noise features flagged in Phase 8 (`mean_imp <= 0`)
- [ ] Run retrain
- [ ] Evaluate: CV MAE, std(predicted values), mean residual, quantile calibration
- [ ] Gate: CV MAE must beat current 3.5107; std(pred) improvement over 0.77 is desired but not blocking
- [ ] Update `model_registry.yaml`

---

### 1.3 — run_diff market-blind retrain

Tasks:
- [ ] Switch training from `feature_columns.json` (294-feature pre-Phase 8 set) to `load_features()` full feature set
- [ ] Add market exclusion equivalent to `_MARKET_COLS_TO_EXCLUDE`
- [ ] Run retrain
- [ ] Evaluate: CV MAE vs current 3.4724; calibration; feature importance analysis to confirm market features are gone
- [ ] Gate: CV MAE within 1% of current; confirm `home_win_prob_consensus` no longer in top-20 features
- [ ] Update `model_registry.yaml`

---

### 1.4 — Post-retrain smoke test

Tasks:
- [ ] Run `predict_today.py` with all three new model artifacts against today's games
- [ ] Confirm prediction coverage for all confirmed-lineup games
- [ ] Spot-check that no market-derived features appear in model output feature sets

---

# Epic 2 — Sub-Model Infrastructure

**Goal:** Establish the storage interface, versioning pattern, and shared tooling that all sub-models will use. Do this before building any sub-model to avoid rework.

---

### 2.1 — Define sub-model output storage schema

Tasks:
- [ ] Decide on storage pattern (new `feature_pregame_sub_model_signals` mart vs. a `mart_sub_model_signals` wide table)
- [ ] Design schema: `game_pk`, `side`, `signal_name`, `signal_value`, `uncertainty`, `sub_model_version`, `computed_at`
- [ ] Write DDL and create table in Snowflake
- [ ] Create corresponding dbt model for the mart

---

### 2.2 — Sub-model versioning convention

Tasks:
- [ ] Define naming convention for sub-model version tags (e.g., `offensive_v1`, `run_env_v1`)
- [ ] Document convention in a `sub_model_registry.yaml` (mirrors structure of `model_registry.yaml`)
- [ ] Add `sub_model_version` tracking to `DAILY_MODEL_PREDICTIONS` or a dedicated audit table

---

### 2.3 — Sub-model evaluation harness

Tasks:
- [ ] Create `evaluate_sub_model.py` script that accepts a signal name and runs:
  - Temporal CV (rolling forward windows)
  - Correlation with outcome residuals
  - Incremental Brier/MAE contribution when added to base model
  - Feature importance rank in augmented model
- [ ] Integrate output into a `sub_model_ablation_report.md` template

---

### 2.4 — Add `computed_at` timestamps to all new feature marts

Tasks:
- [ ] Add `computed_at` (materialization timestamp) as a standard column to all new dbt feature marts going forward
- [ ] Document this as a dbt convention in the project README or CLAUDE.md

---

# Epic 3 — Run Environment Model

**Goal:** Build the first sub-model. Run environment is the best starting point: the target (total runs) is self-contained, the features (park, weather, umpire) are all already ingested, and the signal doesn't depend on any other sub-model.

---

### 3.1 — Define training dataset

Tasks:
- [ ] Query: park factor features, weather features, umpire tendency features, opponent quality controls, total runs scored
- [ ] Training window: 2016+ where weather backfill is available; 2021+ otherwise
- [ ] Validate: no future leakage, no market features

---

### 3.2 — Train run environment model (v1)

Tasks:
- [ ] Build feature matrix (park factors, temperature, wind, roof, umpire ERA+, day/night, elevation)
- [ ] Include opponent quality as training controls (team offensive ratings, starter quality)
- [ ] Train: Ridge regression or NGBoost as initial candidates
- [ ] Evaluate: MAE on total runs, calibration by ballpark bucket, calibration by temperature band
- [ ] Document: training window, feature list, target, metrics in `sub_model_registry.yaml`

---

### 3.3 — Generate and store run environment signals

Tasks:
- [ ] Write prediction script to generate: `run_environment_signal`, `weather_run_modifier`, `umpire_run_modifier`, `environment_volatility_signal`
- [ ] Store in sub-model output mart (from Epic 2)
- [ ] Backfill signals for 2021–2026 training window

---

### 3.4 — Ablation test

Tasks:
- [ ] Add run environment signals to existing totals model feature matrix
- [ ] Run temporal CV with and without the signals
- [ ] Report: incremental MAE improvement, calibration change, feature importance rank
- [ ] Gate: proceed to production integration only if signals show positive incremental value

---

# Epic 4 — Offensive Quality Model

**Goal:** Build a pre-game lineup quality signal that is independent of market data.

---

### 4.1 — Define training dataset

Tasks:
- [ ] Identify lineup feature columns already in the feature store (wRC+, OBP, SLG, wOBA, batting order position, handedness)
- [ ] Target: team runs scored, with opponent quality controls (Version 1 approach per architecture doc)
- [ ] Training window: 2016+

---

### 4.2 — Train offensive quality model (v1)

Tasks:
- [ ] Build feature matrix (projected lineup quality, lineup depth, platoon composition, park-adjusted batting metrics)
- [ ] Train: Ridge regression or gradient boosted trees
- [ ] Evaluate: residual correlation with actual runs scored, season stability of signal
- [ ] Document in `sub_model_registry.yaml`

---

### 4.3 — Generate and store offensive quality signals

Tasks:
- [ ] Generate: `lineup_run_creation_signal`, `lineup_depth_score`, `top_3_lineup_strength`, `bottom_3_lineup_strength`, `lineup_uncertainty_score`
- [ ] Store in sub-model output mart
- [ ] Backfill for 2021–2026

---

### 4.4 — Ablation test

Tasks:
- [ ] Add offensive signals to H2H and totals feature matrices
- [ ] Temporal CV comparison
- [ ] Gate before production integration

---

# Epic 5 — Starter Suppression Model

**Goal:** Build a pre-game starter quality signal that captures stuff, command, and expected depth.

---

### 5.1 — Define training dataset

Tasks:
- [ ] Identify starter feature columns: Stuff+, CSW%, arsenal drift, velocity trend, recent workload, FIP, xFIP
- [ ] Primary target: starter xwOBA allowed in game (cleaner than runs allowed)
- [ ] Auxiliary targets: K%, BB%, innings pitched
- [ ] Training window: 2021+ (Stuff+ coverage-dependent)

---

### 5.2 — Train starter suppression model (v1)

Tasks:
- [ ] Build feature matrix (rolling Stuff+, CSW% last 3 starts, velocity delta, arsenal drift, workload)
- [ ] Train separate signals for: run suppression, expected depth, strikeout quality
- [ ] Evaluate: correlation with in-game xwOBA, K%, IP
- [ ] Document in `sub_model_registry.yaml`

---

### 5.3 — Generate and store starter suppression signals

Tasks:
- [ ] Generate: `starter_run_suppression_signal`, `starter_expected_ip_signal`, `starter_command_signal`, `starter_uncertainty_score`
- [ ] Store in sub-model output mart
- [ ] Backfill for 2021–2026

---

### 5.4 — Ablation test

Tasks:
- [ ] Add signals to H2H and totals feature matrices
- [ ] Temporal CV comparison
- [ ] Gate before production integration

---

# Epic 6 — Bullpen State Model

**Goal:** Build a pre-game bullpen availability/fatigue signal. Version 1 targets arm state, not in-game runs allowed.

---

### 6.1 — Define training dataset

Tasks:
- [ ] Query: bullpen IP last 1/2/3 days, high-leverage appearances, closer rest days, reliever ERA/xwOBA rolling
- [ ] Target (v1): bullpen availability index — derived from workload features, not game-day runs allowed
- [ ] Training window: 2016+

---

### 6.2 — Build bullpen state index (v1)

Tasks:
- [ ] Define bullpen availability index formula (weighted sum of leverage-adjusted IP last 3 days)
- [ ] Validate index against known high-fatigue games (check correlation with next-game bullpen performance)
- [ ] Consider: simple rules-based index first vs. trained model second
- [ ] Document decision in `sub_model_registry.yaml`

---

### 6.3 — Train bullpen quality model (v1)

Tasks:
- [ ] Features: rolling bullpen xwOBA, K/BB, recent usage patterns
- [ ] Target: next-game bullpen xwOBA (not runs allowed, to avoid leverage-context conflation)
- [ ] Evaluate: correlation with out-of-sample bullpen performance
- [ ] Document in `sub_model_registry.yaml`

---

### 6.4 — Generate and store bullpen signals

Tasks:
- [ ] Generate: `bullpen_fatigue_signal`, `bullpen_quality_signal`, `high_leverage_availability_proxy`, `late_game_volatility_signal`
- [ ] Store in sub-model output mart
- [ ] Backfill for 2021–2026

---

### 6.5 — Ablation test

Tasks:
- [ ] Add signals to totals feature matrix
- [ ] Temporal CV comparison
- [ ] Gate before production integration

---

# Epic 7 — Archetype Clustering (Prerequisite for Epic 8)

**Goal:** Define batter archetypes and pitcher archetypes as cluster labels that can be used in the matchup model.

---

### 7.1 — Batter archetype clustering

Tasks:
- [ ] Feature selection: contact rate, walk rate, ISO, pull%, hard-hit%, sprint speed, groundball rate
- [ ] Training window: 2021+ (requires Statcast coverage)
- [ ] Cluster algorithm: k-means or UMAP + HDBSCAN (evaluate 4–8 clusters)
- [ ] Assign cluster labels to all batters in training window
- [ ] Validate clusters are interpretable (e.g., "power/flyball", "contact/groundball", "patient/walk-heavy")
- [ ] Store batter archetype labels in a new dbt mart: `mart_batter_archetypes`
- [ ] Document cluster definitions

---

### 7.2 — Pitcher archetype clustering

Tasks:
- [ ] Feature selection: pitch mix (FB%, SL%, CH%, CB%), velocity, spin rate, extension, movement profile
- [ ] Training window: 2021+
- [ ] Cluster: 4–8 clusters (evaluate)
- [ ] Validate: clusters should map to recognizable pitcher types (e.g., "power FB", "command/soft", "high-spin breaking ball")
- [ ] Store labels in `mart_pitcher_archetypes`
- [ ] Document cluster definitions

---

### 7.3 — Historical archetype label backfill

Tasks:
- [ ] Assign archetype labels to all historical batter-pitcher appearances in training window
- [ ] Validate temporal stability: do cluster assignments shift significantly year-to-year? (Expected: yes for developing players — handle appropriately)

---

# Epic 8 — Matchup Model

**Depends on:** Epic 7 (archetype clustering)

**Goal:** Build a lineup-vs-starter matchup quality signal using archetype × archetype interaction history.

---

### 8.1 — Define training dataset

Tasks:
- [ ] Build batter archetype × pitcher archetype interaction matrix from historical PA data
- [ ] Target: wOBA/xwOBA by archetype pair, K%, BB%, hard-hit%
- [ ] Training window: 2021+

---

### 8.2 — Train matchup model (v1)

Tasks:
- [ ] Feature matrix: lineup archetype composition vs. starter archetype, handedness splits, bat tracking vs. velocity (optional block, 2023-07+)
- [ ] Train: gradient boosted model or interaction regression
- [ ] Evaluate: correlation of matchup signal with same-game offensive output
- [ ] Document in `sub_model_registry.yaml`

---

### 8.3 — Generate and store matchup signals

Tasks:
- [ ] Generate: `matchup_advantage_signal`, `matchup_k_pressure_signal`, `matchup_power_signal`, `matchup_volatility_signal`
- [ ] Store in sub-model output mart
- [ ] Backfill for 2021–2026

---

### 8.4 — Ablation test

Tasks:
- [ ] Add matchup signals to H2H and totals feature matrices
- [ ] Temporal CV comparison
- [ ] Gate before production integration

---

# Epic 9 — Signal Integration & Ablation Testing

**Depends on:** At least one of Epics 3–8 complete.

**Goal:** Establish a systematic process for evaluating sub-model signals and integrating promoted signals into production models.

---

### 9.1 — Build signal evaluation pipeline

Tasks:
- [ ] Script: query sub-model signal mart, join to training data, run ablation CV
- [ ] Metrics: incremental Brier (for H2H), incremental MAE (for totals), calibration shift, feature importance rank
- [ ] Output: `signal_ablation_report.md` per signal group

---

### 9.2 — Promote first round of signals

Tasks:
- [ ] For each sub-model that clears ablation gate: add signals to `load_features()` in `preprocessing.py`
- [ ] Add corresponding imputation rules for any missing-value cases
- [ ] Update feature column JSON files for affected models
- [ ] Re-run temporal CV after each signal group is added

---

### 9.3 — Document signal promotion decisions

Tasks:
- [ ] For each signal: record in `sub_model_registry.yaml` whether it was promoted, rejected, or deferred
- [ ] Note the incremental metric value and the gate threshold used
- [ ] Record which production model version first consumed the signal

---

# Epic 10 — Totals Distribution Model

**Depends on:** Epics 3–6 (at least some signals promoted into feature store); Epic 9 (signal integration baseline established).

**Goal:** Build a totals model that directly addresses the variance-shrinkage failure (current std(pred) = 0.77 vs. threshold 2.0) and produces calibrated run distribution outputs.

---

### 10.1 — Design distribution model architecture

Tasks:
- [ ] Evaluate: NGBoost Normal (current), LightGBM Quantile (Phase 8 challenger), Negative Binomial regression, Quantile regression forest
- [ ] Define evaluation gates: std(pred), quantile calibration, over/under Brier, MAE
- [ ] Confirm: no market features in training matrix

---

### 10.2 — Train totals distribution model

Tasks:
- [ ] Training matrix: Phase 8 features + promoted sub-model signals (from Epic 9), no market features
- [ ] Evaluate all candidate architectures against gates
- [ ] Select champion model
- [ ] Document in `model_registry.yaml`

---

### 10.3 — Generate distribution outputs

Tasks:
- [ ] Produce: `expected_total_runs`, `total_run_variance`, quantile features
- [ ] Store as additional columns in prediction output
- [ ] Smoke test against recent games

---

# Epic 11 — H2H Model Retrain with Sub-Model Signals

**Depends on:** Epic 1 (market-blind retrain complete); Epic 9 (signals promoted).

**Goal:** Retrain the H2H win probability model with market features excluded and with promoted sub-model signals as additional inputs.

---

### 11.1 — Build retrain feature matrix

Tasks:
- [ ] Start from market-blind elasticnet feature set (Epic 1)
- [ ] Add promoted sub-model signals
- [ ] Confirm: no market features present

---

### 11.2 — Retrain H2H model

Tasks:
- [ ] Run full CV sweep over same candidate models as Phase 8 (elasticnet, XGBoost, LightGBM)
- [ ] Evaluate: CV Brier, ECE, calibration curve
- [ ] Gate: must beat market-blind baseline from Epic 1
- [ ] Document in `model_registry.yaml`

---

### 11.3 — CLV evaluation

Tasks:
- [ ] Run live predictions for 2-4 weeks post-promotion
- [ ] Compute mean CLV for new model vs. market-blind baseline
- [ ] Gate for long-term production: mean CLV > 0 sustained over 30+ games

---

# Epic 12 — CLV Meta-Model

**Gate:** Do NOT begin production training until 500+ live CLV-labeled games are available.

**Current status:** ~41 games as of May 2026. Realistically unblocked late July or August 2026.

---

### 12.1 — CLV monitoring (pre-threshold)

Tasks:
- [ ] Weekly: check live CLV game count in `mart_prediction_clv`
- [ ] Monthly: run descriptive CLV analysis (mean by game type, team, model edge bucket)
- [ ] Track: rate of positive CLV games, CLV distribution by edge size
- [ ] Log findings in a running `clv_monitoring_log.md`

---

### 12.2 — Exploratory meta-model (500+ games)

Tasks:
- [ ] Build training matrix: model edge, market disagreement, uncertainty, timing signals, public betting, line movement
- [ ] Target: binary positive CLV indicator
- [ ] Train: logistic regression first (interpretable)
- [ ] Evaluate: AUC, calibration, signal consistency
- [ ] Output: exploratory report only — do not promote to production

---

### 12.3 — Production meta-model (1000+ games)

Tasks:
- [ ] Temporal CV across at least 2 seasons of live data
- [ ] Evaluate: AUC, CLV calibration, ROI in backtest
- [ ] Gate: must demonstrate positive mean CLV in holdout period
- [ ] Document in `model_registry.yaml` as Layer 4 model

---

### 12.4 — Risk and portfolio layer

Tasks:
- [ ] Implement uncertainty-adjusted Kelly sizing
- [ ] Implement exposure caps by game and daily bankroll
- [ ] Integrate meta-model confidence score into sizing formula

---

# Epic 13 — Temporal Data Platform

**Scope:** Long-horizon infrastructure. Begin Phase 10. Not a Phase 9 deliverable.

**Goal:** Evolve the dbt/Snowflake data platform toward point-in-time correctness, SCD Type-2 entities, and historical CLV reconstruction.

---

### 13.1 — Temporal audit (Phase 9 preparatory)

Tasks:
- [ ] Audit all existing feature marts for leakage risk (finalized-season stats, non-temporal joins)
- [ ] Prioritize tables by leakage risk and frequency of use
- [ ] Document in `temporal_audit.md`

---

### 13.2 — Add timestamps to new marts (Phase 9)

Tasks:
- [ ] All new dbt models created in Phase 9 must include a `computed_at` column
- [ ] Enforce in dbt model review checklist

---

### 13.3 — SCD Type-2 for highest-priority entities (Phase 10)

Tasks:
- [ ] Implement SCD Type-2 for: projected starting pitchers, lineup projections, bullpen availability
- [ ] Update downstream feature marts to use point-in-time joins
- [ ] Validate: historical model reconstruction produces same features as original run

---

### 13.4 — Historical CLV reconstruction infrastructure (Phase 10+)

Tasks:
- [ ] Design: `prediction_snapshots` table with full feature version metadata
- [ ] Design: `odds_snapshots` with accurate opening/closing timestamps
- [ ] Implement: historical replay script that reconstructs predictions from stored feature snapshots
- [ ] Validate: spot-check reconstructed predictions against original `DAILY_MODEL_PREDICTIONS` rows

---

# Infrastructure Considerations

This section documents cross-cutting infrastructure concerns that are not tied to a single epic. Each item includes a **trigger** — the point at which it becomes worth acting on — to avoid premature investment.

---

## I1 — ML Training Compute

**Problem:** NGBoost retrains already take >1 hour locally. As sub-models are added (Epics 3–6), the full retrain suite will be several hours. GitHub Actions free tier caps jobs at 6 hours with 2 vCPUs, which will not be sufficient for NGBoost or ensemble training at scale.

**Current state:** Local machine. Works for now.

**Trigger:** When any single training job exceeds 2 hours, or when the total suite (all models + sub-models) can no longer complete in a single GitHub Actions job.

**Options when trigger hits:**
- **GitHub Actions larger runners** — paid, ~$0.008/min for 4-core. Low friction, no new infra.
- **Modal** — serverless GPU/CPU compute, pay-per-second, free tier available. Strong fit for bursty ML training workloads.
- **Spot instance (AWS/GCP/Hetzner)** — cheapest per-compute-minute but requires manual provisioning or scripting.

**Recommendation:** Modal is the cleanest path — call `modal run train_ngboost.py` from GitHub Actions, pay only for training time, no infra to maintain.

---

## I2 — Model Artifact Storage

**Problem:** Production `.pkl` files are tracked in git (with explicit `.gitignore` exceptions). This works for 3 artifacts but will break down as versioned sub-models are added — git is not designed for binary artifact versioning.

**Current state:** 3 `.pkl` files explicitly whitelisted in `.gitignore`. `model_registry.yaml` tracks metadata.

**Trigger:** When a second version of any sub-model is trained (Epic 3+), or when total artifact storage in git exceeds ~50MB.

**Options when trigger hits:**
- **S3 / GCS** — cheap object storage (~$0.023/GB/month S3). Store artifacts keyed by `{model_name}/{version}.pkl`. `model_registry.yaml` holds the S3 path instead of a local path.
- **Git LFS** — easier migration from current state, GitHub charges for storage beyond 1GB.
- **MLflow Tracking Server** — more overhead; not worth it unless you need a full experiment tracking UI.

**Recommendation:** S3 with path stored in `model_registry.yaml`. Minimal code change — just update the artifact load/save path in training and inference scripts.

---

## I3 — Pipeline Failure Alerting

**Problem:** If daily ingestion fails (Parlay API error, Snowflake timeout, dbt model failure), there is currently no proactive alert. You find out when you notice predictions are stale.

**Current state:** GitHub Actions sends email on workflow failure, but only if you notice the email.

**Trigger:** Now. This is a gap that costs nothing to fix and has direct betting impact — a silent ingestion failure means you're betting on stale data.

**Options:**
- **GitHub Actions → Slack webhook** — add a single `actions/slack-notify` step to `daily_ingestion.yml` on failure. Free.
- **`check_data_freshness.py` → alert** — wire the existing freshness check script to send a Slack message or email if any source is stale beyond threshold. Already partially built.
- **Snowflake query alert** — Snowflake has native alerting on query results; can trigger if `DAILY_MODEL_PREDICTIONS` hasn't been written today.

**Recommendation:** Add a Slack webhook failure notification to `daily_ingestion.yml` first (30-minute task). Then wire `check_data_freshness.py` to send a proactive alert if freshness check fails, regardless of whether the pipeline appeared to succeed.

---

## I4 — Secrets Management

**Problem:** API keys and credentials are spread across `.env` files (local), GitHub Actions secrets, and Snowflake. As Parlay API is added and sub-model infrastructure grows, the number of secrets will increase.

**Current state:** `.env` gitignored locally; GitHub Actions secrets for CI. No centralized audit trail.

**Trigger:** When more than ~5 distinct secrets exist across environments, or when onboarding a second team member requires secrets provisioning.

**Options when trigger hits:**
- **Doppler** — free tier covers 1 project/5 secrets. Syncs to GitHub Actions, local `.env`, and CI automatically. Very low friction.
- **AWS Secrets Manager** — more robust, ~$0.40/secret/month. Overkill until you have cloud infra.
- **1Password Secrets Automation** — if already using 1Password personally.

**Recommendation:** Doppler when the trigger hits. Until then, the current `.env` + GitHub Actions secrets pattern is fine.

---

## I5 — Data Observability / Freshness Monitoring

**Problem:** The feature store has 400+ columns derived from 8+ source schemas. Silent data quality failures (stale source, schema change from upstream API, null explosion in a mart) can cause model degradation that isn't immediately visible from CLV metrics.

**Current state:** `check_data_freshness.py` exists. dbt schema tests exist on some models. No systematic coverage.

**Trigger:** After Epic 2 (sub-model infrastructure), when the feature store is actively used for daily predictions. Any gap in feature quality directly affects live bets.

**Options:**
- **dbt tests** — already partially in place. Expand `not_null`, `accepted_values`, and `relationships` tests to all feature mart key columns. Free.
- **Elementary** — dbt-native observability package. Generates anomaly detection and data health reports as a dbt model. Free, open source. Requires a dashboard host (elementary Cloud free tier or self-hosted).
- **Great Expectations** — heavier, more configuration. Not worth it over expanded dbt tests for this use case.

**Recommendation:** Expand dbt tests coverage first (low cost, immediate value). Add Elementary after Epic 2 if dbt tests feel insufficient — it adds distribution-shift detection that pure schema tests miss.

---

## I6 — Snowflake Cost Monitoring

**Problem:** Snowflake costs can spike silently — a bad query, a runaway loop in a script, or a large dbt full-refresh can consume significant credits.

**Current state:** Unknown — no documented budget alert.

**Trigger:** Now. Set a budget alert before costs are a problem, not after.

**Action:** Set a Snowflake resource monitor with a monthly credit cap and an email alert at 75% and 100% utilization. 15-minute task via Snowflake UI.

---

# Acceptance Criteria Summary

| Epic | Gate / Exit Criterion |
|---|---|
| 1 — Market-blind retrains | All three models pass their metric gates; no market features in top-20 importance |
| 2 — Sub-model infrastructure | Output table created; versioning convention documented; evaluation harness working |
| 3 — Run environment | Ablation shows incremental improvement in totals CV MAE |
| 4 — Offensive quality | Ablation shows incremental improvement in H2H and/or totals CV |
| 5 — Starter suppression | Ablation shows incremental improvement in H2H and/or totals CV |
| 6 — Bullpen state | Ablation shows incremental improvement in totals CV |
| 7 — Archetype clustering | Clusters interpretable; labels stable year-over-year; stored in mart |
| 8 — Matchup model | Ablation shows incremental improvement in H2H CV |
| 9 — Signal integration | Promoted signals show positive incremental value; no calibration regressions |
| 10 — Totals distribution | std(pred) > 1.5; quantile calibration pass; MAE ≤ current baseline |
| 11 — H2H with signals | CV Brier beats market-blind baseline; mean CLV positive over 30+ live games |
| 12 — Meta-model | 1000+ CLV games; AUC > 0.55; positive mean CLV in holdout |
| 13 — Temporal platform | Point-in-time joins validated; historical reconstruction matches original predictions |
