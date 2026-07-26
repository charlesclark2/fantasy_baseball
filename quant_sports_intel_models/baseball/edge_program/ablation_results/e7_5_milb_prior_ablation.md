# MLB Edge-E7.5 — MiLB MLE → recalibrated rookie prior (wired into `eb_batter_posteriors_raw`)

**Model:** `milb_mle_prior_v1` · **generated:** 2026-07-26T07:39:22.792567+00:00

> ⚠️ **This wires a performance-based PRIOR for low-MLB-PA rookies, not an edge claim.** For a called-up batter with ~0 MLB PAs the served build previously shrank toward a GENERIC archetype/slot prior; E7.5 replaces that with the E7.3 MiLB→MLB MLE line for the metrics that TRANSLATE — **K%, BB%, and ISO (wide)** — and shrinks the rookie's own MLB line toward it as PAs accrue. **wOBA is NOT wired** (E7.3: no translatable signal beyond level). The E7.3 parameter sd is too tight to price, so E7.5 RECALIBRATES it on held-out MLB data (E13.6): the prior sd is the held-out predictive spread of the MLE mean around realized early-career MLB production. `best_alpha = 0`.

## 1. Recalibration — parameter sd → held-out predictive spread (E13.6)

`σ_resid = std(realized MLB rate − MLE mean)` over graduated players (leakage-safe: each `mle_<m>` was fit only on strictly-prior debut cohorts). It REPLACES the tighter parameter sd `mle_<m>_sd`. The Beta pseudo-count κ = m(1−m)/σ_resid² − 1 (clipped) is the equivalent MLB-PA weight of the prior; ISO uses σ_resid as the Normal prior sd directly. Coverage of ±σ_resid / ±1.645σ_resid against the honest ~0.68 / ~0.90 shows the recalibrated sd is calibrated, not the tight one.

| metric   |   resid_sd |   param_sd_median |   tightness_ratio |   n |   coverage_68 |   coverage_90 |   label_sampling_sd |   true_sd_est |   kappa_floor |   kappa_cap |
|:---------|-----------:|------------------:|------------------:|----:|--------------:|--------------:|--------------------:|--------------:|--------------:|------------:|
| k_pct    |   0.044336 |          0.006134 |             7.228 | 597 |        0.6801 |        0.9045 |            0.023677 |      0.037485 |            20 |         400 |
| bb_pct   |   0.022223 |          0.004325 |             5.138 | 597 |        0.6667 |        0.9062 |            0.014412 |      0.016916 |            20 |         400 |
| iso      |   0.047482 |          0.006802 |             6.981 | 597 |        0.6633 |        0.8878 |            0.019013 |      0.043509 |            20 |         400 |

- `tightness_ratio` = σ_resid ÷ median parameter sd — how much wider the honest predictive sd is than the E7.3 parameter sd (>1 confirms the parameter sd was too tight to price).
- `true_sd_est` = variance-decomposed between-player prior sd (σ_resid² − label-sampling-var); a diagnostic only — the SERVED prior sd stays σ_resid (conservative: the prior is a touch weaker, so the rookie's own MLB line takes over a touch faster — the safe direction).

## 2. Calibration ablation — MLE prior vs the incumbent generic prior (purged, leave-one-cohort-out)

For each debut cohort Y (≥1 strictly-prior cohort): the GENERIC baseline mean = the population mean of the realized MLB metric over PRIOR cohorts (what the generic archetype/level prior collapses to at PA≈0 — E7.3's `archetype_prior` benchmark); the MLE mean = the OOS `mle_<m>`. Each method uses its OWN prior-cohort residual sd (both self-calibrated → the comparison is calibration × SHARPNESS, not a sd handicap). Scored on the cohort-Y rookies. Lower NLL/CRPS/MAE = better; coverage ≈ 0.68/0.90 = honest.

| metric   |   n_scored |   n_cohorts |   mle_nll |   generic_nll |   mle_crps |   generic_crps |   mle_mae |   generic_mae |   mle_cov68 |   generic_cov68 |   mle_cov90 |   generic_cov90 | mle_wins   | notes   |
|:---------|-----------:|------------:|----------:|--------------:|-----------:|---------------:|----------:|--------------:|------------:|----------------:|------------:|----------------:|:-----------|:--------|
| k_pct    |        534 |          10 |  -1.69915 |      -1.36521 |   0.025048 |       0.034793 |  0.035808 |      0.049266 |      0.7004 |          0.6835 |      0.9176 |          0.9139 | True       | []      |
| bb_pct   |        534 |          10 |  -2.37611 |      -2.24463 |   0.012635 |       0.014449 |  0.018066 |      0.020632 |      0.7004 |          0.7022 |      0.9232 |          0.9307 | True       | []      |
| iso      |        534 |          10 |  -1.59148 |      -1.52416 |   0.027868 |       0.029678 |  0.03982  |      0.042328 |      0.7079 |          0.7022 |      0.9307 |          0.9494 | True       | []      |

- **k_pct** — ✅ MLE prior improves rookie calibration: NLL -1.6991 vs -1.3652, CRPS 0.02505 vs 0.03479, MAE 0.03581 vs 0.04927 (n=534 rookies over 10 cohorts).
- **bb_pct** — ✅ MLE prior improves rookie calibration: NLL -2.3761 vs -2.2446, CRPS 0.01263 vs 0.01445, MAE 0.01807 vs 0.02063 (n=534 rookies over 10 cohorts).
- **iso** — ✅ MLE prior improves rookie calibration: NLL -1.5915 vs -1.5242, CRPS 0.02787 vs 0.02968, MAE 0.03982 vs 0.04233 (n=534 rookies over 10 cohorts).

## 3. What is wired (and what is not)

- **Served build:** `dbt/models/eb_posteriors/eb_batter_posteriors_raw.sql` (DuckDB branch, the SF-free lakehouse compute). A `milb_mle_prior` precursor view (this script's S3 output) is joined on `batter_id` (MLBAM). For K%/BB% the MLE mean + κ become the Beta prior (α=m·κ, β=(1−m)·κ); for ISO the MLE mean + σ_resid become the Normal prior. A low-PA rookie WITH an MLE gets the MLE line; the existing generic archetype/slot prior stays for players WITHOUT one, and wOBA is untouched.
- **PA-accrual blend EXTENDED, not duplicated:** the existing Beta-Binomial / Normal-Normal update shrinks from the MLE prior toward the rookie's observed MLB line as season PA grows (κ = equivalent PA). When an MLE prior is present the ZiPS low-PA blend is bypassed for that metric (no double-counted projection).
- **Leakage-safe:** only pre-debut minor-league stats enter the MLE (the E7.3 as-of guard); the prior table is static (rebuilt when the MLE is retrained), read as a W8a precursor.

## 4. Limitations

- **σ_resid carries finite-PA label sampling noise** — so it slightly over-states the between-player prior sd, making the prior marginally weaker (safe). `true_sd_est` reports the decomposed value.
- **Graduated players are self-selected** (they reached the MLB PA floor) — the calibration is on players who established, which is the served population (a rookie getting playing time). Stated, not corrected (inherited from E7.3).
- **Prospect coverage:** 6365 batters carry a calibrated prior (graduated + active prospects).
- **best_alpha = 0** — a rookie betting prior, never a market bet.

