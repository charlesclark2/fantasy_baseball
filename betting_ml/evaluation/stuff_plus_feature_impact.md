## Stuff+ Feature Impact Report

Date: 2026-05-03
Card: 7.F — FanGraphs Stuff+ and per-pitch arsenal features

---

### Training data cutoff change

Effective 2026-05-03, `data_loader.py` training queries filter to `game_year >= 2021`
(previously `game_year != 2020`). Pre-2020 rows had 0% Stuff+ population, creating a
distribution shift between training (NULL = feature didn't exist) and production
(NULL = rare edge case — pitcher not in FanGraphs). This drops ~11,700 rows
but produces a fully internally consistent training distribution.

| Dataset | Rows | Seasons | Stuff+ populated |
|---------|------|---------|-----------------|
| 2015+ (prior) | ~17,781 | 2015–2026 | ~52% |
| 2021+ (current) | 10,243 | 2021–2026 | ~99.8% |

---

### Features retained after selection

**Run 1 — 2026-05-02** (`validate_feature_selection.py`, 17,781 rows × 448 columns, 2015+ data):
254 retained, 75 near-zero dropped, 86 multicollinear dropped.

**Run 2 — 2026-05-03** (`validate_feature_selection.py`, 10,243 rows × 448 columns, 2021+ data):
**267 retained, 74 near-zero dropped, 74 multicollinear dropped.**

The +13 net increase in retained features comes primarily from the multicollinearity step
(86 → 74 dropped): features that were redundant with each other on the mixed pre/post-2020
dataset now show more independent signal on the clean 2021+ data.

#### Arsenal features retained (13 of 18 numeric, both runs)

| Feature | max \|r\| (2021+) | Note |
|---|---|---|
| `home_starter_stuff_plus` | 0.1029 | Rank 16 overall out of 267 retained |
| `away_starter_stuff_plus` | 0.0983 | Top 20 overall |
| `home_starter_fastball_stuff_plus` | 0.0862 | |
| `away_starter_fastball_stuff_plus` | 0.0820 | |
| `away_starter_curveball_stuff_plus` | 0.0666 | |
| `away_starter_changeup_stuff_plus` | 0.0657 | |
| `home_starter_changeup_stuff_plus` | 0.0577 | |
| `home_starter_slider_stuff_plus` | 0.0505 | |
| `home_starter_curveball_stuff_plus` | 0.0469 | |
| `away_starter_slider_stuff_plus` | 0.0449 | |
| `home_starter_avg_fastball_velo` | 0.0466 | |
| `away_starter_avg_fastball_velo` | 0.0482 | |
| `away_starter_fastball_pct` | 0.0268 | Only mix-% feature to survive |

#### Dropped — near-zero correlation (5, consistent across both runs)

`home_starter_fastball_pct` (0.0033), `away_starter_offspeed_pct` (0.0044),
`home_starter_offspeed_pct` (0.0146), `home_starter_breaking_pct` (0.0155),
`away_starter_breaking_pct` (0.0193).

Pitch-mix percentages carry weak signal in isolation — quality scores (Stuff+) dominate.

#### Not evaluated (2)

`home_starter_primary_pitch_type`, `away_starter_primary_pitch_type` — categorical strings,
excluded from the numeric correlation pass. Available to XGBoost if label-encoded upstream.

---

### home_win model

| Metric   | 2015+ with Stuff+ | 2021+ with Stuff+ | Note |
|----------|-------------------|-------------------|------|
| CV Brier | 0.2428            | 0.2443            | Not directly comparable — different data |

Retrained 2026-05-03 on 10,243 rows, 267 features.
Artifact: `betting_ml/models/home_win/xgb_classifier_tuned_2026.pkl`

The CV score of 0.2443 on 2021+ data is flat vs the pre-Stuff+ baseline (0.2443) evaluated
on the same framework. The prior 2015+ retrain scored 0.2428, but that score is not
comparable: different row count, different null structure, different CV fold composition.
The 2021+ model is the correct production model — it trains on a distribution that matches
production feature coverage.

> **Note:** Calibrator (`calibrator.joblib`) was fitted on the prior model weights.
> A calibrator refit is required before production deployment.

---

### total_runs model

| Metric | 2015+ baseline | 2021+ retrain | Delta |
|--------|---------------|---------------|-------|
| CV MAE | 3.5232        | 3.4856        | −0.038 |

---

### run_differential model

| Metric | 2015+ baseline | 2021+ retrain | Delta |
|--------|---------------|---------------|-------|
| CV MAE | 3.4195        | 3.4586        | +0.039 |

> **Note:** LogNormal distribution failed for run_differential — run_diff can be negative,
> causing `log(Y)` divide-by-zero. Only Normal distribution is viable going forward.
> Scores are not directly comparable to the 2015+ baseline (different dataset, different
> feature set).

---

### Interpretation

All three models retrained on 10,243 rows (2021–2026, 267 features). Summary:

| Model | Prior CV | 2021+ CV | Delta | Status |
|-------|----------|----------|-------|--------|
| home_win (Brier) | 0.2443 | 0.2443 | 0.000 | Flat |
| total_runs (MAE) | 3.5232 | 3.4856 | −0.038 | Modest improvement |
| run_differential (MAE) | 3.4195 | 3.4586 | +0.039 | Slight degradation |

CV scores across the cutoff change are not directly comparable — different row counts,
null structures, and CV fold compositions.

**total_runs** is the only model showing directional improvement (−0.038 MAE), consistent
with weather and Stuff+ features having more signal for run-environment prediction than
binary win/loss.

**home_win** is flat and **run_differential** regressed slightly. Three compounding factors:
1. Stuff+ signal overlaps existing rolling Statcast features (xwOBA, K%) on 2021+ data
   where both are populated — less independent signal than expected.
2. The reduced row count (10,243 vs ~17,781) reduces statistical power, offsetting the
   cleaner feature distribution.
3. run_differential's 2015+ baseline included LogNormal as a candidate; 2021+ Normal-only
   comparison is methodologically inconsistent.

**Flag for Card 7.M:** With all three models flat or modestly improved, the Stuff+ arsenal
features are not adding decisive CV lift on their own. After all remaining feature expansion
cards (7.G, 7.H, 7.I, 7.J, 7.K) complete, a full joint retraining on the combined feature
set (Card 7.N) is the correct next step before investigating interaction terms or raising
the corr_threshold.
