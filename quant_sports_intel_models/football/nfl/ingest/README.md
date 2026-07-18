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

## N0.4 — net-new market + status data (Odds API historical/props + injuries/inactives)
The net-new betting data the old stack LACKS: leakage-safe **closing lines** (for CLV), the
**DEEP player props**, and the injury/inactive status that moves NFL lines. Three `on_demand`
registry sources drive the paid feeds — `on_demand=True` means a plain nflverse `backfill`
NEVER pulls them (no accidental Odds-API credit burn); they are named explicitly by
`odds_backfill.py` (or a Dagster op):

| source | endpoint | what | floor | landing |
|---|---|---|---|---|
| `odds_nfl_props` | `/events/{id}/odds` (live) | CURRENT player props (pass/rush/rec yds+tds+att+receptions+anytime-TD) | live only | `nfl/raw/odds_nfl_props/` |
| `odds_nfl_historical` | `/historical/.../odds` | CLOSING game lines (h2h/spread/total) — the CLV benchmark | **2020** | `nfl/raw/odds_nfl_historical/` |
| `odds_nfl_props_historical` | `/historical/.../events/{id}/odds` | CLOSING player props (CLV/props backtest) | **2020** | `nfl/raw/odds_nfl_props_historical/` |

The live game lines (`odds_nfl`) + scores (`odds_nfl_scores`) already landed in N0.2 stay the
recurring cheap feeds.

**Leakage-safe close (the AC):** for each distinct season kickoff `K` (read FREE from nflverse
`schedules`, ET→UTC, DST-correct) the historical snapshot is taken at `K − buffer` (default 5
min) → the captured market is strictly pre-kickoff. Every row also carries the API's own
`commence_time` + `_snapshot_ts`/`_requested_snapshot`, so a Phase-1 CLV mart can enforce the
hard guard (keep only `snapshot_ts < commence_time`) belt-and-suspenders. A tight ±30-min
`commenceTimeFrom/To` isolates exactly that kickoff window's games (the next NFL window is ≥3h
away → no bleed).

**Credits (the AC — Odds-API cost = 10 × #markets × #regions per call):**
`--dry-run` reads schedules (free) and prints the estimate before any paid call. Per season
(`us` region): **game lines ≈ 4,100 cr** (~137 kickoff snapshots × 3 markets × 10); **props
≈ 34,200 cr** (~285 games × 12 markets × 10 — the heavy one). The paid `/historical` path needs
the **MAIN** Odds-API key (the starter tier does not support it).

```bash
# instant credit estimate (NO paid calls):
uv run python -m quant_sports_intel_models.football.nfl.ingest.odds_backfill \
    --sources odds_nfl_historical,odds_nfl_props_historical --seasons 2020-2024 --dry-run

# tiny live VERIFICATION pull (proves the path; caps events/snapshot):
uv run python -m quant_sports_intel_models.football.nfl.ingest.odds_backfill \
    --sources odds_nfl_historical --seasons 2024 --weeks 1 --max-events 3

# BOX — full closing-line backfill (operator; resumable via --skip-existing):
docker compose -f services/dagster/aws/docker-compose.yml exec -T \
    -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
    python -m quant_sports_intel_models.football.nfl.ingest.odds_backfill \
    --sources odds_nfl_historical --seasons 2020-2024 --skip-existing
```

**Injuries / inactives (`injuries`, already in the registry from N0.2, `nfl/raw/injuries/`):**
nflverse `injuries` = the official weekly injury report — `report_status` (Out/Doubtful/
Questionable) + `practice_status`, keyed (season, week, gsis_id), stamped `date_modified`
(point-in-time / as-of, leakage-safe: a report is known before kickoff). ⚠️ **there is NO
dedicated nflverse game-day inactives release** — the 90-min-pre-kickoff inactive LIST is not
published; the leakage-safe pre-kickoff "inactive" signal is `report_status = 'Out'`, and who
actually played is recoverable post-hoc from `pbp_participation` / `snap_counts` (both landed).
Cadence is weekly in-season (a Dagster op / cron names it; ops-scoped, not this data story).

## Cost
nflverse **$0** (free public release Parquet — no API budget, unlike NCAAF's CFBD $10/mo) ·
live Odds API **$0 incremental** (existing sub) · the paid `/historical` CLV backfill is
credit-metered (see N0.4 above — ~4.1k cr/season game lines; props ~34k cr/season → scope
deliberately) · compute = DuckDB over S3 (pennies). **New Phase-0 spend beyond the historical
odds credits: $0.**

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
