# Session Recap — E11.1-W5 (Lakehouse Wave 5: seeds + the mart_game_results/mart_game_spine team/game chain + the W4 deferrals) — for PM Claude

**Date:** 2026-06-28 · **Status:** ✅ **CODE-COMPLETE** — all 15 W5 models dual-branch, structurally validated against S3 (every duckdb branch binds + EXPLAINs, column counts match the live Snowflake tables exactly), both CI gates GREEN. Remaining = operator runs the heavy build + the parity GATE (BEFORE view-flip), then the mechanical cutover. Scope = **Group A (the 10-mart game-results chain) + Group B (the 4 W4-deferred marts)** — operator-approved option.

## What shipped (15 dual-branch models, `tags=['w5_lakehouse']`, `materialized='view'` over `baseball_data.lakehouse_ext.*`)

**Group A — the seeds + mart_game_results/mart_game_spine team/game chain (10):**
`dim_team_name_lookup`, `mart_game_results`, `mart_game_spine`, `mart_head_to_head_team_history`, `mart_home_away_splits`, `mart_park_run_factors`, `mart_team_pythagorean_rolling`, `mart_team_rolling_offense`, `mart_team_rolling_pitching`, `mart_team_season_record`.

**Group B — the 4 W4-deferred marts + their staging precursor (5):**
`mart_eb_park_factors`, `mart_bullpen_effectiveness`, `mart_team_fielding_oaa`, `mart_team_defense_quality_rolling`, `stg_batter_sprint_speed`.

Every model descends from data already in S3 (`stg_batter_pitches` W1, the W3pre `stg_statsapi_games`, the W2 `mart_starting_pitcher_game_log`, the W1 `mart_pitch_*`) + the seeds + 4 one-time-exported raw tables. **Column counts match the live Snowflake `betting.*` tables EXACTLY for all 15** (28/15/24/86/6/9/49/92/23/4 Group A + 11/19/9/14/12 Group B).

New/changed infra: `scripts/export_w5_raw_to_s3.py` (seeds `ref_teams`/`ref_team_aliases` + raw `eb_park_factors_raw`/`eb_bullpen_team_posteriors`/`oaa_team_season_raw`/`sprint_speed_raw`), `scripts/parity_check_w5.py`, `scripts/ddl/generate_w5_external_tables.py`, `W5_*` lists + `_build_w5` + `_register_s3_glob_views` + opt-in `--w5`/`--w5-only`/`--w5-group-a-only` in `scripts/run_w1_lakehouse.py`, `W5_TABLES` (best-effort) in `scripts/refresh_w1_external_tables.py`, daily-op comment in `pipeline/ops/daily_ingestion_ops.py`.

Gates at handoff: `dbtf compile` **1771/1771 ✅** · fast pytest **683 passed, 1 skipped ✅**.

**✅ PARITY GREEN (operator-run 2026-06-28, BEFORE view-flip = genuinely independent SF-CTAS vs DuckDB/S3).** All 15 models pass the gates (row-count + PK uniqueness). One iteration: `mart_home_away_splits` initially failed `pk_uniq` because the parity PK `(team, home_away_flag, game_date)` collides on **doubleheaders** — the true grain is per-GAME; fixed `parity_check_w5.py` PK → `(game_pk, team)` (a parity-check fix, NOT a mart change — rows matched 52,862=52,862 throughout). The sample-hash WARNs on every model are the **known non-blocking artifact** (the `concat_ws('|', COLUMNS(*))` hash is degenerate in this DuckDB build AND SF↔DuckDB FLOAT stringification differs) — same call W4 made (gate on rows+PK). Beyond that I ran a **value-level aggregate spot-check** (2023 completed season): **integer sums match EXACTLY** (e.g. `sum(runs_scored)=22,430` both sides), float averages differ only at the 5th–6th decimal (averaging-order noise) — confirming **no systematic value error**. Safe to cut over.

## ⭐ Scope decision (operator-approved option "Group A + B"; mirrors the W3-main / W4 pivot)
Tracing the full DAG, W5 is bigger than the AC headline. We shipped the clean unblocked set and **DEFERRED three genuinely-blocked items** (below). User chose A+B over "A only" and over "everything."

## 🟠 CAREFUL-TIER finding (the W4 audit said W5 keeps the careful tier — here's the result)
**The ONLY request-time read of any W5 mart in the live backend (`app/backend/**`) is `mart_team_pythagorean_rolling`** in the game-detail endpoint's Snowflake FALLBACK (`picks.py` `_GAME_STATUS_QUERY`, behind the DynamoDB serving cache → `serving_cache.get_cache` is primary). `mart_game_results`/`mart_game_spine` are read at request time ONLY by the dead legacy Streamlit (`app/pages/4_Model_Performance.py` — not edited); everywhere else they're batch (training, `write_serving_store`, predict_today, settlement). **Decision: LEFT the fallback in place** — post-cutover it reads the S3-backed external-table view (no code change; DynamoDB stays primary). Removing it (the P2b `/picks/ev` precedent) would make game-detail return null pythagorean on a cache miss — net worse, so not done. **Post-cutover verification (operator): hit a game-detail endpoint, confirm `home_pyth_pct`/`away_pyth_pct` populate; confirm the daily settlement op (`settle_user_bets`) runs green (it batch-reads `mart_game_results`).**

