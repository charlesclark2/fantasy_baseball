# Odds Capture — Railway cron service (Story 12.3.7 / A2.18)

Live MLB odds capture from **The Odds API**, running on a **Railway cron container** — *not*
GitHub Actions (repo is going private) and *not* a Dagster job (keeps the I/O-bound HTTP poll
off the Dagster+ run-minute bill). Each cron fire runs once and exits.

## Architecture

```
Railway cron (*/30)                          Dagster (daemon)
  └─ entrypoint.sh                             odds_rebuild_sensor (every 5 min)
       └─ odds_api_ingestion.py odds            └─ cursor on MAX(ingestion_ts) of mlb_odds_raw
            --regions us us2 eu                      └─ new capture? → odds_oddsapi_rebuild_job
            --markets h2h totals                          └─ dbtf run: stg_oddsapi_odds → mart_odds_outcomes
       writes → oddsapi.mlb_odds_raw                          → mart_closing_line_value, mart_prediction_clv,
                                                                mart_odds_line_movement
```

- **Cost:** live endpoint = `markets(2) × regions(3)` = **6 credits/call**. At `*/30` ≈ 48/day ≈ ~8.6k/mo (trivial). Tighten the cron to game hours if desired.
- **Books captured:** all `us` + `us2` + `eu` → Bovada (target), Pinnacle (sharp), DraftKings, FanDuel, BetMGM, etc.
- **Lineage:** flows through the EXISTING `mart_odds_outcomes` UNION (`stg_oddsapi_odds`), untouched since the migration.

## Railway setup

1. **New service** → Deploy from this repo. Leave **Root Directory = repo root** (the build needs `scripts/` in context). Railway has no "Dockerfile Path" UI field and would otherwise auto-detect the repo-root `./Dockerfile` (the heavy Dagster/ML service) → "error deploying from source". Instead point this service at the scoped config: **Settings → Config-as-code (Railway Config File) = `services/odds_capture/railway.toml`**. That file pins `builder = DOCKERFILE`, `dockerfilePath = services/odds_capture/Dockerfile`, and the cron schedule.
2. **Variables** (Settings → Variables):
   - `ODDS_API_KEY` — main Odds API key. **Live capture needs a *renewing* plan** (~3–8k credits/mo); the historical-backfill 100k expires 6/23, so confirm a sustaining monthly tier before relying on this for ongoing capture.
   - `ODDS_API_STARTER_KEY` — *optional*. By design the script tries this cheap key first for live `odds` and **auto-falls-back to `ODDS_API_KEY` on 401/422 (exhaustion)** — it preserves the main key's budget. Safe to set or omit.
   - `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_ROLE`
   - `SNOWFLAKE_PRIVATE_KEY` — the **full PEM contents** of the key-pair private key (entrypoint writes it to a file at runtime).
3. **Cron Schedule** — set in `railway.toml` (`cronSchedule = "*/30 * * * *"`); edit there for a tighter game-hours window (e.g. `*/30 13-23 * * *`). No UI step needed.
4. Deploy. Watch the deploy logs for `[odds_capture] ... done` and a non-error exit.

## Validation (before cutover)

```sql
-- new rows landing from the Railway service
select max(ingestion_ts), count(*) from baseball_data.oddsapi.mlb_odds_raw
where ingestion_ts > dateadd('hour', -2, current_timestamp());
```
- Confirm `odds_rebuild_sensor` is ON in Dagster and fired `odds_oddsapi_rebuild_job` after a capture.
- Confirm `mart_odds_outcomes` / `mart_odds_line_movement` show fresh `data_source` rows for today.

## Cutover (do AFTER validation — this is the A2.18 saving)

Only once the Railway path is proven end-to-end:
1. **Disable the Parlay `odds_snapshot` Dagster schedules** in `pipeline/schedules/intraday_schedules.py`
   (the 17 `odds_snapshot_*` `ScheduleDefinition`s) — this removes the **#1 Dagster+ run-minute driver
   (~1,044 min/mo, ~42%)** before billing starts 6/18.
2. Keep `.github/workflows/odds_snapshot.yml` (Parlay) as **`workflow_dispatch`-only manual failover** (already is).
3. Odds API is now **primary**; Parlay is the retired failover. Because only Odds-API writes
   `mart_odds_outcomes` going forward, the `mart_odds_line_movement` live path is single-source —
   no dedup needed beyond the historical-authoritative rule already in the model.

## Follow-ups
- Per-source freshness + quota-header alert (the thing Parlay silently lacked) — small Dagster sensor or a check in `odds_api_ingestion.py`.
- This container is the foundation for the Story 12.11 always-on streaming consumer (Parlay SSE/WS) if/when that's built.
