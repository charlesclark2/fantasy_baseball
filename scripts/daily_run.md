# Daily Ingestion Runbook

## Snowflake Task DAG (unattended production runs)

The Snowflake Task DAG (`task_savant_ingestion`, root task, 08:00 ET daily) runs the full ingestion sequence automatically in production. No manual action is needed on normal days.

**DAG topology:**
```
task_savant_ingestion  (ROOT, CRON 0 8 * * * America/New_York)
    → task_statsapi_schedule
        → task_oddsapi_events
            → task_oddsapi_odds
                → task_github_actions_trigger  (dispatches dbt_daily_build.yml)
```

**Trigger a manual run** (e.g., after a missed day or for testing):
```sql
EXECUTE TASK baseball_data.config.task_savant_ingestion;
```

**Monitor task status:**
```sql
SELECT name, state, scheduled_time, completed_time, error_message
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY())
ORDER BY scheduled_time DESC
LIMIT 10;
```

**Check pipeline run log:**
```sql
SELECT * FROM baseball_data.config.pipeline_run_log ORDER BY run_ts DESC LIMIT 10;
```

If a task shows `FAILED`, fix the underlying issue and re-execute the root task. Each downstream procedure checks its predecessor's return value and writes `status = 'SKIPPED'` rather than cascading a failure — re-running after a fix will pick up where the DAG left off.

The manual sequence below remains the canonical path for development, debugging, and one-off backfills.

---

Run these commands from the `scripts/` directory each day to keep all Snowflake source tables current. The order below matches data dependencies: Statcast and Stats API data feed the dbt mart layer, and odds data is independent.

## Prerequisites

All scripts read credentials from the project root `.env` file. Confirm the following variables are set before running:

```
SNOWFLAKE_ACCOUNT
SNOWFLAKE_USER
SNOWFLAKE_WAREHOUSE
SNOWFLAKE_PRIVATE_KEY_PATH
ODDS_API_KEY
```

All commands must be run from the `scripts/` directory (where `pyproject.toml` lives):

```bash
cd /path/to/baseball_betting_and_fantasy/scripts
```

---

## Step 1 — Statcast pitch data (`savant_ingestion.py`)

Auto-detects the last loaded date and ingests everything through yesterday. No arguments needed for daily runs.

```bash
uv run savant_ingestion.py batter_pitches
```

What it does: queries `MAX(game_date)` from `baseball_data.savant.batter_pitches`, then fetches one calendar day at a time from Baseball Savant from that date + 1 day through yesterday. Each day is deleted before re-insertion (idempotent). Days with no game data are skipped automatically.

---

## Step 2 — Stats API schedule (`ingest_statsapi.py`)

Refreshes the current calendar month's schedule and confirmed lineup data. Defaults to the current month only — this avoids re-processing years of historical data on every daily run.

```bash
uv run ingest_statsapi.py schedule
```

What it does: upserts one row per calendar month into `baseball_data.statsapi.monthly_schedule`. Each row holds the full API response (schedule + lineup hydration) for that month as a VARIANT. The current month row is overwritten on every run, so newly confirmed lineups are picked up automatically.

### When to widen the window

Lineup data for a given game can be retroactively populated by the Stats API after the game date. If you suspect missing lineups for recent games, refresh the prior month as well:

```bash
uv run ingest_statsapi.py schedule --start-date 2026-04-01
```

For a full historical backfill (initial load or disaster recovery):

```bash
uv run ingest_statsapi.py schedule --start-date 2015-04-01
```

> **Do not run the schedule command without `--start-date` and expect it to cover all historical seasons.** The default window is the current month only. For a backfill, pass `--start-date 2015-04-01` explicitly.

---

## Step 3 — Odds API events and odds (`odds_api_ingestion.py`)

Two independent calls. Both are append-only (no deletes) — each run adds a new snapshot row tagged with a shared `load_id`.

### 3a — Upcoming events

Fetches the next 7 days of MLB events. No arguments needed.

```bash
uv run odds_api_ingestion.py events
```

