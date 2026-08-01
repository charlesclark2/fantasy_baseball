# MLB Edge-E7.5 — MiLB MLE → recalibrated rookie prior (wired into `eb_batter_posteriors_raw`)

**Model:** `milb_mle_prior_v1` · **generated:** 2026-08-01T23:34:37.582225+00:00

> ⚠️ **This run was gated by E7.5b and the served parquet is MIXED.** The recalibration and ablation tables below are the CHALLENGER's, for all metrics. What actually ships: **bb_pct, iso** from the challenger MLE; **k_pct** did NOT clear the head-to-head gate and keeps the previously-served `milb_mle_v1` values VERBATIM. Read [`e7_5b_mle_prior_head_to_head.md`](e7_5b_mle_prior_head_to_head.md) for the per-metric verdict and the numbers that are actually serving for the held-back metric(s).

> ⚠️ **This wires a performance-based PRIOR for low-MLB-PA rookies, not an edge claim.** For a called-up batter with ~0 MLB PAs the served build previously shrank toward a GENERIC archetype/slot prior; E7.5 replaces that with the E7.3 MiLB→MLB MLE line for the metrics that TRANSLATE — **K%, BB%, and ISO (wide)** — and shrinks the rookie's own MLB line toward it as PAs accrue. **wOBA is NOT wired** (E7.3: no translatable signal beyond level). The E7.3 parameter sd is too tight to price, so E7.5 RECALIBRATES it on held-out MLB data (E13.6): the prior sd is the held-out predictive spread of the MLE mean around realized early-career MLB production. `best_alpha = 0`.

## 1. Recalibration — parameter sd → held-out predictive spread (E13.6)

`σ_resid = std(realized MLB rate − MLE mean)` over graduated players (leakage-safe: each `mle_<m>` was fit only on strictly-prior debut cohorts). It REPLACES the tighter parameter sd `mle_<m>_sd`. The Beta pseudo-count κ = m(1−m)/σ_resid² − 1 (clipped) is the equivalent MLB-PA weight of the prior; ISO uses σ_resid as the Normal prior sd directly. Coverage of ±σ_resid / ±1.645σ_resid against the honest ~0.68 / ~0.90 shows the recalibrated sd is calibrated, not the tight one.

| metric   |   resid_sd |   param_sd_median |   tightness_ratio |   n |   coverage_68 |   coverage_90 |   label_sampling_sd |   true_sd_est |   kappa_floor |   kappa_cap |
|:---------|-----------:|------------------:|------------------:|----:|--------------:|--------------:|--------------------:|--------------:|--------------:|------------:|
| k_pct    |   0.044539 |          0.005997 |             7.427 | 601 |        0.6739 |        0.9002 |            0.023718 |      0.037699 |            20 |         400 |
| bb_pct   |   0.021457 |          0.004123 |             5.204 | 601 |        0.6889 |        0.9185 |            0.014447 |      0.015864 |            20 |         400 |
| iso      |   0.046649 |          0.006444 |             7.239 | 601 |        0.6889 |        0.8985 |            0.019057 |      0.042579 |            20 |         400 |