## 🩹 DuckDB-compat lessons baked in (reusable — add to the program checklist)
1. **`at` is a RESERVED word in DuckDB** — the away-team table alias `at` (Snowflake-fine) breaks the parser. Renamed `at` → `at_` in `mart_game_results`/`mart_team_pythagorean_rolling`/`mart_team_season_record` (`mart_head_to_head` already used `at_`).
2. **CTE-name == base-table-name self-references in DuckDB** — a `ref_teams as (select * from ref_teams)` CTE (after the `{{ ref }}`→plain-name rewrite) self-references → error. Renamed those CTEs `ref_teams` → `team_ref` (game_results/head_to_head/pythagorean/season_record).
3. **The `{% if is_incremental() %} … {% else %} <real filter> {% endif %}` shape** — the runner's non-greedy is_incremental stripper would delete the WHOLE block INCLUDING the `{% else %}` real `where game_type='R'` filter. Authored the duckdb branch with the else-arm INLINED, not relying on the stripper (rolling_offense/pitching/bullpen).
4. **`game_date` typing** — `stg_batter_pitches`/`mart_pitch_*` store `game_date` as **VARCHAR** in the parquet; cast `::date` before any RANGE-interval window (home_away_splits via `select * replace`, rolling marts in their PA CTE, bullpen pitches CTE). `mart_game_results` emits `max(game_date::date)` → **DATE** (matches the retired Snowflake `MART_GAME_RESULTS.GAME_DATE` DATE); `mart_game_spine` emits `::timestamp` on BOTH union arms → **TIMESTAMP** (matches `MART_GAME_SPINE.GAME_DATE` TIMESTAMP_NTZ, which the original UNION promoted DATE→TIMESTAMP_NTZ).
5. **`dbt_utils.date_spine()` can't survive the bespoke extractor** (it renders a macro the runner can't resolve) — inlined as a DuckDB `range(date '2015-01-01', date '2030-12-31', interval '1 day')` (end-exclusive, matches date_spine; the 2030 tail never reaches output). `mart_team_season_record` only.
6. **Literal `{% else %}` in a SQL `--` comment is parsed by dbt Jinja** → "unknown statement else" compile error. Don't write Jinja tags in prose comments (bit two rolling marts; fixed).
7. **First incremental→view conversion in the program** — `mart_game_results` + 4 others were `incremental`; the lakehouse build is a full rebuild each run, so the dual-branch just drops the incremental config + WHERE arms (the external-table view is materialized out-of-band by `run_w1_lakehouse.py`).

## ⚙️ OPERATOR RUN-ORDER (W5 is OPT-IN until validated — `--w5` not on the daily op yet)

```
# 1. Export seeds + the 4 W4-deferred raw tables → S3 parquet
uv run python scripts/export_w5_raw_to_s3.py

# 2. Build the W5 marts → S3  (>1 min; reads the W1/W2/W3pre parquet, builds Group A + B)
#    PREREQ: the W3pre stg_statsapi_games parquet must exist (run --w3pre once if not).
uv run python scripts/run_w1_lakehouse.py --w5-only
#    (--w5-group-a-only restricts to the 10-mart Group A chain; --w5 also runs W1+W2+W3 first.)

# 3. Generate + REVIEW + run the external-table DDL in Snowflake (BEFORE the PR merges)
uv run python scripts/ddl/generate_w5_external_tables.py   # → scripts/ddl/w5_external_tables.generated.sql
#    review (esp. mart_game_results=DATE, mart_game_spine=TIMESTAMP_NTZ), then run it in Snowflake.

# 4. Refresh external tables (or rely on refresh_w1_external_tables_op)
uv run python scripts/refresh_w1_external_tables.py

# 5. PARITY GATE — must be GREEN before cutover (runs while marts are still SF tables)
uv run python scripts/parity_check_w5.py
#    Freshness-tolerant set (descend from the S3 pitch substrate ⊇ Snowflake) flagged informational;
#    the 3 raw/seed-fed (dim_team_name_lookup, stg_batter_sprint_speed, mart_eb_park_factors) match <0.1%.

# 6. Merge PR → P5 CD auto-deploys (dbt/** + scripts/**). Post-deploy: spot-check a few SF views
#    resolve; hit a game-detail endpoint (pythagorean fields populate); confirm settlement runs green.
```

**Build-ordering note (load-bearing):** within `_build_w5`, `dim_team_name_lookup` + `mart_game_results` are built & registered as DuckDB views BEFORE `mart_game_spine` (which reads both), and the spine BEFORE the Group B marts that read it (`mart_team_fielding_oaa`, `mart_team_defense_quality_rolling`). The seeds + `stg_statsapi_games` + W2 `mart_starting_pitcher_game_log` are registered from S3 first.