Writes one row to `baseball_data.oddsapi.mlb_events_raw` with the full event array in `raw_json`. The dbt staging layer (`stg_oddsapi_events`) flattens this into individual event rows.

### 3b — Current odds

Fetches moneyline (`h2h`) and totals (`totals`) markets from US bookmakers. No arguments needed.

```bash
uv run odds_api_ingestion.py odds
```

Writes one row per event per market/region combination to `baseball_data.oddsapi.mlb_odds_raw`. The dbt staging layer (`stg_oddsapi_odds`) flattens these into individual outcome rows for line movement analysis.

To fetch additional markets or regions:

```bash
uv run odds_api_ingestion.py odds --markets h2h totals spreads --regions us us2 eu
```

**API credit note:** Each `odds` run costs multiple API credits (one per market × region combination; default: 2 markets × 2 regions = 4 calls). Check remaining credits in the log output (`x_requests_remaining`) or in the raw tables. Budget roughly 8–12 credits per full daily run.

---

## Step 4 — Refresh dbt mart layer

After ingestion, rebuild the dbt models to propagate new source data through the mart layer. Run from the `dbt/` directory:

```bash
cd ../dbt
dbtf build
```

To rebuild only the models downstream of a specific source (faster during development):

```bash
dbtf build --select +mart_game_results
dbtf build --select +mart_odds_events+
```

---

---

## Lineup Monitor Architecture

The lineup monitor is a separate, always-on hourly pipeline that watches for confirmed starting lineups and triggers an incremental dbt build when both lineups for a game are locked.

**System diagram:**
```
Snowflake Task (CRON 0 * * * * ET)
    → lineup_monitor_proc (Snowpark Python)
        → stg_statsapi_lineups_wide  (reads confirmed game_pks)
        → lineup_monitor_state       (deduplication guard)
        → GitHub REST API POST /dispatches
            → GitHub Actions: dbt_staging_build.yml
                → dbtf build --select +stg_statsapi_lineups+
```

**Required GitHub Secrets** (same Snowflake credentials used by `dbt_daily_build.yml`):

| Secret | Value / Source |
|---|---|
| `SNOWFLAKE_ACCOUNT` | Snowflake account identifier (e.g. `abc123.us-east-1`) |
| `SNOWFLAKE_USER` | Snowflake service user (e.g. `dbt_user`) |
| `SNOWFLAKE_PRIVATE_KEY` | RSA private key PEM content (no passphrase) |
| `SNOWFLAKE_DATABASE` | `baseball_data` |
| `SNOWFLAKE_WAREHOUSE` | `COMPUTE_WH` |
| `SNOWFLAKE_ROLE` | Role with dbt model access (e.g. `transformer`) |

**Manual trigger** (trigger for a specific game_pk without waiting for the hourly fire):
```bash
gh workflow run dbt_staging_build.yml -f game_pk=<game_pk> -f triggered_by=manual
```

**Suspend the task during off-season:**
```sql
ALTER TASK baseball_data.config.task_lineup_monitor SUSPEND;
```

**Re-enable for the season:**
```sql
ALTER TASK baseball_data.config.task_lineup_monitor RESUME;
```

**Check the last 24 hours of task run history:**
```sql
SELECT * FROM TABLE(
  information_schema.task_history(
    task_name=>'TASK_LINEUP_MONITOR',
    scheduled_time_range_start=>DATEADD('hour', -24, CURRENT_TIMESTAMP)
  )
);
```

**Check recent dispatch state:**
```sql
SELECT * FROM baseball_data.config.lineup_monitor_state
ORDER BY triggered_at DESC
LIMIT 20;
```

**Check pipeline audit log for lineup monitor entries:**
```sql
SELECT * FROM baseball_data.config.pipeline_run_log
WHERE task_name = 'lineup_monitor_proc'
ORDER BY run_ts DESC
LIMIT 20;
```

---

## Full daily sequence (copy-paste)

```bash
cd /path/to/baseball_betting_and_fantasy/scripts

uv run savant_ingestion.py batter_pitches
uv run ingest_statsapi.py schedule
uv run odds_api_ingestion.py events
uv run odds_api_ingestion.py odds

cd ../dbt
dbtf build
```
