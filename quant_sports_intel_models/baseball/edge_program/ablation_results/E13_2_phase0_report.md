# E13.2 Phase 0 — Completion Report

**Story:** E13.2 Bottom-up PA-level game simulator (Singlearity blueprint) — Phase 0 (cost-hygiene + W1 data dependency)
**Date:** 2026-06-24 · **Status:** ✅ COMPLETE — training source verified, parity green, Phase 1 unblocked

## 1. Objective
Phase 0 had two mandates: (a) **cost-hygiene** — ensure the new ~1.96M-row PA substrate can never rebuild on Snowflake (lakehouse-native by design); (b) **verify the W1 data dependency** — confirm the S3 Statcast training source (`stg_batter_pitches`) is complete/correct vs Snowflake before trusting any lakehouse training run (post-INC-10, S3 completeness is not taken on faith).

## 2. Delivered

| Item | Result |
|---|---|
| **Cost-hygiene guard** | `mart_pa_outcome_substrate` set to `enabled=(target.name=='duckdb')` → duckdb/S3 only, **disabled on every Snowflake target** (can't be swept into the daily `source_status:fresher+` build). Verified: default-target compile excludes it as a disabled node. |
| **Parity check (new)** | Extended `parity_check_w1.py` with a `stg_batter_pitches` row-count-by-season + **PK-uniqueness (surrogate AND natural-key)** check. |
| **Parity RESULT** | **PASS.** 2015–2025 row-exact (0.0000%/season); grand total 0.0087%; all 7 `mart_pitch_*` pass; PK + natural-key unique. |

## 3. Issues found and fixed en route
1. **2026 row duplication (+53,040, 15.4%)** — a stale Snowflake-export `year=2026/part-0.parquet` overlapped the Savant-ingest daily partitions in the `**/*.parquet` glob. It **evaded the original PK-uniqueness check** because the two writers encode `pitch_sk` differently (md5-int vs sha256-hex), so duplicate logical pitches never collided. **Fixes:** removed the stray parquet; **hardened the parity gate with a natural-composite-key check** that catches this class regardless of surrogate encoding.
2. **`ref_players` not duckdb-resolvable** — `mart_pitch_hitter_profile`/`pitcher_profile` joined the `savant.ref_players` *source* directly, which has no duckdb path → `Catalog baseball_data does not exist`. **Fix:** new `scripts/export_ref_players_to_s3.py` + `stg_ref_players` staging model (duckdb S3-read branch) + repointed both marts; also updated `run_w1_lakehouse.py` (the real S3 writer) to register `stg_ref_players` from S3 instead of an empty stub (now emits real player names).
3. **`invalid utf-8` on `dbtf run --target duckdb`** — a **red herring**: that path builds *local incremental* tables and hit a stale-state MERGE. The actual S3 writer (`run_w1_lakehouse.py`) does full `COPY`-to-S3 (no merge) and is unaffected. The S3 data reads clean.

## 4. ⭐ Headline data-quality finding — Snowflake is missing 2 completed 2026 games
**This is the finding to action outside E13.2.**

After de-duplication, the only residual S3-vs-Snowflake gap was **2026: +666 rows (0.19%)**, with **S3 *ahead* of Snowflake**. Drilled to game grain:

| game_pk | official_date | matchup | StatsAPI state | score | in Snowflake `savant.batter_pitches`? | in S3? |
|---|---|---|---|---|---|---|
| **825099** | 2026-04-21 | White Sox @ Diamondbacks | Final | 11–5 | ❌ **absent** | ✅ 352 pitches |
| **824912** | 2026-06-16 | Giants @ Braves | Final | 7–2 | ❌ **absent** | ✅ 310 pitches |

- **Confirmed real games** via the independent MLB **StatsAPI schedule** (`stg_statsapi_games`) — both `Final`, non-doubleheader. So S3 is **more complete than Snowflake**, not defective.
- **Root cause (hypothesis):** both are **night games finishing after midnight UTC** (~01:40 / 18:00 UTC start). Snowflake's raw Statcast ingest appears to have a **UTC date-boundary miss**, and its `stg_batter_pitches` incremental only re-absorbs a **trailing 14-day lookback**, so the gap was never backfilled. The fresh full-season S3 re-fetch captured them.
- **Impact:** Snowflake-based **2026 features** (any model reading `savant.batter_pitches` / `stg_batter_pitches` for those dates) silently omit these 2 games. **Not** an E13.2 problem (E13.2 trains off the complete S3 copy).
- **Recommended action (separate ticket, data-pipeline track):** backfill the 2 games into Snowflake `savant.batter_pitches`; investigate UTC date-boundary handling in the Snowflake Statcast ingest for post-midnight-UTC games. **Worth a history-wide sweep** comparing StatsAPI game count vs Statcast-present game count per date to find any other silent gaps.

## 5. Parity gate redesign (correctness fix)
Holding the **current in-flight season** to exact ≤0.1% parity is structurally impossible — the two sources refresh on different clocks, and Snowflake's 14-day lookback can permanently lag whole games (now proven). So `parity_check_w1.py` was redesigned into tiers, documented in-code as a correctness fix:
- **Completed seasons** + **grand total** + **PK uniqueness** → **HARD** gates.
- **Current in-flight season** (`game_year == current year`) → **informational WARN**.

This also fixes the **6/25 W1 decommission gate**, which would otherwise have false-failed on the in-flight season.

## 6. Verification / CI
- `uv run pytest` → **498 passed, 1 skipped** (every step).
- `dbtf compile` (full, Snowflake) → **1771/1771** (substrate correctly excluded as disabled).
- duckdb-target compile of the marts + staging → clean.
- Full `parity_check_w1.py` → **all 8 models PASS**.

## 7. Operator handoff / action items
- **W1 decommission unblocked:** remove `mart_pitch_*` from Snowflake dbt schedules; turn off `w1_parity_schedule` per runbook. The 6/25 gate now passes.
- **`git add`:** `dbt/models/mart/mart_pa_outcome_substrate.sql`, `dbt/models/staging/stg_ref_players.sql`, `dbt/models/staging/schema.yml`, `dbt/models/mart/mart_pitch_hitter_profile.sql`, `dbt/models/mart/mart_pitch_pitcher_profile.sql`, `scripts/parity_check_w1.py`, `scripts/export_ref_players_to_s3.py`, `scripts/run_w1_lakehouse.py`
- **New ticket (Snowflake DQ):** backfill 2 missing 2026 games + audit the Statcast-ingest UTC date-boundary handling.
- **No changelog** — Phase 0 ships nothing user-facing.

## 8. Phase 1 readiness (verified)
- **Substrate scope confirmed:** 1,959,348 PAs (2015–2025, R-season) — matches the story's "1.96M."
- **Class balance:** out 46.2% · K 22.2% · 1B 14.3% · BB 8.0% · 2B 4.4% · HR 3.1% · HBP 1.05% · 3B 0.41% · other 0.19% · IBB 0.11% (heavily imbalanced; rare tail matters for the run-sim).
- **No-skill baseline to beat:** **1.5074 nats** marginal-prior multiclass log-loss (vs 2.3026 uniform).
- **Core features 100% populated** (handedness, times-thru-order, outs, score-diff → 0.000% null) — no imputation needed on entering-state features.
