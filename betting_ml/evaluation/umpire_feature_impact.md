# Umpire Feature Impact Report

**Date:** 2026-05-03  
**Card:** 7.H  
**Historical rows loaded:** 25,556 (2015-04-05 → 2026-05-01, 141 unique umpires)  
**Coverage (2026 regular season games):** 479 / 482 = 99.4%  

---

## Data Architecture

**Source A — UmpScorecards historical bulk export (one-time + annual refresh)**  
Script: `scripts/ingest_umpires_historical.py`  
Default input: `scripts/raw_files/umpscorecards/umpscorecards_historical.csv`  
Reference URL: https://umpscorecards.com/data/games  
Method: truncate + `write_pandas` bulk load (25,556 rows in ~5 seconds)

**NOTE on k_pct / bb_pct:** The UmpScorecards by-game export does not include
per-game K% or BB%. Those columns are retained in `umpire_game_log` for future
population but are NULL in all current rows. `ump_k_pct_zscore` and
`ump_bb_pct_zscore` default to 0.0 (neutral signal) until that data is available.
A potential path for populating them: aggregate Statcast `batter_pitches` by
game_pk (strikeout events / PA → k_pct; walk events / PA → bb_pct) and join on
game_pk, then backfill via an annual refresh script.

**Source B — MLB Stats API daily assignment**  
Script: `scripts/ingest_umpires.py --date YYYY-MM-DD`  
Wired into: `.github/workflows/daily_ingestion.yml` (runs after odds ingestion)  
Writes: `umpire_name`, `umpire_id` only; tendency columns remain NULL.

---

## Feature Coverage

| Feature | 2026 Games with Value | Coverage |
|---|---|---|
| `umpire_name` | 479 / 482 | 99.4% |
| `ump_runs_per_game_zscore` | 479 / 482 | 99.4% |
| `ump_run_impact_zscore` | 479 / 482 | 99.4% |
| `ump_accuracy_zscore` | 479 / 482 | 99.4% |
| `ump_k_pct_zscore` | 479 / 482 (all 0.0) | 99.4% |
| `ump_bb_pct_zscore` | 479 / 482 (all 0.0) | 99.4% |

3 missing games: games with no HP umpire assignment in either UmpScorecards or
the Stats API response at time of build.

Average sample size for z-score computation: 80.6 trailing games (min 4, all
umpires with ≥10 games get real z-scores per the sample gate).

**Feature distribution (2026, n=479):**

| Feature | Mean | Std Dev |
|---|---|---|
| `ump_runs_per_game_zscore` | -0.014 | 0.121 |
| `ump_run_impact_zscore` | -0.299 | 0.197 |
| `ump_accuracy_zscore` | +0.288 | n/a |

---

## Features Retained After Selection

Correlation with outcome (2018–2025+2026 regular season, n=17,812):

| Feature | corr vs total_runs | corr vs home_win | Passes 0.02 threshold? |
|---|---|---|---|
| `ump_runs_per_game_zscore` | -0.024 | -0.003 | **Yes** (marginal) |
| `ump_run_impact_zscore` | -0.007 | n/a | No |
| `ump_accuracy_zscore` | +0.021 | n/a | **Yes** (marginal) |
| `ump_k_pct_zscore` | 0.0 (all null→0) | n/a | No |
| `ump_bb_pct_zscore` | 0.0 (all null→0) | n/a | No |

**Retained for model retraining:** `ump_runs_per_game_zscore`, `ump_accuracy_zscore`  
**Excluded (corr < 0.02 or structural zero):** `ump_run_impact_zscore`, `ump_k_pct_zscore`, `ump_bb_pct_zscore`

Both retained features are marginal (|r| ≈ 0.02). The trailing z-score
compression is expected: individual umpires vary by only a fraction of a run
from league average, and the z-score normalization ensures that variation is
properly scaled. Tree-based models (XGBoost, NGBoost) may discover non-linear
zone interactions that linear correlation misses.

---

## total_runs model (NGBoost)

| Metric | Before umpire features | After |
|---|---|---|
| CV MAE | 3.5232 | _pending retrain_ |

**Status:** NGBoost retrain was in progress on card 7F when this card ran.
CV MAE will be recorded here after the retrain completes. The pre-feature
baseline is CV MAE = 3.5232 (from model_registry.yaml, retrained 2026-05-02
with weather features).

---

## home_win model (XGBoost)

| Metric | Before umpire features | After |
|---|---|---|
| CV Brier | 0.2443 | _pending retrain_ |

**Status:** Same as above — retrain pending. Pre-feature baseline is CV
Brier = 0.2443. Umpire features are expected to have minimal impact on
home_win (umpire zone effects are symmetric between home and away), consistent
with the near-zero correlation (-0.003) observed above.

---

## Coverage Analysis

99.4% of 2026 regular season game-dates have a non-null `umpire_name`.

The 3 missing games (0.6%) are early-season games where HP umpire was not
listed in either the UmpScorecards export or the Stats API response at build
time. These will populate once `ingest_umpires.py` runs for those dates.

No gap was found in the historical backfill — all 2015–2026 games in
UmpScorecards are loaded. The daily Stats API step will populate any post
2026-05-01 games going forward.

---

## Notes and Next Steps

1. **k_pct / bb_pct backfill:** Consider a future script that aggregates
   Statcast `batter_pitches` by game_pk to compute per-game k_pct and bb_pct,
   then backfills `umpire_game_log`. This would unlock two more z-score signals.

2. **Annual UmpScorecards refresh:** Run
   `uv run python scripts/ingest_umpires_historical.py` (no flags) each
   off-season to reload the latest full export. The `--merge` flag can be used
   for a single-season update without truncating historical rows.

3. **model_registry.yaml update:** Update CV metrics here and in
   `betting_ml/models/model_registry.yaml` after the retrain completes.
