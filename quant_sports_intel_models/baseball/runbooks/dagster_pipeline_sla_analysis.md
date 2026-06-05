# Epic A1.1 — Pipeline Timing Audit

**Generated:** 2026-06-05 02:23 UTC  
**Audit window:** Last 14 days  
**SLA definition:** morning predictions inserted ≥30 min before earliest scheduled first pitch  
**Dagster Cloud data:** ✅ Available  

---

## Executive Summary

| Metric | Value |
|---|---|
| Days audited | 12 |
| **Morning SLA compliance (≥30 min before first pitch)** | **10/11 days (91%)** |
| SLA failures | 1 day(s) |
| Days with post-lineup re-run | 6/12 (50%) |
| Failure modes identified | 5 |
| Top failure mode | Morning run absent |

> ⚠️  **SLA compliance is 91%** — below the 95% target required for beta launch.

> ⚠️  **Post-lineup re-run fires on only 50% of days** — A1.2 is required before beta launch.

---

## Per-Day SLA Table

All timestamps UTC. `Morning ready` = Dagster `predict_today_morning` step end (if available) or earliest `INSERTED_AT` from `daily_model_predictions`.

| Date | Job Start | Morning Ready | Earliest 1st Pitch | SLA Deadline | Margin | SLA | Post-Lineup? | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-05-24 | 12:00:23 UTC | 12:11:30 UTC | 16:15:00 UTC | 15:45:00 UTC | +213m | ✅ PASS | ❌ | — |
| 2026-05-25 | 12:00:16 UTC | 12:09:27 UTC | 17:35:00 UTC | 17:05:00 UTC | +296m | ✅ PASS | ❌ | — |
| 2026-05-26 | 12:00:17 UTC | 12:10:36 UTC | 22:10:00 UTC | 21:40:00 UTC | +569m | ✅ PASS | ❌ | — |
| 2026-05-27 | 12:00:16 UTC | 12:09:58 UTC | 17:07:00 UTC | 16:37:00 UTC | +267m | ✅ PASS | ✅ | — |
| 2026-05-28 | 13:50:27 UTC | 13:51:34 UTC | 17:10:00 UTC | 16:40:00 UTC | +168m | ✅ PASS | ✅ | — |
| 2026-05-29 | 12:00:18 UTC | 12:11:35 UTC | 22:40:00 UTC | 22:10:00 UTC | +598m | ✅ PASS | ❌ | — |
| 2026-05-30 | 12:00:13 UTC | 12:11:15 UTC | 18:10:00 UTC | 17:40:00 UTC | +329m | ✅ PASS | ❌ | — |
| 2026-05-31 | 12:00:11 UTC | — | 16:15:00 UTC | 15:45:00 UTC | — | ⚠️  UNKNOWN | ✅ | job=FAILURE; failed: dbt_daily_build |
| 2026-06-01 | 12:00:21 UTC | 12:10:59 UTC | 22:40:00 UTC | 22:10:00 UTC | +599m | ✅ PASS | ❌ | ⚠️ pre-job-start insertion (backfill?) |
| 2026-06-02 | 19:25:20 UTC | 19:35:24 UTC | 22:40:00 UTC | 22:10:00 UTC | +155m | ✅ PASS | ✅ | — |
| 2026-06-03 | 14:48:35 UTC | 14:51:27 UTC | 17:05:00 UTC | 16:35:00 UTC | +104m | ✅ PASS | ✅ | — |
| 2026-06-04 | 20:30:01 UTC | 20:00:54 UTC | 17:05:00 UTC | 16:35:00 UTC | -206m | ❌ FAIL | ✅ | — |

---

## Op Duration Summary

Durations measured from Dagster Cloud step stats. Ops not observed in any run are omitted.

