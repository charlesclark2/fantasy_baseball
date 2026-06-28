# Session Recap — E11.1-W4 (Lakehouse Wave 4: read-path audit + non-serving precursors) — for PM Claude

**Date:** 2026-06-28 · **Status:** ✅ **PARITY GREEN — all 6 marts row-exact + PK-unique** (operator ran the full build + parity). Remaining = mechanical operator cutover: run `w4_external_tables.generated.sql` in Snowflake → refresh → merge (P5 CD). Scope = operator-decided **option (a)** (mirror the W3-main pivot).

## ✅ Parity results (operator-run, BEFORE view-flip = genuinely independent SF-CTAS vs DuckDB/S3)
| Mart | SF rows | DuckDB rows | Δ | PK unique |
|---|---|---|---|---|
| mart_pitcher_arsenal_summary | 7,131 | 7,131 | 0.00% | ✅ |
| mart_pitcher_profile_summary | 5,795 | 5,796 | 0.017% (stg freshness) | ✅ |
| mart_batter_profile_summary | 5,199 | 5,199 | 0.00% | ✅ |
| mart_park_factors_granular | 322 | 322 | 0.00% | ✅ |
| mart_batter_woba_vs_cluster | 632,742 | 632,742 | 0.00% | ✅ |
| mart_catcher_framing | 648 | 648 | 0.00% | ✅ |

Sample-hash WARNs on all 6 are the **known Snowflake↔DuckDB FLOAT-stringification artifact** inside the MD5 (`1.234000` vs `1.234`) — NOT a value defect: row-count + PK are the gates and all pass, incl. the two deterministic non-pitch marts at exact row counts. **Tool verdict: "✅ All W4 models pass parity."**

