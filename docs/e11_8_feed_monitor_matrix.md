# E11.8 — Feed → Monitor → Severity Matrix

**Shipped: 2026-06-22.** Systematic pass following INC-7 (odds /events feed dead 18 days,
undetected) and INC-8 (archetype posteriors dead 22 days, compute never scheduled). Every
serving-critical feed now has a HARD alert (sensor raises → Dagster email-on-failure); every
peripheral feed has at minimum a WARN-level check.

## How alerts fire

Dagster's standard mechanism: a sensor tick that **raises an Exception** marks the tick as
FAILED and triggers the Dagster+ email-on-failure alert configured on that sensor. A
`SkipReason` (used for transient errors and off-day skips) is silent — it never pages.

**Contract**:
- **HARD-ALERT**: sensor raises → tick FAILS → email fires. Use for serving-critical feeds.
- **WARN**: `check_data_freshness` op (WARN tier in daily_ingestion_job) or `context.log.warning`.
  Advisory. Never pages, never blocks.
- **HALT**: op raises inside the job. Blocks predictions. Used for signal freshness (blocking gate).

---

## Feed → Monitor → Severity Matrix

| Feed | Table | Cadence | Severity | Monitor | Notes |
|------|-------|---------|----------|---------|-------|
| **Odds (live)** | `oddsapi.mlb_odds_raw` | 30 min (Railway cron) | **HARD-ALERT** | `odds_freshness_alert_sensor` (raises; staleness > 90 min OR quota low) | INC-7 class — the original incident |
| **Schedule / games** | `statsapi.monthly_schedule` + `betting.stg_statsapi_games` | 30 min (Railway) + daily job | **HARD-ALERT** | `schedule_freshness_alert_sensor` (raises; stale > 4h OR 0 games loaded on game day after 14:30 UTC) | NEW E11.8; was WARN-only before |
| **Statcast pitches** | `savant.batter_pitches` | Daily (Savant → daily job + catchup sensor) | **HARD-ALERT** | `statcast_freshness_sensor` (SLA breach: raises; normal catchup: fires job) | E11.8 fix: SLA breach now raises (was SkipReason) |
| **Predictions written** | `betting_ml.daily_model_predictions` | Daily + post-lineup | **HARD-ALERT** | `pregame_alert_sensor` (raises 45 min before first pitch) | Catches any upstream failure that blocks predict |
| **Model health / skill** | `betting_ml.daily_model_predictions` (rolling 30d) | Daily | **HARD-ALERT** | `model_health_alert_sensor` (raises on corr/spread/Brier gate failure) | Catches serving regressions |
| **Signal freshness (run_env + offense)** | `betting_features.feature_pregame_sub_model_signals` | Daily | **HALT** | `signal_freshness_check` op in daily_ingestion_job (raises if critical signals absent) | Blocks predict if minimum signals missing |
| **Pipeline completeness** | `betting_ml.pipeline_status` | Daily | **HARD-ALERT** | `pregame_alert_sensor` (checks pipeline_status == 'complete') | |
| **Daily job not started** | `betting_ml.daily_model_predictions` | Daily | Fires job | `morning_watchdog_sensor` (RunRequest to trigger job) | Watchdog, not alert — fires a re-run |
| **Odds quota** | `oddsapi.mlb_odds_raw.x_requests_remaining` | 30 min | **HARD-ALERT** | `odds_freshness_alert_sensor` (raises on low MAIN-key quota) | Part of odds sensor |
| **Archetype posteriors** | `betting.mart_player_archetype_posteriors` | Daily (daily job + catchup job) | **WARN** | `check_data_freshness` (non_blocking, 48h) | INC-8 root cause; now wired in BOTH daily + catchup jobs (E11.8) |
| **Player sequential posteriors** | `betting.player_sequential_posteriors` | Daily | **WARN** | `check_data_freshness` (non_blocking, 36h) | |
| **Team sequential posteriors** | `betting.team_sequential_posteriors` | Daily | **WARN** | `check_data_freshness` (non_blocking, 36h) | |
| **EB bullpen posteriors** | `betting.eb_bullpen_team_posteriors` | Daily | **WARN** | `check_data_freshness` (non_blocking, 48h) | |
| **Umpire HP assignment** | `statsapi.umpire_game_log` (statsapi source) | Daily + lineup monitor | **WARN** | `check_data_freshness` (non_blocking, 48h, game-day only) | Staleness expected pre-10 AM ET |
| **Umpire scorecards (tendency)** | `statsapi.umpire_game_log` (umpscorecards source) | Daily | **WARN** | `check_data_freshness` (non_blocking, 96h) | |
| **FanGraphs Stuff+** | `fangraphs.fg_stuff_plus_raw` | Weekly Sunday | **WARN** | `check_data_freshness` (blocking in script, 192h) | Note: blocking in script but op is WARN tier |
| **FanGraphs hitting leaderboard** | `fangraphs.fg_hitting_leaderboard_raw` | Daily | **WARN** | `check_data_freshness` (non_blocking, 36h) | Fantasy asset only; not in betting model |
| **Player transactions** | `statsapi.player_transactions` | Daily | **WARN** | `check_data_freshness` (non_blocking, **36h on `ingestion_ts`**) | INC-12 fix: was `effective_date`/168h — event-date monitor can't distinguish "quiet day" from "broken feed"; `ingestion_ts` ticks on every 7-day-lookback run even with zero new transactions |
| **ActionNetwork public betting** | `actionnetwork.public_betting_raw` | Daily | **WARN** | `check_data_freshness` (blocking in script, 36h) | |
| **Derivative odds (team_totals / alt_totals)** | `oddsapi.derivative_odds_raw` | 30 min (Railway cron) | **WARN** | `check_data_freshness` (non_blocking, 4h) | NEW E11.8; EVAL/CLV-only, not model input |
| **Park factors** | `betting.eb_park_factors_raw` | Annual (season start) | **WARN** | `check_data_freshness` (non_blocking, 4320h / 180d) | NEW E11.8; annual update via fit_park_priors.py |
| **Weather** | Open-Meteo (no raw table) | Hourly Railway cron | None (soft-fail only) | No alert; weather is a WARN-tier model input with imputation fallback | |
| **CLV drift** | `betting_features.feature_pregame_meta_model_features` | Daily | **HARD-ALERT** | `clv_alert_sensor` (raises if pct_positive_clv < 35%) | Model-quality alert, not feed freshness |
| **H2H conviction picks** | `betting_ml.daily_model_predictions` | Daily pre-game | Informational | `conviction_pick_alert_sensor` (raises with picks digest) | Not a freshness alert |

