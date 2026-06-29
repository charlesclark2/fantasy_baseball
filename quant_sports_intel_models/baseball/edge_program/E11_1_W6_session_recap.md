# E11.1-W6 session recap — the odds/CLV + odds-serving tier (the most serving-coupled wave)

**Status: CODE-COMPLETE 2026-06-28 (Opus). Parity + external-table create + cutover = operator.**

Migrated the final mart tier — **15 dual-branch models** (`tags=['w6_lakehouse']`, `materialized='view'`
over `baseball_data.lakehouse_ext.*`) — off Snowflake → DuckDB/S3. This is the tier the program's
"serving moves last" warning was about: it carries the request-time fallback reads AND the
**intraday** odds-serving refresh.

## The 15 models
**2 Group-C staging flattens** (inherited from W5):
- `stg_statsapi_venues` ← `venues_raw` RAW JSON (lakehouse_raw; NEW precursor export)
- `stg_statsapi_lineups` ← `monthly_schedule` RAW JSON (lakehouse_raw; already exported W3pre)

**13 odds/CLV + odds-serving marts** (built in dep order):
`mart_odds_outcomes` (incremental→view, **PARTITIONED** — see below) → `mart_odds_events` →
`mart_game_odds_bridge` → `mart_odds_consensus`, `mart_odds_line_movement`,
`mart_closing_line_value` → `mart_clv_labeled_games` → `mart_clv_label_count`,
`mart_prediction_clv` → `mart_derivative_closes` → `mart_bookmaker_disagreement` +
the 2 Group-C marts `mart_team_schedule_context`, `mart_player_game_starts`.

## Precursor exports (`scripts/export_w6_raw_to_s3.py`)
Only **3** needed (the odds STAGING is already in S3 from W3pre):
- `odds_snapshots_historical` (2021–25, ~2.6M rows, STATIC) → `lakehouse/.../part-0.parquet` —
  read DIRECTLY (via `source()`) by `mart_closing_line_value` + `mart_odds_line_movement`.
- `daily_model_predictions` (~54k, RECURRING MIRROR) → read by `mart_prediction_clv` +
  `mart_clv_labeled_games`. The Snowflake table STAYS the serving write/read target; this is only
  an S3 mirror for the lakehouse CLV build. ⚠️ **must be re-exported before each W6 daily build,
  AFTER predict_today**, else the /performance CLV marts go stale.
- `venues_raw` (~96 rows VARIANT) → `lakehouse_raw/venues_raw/` for the venues flatten.

Both flat exports are read by the marts as **TYPED views** registered in `run_w1_lakehouse._build_w6`
(`SELECT * REPLACE (score_date::date, inserted_at::timestamp, snapshot_ts::timestamptz, …)`) so the
marts' DATE / TIMESTAMP_NTZ / TIMESTAMP_TZ output columns match Snowflake exactly.

## ⭐ INTRADAY REFRESH — option (b) today-scoped partitioned rebuild (operator-decided)
The W6-unique problem: `mart_odds_outcomes`/`mart_game_odds_bridge` rebuild **intraday** on the
odds-capture cycle (`odds_current_rebuild_sensor`), not the daily op. Post-cutover the intraday
Snowflake `dbt run` only rebuilds the VIEW (a no-op for data) → served prices would go stale
(INC-16) unless the S3 parquet is rebuilt + the external table REFRESHed on the odds cadence.

**`mart_odds_outcomes` parquet is split into two date buckets** the external table UNIONs:
- `mart_odds_outcomes/_history/data.parquet` — `commence_date < today` (frozen; daily full build)
- `mart_odds_outcomes/_current/data.parquet`  — `commence_date >= today` (intraday rewrite, O(today))

