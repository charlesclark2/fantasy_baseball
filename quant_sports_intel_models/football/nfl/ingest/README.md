# NFL lakehouse ingest (NFL-N0.2)

Instantiates the shared `sport_data_platform.md` pattern for NFL (the 2nd sport after
NCAAF-P0.2): **nflverse release Parquet / Odds API → S3 Delta lake → dbt-duckdb staging**.
Weekly-batch, cheap, Delta-native. A **FRESH re-pull** — the stale Snowflake `FOOTBALL_DATA`
rows are NOT migrated (brownfield, `nfl_data_inventory.md` §0).

## Layout (matches `sport_data_platform.md §2`)
```
football/nfl/ingest/
  s3io.py          # SHARED (copy of NCAAF): records/DataFrame → season-partitioned Delta in S3
                   #   (AKID-safe auth) + 2 NFL hardenings: null-col→string, empty-slice skip
  sources.py       # NFL-SPECIFIC: the 32-table registry (nflverse typed + Odds API raw_json)
  handler.py       # SHARED: registry-driven entrypoint (Lambda + Dagster-op + CLI); forks the
                   #   write on spec.typed (write_dataframe vs write_records)
  backfill.py      # SHARED: off-Lambda fresh-repull runner (2016–2025 advanced-stack window)
  query_lake.py    # SHARED: the DuckDB-over-lake parity tool (§7A)
  Dockerfile / requirements.txt
quant_sports_intel_models/sports_dbt/   # the SHARED new-sports dbt-duckdb project (NOT MLB's)
  macros/nfl_lake.sql
  models/nfl/staging/stg_nfl_*.sql
```
`s3io/handler/backfill/query_lake` are sport-agnostic (copied from NCAAF); only `sources.py` +
the dbt models are NFL-specific.

## The ONE structural divergence from NCAAF: TYPED, not JSON
nflverse ships **typed release Parquet** (145-col player weeks, 372-col PBP, …). So NFL reads
each asset via DuckDB `read_parquet` → a pandas DataFrame → `s3io.write_dataframe` (**typed
Delta**, columns preserved), and the staging is plain column renames — NOT `json_extract`. Only
the two Odds API feeds stay JSON (`write_records` / `raw_json`), like NCAAF.

## Architecture decisions inherited
- **Delta-native from day one** (E11.20): raw tables are Delta, season-partitioned; a weekly
  re-pull overwrites the current-season partition (idempotent, ACID, no glob-dup/INC-31).
- **New sport-agnostic bucket** `credence-sports-lakehouse`, prefix-isolated per sport
  (`s3://…/nfl/raw/<source>/`). Shared with NCAAF. **Operator creates the grant** (bucket
  already exists from NCAAF-P0.2).
- **Orchestration = the existing Dagster EC2 box** (unmetered), NOT Lambda+EventBridge.
- **Serving = DynamoDB→S3** (Railway is decommissioned).
- **S3 auth = the instance role** (`s3io.storage_options()` resolves the botocore chain and
  passes explicit creds to delta-rs — the AKID landmine cure; never inline keys).

## Run
```bash
# weekly incremental (current season) — writes S3 (BOX; instance-role write):
uv run python -m quant_sports_intel_models.football.nfl.ingest.handler --seasons 2025

# offline dev / smoke — writes a LOCAL Delta tree (no bucket / no S3 creds), scoped:
uv run python -m quant_sports_intel_models.football.nfl.ingest.handler \
    --seasons 2024 --sources schedules,snap_counts,odds_nfl --local-root /tmp/nfl_lake

# full fresh backfill (off-Lambda; ON THE BOX — heavy PBP feeds, in-region PUTs):
uv run python -m quant_sports_intel_models.football.nfl.ingest.backfill --seasons 2016-2025

# dbt-duckdb staging (from quant_sports_intel_models/sports_dbt/, dbt-core NOT fusion):
dbt build --project-dir . --profiles-dir . --select "nfl.staging.*"
```

## Cost
nflverse **$0** (free public release Parquet — no API budget, unlike NCAAF's CFBD $10/mo) ·
Odds API **$0 incremental** (existing sub; ~97.7k req remaining) · compute = DuckDB over S3
(pennies). **Total new Phase-0 spend: $0.**

## N0.1 landmines encoded here (do not rediscover — `nfl_data_inventory.md` §1)
- **No `nfl_data_py`** (abandoned; pins pandas==1.5.3 → won't build on py3.12) → read release
  Parquet directly via DuckDB.
- **Column names differ between assets** → every asset DESCRIBEd live 2026-07-17; the registry
  URLs + season columns are observed truth.
- **`stats_player_week` (145 cols)**, NOT legacy `player_stats` (53 cols, caps 2024).
- **Advanced-feed floors** differ (NGS/participation 2016, PFR 2018, FTN 2022) → a below-floor
  per-year read 404s → returned as an empty slice (clean skip, not an error).
- **`pbp_participation` has no `season` column** (keyed `nflverse_game_id`) → the URL year is
  stamped as the partition.
- **Wide-PBP `void` landmine (N0.2 smoke):** an all-null column in a season slice → pyarrow
  `null` type → Delta `void` → `delta_scan` read FAILS. `s3io._sanitize_null_columns` recasts
  null → string before every typed write.
- **Cross-season type-drift (N0.2 box backfill):** nflverse types a column per-season-file —
  `jersey_number` / `draft_number` are VARCHAR ≤2015 (dirty values like `'79D'`) but INTEGER
  2016+. Landed as separate season partitions with `schema_mode='merge'`, the first-written
  season fixes the Delta column type → a later season with the other type fails the merge cast
  (`Cannot cast string '79D' to Int32`). Cure: the registry `str_cols` VARCHAR-pins those columns
  at read (`_projection`) so the Delta type is stable across seasons. ⚠️ if a column's stored
  Delta type already drifted, the table must be DROPPED + rebuilt (INC-19 discipline) — a
  `--full-refresh` won't change a stored type.
- **Two nflverse URL shapes:** per-season `<tag>/<prefix>_YYYY.parquet` vs single-file
  `<tag>/<asset>.parquet` (filter by `season`).
