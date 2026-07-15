# NCAAF lakehouse ingest (NCAAF-P0.2)

Instantiates the shared `sport_data_platform.md` pattern for NCAAF: **CFBD / Odds API /
nflverse → S3 Delta lake → dbt-duckdb staging**. Weekly-batch, cheap, Delta-native.

## Layout (matches `sport_data_platform.md §2`)
```
football/ncaaf/ingest/
  cfbd_client.py   # landmine-hardened CFBD v2 client (the 200-text/html JSON guard)
  s3io.py          # SHARED: records/DataFrame → season-partitioned Delta in S3 (AKID-safe auth)
  sources.py       # NCAAF-SPECIFIC: the 24-table registry (source→fetch→grain→partition→cadence)
  handler.py       # SHARED: registry-driven entrypoint (Lambda + Dagster-op + CLI)
  backfill.py      # SHARED: off-Lambda full-history runner (2014–2025)
  query_lake.py    # SHARED: the DuckDB-over-lake parity tool (§7A)
  Dockerfile / requirements.txt
quant_sports_intel_models/sports_dbt/   # the SHARED new-sports dbt-duckdb project (NOT MLB's)
  models/ncaaf/staging/stg_ncaaf_*.sql
```
`s3io/handler/backfill/query_lake/cfbd_client` are sport-agnostic — NFL/NCAAB reuse them
unchanged (§2 "copy or symlink across sports"); only `sources.py` + the dbt models differ.

## Architecture decisions inherited
- **Delta-native from day one** (E11.20): raw tables are Delta, season-partitioned; a weekly
  re-pull overwrites the current-season partition (idempotent, ACID, no glob-dup/INC-31).
- **New sport-agnostic bucket** `credence-sports-lakehouse`, prefix-isolated per sport
  (`s3://…/ncaaf/raw/<source>/`). NOT the MLB bucket. **Operator creates it + the grant.**
- **Orchestration = the existing Dagster EC2 box** (unmetered), NOT Lambda+EventBridge.
- **Serving = DynamoDB→S3** (Railway is decommissioned).
- **S3 auth = the instance role** (`s3io.storage_options()` resolves the botocore chain and
  passes explicit creds to delta-rs — the AKID landmine cure; never inline keys).

## Run
```bash
# weekly incremental (current season) — writes S3:
uv run python -m quant_sports_intel_models.football.ncaaf.ingest.handler --seasons 2025

# offline dev / smoke — writes a LOCAL Delta tree (no bucket needed), scoped:
uv run python -m quant_sports_intel_models.football.ncaaf.ingest.handler \
    --seasons 2024 --sources games,odds_ncaaf --weeks 1 --local-root /tmp/ncaaf_lake

# full-history backfill (off-Lambda; ~15.8k CFBD calls → needs the Tier-3 key):
uv run python -m quant_sports_intel_models.football.ncaaf.ingest.backfill --seasons 2014-2025

# dbt-duckdb staging (from quant_sports_intel_models/sports_dbt/, dbt-core NOT fusion):
dbt build --project-dir . --profiles-dir . --select "ncaaf.staging.*"
```

## Cost
CFBD **$10/mo** (Patreon Tier 3 — the free tier's 1,000/mo can't do the ~15.8k-call
backfill) · Odds API **$0 incremental** (existing sub) · nflverse **$0** · compute = DuckDB
over S3 (pennies). **Total new Phase-0 spend: $10/mo.**

## P0.1 landmines encoded here (do not rediscover)
- CFBD wrong path → **200 text/html** (Swagger), not 404 → `cfbd_client.get()` asserts JSON.
- `/plays/stats` 2,000-row cap → pulled per `gameId`. `/plays` requires `week`.
- year-only endpoints (roster/usage/…) are **1 call/season** — no 136-team loop.
- `/game/box/advanced` takes `id=`. nflverse read as **release Parquet** (nfl_data_py is dead).