---

## Scheduling audit (INC-8 pattern: "hand-run-only")

Every model-input compute is now wired to a Dagster job or Railway cron:

| Compute | Wired To | Cadence | Notes |
|---------|----------|---------|-------|
| `compute_archetype_posteriors.py` | `daily_ingestion_job` (E11.8 fix) **AND** `statcast_catchup_job` | Daily | Was NEVER scheduled before INC-8 |
| `compute_elo.py` | `daily_ingestion_job` + `statcast_catchup_job` | Daily | |
| `update_player_posteriors.py` | `daily_ingestion_job` + `statcast_catchup_job` | Daily | |
| `update_team_posteriors.py` | `daily_ingestion_job` + `statcast_catchup_job` | Daily | |
| `update_matchup_cell_posteriors.py` | `daily_ingestion_job` + `statcast_catchup_job` | Daily | |
| EB bullpen posteriors | `daily_ingestion_job` (dbt model via `dbt_build_bullpen_posteriors_op`) + catchup | Daily | Was Python script; migrated to dbt A2.11 |
| EB starter/lineup posteriors | `daily_ingestion_job` + `lineup_monitor_job` (dbt models) | Daily + post-lineup | Migrated to dbt A2.11 |
| Sub-model signal generators (8 ops) | `daily_ingestion_job` | Daily | |
| Stacking weights | `weekly_ml_job` (Monday) | Weekly | |
| Bayesian CLV meta-model | `weekly_meta_model_job` (Wednesday) | Weekly | |
| Player profiles | `weekly_player_profiles_job` | Weekly | |
| `fit_park_priors.py` + `fit_granular_park_priors.py` | **HAND-RUN** | Annual (season start) | Acceptable — annual data; WARN monitor added |
| `ingest_fangraphs_zips_*.py` | **HAND-RUN** | Annual | Fantasy/analytics asset only; not in betting model serving path |
| `savant_ingestion.py` (park factor raw data) | **HAND-RUN** (feeds fit_park_priors) | Annual | Same as above |

