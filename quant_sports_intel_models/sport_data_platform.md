# Sport Data Platform — Lean Lakehouse Architecture (shared)

**Status:** v1.0 — the canonical pre-profit data architecture for **all new sport spinoffs**.
**Last updated:** 2026-06-18 _(refresh on any material change)_
**Used by:** `football/nfl/`, `football/ncaaf/`, `basketball/ncaab/` — each sport **instantiates this pattern; it does not re-invent it.** (MLB stays on its established Snowflake/Dagster stack; this is for the pre-profit sports.)
**Parents:** `multi_sport_roadmap.md` (esp. §6) · MLB `baseball/edge_program/` conventions (§0/§6).

> **One-line thesis:** land free sport data as **Parquet in an S3 data lake**, orchestrate the pulls with **Lambda + EventBridge** (pennies, serverless, already in our AWS footprint), transform with **`dbt-duckdb` over S3** (free, in-process), serve precomputed results from the existing **Railway PG**. When a sport earns it, **swap only the layers above S3** (Lambda→Dagster, DuckDB→Snowflake) — the lake stays.

> 🚩🚩 **STALENESS CORRECTIONS — READ BEFORE COPYING ANYTHING BELOW (2026-07-13, from NCAAF-P0.1; applies to NFL + NCAAB too):** two recommendations in this doc are now WRONG — the inline examples below (Dockerfile, `sources.py`, the diagram, the reverse-ETL) are NOT yet rewritten, so do NOT copy them verbatim:
> 1. **`nfl_data_py` IS ABANDONED** — it pins `pandas==1.5.3`, which will NOT build on py3.12 (§4/§10 still recommend it). ⇒ **read the nflverse release Parquet DIRECTLY via DuckDB** `read_parquet('https://github.com/nflverse/nflverse-data/releases/download/<asset>/<asset>.parquet')` — dependency-free + lakehouse-native. Drop the `nfl_data_py` Docker dep.
> 2. **"Railway PG" is DECOMMISSIONED (INC-16).** Serving = **DynamoDB (primary) → S3 (fallback)**, same as MLB post-decommission. Do NOT stand up Railway anywhere in a new sport.
> 3. **CFBD wrong-path gotcha (NCAAF, likely other REST sources):** a wrong CFBD path returns **`200 text/html`** (a Swagger page), not a 404 → every fetcher must assert `Content-Type: application/json` + that the body parses; status 200 is NOT a success signal.
> _(A fuller doc-refresh to rewrite the inline `nfl_data_py`/Railway references is a small queued fix-up — until then this banner governs.)_