| Op | Runs | Mean | p90 | Max | Fail Rate |
|---|---|---|---|---|---|
| `ingest_parlay_events` | 15 | 0m 06s | 0m 08s | 0m 08s | 0% |
| `ingest_parlay_canonical_events` | 15 | 0m 10s | 0m 19s | 0m 23s | 0% |
| `ingest_parlay_odds` | 15 | 1m 17s | 1m 51s | 2m 20s | 0% |
| `ingest_action_network` | 15 | 0m 12s | 0m 16s | 0m 16s | 0% |
| `ingest_statcast` | 15 | 0m 16s | 0m 23s | 0m 27s | 0% |
| `ingest_statsapi_schedule` | 15 | 0m 06s | 0m 09s | 0m 09s | 0% |
| `ingest_weather` | 15 | 0m 39s | 0m 44s | 4m 48s | 7% |
| `ingest_umpires_early` | 14 | 0m 01s | 0m 04s | 0m 05s | 0% |
| `ingest_fangraphs_stuff_plus` | 16 | 0m 11s | 1m 26s | 1m 34s | 0% |
| `ingest_fangraphs_hitting_leaderboard` | 18 | 0m 27s | 0m 42s | 1m 23s | 0% |
| `ingest_transactions` | 15 | 0m 07s | 0m 08s | 0m 09s | 0% |
| `ingest_oaa` | 16 | 0m 19s | 0m 25s | 0m 27s | 12% |
| `compute_elo` | 14 | 1m 37s | 1m 45s | 1m 46s | 0% |
| `check_data_freshness` | 14 | 0m 06s | 0m 08s | 0m 09s | 0% |
| `dbt_daily_build` | 15 | 2m 46s | 3m 15s | 3m 23s | 7% |
| `generate_run_env_signals_op` | 6 | 0m 14s | 0m 24s | 0m 24s | 33% |
| `generate_offense_signals_op` | 6 | 0m 11s | 0m 17s | 0m 17s | 33% |
| `generate_starter_signals_op` | 5 | 0m 18s | 0m 21s | 0m 21s | 0% |
| `generate_starter_ip_signals_op` | 6 | 0m 11s | 0m 18s | 0m 18s | 33% |
| `generate_bullpen_signals_op` | 4 | 0m 17s | 0m 19s | 0m 19s | 0% |
| `generate_matchup_signals_op` | 5 | 0m 24s | 0m 28s | 0m 28s | 0% |
| `dbt_sub_model_signals_rebuild` | 4 | 0m 05s | 0m 06s | 0m 06s | 0% |
| `signal_freshness_check` | 4 | 0m 04s | 0m 06s | 0m 06s | 0% |
| `update_market_features_scd2` | 8 | 0m 04s | 0m 05s | 0m 05s | 0% |
| `dbt_pregame_odds_rebuild` | 10 | 0m 31s | 0m 58s | 0m 58s | 20% |
| `update_lineup_state_scd2` | 8 | 0m 04s | 0m 05s | 0m 05s | 0% |
| `dbt_lineup_feature_rebuild` | 8 | 1m 01s | 1m 23s | 1m 23s | 0% |
| `ingest_umpires_late` | 14 | 0m 03s | 0m 07s | 0m 15s | 7% |
| `compute_eb_bullpen_posteriors_op` | 1 | 0m 10s | 0m 10s | 0m 10s | 0% |
| `update_player_posteriors_op` | 1 | 0m 10s | 0m 10s | 0m 10s | 0% |
| `update_team_posteriors_op` | 1 | 0m 06s | 0m 06s | 0m 06s | 0% |
| `update_matchup_cell_posteriors_op` | 1 | 0m 09s | 0m 09s | 0m 09s | 0% |
| `dbt_umpire_feature_rebuild` | 13 | 0m 33s | 0m 32s | 1m 21s | 0% |
| `predict_today_morning` | 13 | 0m 40s | 0m 50s | 0m 52s | 0% |
| `check_prediction_coverage` | 13 | 0m 02s | 0m 03s | 0m 04s | 0% |
| `dbt_mart_prediction_clv` | 13 | 0m 04s | 0m 05s | 0m 05s | 0% |
| `compute_model_health` | 13 | 0m 05s | 0m 07s | 0m 07s | 0% |
| `backfill_prediction_log` | 13 | 0m 06s | 0m 07s | 0m 08s | 0% |
| `ingest_fangraphs_catcher_framing *` | 15 | 0m 00s | — | 0m 06s | 0% |
| `ingest_odds_api_events *` | 3 | 0m 00s | — | 0m 00s | 0% |
| `ingest_odds_api_odds *` | 3 | 0m 00s | — | 0m 00s | 0% |
| `ingest_sprint_speed *` | 12 | 0m 00s | — | 0m 07s | 0% |