Disjoint split on the LA `commence_date == today`. Columns (incl. `commence_date`) stay IN the
parquet (NOT Hive `PARTITION_BY`, which strips the partition column from the file and breaks the
external-table column inference). Intraday rewrites ONLY `_current` (S3 multipart ⇒ atomic — a
failed COPY leaves the prior good object live). The intraday `_current` flatten reads a RECENT raw
window (ingestion `dt >= today − 12 days`, a literal dt-glob list) so it's O(recent) yet COMPLETE
(no game's odds are captured >~7 days ahead); the daily full build re-establishes both buckets.

**Runner (`scripts/run_w1_lakehouse.py`):** `--w6` (daily full, both buckets) / `--w6-only` /
`--w6-odds-current` (intraday: rewrite `_current` + `mart_game_odds_bridge` only). `_register_mart_views`
globs `**/*.parquet` for partitioned marts. Added `INSTALL icu; LOAD icu` + `SET TimeZone='UTC'`
(W6 marts use `AT TIME ZONE` for the LA/ET windows; UTC pin makes the NTZ↔TZ union casts
deterministic). Harmless for W1–W5.

**Refresh (`scripts/refresh_w1_external_tables.py`):** `W6_TABLES` (daily best-effort); `--w6-odds`
(intraday: `mart_odds_outcomes` + `mart_game_odds_bridge`, REQUIRED/HALT); `--w6-clv` (once/day:
closing_line_value + prediction_clv + line_movement).

**Dagster wiring (`pipeline/ops/intraday_ops.py`):** `odds_current_dbt_rebuild` (+scope='odds') and
`odds_clv_dbt_rebuild` (+scope='clv') now call `_w6_lakehouse_intraday`, **gated behind
`W6_LAKEHOUSE_INTRADAY` (default off)** so it's a clean NO-OP until cutover — the operator flips the
env var to `1` AFTER creating the external tables + validating parity. ALERT-tier: a failure warns
LOUD (stale prices visible) but never crashes the capture op. The existing Snowflake `dbt run` is
kept (harmless view-rebuild post-cutover; drop once validated).

## DuckDB-compat lessons (new this wave)
- **`::float` is 32-bit REAL in DuckDB but 64-bit DOUBLE in Snowflake** → use `::double` in every
  duckdb branch (caught venue latitude 40.82 → 40.8199996). Fixed in venues/consensus/derivative/disagreement.
- Snowflake `convert_timezone('UTC','America/New_York', ts)` → `ts::timestamp at time zone 'UTC' at
  time zone 'America/New_York'` (needs ICU; session tz UTC).
- `iff(c,a,b)` → `CASE`; `count_if(c)` → `count(*) filter (where c)`; `dateadd('minute',720,x)` →
  `x + interval 720 minute`; `dateadd('day',-1,x)` → `x - interval 1 day`.
- **Zip-unnest for array index** (stg_statsapi_lineups `batting_order`): two `unnest()` in one SELECT
  zip position-wise — `unnest(range(1, len(players)+1)) as batting_order, unnest(players) as player`.
  Dedup the schedule blob to latest-snapshot-per-game_pk BEFORE exploding players (the W3pre OOM guard).
- `mlb_odds_raw.home_team`/`away_team` are real Snowflake columns but the W3pre raw export carries only
  `raw_json` → the disagreement historical flatten reads `json_extract_string(raw_json,'$.home_team')`
  (identical value).
- Two marts mix DATE (historical arm) + TIMESTAMP (live/bridge arm) in a UNION → Snowflake promotes to
  TIMESTAMP_NTZ; DuckDB promotes identically (DATE→TIMESTAMP). `close_snapshot_ts` is TIMESTAMP_TZ; the
  few LIVE-arm rows' NTZ→TZ promotion can differ by session tz (parity treats it as a WARNING, not a gate).

## Read-path audit (careful tier — confirmed)
Every request-time read of a W6 mart in `app/backend/**` is **fallback-tier** (DynamoDB → S3 →
Snowflake last resort): `picks.py` reads `daily_model_predictions` + `mart_odds_outcomes` +
`mart_odds_line_movement`; `performance.py` reads `mart_clv_labeled_games` + `daily_model_predictions`.
All behind `serving_cache.get_cache(...)`. Post-cutover those Snowflake fallbacks serve the S3-backed
view (like W5's pythagorean). `mart_team_schedule_context`/`mart_player_game_starts` are batch (feature
build) — not request-read. **Post-cutover VERIFY LIVE** (operator): EV Tracker, Line Shopping,
game-detail, `mart_odds_outcomes` freshness — not just parity.

## Gates
`dbtf compile` 1771/1771 ✅. fast pytest 690 passed / 1 skipped ✅. All 15 duckdb branches bind + the
zip-unnest/venue-flatten/xref-pivot/partition-split verified on synthetic data. `state:modified+ build`
is operator-gated (needs the external tables) — CI passes on clean runners post-table-create. Expect
possible stale dbt-test fires across the odds/CLV downstream subgraph (W3pre lesson) — verify old==new
data (it's infra), then fix the stale test bound, don't change mart semantics.

## ⏭️ Operator run-order (per program order — external tables BEFORE the PR merges)
1. `uv run python scripts/export_w6_raw_to_s3.py`  (>1 min on odds_snapshots_historical 2.6M)
2. `uv run python scripts/run_w1_lakehouse.py --w6`  (writes W6 parquet, incl. mart_odds_outcomes _history/_current)
3. `uv run python scripts/parity_check_w6.py`  (BEFORE flipping to views — non-tautological)
4. `uv run python scripts/ddl/generate_w6_external_tables.py` → review → run the DDL in Snowflake (15 lakehouse_ext tables)
5. `uv run python scripts/refresh_w1_external_tables.py` (or just confirm W6_TABLES refresh)
6. Merge dev→main (P5 CD redeploys). THEN: `W6_LAKEHOUSE_INTRADAY=1` on the box + run the daily op
   with `--w6` (and add the dmp re-export after predict_today).
7. **Post-cutover live check:** EV Tracker / Line Shopping / game-detail / `mart_odds_outcomes` fresh;
   intraday odds cycle rewrites `_current` + REFRESHes the external table (served prices stay fresh).

## git add
```
scripts/run_w1_lakehouse.py
scripts/export_w6_raw_to_s3.py
scripts/ddl/generate_w6_external_tables.py
scripts/refresh_w1_external_tables.py
scripts/parity_check_w6.py
pipeline/ops/intraday_ops.py
pipeline/ops/daily_ingestion_ops.py
dbt/models/staging/stg_statsapi_venues.sql
dbt/models/staging/stg_statsapi_lineups.sql
dbt/models/mart/mart_odds_outcomes.sql
dbt/models/mart/mart_odds_events.sql
dbt/models/mart/mart_game_odds_bridge.sql
dbt/models/mart/mart_odds_consensus.sql
dbt/models/mart/mart_odds_line_movement.sql
dbt/models/mart/mart_closing_line_value.sql
dbt/models/mart/mart_clv_labeled_games.sql
dbt/models/mart/mart_clv_label_count.sql
dbt/models/mart/mart_prediction_clv.sql
dbt/models/mart/mart_derivative_closes.sql
dbt/models/mart/mart_bookmaker_disagreement.sql
dbt/models/mart/mart_team_schedule_context.sql
dbt/models/mart/mart_player_game_starts.sql
quant_sports_intel_models/baseball/edge_program/E11_1_W6_session_recap.md
quant_sports_intel_models/baseball/edge_program/story_prompts.md
```
EXCLUDED (gitignored S3 artifacts): `w6_external_tables.generated.sql` is generated; the parquet
under `s3://…/lakehouse/` is S3-only.

⇒ After W6 cutover, only the READERS (feature/serving layer) + the Cortex narrative remain on
Snowflake → **W7 (= Wsv)** finishes the program.