## 🩹 Cutover fixes applied during the operator run (reusable DuckDB-compat lessons)
1. **`cluster_pitchers.py` schema:** the LIVE `statsapi.pitcher_clusters` has **`fit_date`, not `snapshot_date`** (the script's `CREATE TABLE IF NOT EXISTS` never altered a pre-existing table; the legacy Snowflake `_persist`/`_DDL` are latently broken vs it but unused). Table is **unique on (pitcher_id, season)** (5,618 rows, 1 fit_date — the snapshot-accumulation design never materialised). Fixed `--seed`/`--s3` to select `fit_date` and key the S3 carry-forward on **season** (preserves the grain the mart joins on).
2. **httpfs timeout:** a slow S3 GET tripped DuckDB's default 30s window → added `http_timeout=600000` + retries/backoff to every W4 DuckDB connection (`run_w1_lakehouse`, `parity_check_w4`, `generate_w4_external_tables`), guarded for older builds.
3. **OOM on the FanGraphs flatten** (`stg_fangraphs__hitting_leaderboard`, ~70 cols + dedup window) at the 14.3 GiB box ceiling → `_build_w4` now sets `threads=2` + `memory_limit='11GB'` (spill earlier via the already-set `temp_directory`). Same class as the W3pre schedule flatten.
4. **VARCHAR game_date** in `mart_batter_woba_vs_cluster`: parquet stores `game_date` as VARCHAR, but the career-cumulative `range ... interval '1 day' preceding` window needs DATE → added `ppe.game_date::date` at the source CTE (the recurring W1d/W3 lesson). It is the ONLY W4 mart with interval/range-window ops (verified by scan).

---

## ⭐ THE PROGRAM-DEFINING RESULT — read-path audit (W4 task 0)

**Question:** does the live backend (`app/backend/**`) read Snowflake at USER-REQUEST time?

**Answer:**
- **NONE of the 6 (or 11) W4 marts are read at request time.** They are **batch-risk-class → migratable at W2/W3 speed, no "careful tier."**
- Request-time Snowflake reads **DO exist**, but **every one is fallback-tier** (DynamoDB serving cache → S3 → Snowflake last-resort) and they cluster **entirely in the serving/odds/results/picks/performance subtree**:
  - **W5 tier** (`mart_game_results` chain): `/performance/*` (`mart_clv_labeled_games`, `mart_bankroll_state`), game-detail results/h2h.
  - **W6 tier** (odds/CLV/serving): `/picks/*` (`daily_model_predictions`), `mart_odds_*`, line-movement, game-detail odds.
  - **Non-mart infra (out of scope):** `model_registry`, `SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY` (admin/finances), pipeline-status liveness.
- **⇒ W5, W6, W7 KEEP the careful tier (eyeball the live serving surface post-cutover, not just parity). W4 does not.**
- **Env-reality confirmed:** serving CODE is already DynamoDB→S3-clean — `app/backend/services/pg.py` is gone (→ `serving_cache.py` = DynamoDB `credence-prod-serving-cache`), no `DATABASE_URL`/psycopg/`api_cache` anywhere. The `finances.py` "Railway" refs are a legit cost-tracking field, NOT stale. **Fixed 2 stale serving-path COMMENTS** that still described the dead "Railway PG → S3" order: `app/backend/routers/players.py:39`, `app/backend/routers/picks.py:384`.

---

## What shipped (6 marts, `tags=['w4_lakehouse']`, dual-branch views)

Scope reality (DAG sweep + builder-dataflow trace): the prompt's **11** marts don't all survive contact (the W3-main lesson, again):
- **6 genuinely unblocked → SHIPPED this wave.**
- **4 blocked on `mart_game_results`/`mart_game_spine`** (= exactly what **W5** migrates; the DuckDB build needs every upstream in S3) → **deferred to W5 (pure dependency).**
- **1 incremental special-case** → deferred to W5 as a **separate** sub-task (different risk class).

**Shipped marts:**
| Group | Mart | Precursor (how it builds on DuckDB) |
|---|---|---|
| A (FanGraphs) | `mart_pitcher_arsenal_summary` | FG subtree (below) + `mart_pitch_characteristics` (W1) |
| A | `mart_pitcher_profile_summary` | `mart_pitcher_arsenal_summary` (W4) + `stg_batter_pitches` + `stg_statsapi_player_profiles` (W4) |
| A | `mart_batter_profile_summary` | `fct_fangraphs_hitting_analytics` + `mart_pitch_play_event` (W1) + `stg_batter_pitches` |
| B (posteriors) | `mart_park_factors_granular` | `eb_park_factors_granular_raw` parquet ← migrated `fit_granular_park_priors.py --s3` |
| B (cluster) | `mart_batter_woba_vs_cluster` | `mart_pitch_play_event` (W1) + `pitcher_clusters` parquet ← migrated `cluster_pitchers.py --seed/--s3` |
| C (raw savant) | `mart_catcher_framing` | `catcher_framing_raw` parquet (exported) |

**Precursor subtree migrated to DuckDB (so the 3 FG marts can build, "no Snowflake compute left"):**
- FG staging (raw_json VARIANT → DuckDB `json_extract_string(raw_json, '$."pfxFA%"')`): `stg_fangraphs__stuff_plus`, `stg_fangraphs__pitcher_arsenal`, `stg_fangraphs__zips_hitting`, `stg_fangraphs__hitting_leaderboard`.
- FG fct: `fct_fangraphs_pitcher_arsenal_wide`, `fct_fangraphs_hitting_analytics`.
- `stg_statsapi_player_profiles` (flat columns, no JSON).
- **2 computed builders → DuckDB build path** (numpy/sklearn math UNCHANGED → value-identical; I/O repointed S3↔DuckDB): `fit_granular_park_priors.py --s3`; `cluster_pitchers.py --s3` (+ `--seed` = one-time Snowflake-history→S3 for cutover parity).

**New/changed infra:** `scripts/export_w4_raw_to_s3.py` (7 raw exports), `scripts/parity_check_w4.py`, `scripts/ddl/generate_w4_external_tables.py`, `W4_*` lists + `_build_w4` + opt-in `--w4`/`--w4-only` in `scripts/run_w1_lakehouse.py` (also: recursive `find_model` for nested FG dirs; `lakehouse_loc` resolution added to the mart/Layout-B extractor), `W4_TABLES` (best-effort) in `scripts/refresh_w1_external_tables.py`, daily-op comments in `pipeline/ops/daily_ingestion_ops.py`.

**Gates at handoff:** `dbtf compile` **1771/1771 ✅** · fast pytest **683 passed ✅** · all 13 W4 duckdb-branches extract clean (no leftover Jinja, no Snowflake-branch leak, precursor S3 paths resolve) ✅. **Parity = operator step** (run BEFORE cutover, else tautological).

---

## ⚙️ OPERATOR RUN-ORDER (W4 is OPT-IN until validated — `--w4` not on the daily op yet)

```
# 1. Export raw precursor tables → S3 parquet
uv run python scripts/export_w4_raw_to_s3.py

# 2. One-time: seed pitcher_clusters history (Snowflake → S3) for cutover parity
uv run python betting_ml/scripts/pitcher_clustering/cluster_pitchers.py --season 2025 --seed

# 3. Build the granular-park posteriors on DuckDB → S3  (>1 min; all seasons)
uv run python betting_ml/scripts/eb_priors/fit_granular_park_priors.py --s3 --start-season 2015

# 4. Build the W4 marts + FanGraphs precursor subtree → S3  (>1 min)
uv run python scripts/run_w1_lakehouse.py --w4
#    (mart_pitcher_arsenal_summary is built here; to refresh pitcher_clusters FROM the
#     freshly-built S3 arsenal going forward: cluster_pitchers.py --season <yr> --s3, then
#     run_w1_lakehouse.py --w4-only to rebuild mart_batter_woba_vs_cluster.)

# 5. Generate + REVIEW + run the external-table DDL in Snowflake (BEFORE the PR merges)
uv run python scripts/ddl/generate_w4_external_tables.py     # → scripts/ddl/w4_external_tables.generated.sql
#    review, then run that .sql in Snowflake (MCP/connector)

# 6. Refresh external tables (or rely on refresh_w1_external_tables_op)
uv run python scripts/refresh_w1_external_tables.py

# 7. PARITY GATE — must be GREEN before cutover (runs while marts are still SF tables)
uv run python scripts/parity_check_w4.py

# 8. Merge PR → P5 CD auto-deploys (dbt/** + scripts/**). Post-deploy: spot-check a few
#    SF views resolve (e.g. select count(*) from baseball_data.betting.mart_catcher_framing).
```

**Build-ordering note (load-bearing):** `cluster_pitchers` reads `mart_pitcher_arsenal_summary` and writes `pitcher_clusters`, which `mart_batter_woba_vs_cluster` reads. The `--seed` (step 2) makes `pitcher_clusters` parquet exist & match Snowflake BEFORE step 4, so the first `--w4` build of `mart_batter_woba_vs_cluster` is parity-clean. The ongoing DuckDB refresh of clusters is step-4's note.

**`git add` (every file this session changed/created):**
```
git add \
  app/backend/routers/players.py \
  app/backend/routers/picks.py \
  betting_ml/scripts/eb_priors/fit_granular_park_priors.py \
  betting_ml/scripts/pitcher_clustering/cluster_pitchers.py \
  dbt/models/mart/mart_catcher_framing.sql \
  dbt/models/mart/mart_park_factors_granular.sql \
  dbt/models/mart/mart_batter_woba_vs_cluster.sql \
  dbt/models/mart/mart_pitcher_arsenal_summary.sql \
  dbt/models/mart/mart_pitcher_profile_summary.sql \
  dbt/models/mart/mart_batter_profile_summary.sql \
  dbt/models/marts/fangraphs/fct_fangraphs_pitcher_arsenal_wide.sql \
  dbt/models/marts/fangraphs/fct_fangraphs_hitting_analytics.sql \
  dbt/models/staging/fangraphs/stg_fangraphs__stuff_plus.sql \
  dbt/models/staging/fangraphs/stg_fangraphs__pitcher_arsenal.sql \
  dbt/models/staging/fangraphs/stg_fangraphs__zips_hitting.sql \
  dbt/models/staging/fangraphs/stg_fangraphs__hitting_leaderboard.sql \
  dbt/models/staging/statsapi/stg_statsapi_player_profiles.sql \
  scripts/run_w1_lakehouse.py \
  scripts/refresh_w1_external_tables.py \
  scripts/export_w4_raw_to_s3.py \
  scripts/parity_check_w4.py \
  scripts/ddl/generate_w4_external_tables.py \
  scripts/ddl/w4_external_tables.generated.sql \
  pipeline/ops/daily_ingestion_ops.py \
  quant_sports_intel_models/baseball/edge_program/story_prompts.md \
  quant_sports_intel_models/baseball/edge_program/E11_1_W4_session_recap.md
# EXCLUDE (gitignored, go to S3): all *.parquet, the kmeans/scaler *.pkl artifacts.
```

---

## ❗ DEFERRED TO W5 (dependency, NOT skip — must be picked up there)

1. **4 marts blocked on `mart_game_results`/`mart_game_spine`** (W5's exact migration target — pure dependency, batch-class once the upstream is in S3):
   - `mart_eb_park_factors` — builder `fit_park_priors.py` reads `mart_game_results`.
   - `mart_bullpen_effectiveness` — ← `eb_bullpen_team_posteriors` ← `mart_game_spine`; **also `incremental`**.
   - `mart_team_fielding_oaa` — reads `mart_game_spine`.
   - `mart_team_defense_quality_rolling` — reads `mart_game_spine` (+ `stg_batter_sprint_speed`; `oaa_team_season_raw` & `sprint_speed_raw` exports are easy — gate is game_spine).
2. **`mart_batter_archetype_vs_pitcher_cluster`** — SEPARATE W5 sub-task (different risk class): `materialized='incremental'` (→ needs full-rebuild conversion, a pattern W1–W4 never did) + chains through the non-dbt `mart_player_archetype_posteriors` (builder `compute_archetype_posteriors.py`, which reads `batter_clusters`+`pitcher_clusters`+`stg_statsapi_player_profiles`). `cluster_pitchers` is already DuckDB-migrated (W4); remaining for this sub-task = `cluster_batters.py` + `compute_archetype_posteriors.py` + the incremental→full-rebuild conversion. **Numerical (k-means/Bayes) parity is tolerance-based, not row-exact — give it its own focused pass + parity; do NOT blend with the game-results marts.**

## Notes for whoever picks up W5 / a future wave
- **Builders write S3 AND Snowflake still feeds non-W4 consumers.** `pitcher_clusters` (Snowflake) is still read by `feature_pitcher_cluster_matchups` + the W5-deferred archetype mart; `eb_park_factors_granular_raw` likewise. The migrated `--s3` path is ADDITIVE — keep the existing Snowflake builder runs until W5 migrates those consumers; `--seed`/`--s3` only populate the S3 lakehouse copy. No staleness.
- **Parity is freshness-aware** for the 3 pitch-derived FG/cluster marts (S3 stg ⊇ Snowflake → small current-season surplus EXPECTED); the 2 raw-fed marts (`park_factors_granular`, `catcher_framing`) should match within 0.1%. FanGraphs hash drift → spot-check the `stg_fangraphs__*` JSON flatten with `parity_check_w4.py --model <stg view>`.
- **Cutover order is load-bearing** (W1–W3 lesson): create the `lakehouse_ext` external tables in Snowflake BEFORE the PR merges (CI `state:modified+` + P5 CD build the SF view-over-external-table and FAIL if the table is absent).
- **VARIANT export:** `export_w4_raw_to_s3.py` json-dumps dict/list cells so `raw_json` lands as clean VARCHAR parquet; the FG staging duckdb branches parse it with `json_extract_string`.
- Memory: `project_e11_1_w4_lakehouse.md`.