---

## Failure Mode Analysis

Ranked by occurrence count descending.

### FM-3 — Post-lineup re-run absent

**Occurrences:** 6 / 12 days  
**Affected dates:** 2026-05-24, 2026-05-25, 2026-05-26, 2026-05-29, 2026-05-30, 2026-06-01  
**SLA impact:** MEDIUM — morning predictions available but lineup accuracy degraded  

lineup_monitor sensor did not trigger a post-lineup prediction re-run. Predictions served to the app may be based on projected lineups, not confirmed lineups.

### FM-5 — Job start significantly delayed

**Occurrences:** 4 / 12 days  
**Affected dates:** 2026-05-28, 2026-06-02, 2026-06-03, 2026-06-04  
**SLA impact:** HIGH — entire pipeline shifted later; early-game SLA at risk  

daily_ingestion_job did not start until >1h after the scheduled 12:00 UTC start time. This compresses the available window for all downstream ops.

### FM-1 — Morning run absent

**Occurrences:** 1 / 12 days  
**Affected dates:** 2026-05-31  
**SLA impact:** CRITICAL — no predictions available at all for those game days  

daily_ingestion_job completed but no 'morning' predictions were inserted. Either predict_today_morning op was skipped/failed, or the job itself did not run.

### FM-2 — Morning predictions arrived after SLA deadline

**Occurrences:** 1 / 12 days  
**Affected dates:** 2026-06-04  
**SLA impact:** HIGH — predictions available but after games started  

Morning predictions were inserted but AFTER the 30-minute-before-first-pitch deadline. Likely caused by slow upstream ops delaying predict_today_morning.

**Average miss by:** 206 minutes

### FM-4 — Op failure: dbt_daily_build

**Occurrences:** 1 / 12 days  
**Affected dates:** 2026-05-31  
**SLA impact:** VARIABLE — depends on whether op is on the critical path to predict_today_morning  

dbt_daily_build failed in 1 of 12 runs.

---

## A1.6 — Scheduler Reliability

### FM-5 late-start incidents

All 4 late-start runs eventually **succeeded** — the job body ran in ~20 minutes once it started. Root cause is in the time between the 12:00 UTC schedule tick and actual run start, not in op performance.

| Date | Run ID | Scheduled | Actual start | Delay |
|------|---------|-----------|-------------|-------|
| 2026-05-28 | `a114d2af` | 12:00 UTC | 13:50 UTC | +110m |
| 2026-06-02 | `8541e30a` | 12:00 UTC | 19:25 UTC | +445m |
| 2026-06-03 | `0637f515` | 12:00 UTC | 14:48 UTC | +168m |
| 2026-06-04 | `6cc6e718` | 12:00 UTC | 20:30 UTC | +510m |

### Root cause investigation steps

**Step 1 — Confirm whether schedule ticks fired at 12:00 UTC**

In Dagster Cloud UI:
1. Automations → Schedules → `daily_ingestion_schedule`
2. Click "Tick history"
3. For each of the 4 dates, find the 12:00 UTC tick. Check its status:
   - `SUCCESS` → tick fired and run was requested; delay is post-tick (FM-A or FM-C)
   - `SKIPPED` → tick fired but was suppressed (paused schedule or run already in flight)
   - **missing entirely** → scheduler miss (FM-B); file a Dagster Cloud support ticket

**Step 2 — Measure tick-to-run-start gap**

If a tick shows `SUCCESS`, click it to expand. It will show the "Run ID" that was created and the exact timestamp the run transitioned from `QUEUED` to `STARTED`. If QUEUED→STARTED gap is:
- **>5 min**: agent was unavailable to dequeue the run → FM-A
- **<1 min**: agent was alive; look at first-op start time (FM-C or FM-D)

**Step 3 — Check agent health on those dates (Railway)**

1. Open Railway → your Dagster agent service → Deployments tab
2. Filter around 11:45–12:15 UTC for each affected date
3. Look for:
   - Container restart events (OOM kill = FM-A resource issue)
   - Deploy events that caused downtime during the tick window
   - Health-check failure logs
4. Check CPU/memory metrics at 12:00 UTC on each date