- `tightness_ratio` = σ_resid ÷ median parameter sd — how much wider the honest predictive sd is than the E7.3 parameter sd (>1 confirms the parameter sd was too tight to price).
- `true_sd_est` = variance-decomposed between-player prior sd (σ_resid² − label-sampling-var); a diagnostic only — the SERVED prior sd stays σ_resid (conservative: the prior is a touch weaker, so the rookie's own MLB line takes over a touch faster — the safe direction).

## 2. Calibration ablation — MLE prior vs the incumbent generic prior (purged, leave-one-cohort-out)

For each debut cohort Y (≥1 strictly-prior cohort): the GENERIC baseline mean = the population mean of the realized MLB metric over PRIOR cohorts (what the generic archetype/level prior collapses to at PA≈0 — E7.3's `archetype_prior` benchmark); the MLE mean = the OOS `mle_<m>`. Each method uses its OWN prior-cohort residual sd (both self-calibrated → the comparison is calibration × SHARPNESS, not a sd handicap). Scored on the cohort-Y rookies. Lower NLL/CRPS/MAE = better; coverage ≈ 0.68/0.90 = honest.

| metric   |   n_scored |   n_cohorts |   mle_nll |   generic_nll |   mle_crps |   generic_crps |   mle_mae |   generic_mae |   mle_cov68 |   generic_cov68 |   mle_cov90 |   generic_cov90 | mle_wins   | notes   |
|:---------|-----------:|------------:|----------:|--------------:|-----------:|---------------:|----------:|--------------:|------------:|----------------:|------------:|----------------:|:-----------|:--------|
| k_pct    |        538 |          10 |  -1.6802  |      -1.36533 |   0.02534  |       0.034805 |  0.035755 |      0.049316 |      0.6859 |          0.6803 |      0.9126 |          0.9145 | True       | []      |
| bb_pct   |        538 |          10 |  -2.44067 |      -2.24302 |   0.011808 |       0.014483 |  0.016751 |      0.02069  |      0.7193 |          0.7007 |      0.9331 |          0.9331 | True       | []      |
| iso      |        538 |          10 |  -1.64763 |      -1.50727 |   0.026024 |       0.029991 |  0.037109 |      0.042628 |      0.7286 |          0.7007 |      0.9238 |          0.9498 | True       | []      |

- **k_pct** — ✅ MLE prior improves rookie calibration: NLL -1.6802 vs -1.3653, CRPS 0.02534 vs 0.03481, MAE 0.03576 vs 0.04932 (n=538 rookies over 10 cohorts).
- **bb_pct** — ✅ MLE prior improves rookie calibration: NLL -2.4407 vs -2.2430, CRPS 0.01181 vs 0.01448, MAE 0.01675 vs 0.02069 (n=538 rookies over 10 cohorts).
- **iso** — ✅ MLE prior improves rookie calibration: NLL -1.6476 vs -1.5073, CRPS 0.02602 vs 0.02999, MAE 0.03711 vs 0.04263 (n=538 rookies over 10 cohorts).

## 3. What is wired (and what is not)

- **Served build:** `dbt/models/eb_posteriors/eb_batter_posteriors_raw.sql` (DuckDB branch, the SF-free lakehouse compute). A `milb_mle_prior` precursor view (this script's S3 output) is joined on `batter_id` (MLBAM). For K%/BB% the MLE mean + κ become the Beta prior (α=m·κ, β=(1−m)·κ); for ISO the MLE mean + σ_resid become the Normal prior. A low-PA rookie WITH an MLE gets the MLE line; the existing generic archetype/slot prior stays for players WITHOUT one, and wOBA is untouched.
- **PA-accrual blend EXTENDED, not duplicated:** the existing Beta-Binomial / Normal-Normal update shrinks from the MLE prior toward the rookie's observed MLB line as season PA grows (κ = equivalent PA). When an MLE prior is present the ZiPS low-PA blend is bypassed for that metric (no double-counted projection).
- **Leakage-safe:** only pre-debut minor-league stats enter the MLE (the E7.3 as-of guard); the prior table is static (rebuilt when the MLE is retrained), read as a W8a precursor.

## 4. Limitations

- **σ_resid carries finite-PA label sampling noise** — so it slightly over-states the between-player prior sd, making the prior marginally weaker (safe). `true_sd_est` reports the decomposed value.
- **Graduated players are self-selected** (they reached the MLB PA floor) — the calibration is on players who established, which is the served population (a rookie getting playing time). Stated, not corrected (inherited from E7.3).
- **Prospect coverage:** 6376 batters carry a calibrated prior (graduated + active prospects).
- **best_alpha = 0** — a rookie betting prior, never a market bet.