---

## Monitor-the-monitors

**INC-5 lesson**: a freshness monitor that itself silently fails is the same blind spot.

All HARD-ALERT sensors follow this contract:
- **Transient Snowflake / connection errors** → `yield SkipReason(...)`. The tick succeeds
  (doesn't page). The real condition persists across ticks and will fire once the connection
  recovers. This prevents false pages on infra blips.
- **Real problem detected** → `raise Exception(...)`. The tick FAILS, triggering Dagster+'s
  email-on-failure alert. The sensor retries on every subsequent tick, so self-healing
  (e.g., Statcast arriving late) is automatically detected on the next pass.
- **Off-day / outside alert window** → `yield SkipReason(...)`. Silent skip.

**E11.8 fix**: `statcast_freshness_sensor` previously used `SkipReason` for the SLA breach
case (data still missing within 2h of first pitch). This was silent — no email fired.
Changed to `raise Exception` so the SLA breach actually pages.

**Dagster+ configuration**: enable the "sensor tick failure" alert policy in the Dagster+
UI for all HARD-ALERT sensors (`odds_freshness_alert_sensor`,
`schedule_freshness_alert_sensor`, `statcast_freshness_sensor`,
`pregame_alert_sensor`, `model_health_alert_sensor`). This means a tick that raises will
send an email to the configured recipients. Without this policy, raising is still visible
in the Dagster UI but does not send an email.

---

## Display-derived status coverage (INC-12 lesson)

Some user-visible statuses are **not monitored at the source level** because they derive from
a multi-hop chain (raw table → dbt mart → serving store). A source-table freshness check
catches a feed outage but NOT a stale serving-store blob if the write step is skipped or the
cache read returns a stale permanent row.

| Display status | Chain | Risk | Coverage |
|---------------|-------|------|----------|
| `is_on_il` (player page) | `player_transactions` → dbt marts → `api_cache player/{id}` | Stale `is_permanent` blob survives date rollover and shadows the fresh daily write | INC-12 fix: `pg.get_cache` now uses `ORDER BY updated_at DESC` on the `is_permanent` path, so the most-recently-written permanent row always wins |
| Player game log | `mart_starting_pitcher_game_log` → `api_cache player/{id}` | Same stale-blob issue | Same fix |
| Team record / score | `stg_statsapi_games` → `api_cache picks/game/{pk}` | Non-permanent — date-scoped, refreshes daily | OK |
| Model skill score | `daily_model_predictions` (rolling 30d) | Monitored by `model_health_alert_sensor` (HARD-ALERT) | OK |

**Lesson**: any blob written `is_permanent=True` that reflects a **mutable current state**
(IL status, team roster, player availability) needs the serving-store read path to always
return the **latest** write, not an arbitrary heap-order row. The `ORDER BY updated_at DESC`
fix closes this class of bugs for all permanent-blob reads.

---

## Resolution quick-reference

| Alert | First check | Manual fix |
|-------|-------------|------------|
| `odds_freshness_alert_sensor` STALE | Railway `odds_capture` service logs | Restart odds_capture Railway service |
| `odds_freshness_alert_sensor` QUOTA | Odds-API dashboard: plan / renewal | Top up MAIN key or re-enable Parlay |
| `schedule_freshness_alert_sensor` | Railway `schedule_capture` service logs | `uv run python scripts/ingest_statsapi.py schedule` |
| `statcast_freshness_sensor` SLA | Baseball Savant publish time; savant_ingestion logs | `uv run python scripts/savant_ingestion.py batter_pitches` |
| `pregame_alert_sensor` | `pipeline_status` row for today; Dagster daily job run | Re-trigger `daily_ingestion_job` from Dagster UI |
| `model_health_alert_sensor` | `betting_ml.model_health_log`; serving feature coverage | Inspect post-lineup predictions for feature nulls |
| Archetype posteriors stale (WARN) | `mart_player_archetype_posteriors.as_of_date` | `uv run python betting_ml/scripts/eb_priors/compute_archetype_posteriors.py --mode today` |
