# Monitoring Runbook

## Overview

Three automated checks run daily via `daily_ingestion.yml` GitHub Actions. Each check exits non-zero on failure, causing the GHA step — and the overall workflow — to fail visibly.

| Check | Script | Trigger position in workflow |
|---|---|---|
| Data Freshness | `check_data_freshness.py` | End of `ingest` job, before `dbt-build` |
| Prediction Coverage | `check_prediction_coverage.py` | `predict` job, immediately after `predict_today.py` |
| Calibration Drift (ECE) | `compute_model_health.py` | `predict` job, after `dbtf build` |

---

## Check 1: Data Freshness (`check_data_freshness.py`)

### What it checks

Queries `MAX(ingestion_timestamp)` for each source table and compares the elapsed time against a per-table freshness threshold. On game-day-only tables, the check is skipped entirely on off-days.

### Thresholds

| Source table | Max stale (hours) | Game day only? |
|---|---|---|
| `savant.batter_pitches` | `game_date` (DATE) | 48h | No |
| `oddsapi.mlb_odds_raw` | `ingestion_ts` | 6h | Yes |
| `fangraphs.fg_stuff_plus_raw` | `ingestion_ts` | 192h (8 days) | No |
| `statsapi.umpire_game_log` | `loaded_at` | 36h | No |
| `statsapi.player_transactions` | `effective_date` (DATE) | 168h (7 days) | No |
| `statsapi.monthly_schedule` | `month_end_date` (DATE) | 48h | Yes |

### Alert behavior

Exits non-zero. The GHA `ingest` job step fails, blocking `dbt-build` and all downstream jobs.

### Resolution

1. Check the GHA step log to identify which table(s) exceeded their threshold.
2. For transient failures (API rate limit, network hiccup): re-run the relevant ingestion script manually:
   ```bash
   uv run python scripts/savant_ingestion.py batter_pitches
   uv run python scripts/odds_api_ingestion.py odds
   uv run python scripts/ingest_fangraphs_stuff_plus.py --season $(date +%Y) --window-types 14d,30d,season
   uv run python scripts/ingest_umpires.py --date $(date +%Y-%m-%d)
   uv run python scripts/ingest_transactions.py --start-date $(date -v-7d +%Y-%m-%d) --end-date $(date +%Y-%m-%d)
   uv run python scripts/ingest_statsapi.py schedule
   ```
3. After re-ingesting, re-run `check_data_freshness.py` locally to confirm the table is fresh before re-triggering the workflow.

### False positives

- **`mlb_odds_raw` and `monthly_schedule`** are `game_day_only` — these checks are automatically skipped on off-days. If the script fires on an off-day, verify that `monthly_schedule` shows games for the check date.
- **`fg_stuff_plus_raw`** is a weekly Sunday ingest. Mid-week staleness up to 8 days is expected — the threshold is set accordingly.

---

## Check 2: Prediction Coverage (`check_prediction_coverage.py`)

### What it checks

After `predict_today.py` runs, compares:
- **Expected games**: count of rows in `statsapi.monthly_schedule` where `game_date = today AND has_full_lineup = true`
- **Scored games**: count of rows in `betting_ml.daily_model_predictions` where `game_date = today`

Coverage = scored / expected. Fails if coverage < 90%.

### Alert threshold

Coverage < 90% on any game day.

### Alert behavior

Exits non-zero. The GHA `predict` job step fails.

### Resolution

1. Check which games were expected vs. scored:
   ```sql
   -- Expected games (confirmed lineups via feature store)
   SELECT game_pk, home_team, away_team
   FROM baseball_data.betting_features.feature_pregame_game_features
   WHERE game_date = CURRENT_DATE AND has_full_data = true;

   -- Scored games
   SELECT game_pk, game_date
   FROM baseball_data.betting_ml.daily_model_predictions
   WHERE game_date = CURRENT_DATE;
   ```
2. If lineups weren't confirmed in time: `has_full_lineup` may not yet be `true` for late-posting lineups. Wait ~30 min and re-run `ingest_statsapi.py schedule` followed by `predict_today.py`.
3. Run `predict_today.py` manually for the missed game date:
   ```bash
   uv run python scripts/predict_today.py --date $(date +%Y-%m-%d) --prediction-type morning
   ```
4. On off-days (expected_games = 0), the script exits 0 automatically — no action required.

---

## Check 3: Calibration Drift / Model Health (`compute_model_health.py`)

### What it checks

Computes rolling 14-day **Expected Calibration Error (ECE)** and **Brier score** on `baseball_data.config.prediction_log` rows where `outcome IS NOT NULL`. ECE measures how well stated probabilities match actual observed frequencies across 10 equal-width probability bins.

### Alert threshold

ECE > 0.04 (2× the elasticnet calibration baseline of 0.0202, established in Phase 7).

### Alert behavior

Exits non-zero AND writes `alert_fired = true` to `baseball_data.betting_ml.model_health_log`.

### Querying alert history

```sql
SELECT run_date, target, window_days, ece, brier, sample_n, alert_fired
FROM baseball_data.betting_ml.model_health_log
ORDER BY run_date DESC
LIMIT 30;

-- Recent alerts only
SELECT run_date, target, ece, brier, sample_n
FROM baseball_data.betting_ml.model_health_log
WHERE alert_fired = true
ORDER BY run_date DESC;
```

### Resolution

1. Check how many days the ECE has been elevated and whether it is trending up:
   ```sql
   SELECT run_date, ece, brier, sample_n
   FROM baseball_data.betting_ml.model_health_log
   WHERE target = 'home_win'
   ORDER BY run_date DESC
   LIMIT 14;
   ```
2. If ECE has been elevated for < 3 consecutive days and sample_n < 30: this may be noise from a small outcome window. Monitor and do not recalibrate yet.
3. If ECE remains elevated for 3+ consecutive days with sample_n > 50: consider recalibrating the Platt scaling layer:
   ```bash
   # Refit calibrator using current 2026 in-season results
   uv run python betting_ml/scripts/fit_calibrator.py --target home_win
   ```
4. If recalibration does not resolve the drift, consider a full model retrain (deferred to Phase 9 cadence decisions).

### Silencing a false positive

For a one-off date where the alert fired due to an unusual slate (e.g., rain-shortened games distorting outcomes), acknowledge by inserting a manual override row:

```sql
-- Do not delete; insert an acknowledged note in the model_health_log
-- (add an 'acknowledged' column first if this becomes recurring)
-- For now, document the reason in the git commit or daily_run.md
```

Re-run `compute_model_health.py` the following day. If ECE returns to normal, no further action is needed.

---

## Querying Alert History (All Checks)

```sql
-- Full model health log
SELECT *
FROM baseball_data.betting_ml.model_health_log
ORDER BY run_date DESC, target;

-- Last 14 days of ECE trend
SELECT run_date, ece, brier, sample_n, alert_fired
FROM baseball_data.betting_ml.model_health_log
WHERE target = 'home_win'
  AND run_date >= DATEADD(day, -14, CURRENT_DATE)
ORDER BY run_date;
```