> ## 🏛️ CROSS-SPORT ARCHITECTURE DECISIONS (operator Q&A 2026-07-13 — apply to NCAAF + NFL + NCAAB)
> 1. **dbt: a SEPARATE `dbt-duckdb` project for the new sports — NOT the MLB dbt project.** MLB's dbt is Snowflake-targeted with its own manifest / `state:modified+` CI / type-contract guards; the new sports are DuckDB/S3-native with a fully DISJOINT DAG (zero cross-sport refs). Mixing adapters + inheriting MLB's Snowflake CI baggage = a mess. ⇒ **ONE new `dbt-duckdb` project shared across NCAAF/NFL/NCAAB**, with per-sport model folders + per-sport schemas (`ncaaf_staging`/`ncaaf_marts`, etc.); split into per-sport projects ONLY if they later diverge. Keeps each sport's build unable to break MLB's, and vice-versa.
> 2. **S3: a NEW sport-agnostic bucket, PREFIX-separated by sport — not the MLB bucket, not one bucket per sport.** The MLB bucket (`baseball-betting-ml-artifacts`) is baseball-named; a new bucket (e.g. `credence-sports-lakehouse`) with `s3://…/<sport>/raw/<source>/season=YYYY/…` keeps naming clean + IAM/lifecycle isolated while sharing one bucket across the new sports (cheaper + simpler than per-sport buckets). Operator: create the bucket + the instance-role grant. (Scripts are ALREADY accounted for by §2's per-sport `<sport>/ingest/` layout + shared `s3io/handler/backfill` utils.)
> 3. **Orchestration: the EXISTING self-hosted Dagster EC2 — NOT Lambda + EventBridge (the §1/§4 recommendation is now STALE).** The Lambda+EventBridge choice existed to dodge **Dagster+ metered run-minutes** — but Dagster+ is GONE (INC-16); we self-host Dagster OSS on EC2, which is UNMETERED, and the box runs 24/7 for MLB already ⇒ NCAAF's weekly ops are ~free marginal cost + inherit the box's proven patterns (dbt-runner, the tiered HALT/WARN/ALERT failure contract, the monitors). ⚠️ **ISOLATE per sport:** separate jobs/schedules/code-location namespacing so a new-sport failure can't touch MLB serving (and vice-versa). ⇒ **update §1/§4: pulls run as Dagster ops on the box, not Lambda.**

---

## 1. The pattern
```
                 EventBridge cron (weekly in-season)
                          │  {sport, sources, seasons, mode}
                          ▼
   free APIs ──▶  Lambda ingest ──▶  S3 data lake (Parquet)
   (nfl_data_py,    (fetch→Parquet)    s3://<bucket>/<sport>/raw/<source>/season=YYYY/part-*.parquet
    CFBD, Odds API)                          │
                                             ▼
                              dbt-duckdb  (reads S3 Parquet)
                              staging → marts  (free, in-process)
                                             │
                         serving marts ──────┼────▶ Railway PG  ──▶ Credence app
                         (reverse-ETL)       └────▶ (optional) marts back to S3 Parquet
   backfill (2015–present): one-off OFF-Lambda (container/EC2) using the SAME ingest fns
   migrate later: Lambda→Dagster, DuckDB→Snowflake (COPY/external tables from the SAME S3)
```

## 2. Repo layout (identical shape per sport)
```
quant_sports_intel_models/<sport>/
  <sport>_guide.md
  <sport>_data_inventory.md          # the sport's master data file
  ingest/
    s3io.py            # SHARED util: DataFrame → partitioned Parquet in S3 (copy or symlink across sports)
    sources.py         # SPORT-SPECIFIC registry: source name → fetch fn + season col + table name
    handler.py         # SHARED Lambda entrypoint (registry-driven; sport passed in the event)
    backfill.py        # SHARED off-Lambda runner for full-history pulls
    Dockerfile         # container image (deps too big for a zip)
    requirements.txt
  dbt/                 # dbt-duckdb project
    profiles.yml
    dbt_project.yml
    models/_sources.yml
    models/staging/*.sql
    models/marts/*.sql
  infra/
    eventbridge.tf     # (or serverless.yml) schedule + Lambda + IAM
```
`s3io.py`, `handler.py`, `backfill.py`, `tools/query_lake.py` (§7A), the dbt-duckdb `profiles.yml`, and the EventBridge module are **shared boilerplate** — only `sources.py`, the dbt models, and the schedule payload are sport-specific.

> 🧨 **REUSABLE BACKFILL LANDMINES (carry across ALL sports — surfaced by NCAAF-P0.6, apply equally to NFL-N0.4 + MLB backfills):**
> 1. **Season defaults MUST be clock-derived, never pinned.** A hard-coded season range (e.g. `2020–2024`) is **stale by a full season the day it merges** — P0.6 shipped pinned and silently missed 2025. Derive the default from the clock (`last_completed_season()`), and handle January conservatively so a default run never pulls an in-progress season.
> 2. **`--skip-existing` will silently PROTECT a partial/stub partition.** A 3-event `--max-events N` verification stub was preserved by a later full backfill because `--skip-existing` saw the partition as "present" — caught only by the coverage check, not the run. ⇒ re-pull a stubbed season WITHOUT the flag; never trust partition-presence as completeness.
> 3. **Ship a re-runnable acceptance check with exit 0/1** (like P0.6's `verify_odds_historical.py`) so coverage/quality can gate CI or a handoff — it's what caught both #2 and an FBS-orphan misclassification here.
> 4. **Paid per-event sources: `on_demand`-gate them out of the default backfill** so a routine free pull can never burn paid credits; the paid source must be named explicitly.

## 3. S3 lake conventions
- **Key scheme:** `s3://<bucket>/<sport>/raw/<source>/season=YYYY/part-0000.parquet` (one logical table per `source`; partition by `season`, add `/week=NN/` only where natural).
- **Idempotent writes:** each run **overwrites the (source, season) partition** (delete-prefix → put). Weekly incremental = re-pull the *current* season and rewrite just that partition. Backfill = all seasons, once, off-Lambda.
- **Format:** Parquet (snappy) via pyarrow; preserve dtypes (pandas→pyarrow). Lowercase column names.
- **One bucket, many sports** (prefix-isolated) keeps IAM + cost simple.

## 4. Ingest scaffold (copy-paste starting point)

**`ingest/s3io.py`** — shared:
```python
import io, boto3, pyarrow as pa, pyarrow.parquet as pq
_s3 = boto3.client("s3")

def write_partition(df, bucket, sport, source, season, *, week=None):
    """Overwrite one (source, season[, week]) partition with a single Parquet object."""
    prefix = f"{sport}/raw/{source}/season={season}" + (f"/week={week}" if week is not None else "")
    # clear existing objects under the partition (idempotent)
    for page in _s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix + "/"):
        objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objs: _s3.delete_objects(Bucket=bucket, Delete={"Objects": objs})
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), buf, compression="snappy")
    _s3.put_object(Bucket=bucket, Key=f"{prefix}/part-0000.parquet", Body=buf.getvalue())
    return len(df)
```

**`ingest/sources.py`** — sport-specific (NFL shown; the prior notebook's exact list):
```python
import nfl_data_py as nfl
# registry: source_name -> (fetch(seasons)->DataFrame, season_col)
SOURCES = {
    "weekly_data":            (lambda yrs: nfl.import_weekly_data(yrs),                 "season"),
    "weekly_rosters":         (lambda yrs: nfl.import_weekly_rosters(yrs),              "season"),
    "rosters":                (lambda yrs: nfl.import_seasonal_rosters(yrs),            "season"),
    "schedules":              (lambda yrs: nfl.import_schedules(yrs),                   "season"),
    "depth_charts":           (lambda yrs: nfl.import_depth_charts(yrs),                "season"),
    "snap_counts":            (lambda yrs: nfl.import_snap_counts(yrs),                 "season"),
    "combine_data":           (lambda yrs: nfl.import_combine_data(yrs),                "season"),
    "draft_picks":            (lambda yrs: nfl.import_draft_picks(yrs),                 "season"),
    "injuries":               (lambda yrs: nfl.import_injuries(yrs),                    "season"),  # NEW (was missing)
    "passing_next_gen_stats":   (lambda yrs: nfl.import_ngs_data("passing", yrs),       "season"),
    "rushing_next_gen_stats":   (lambda yrs: nfl.import_ngs_data("rushing", yrs),       "season"),
    "receiving_next_gen_stats": (lambda yrs: nfl.import_ngs_data("receiving", yrs),     "season"),
    "passing_pro_football_ref":   (lambda yrs: nfl.import_weekly_pfr("pass", yrs),      "season"),
    "rushing_pro_football_ref":   (lambda yrs: nfl.import_weekly_pfr("rush", yrs),      "season"),
    "receiving_pro_football_ref": (lambda yrs: nfl.import_weekly_pfr("rec", yrs),       "season"),
}
```

**`ingest/handler.py`** — shared Lambda entrypoint (registry-driven):
```python
import os, importlib
from s3io import write_partition

def lambda_handler(event, _ctx=None):
    sport   = event["sport"]                       # "nfl" | "ncaaf" | "ncaab"
    seasons = event["seasons"]                     # e.g. [2026] incremental, or a backfill range
    names   = event.get("sources")                 # None => all
    reg     = importlib.import_module(f"{sport}.ingest.sources").SOURCES
    bucket  = os.environ["LAKE_BUCKET"]
    manifest = {}
    for name in (names or reg):
        fetch, season_col = reg[name]
        df = fetch(seasons)
        for season, part in df.groupby(season_col):
            manifest[f"{name}/{season}"] = write_partition(part, bucket, sport, name, int(season))
    return {"ok": True, "rows": manifest}
```
**`ingest/backfill.py`** — same logic, run OFF-Lambda for full history (no 15-min cap): `python -m ingest.backfill --sport nfl --seasons 2015-2026`.

**Packaging (`Dockerfile`)** — deps (nfl_data_py + pandas + pyarrow) exceed the zip limit, so use a container image:
```dockerfile
FROM public.ecr.aws/lambda/python:3.12
COPY ingest/ ${LAMBDA_TASK_ROOT}/ingest/
RUN pip install --no-cache-dir nfl_data_py pandas pyarrow boto3
CMD ["ingest.handler.lambda_handler"]
```
- **Lambda config:** memory 2–3 GB, timeout 5–15 min (weekly incremental fits; backfill runs off-Lambda).
- **IAM:** least-privilege role — `s3:PutObject/GetObject/DeleteObject/ListBucket` scoped to `<bucket>/<sport>/*`; API keys (Odds API) via Lambda env / SSM Parameter Store. **No** `ACCOUNTADMIN`, no warehouse, no keys in code.

## 5. Schedule (`infra/eventbridge.tf`, sketch)
```hcl
resource "aws_scheduler_schedule" "nfl_weekly" {
  schedule_expression = "cron(0 12 ? * TUE *)"      # weekly in-season, after MNF (UTC)
  target {
    arn      = aws_lambda_function.sport_ingest.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ sport = "nfl", seasons = [2026], mode = "incremental" })
  }
}
```
One Lambda + one schedule per sport (or per sport×source if you want isolation). Odds API gets its own schedule (more frequent in-season).

## 6. Transform — `dbt-duckdb` over S3 (scaffold)

**`dbt/profiles.yml`** (DuckDB reads S3 directly; creds via IAM credential chain):
```yaml
sport_lake:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "{{ env_var('DBT_DUCKDB_PATH', 'build/sport.duckdb') }}"
      extensions: [httpfs, parquet]
      settings:
        s3_region: us-east-1
        # prefer the credential chain (IAM role) over inline keys:
        s3_use_ssl: true
      # for marts written back to the lake:
      external_root: "s3://{{ env_var('LAKE_BUCKET') }}/{{ env_var('SPORT') }}/marts"
```

**`dbt/models/_sources.yml`** (raw Parquet as external sources):
```yaml
version: 2
sources:
  - name: nfl_raw
    meta: { external_location: "s3://{{ env_var('LAKE_BUCKET') }}/nfl/raw/{name}/**/*.parquet" }
    tables: [{name: weekly_data}, {name: schedules}, {name: depth_charts},
             {name: snap_counts}, {name: combine_data}, {name: injuries},
             {name: passing_next_gen_stats}, {name: rushing_next_gen_stats},
             {name: receiving_next_gen_stats}, {name: passing_pro_football_ref},
             {name: rushing_pro_football_ref}, {name: receiving_pro_football_ref},
             {name: weekly_rosters}, {name: rosters}, {name: draft_picks}]
```

**`dbt/models/staging/stg_weekly_data.sql`** (clean/rename — port the prior `jaffle_shop` logic here):
```sql
select *  -- replace with the explicit select/renames from the prior staging model
from {{ source('nfl_raw', 'weekly_data') }}
```
Marts (`fct_player_week`, `mart_player_season`, `mart_projections_preseason`, `dim_nfl_betting`, …) port over **unchanged in SQL** — only the source layer differs. Materialize marts as DuckDB tables, and/or `external` Parquet back to S3 for reuse.

- **Where dbt runs:** in-process — a small container (CI, a second Lambda, or a tiny scheduled Fargate task) reading/writing S3. Free compute; no warehouse.

## 7. Serving
Reverse-ETL the **serving marts** (projections, picks, transparency rows) into **Railway PG**, mirroring MLB's `write_serving_store.py` — the Credence app reads PG, never the lake at request time. (DuckDB can write to Postgres via its `postgres` extension, or a tiny loader does `df → PG`.)

## 7A. Querying the lake — the dev loop (humans **and** Claude Code)  ⚠️ critical
**The lake is fully queryable, and the iteration loop is as fast or faster than Snowflake-via-MCP — via DuckDB.** DuckDB reads S3 Parquet directly (`read_parquet('s3://…')`, `httpfs`), with no warehouse to resume, no credits, instant. **This must be a first-class affordance, or the agent rewrites connection boilerplate every session (the slow pattern).** Today a Claude Code session reaches for the **Snowflake MCP** to run SQL; the lake's **parity tool is `query_lake.py`** (below) — point every new-session prompt at it.

**Ways to query, fastest dev-loop first:**
1. **`query_lake.py` helper (the parity tool):** preconfigured DuckDB + `httpfs` + S3 credential chain → `q(sql) -> DataFrame`. Any session does `from tools.query_lake import q; q("select … from read_parquet('s3://…/**/*.parquet')")`.
2. **DuckDB CLI / one-liner (ad hoc):** `duckdb -c "INSTALL httpfs; LOAD httpfs; SELECT … read_parquet('s3://…')"`.
3. **Local sync for zero-latency heavy iteration:** `aws s3 sync s3://<bucket>/<sport>/ ./.lake/` then DuckDB over local Parquet — no per-query S3 latency/cost.
4. **The `dbt-duckdb` build file** (`build/sport.duckdb`) is itself directly queryable — it holds the staging + marts after `dbt build`.
5. **Athena** (optional): serverless SQL-over-S3 if you want a hosted endpoint or an Athena MCP later; pay-per-query.

**Requirement (the only gotcha):** the session needs **AWS credentials** (env vars or an IAM profile) with read on the bucket — the same machine that already has S3 access. DuckDB uses the standard credential chain; `INSTALL/LOAD httpfs+parquet` once.

**Why it's ≥ the Snowflake-MCP loop:** local, free, no warehouse resume, and you can pull a slice down for instant iteration. The cost was never query *capability* — it's just a different engine (DuckDB) reached via a helper instead of an MCP.

**`tools/query_lake.py`** (shared — ship it with the scaffold):
```python
import os, duckdb
_con = duckdb.connect()
_con.sql("INSTALL httpfs; LOAD httpfs; INSTALL parquet; LOAD parquet;")
_con.sql(f"SET s3_region='{os.environ.get('AWS_REGION', 'us-east-1')}';")  # creds via the IAM chain
LAKE = f"s3://{os.environ['LAKE_BUCKET']}"

def q(sql: str):
    """Run SQL against the lake; returns a pandas DataFrame. Use read_parquet('{LAKE}/<sport>/raw/<src>/**/*.parquet')."""
    return _con.sql(sql).df()
# e.g. q(f"select season, count(*) from read_parquet('{LAKE}/nfl/raw/weekly_data/**/*.parquet') group by 1 order by 1")
```
> **Snowflake parity for MLB-after-migration (E11.1):** once baseball moves to the lake, the same `query_lake.py` is how a session explores the baseball lake — the Snowflake-MCP loop is replaced by the DuckDB loop, not lost. (Snowflake-resident MLB data stays MCP-queryable until/unless it migrates.)

## 8. How a new sport plugs in (checklist)
1. `mkdir <sport>/ingest <sport>/dbt <sport>/infra`; copy `s3io.py`, `handler.py`, `backfill.py`, `tools/query_lake.py`, `profiles.yml`, the EventBridge module.
2. Write **`<sport>/ingest/sources.py`** — the sport's fetchers (NFL=`nfl_data_py`, NCAAF=CFBD, NCAAB=efficiency source; all + The Odds API).
3. Backfill once off-Lambda → S3; wire the weekly EventBridge schedule.
4. Write `dbt/models/_sources.yml` + staging + marts; `dbt build`.
5. Reverse-ETL serving marts → Railway PG; surface in Credence.
6. Write/refresh `<sport>_data_inventory.md` against the lake.

## 9. Migration to post-profit infra (no rewrite)
The **S3 Parquet lake is the durable core.** When a sport earns heavier infra:
- **Lambda → Dagster:** Dagster ops call the *same* `ingest/` functions; EventBridge schedule → Dagster schedule/sensor.
- **DuckDB → Snowflake:** Snowflake **external tables** or `COPY INTO` from the *same* S3 prefixes; dbt re-targets (the model SQL is shared, so it's an adapter/profile change, not a rewrite).
- Serving (Railway PG + Credence) is unchanged.

## 10. Per-sport source registries
- **NFL** (`football/nfl/`): `nfl_data_py` import_* per §4 — **re-pull fresh** (brownfield; the Snowflake `FOOTBALL_DATA` data is stale). Add `import_injuries` (was missing) + Odds API.
- **NCAAF** (`football/ncaaf/`): **CollegeFootballData (CFBD)** API (PBP/rosters/recruiting/talent) + draft/combine + Odds API; plus the college→NFL feeder xref.
- **NCAAB** (`basketball/ncaab/`): efficiency/tempo source (Torvik/KenPom-style or computed from PBP) + Odds API.
- **All:** **The Odds API** (odds/props/scores) on its own Lambda+schedule → `<sport>/raw/odds_*`.

```
▶ New-session prompt — build the platform scaffold (first instance: NFL)
Read: this guide (sport_data_platform.md) IN FULL + multi_sport_roadmap.md §6 + football/nfl/nfl_guide.md
(the port plan) + football/nfl/nfl_data_inventory.md (the prior Snowflake models to port).

Build the SHARED scaffold against NFL as the first instance:
  1. ingest/: s3io.py + handler.py + backfill.py (per §4) + football/nfl/ingest/sources.py (the nfl_data_py
     registry, incl. import_injuries). Containerized (Dockerfile). Backfill 2015–present OFF-Lambda → S3 lake.
  2. infra/: one Lambda + a weekly EventBridge schedule (incremental, current season); least-privilege S3 IAM;
     Odds API key in SSM. (Lambda container image; mem 2–3GB; backfill runs off-Lambda.)
  3. dbt/ (dbt-duckdb): profiles.yml + _sources.yml (external Parquet) + port the prior jaffle_shop staging +
     refined marts (fct_player_week, NGS satellites, mart_player_season, mart_projections_preseason,
     dim_nfl_betting) — SQL unchanged, only the source layer differs. dbt build over S3.
  4. Reverse-ETL the serving marts → Railway PG; refresh nfl_data_inventory.md against the lake.
  5. Ship tools/query_lake.py (§7A) — the DuckDB-over-S3 helper that is the PARITY TOOL to the Snowflake MCP;
     every later session explores the lake via it (e.g. `from tools.query_lake import q; q("select … read_parquet('s3://…')")`).
Keep it weekly batch + incremental + idempotent-partition writes. Conventions: uv run python; IAM/SSM for
secrets (NO ACCOUNTADMIN / keys-in-code); do not git commit/push. Make the shared pieces reusable so NCAAB/NCAAF
only add a sources.py + dbt models + a schedule.
```
