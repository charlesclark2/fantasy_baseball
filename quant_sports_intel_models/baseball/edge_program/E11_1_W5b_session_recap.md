# Session Recap — E11.1-W5b (the ARCHETYPE builder-mini-wave — TOLERANCE risk class) — for PM Claude

**Date:** 2026-06-28 · **Status:** ✅ **CODE-COMPLETE — tolerance-parity VERIFIED value-exact, both CI gates green.** The seeds (`batter_clusters` + the posteriors) are already in S3 (run this session). Remaining = operator runs the full mart build + the tolerance gate + the mechanical cutover.

## What shipped
The single dual-branch mart **`mart_batter_archetype_vs_pitcher_cluster`** (incremental → `view`, `tags=['w5b_lakehouse']`) + its full builder chain migrated to DuckDB/S3 I/O (numpy/sklearn math UNCHANGED):
- **`betting_ml/scripts/batter_clustering/cluster_batters.py`** — `--s3`/`--seed` (direct analogue of the W4 `cluster_pitchers.py`): reads `mart_batter_profile_summary` (W4 mart, S3) + `ref_players` from S3, writes `batter_clusters` parquet; k-means `random_state=42, n_init=10` unchanged. **Seeded 5,099 rows → S3 this session.**
- **`betting_ml/scripts/eb_priors/compute_archetype_posteriors.py`** — `--s3`/`--seed`: reads the rolling substrate (`stg_batter_pitches`), profiles, and the two cluster tables from S3 via DuckDB (rewriting the Snowflake rolling SQL — `_duck_sql_for`), loads the `*_archetypes` centroids/scalers from S3 (already S3-first), and writes the posteriors parquet. The Bayesian `_compute_posterior`/`_gaussian_likelihood` is byte-for-byte the same. **Seeded all 683,362 Snowflake posteriors → S3 this session (13s).**
- **`mart_batter_archetype_vs_pitcher_cluster.sql`** — dual-branch; the DuckDB branch reads the posteriors parquet directly (`read_parquet(lakehouse_loc(...))`), drops the `is_incremental` blocks, and rewrites the Snowflake `lateral flatten(input => cluster_probs)` into a DuckDB `json_keys`/`json_extract` unnest (see lessons).

New/changed infra: `--archetype`/`--archetype-only` + `_build_archetype` + `ARCHETYPE_MODELS` in `run_w1_lakehouse.py`; `ARCHETYPE_TABLES` (best-effort) in `refresh_w1_external_tables.py`; `scripts/ddl/generate_w5b_external_tables.py`; `scripts/parity_check_w5b.py` (tolerance).

Gates: `dbtf compile` **1771/1771 ✅** · fast pytest **683 passed ✅**.

## ⭐ Tolerance-parity result (VERIFIED this session — the headline)
**Reading the SEEDED posteriors, the mart is value-EXACT.** On the matched late-2025 slice (full 180-day window): **1,125 / 1,125 rows matched on (batter_label, pitcher_label, game_date) with mean|Δadj_woba| = 0.0, max|Δ| = 0.0**. The soft-weight + 180-day-rolling + shrinkage SQL is deterministic over identical posteriors, and `round(…,3)` absorbs float wisps. ⇒ **the mart cutover (reading seeded posteriors) is row-exact-grade; the TOLERANCE band only applies when the posteriors are REBUILT on DuckDB (`compute_archetype_posteriors.py --s3`)** — there the rolling-stat SQL's Snowflake↔DuckDB float precision propagates through `exp(−dist²)` into cluster_probs (~1e-4) and into adj_woba's 3rd decimal. `parity_check_w5b.py` encodes both: mart value-drift bands (mean|Δ|≤0.005, ≥99% within 0.01) + posteriors MAP-cluster agreement (≥98%).

## 🩹 DuckDB-compat lessons (program checklist — new this wave)
1. **Snowflake `lateral flatten(input => variant_obj)` → DuckDB list-comprehension unnest.** `cluster_probs` is a VARCHAR-JSON `{label: prob}` in the parquet; a direct `cast(... as MAP(VARCHAR,DOUBLE))` FAILS. The pattern that works:
   ```sql
   unnest([{'lab': k, 'p': json_extract(bap.cluster_probs, '$."' || k || '"')::double}
           for k in json_keys(bap.cluster_probs)]) as u(e)
   -- then u.e.lab as label, u.e.p as prob
   ```