**`git add` (every file this session changed/created):**
```
git add \
  dbt/models/mart/dim_team_name_lookup.sql \
  dbt/models/mart/mart_game_results.sql \
  dbt/models/mart/mart_game_spine.sql \
  dbt/models/mart/mart_head_to_head_team_history.sql \
  dbt/models/mart/mart_home_away_splits.sql \
  dbt/models/mart/mart_park_run_factors.sql \
  dbt/models/mart/mart_team_pythagorean_rolling.sql \
  dbt/models/mart/mart_team_rolling_offense.sql \
  dbt/models/mart/mart_team_rolling_pitching.sql \
  dbt/models/mart/mart_team_season_record.sql \
  dbt/models/mart/mart_eb_park_factors.sql \
  dbt/models/mart/mart_bullpen_effectiveness.sql \
  dbt/models/mart/mart_team_fielding_oaa.sql \
  dbt/models/mart/mart_team_defense_quality_rolling.sql \
  dbt/models/staging/stg_batter_sprint_speed.sql \
  scripts/run_w1_lakehouse.py \
  scripts/refresh_w1_external_tables.py \
  scripts/export_w5_raw_to_s3.py \
  scripts/parity_check_w5.py \
  scripts/ddl/generate_w5_external_tables.py \
  scripts/ddl/w5_external_tables.generated.sql \
  pipeline/ops/daily_ingestion_ops.py \
  quant_sports_intel_models/baseball/edge_program/story_prompts.md \
  quant_sports_intel_models/baseball/edge_program/E11_1_W5_session_recap.md
# EXCLUDE (gitignored, go to S3): all *.parquet.
```

## ⚠️ BUILDER DUAL-WRITE caveat carried forward (W4 → W5 → W7)
Group B reads the S3 mirror of `eb_park_factors_raw` / `eb_bullpen_team_posteriors` / `oaa_team_season_raw` / `sprint_speed_raw`. The builders that WRITE those (`fit_park_priors.py`, the `eb_bullpen_team_posteriors` dbt model, the FanGraphs-OAA + Savant-sprint ingests) **KEEP their Snowflake writes** — this export is the one-time/opt-in S3 mirror. The recurring-freshness wiring (run the export inside the daily op + flip `--w5` default-on) is the **cutover follow-up**, same as W4's opt-in rollout. Likewise the W4 `cluster_pitchers`/`fit_granular_park_priors --s3` Snowflake writes still feed the feature layer → drop at **W7**.

## ❗ DEFERRED (dependency/risk, NOT skip — must be picked up later)

1. **`mart_player_profile_identity`** → **W7**: hard-blocked on `feature_pregame_injury_status` (a `feature_*` SCD-2 model = the W7 feature layer). Its other upstreams (W2 marts + `stg_statsapi_player_profiles` W4 + `stg_statsapi_lineups`) are fine once the latter lands.
2. **`mart_team_schedule_context` + `mart_player_game_starts`** → a **W5b mini-wave or W6**: each needs a NEW staging-flatten precursor not yet in S3 — `stg_statsapi_venues` (← `source('statsapi','venues_raw')`) and `stg_statsapi_lineups` (← `source('statsapi','monthly_schedule')`, the SAME raw blob already in `lakehouse_raw/monthly_schedule` → a W3pre-style flatten). Both read the Group-A `mart_game_spine` (now migratable). Tractable; just out of this session's A+B scope.
3. **The archetype sub-task** (`mart_batter_archetype_vs_pitcher_cluster`) → its **OWN builder-mini-wave** (the prompt explicitly permits splitting): `materialized='incremental'` → full-rebuild conversion + the non-dbt `mart_player_archetype_posteriors` (builder `compute_archetype_posteriors.py`) + `cluster_batters.py` (`cluster_pitchers.py` already migrated in W4). **DISTINCT risk class — Bayesian/k-means → TOLERANCE-based parity, not row-exact** → its own focused pass + parity treatment; do NOT blend with the game-results marts.

## Notes for whoever picks up the deferrals / a future wave
- **Cutover order is load-bearing** (W1–W4 lesson): create the `lakehouse_ext` external tables in Snowflake BEFORE the PR merges (CI `state:modified+` + P5 CD build the SF view-over-external-table and FAIL if the table is absent).
- **Seeds stay dbt seeds** — `ref_teams`/`ref_team_aliases` are NOT decommissioned (tiny static, ~0 cost). The S3 parquet + the DuckDB view exist only so the build can read them; **no external table for the seeds** (the `generate_w5_external_tables.py` list excludes them).
- **Parity freshness-aware**: the pitch/spine-derived marts (most of W5) will show a small DuckDB current-season / today's-scheduled SURPLUS (S3 `stg_batter_pitches` ⊇ Snowflake) — EXPECTED, flagged informational; only the 3 raw/seed-fed marts must match <0.1%. Hash WARNs = the known FLOAT/DATE-stringification artifact (row-count + PK are the gates).
- Memory: `project_e11_1_w5_lakehouse.md`.