**Step 4 — Code location load time (if FM-C suspected)**

Only relevant if tick fired and QUEUED→STARTED was <1 min but first op was slow. Time locally:
```bash
time python -c "import pipeline"
```
If >30 seconds, profile with:
```bash
python -X importtime -c "import pipeline" 2>&1 | sort -t= -k2 -rn | head -20
```

### FM classification (fill in after steps above)

| Run ID | Tick fired? | QUEUED→STARTED | FM class | Evidence | Action |
|--------|------------|----------------|----------|----------|--------|
| `a114d2af` | | | | | |
| `8541e30a` | | | | | |
| `0637f515` | | | | | |
| `6cc6e718` | | | | | |

### Fix: Railway agent self-heal policy (apply if FM-A confirmed)

Option A — Health-check restart (recommended):
1. Railway → agent service → Settings → Health Checks
2. Set: Interval=60s, Timeout=10s, Unhealthy threshold=3 → restart

Option B — Pre-emptive daily restart:
Add a Railway cron that restarts the agent at 11:55 UTC daily (5 min before the Dagster schedule tick):
```
55 11 * * * railway restart <service-name>
```

### Fix: Watchdog sensor (deployed — A1.6)

`pipeline/sensors/morning_watchdog_sensor.py` is live as `morning_watchdog_sensor`. Ticks every 15 minutes. If `daily_model_predictions` has no `morning` rows for today by 13:30 UTC on a game day, it emits a `RunRequest` for `daily_ingestion_job`. `run_key=morning-watchdog-{today}` caps it at one auto-trigger per day.

**Testing procedure:**
1. Automations → Schedules → `daily_ingestion_schedule` → Pause (or skip the 12:00 UTC tick)
2. Wait until 13:30 UTC on a game day
3. Automations → Sensors → `morning_watchdog_sensor` → verify a tick appears that yields a `RunRequest`
4. Confirm `daily_ingestion_job` starts within 5 minutes
5. Re-enable the schedule

---

## A1.2–A1.5 Sequencing Recommendation

Based on this audit, the following stories are most urgent:

- **A1.2 (Post-lineup re-run) — REQUIRED.** Morning run was absent on at least one day; morning predictions arrived after the sla deadline on at least one day; post-lineup re-run fires on only 50% of days — lineup_monitor sensor may not be triggering the post-predict op. A reliable post-lineup trigger is the highest-leverage fix: it ensures at least one confirmed-lineup prediction exists before game time even when the morning run is delayed.

- **A1.3 (Signal freshness gate) — HIGH PRIORITY.** Ops are failing or the morning run is missing entirely on some days. The non-blocking `signal_freshness_check_op` means `predict_today_morning` can run on stale signals — or be silently skipped — without any alert surfaced to the operator.

---

## Appendix — Raw Per-Day Data

| Date | Score Date Morning Ins. | Score Date Post-Lineup Ins. | Dagster Run ID | Dagster Status |
|---|---|---|---|---|
| 2026-05-24 | 12:11:26 UTC | — | fb30af47… | SUCCESS |
| 2026-05-25 | 12:09:23 UTC | — | 8f907f24… | SUCCESS |
| 2026-05-26 | 12:10:31 UTC | — | f146115b… | SUCCESS |
| 2026-05-27 | 12:09:54 UTC | 21:45:36 UTC | 0df55797… | SUCCESS |
| 2026-05-28 | 13:51:31 UTC | 15:45:57 UTC | a114d2af… | SUCCESS |
| 2026-05-29 | 12:11:32 UTC | — | 9709e6cb… | SUCCESS |
| 2026-05-30 | 12:11:12 UTC | — | 7e4e9c78… | SUCCESS |
| 2026-05-31 | — | 17:46:13 UTC | eaef740d… | FAILURE |
| 2026-06-01 | 06:22:27 UTC | — | 50463863… | SUCCESS |
| 2026-06-02 | 19:15:35 UTC | 19:46:31 UTC | 8541e30a… | SUCCESS |
| 2026-06-03 | 14:51:24 UTC | 16:46:44 UTC | 0637f515… | SUCCESS |
| 2026-06-04 | 20:00:54 UTC | 20:46:57 UTC | 6cc6e718… | SUCCESS |