2. **`matched` is a DuckDB reserved word** (MERGE) — don't use it as a column alias (use `n_matched`).
3. **`game_date::date`** in the DuckDB branch (the parquet stores it VARCHAR) to match the retired DATE type + drive the 180-day RANGE-interval window (the recurring W1d/W3/W5 lesson).
4. **Builder I/O migration is mechanical** when the math is numpy/sklearn: repoint the SQL source to S3 (register views / `read_parquet`), rewrite the write to a parquet `COPY`, leave every numeric line untouched. `cluster_batters.py` was a near-copy of `cluster_pitchers.py`; `compute_archetype_posteriors.py` only needed `_duck_sql_for` (table-name + `CURRENT_DATE()` + as_of_date-cast rewrites) + an S3 persist.

## ⚙️ OPERATOR RUN-ORDER (W5b is OPT-IN — `--archetype` not on the daily op)
```
# 1. (DONE this session) Seed the cluster + posteriors baselines → S3:
uv run python betting_ml/scripts/batter_clustering/cluster_batters.py --season 2025 --seed
uv run python betting_ml/scripts/eb_priors/compute_archetype_posteriors.py --seed

# 2. Build the archetype mart → S3  (>1 min: 7.78M PA events × 25-cell soft-weight + 180d window)
uv run python scripts/run_w1_lakehouse.py --archetype-only

# 3. TOLERANCE GATE — BEFORE the view-flip
uv run python scripts/parity_check_w5b.py                       # mart (value-exact vs seeded)
#   (optional, validates the off-Snowflake build:)
#   uv run python betting_ml/scripts/eb_priors/compute_archetype_posteriors.py --s3 --mode backfill --season 2025
#   uv run python scripts/parity_check_w5b.py --target posteriors

# 4. Generate + REVIEW + run the external-table DDL in Snowflake (BEFORE the PR merges)
uv run python scripts/ddl/generate_w5b_external_tables.py       # → scripts/ddl/w5b_external_tables.generated.sql
# 5. Refresh + merge → P5 CD.
uv run python scripts/refresh_w1_external_tables.py
```

**`git add`:**
```
git add \
  dbt/models/mart/mart_batter_archetype_vs_pitcher_cluster.sql \
  betting_ml/scripts/batter_clustering/cluster_batters.py \
  betting_ml/scripts/eb_priors/compute_archetype_posteriors.py \
  scripts/run_w1_lakehouse.py \
  scripts/refresh_w1_external_tables.py \
  scripts/parity_check_w5b.py \
  scripts/ddl/generate_w5b_external_tables.py \
  scripts/ddl/w5b_external_tables.generated.sql \
  quant_sports_intel_models/baseball/edge_program/story_prompts.md \
  quant_sports_intel_models/baseball/edge_program/E11_1_W5b_session_recap.md
# EXCLUDE (gitignored → S3): *.parquet, the kmeans/scaler *.pkl artifacts.
```

## ⚠️ BUILDER DUAL-WRITE caveat (carry forward)
The Snowflake `mart_player_archetype_posteriors` and `statsapi.batter_clusters` tables have **OTHER live consumers** (`generate_matchup_signals.py`, `update_matchup_cell_posteriors.py`, `fit_archetype_priors.py`, `build_matchup_training_data.py`, the daily freshness checks). So the builders **KEEP their Snowflake writes** — `--s3`/`--seed` only populate the S3 lakehouse copy (additive, no staleness). The Snowflake posteriors/cluster compute does NOT zero out until those consumers migrate (a future wave). Same caveat as W4/W5.

## Notes
- Cutover order load-bearing: create the `lakehouse_ext.mart_batter_archetype_vs_pitcher_cluster` external table BEFORE the PR merges. The posteriors parquet is a **builder output** — read directly by the mart's duckdb branch, **no external table** (like W4 `pitcher_clusters`).
- `mart_player_archetype_posteriors` was DEAD 2026-05-31→backfilled (see `check_data_freshness.py`); the freshness sensor is separate from this migration.
- Memory: `project_e11_1_w5b_archetype.md`.
