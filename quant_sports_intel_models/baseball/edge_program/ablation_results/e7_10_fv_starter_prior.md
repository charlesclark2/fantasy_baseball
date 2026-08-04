# MLB Edge-E7.10 — is pre-debut FanGraphs FV an incremental cold-start RATE prior for debuting STARTERS?

**Study:** `e7.10-v1` · **generated:** 2026-08-04T03:58:27.796436+00:00 · **pre-registration:** `e7_10_preregistration.md` (written before any arm was scored)

> ⚠️ **This is a cold-start PRIOR-CALIBRATION study, not an edge claim — `best_alpha = 0`.** It asks one question: does the pre-debut FV grade improve the K% / BB% / GB% prior a debuting starter gets in `eb_starter_posteriors`, **over the E7.5p MiLB-MLE prior already wired there**? A clean NULL is a valid, high-value answer — it says keep leaning on our own MLE translation and do not pay for scouting hype in the serving path — and it is NOT forced into a survivor.

> 🧭 **E7.8 IS NOT THIS RESULT.** E7.8 graded FV against 3-year dynasty FANTASY POINTS and found it complements our performance read for pitchers. Different target, different population, different decision. E7.8 is why this study was worth running; it is not evidence for its conclusion.

## 0. Verdict

| metric   | verdict   |   n_folds |   n_scored |   CRPS A1_mle_fv |   CRPS C0 (matched foil) |   CRPS L0 (served today) | rel gain vs foil   | fold wins    |      p | BH    |   PBO |      DSR |
|:---------|:----------|----------:|-----------:|-----------------:|-------------------------:|-------------------------:|:-------------------|:-------------|-------:|:------|------:|---------:|
| gb_pct   | DROP      |         6 |        233 |         0.031745 |                 0.031582 |                 0.031085 | -0.51%             | 1/6 (need 5) | 0.7367 | False |   0.4 | 0.127161 |
| k_pct    | DROP      |         6 |        233 |         0.023701 |                 0.023653 |                 0.023667 | -0.20%             | 3/6 (need 5) | 0.5731 | False |   0.7 | 0.267045 |
| bb_pct   | DROP      |         6 |        233 |         0.013034 |                 0.013003 |                 0.013005 | -0.24%             | 2/6 (need 5) | 0.8858 | False |   0.6 | 0.347959 |

**🎯 TAKEAWAY — NULL. No metric clears the pre-registered bar, so nothing is wired and the E7.5p MLE prior stands as the sole cold-start term, unchanged.** §4 states, per metric, WHICH of the eight null states this is and whether any re-test trigger is reachable — a null without that classification is a shrug, not a finding (MH2).

- **gb_pct** — 🟡 no arm clears: best eligible `A1_mle_fv` CRPS 0.03174 vs foil 0.03158 (-0.51%, fold win rate 17%; the pre-registered bar is a strict OOS improvement in ≥60% of folds; calibrated clause needs 5/6 at α=0.2 (got 1; the legacy ≥60% bar would fire 34.4% of the time on a NULL)). DROPPED.
- **k_pct** — 🟡 no arm clears: best eligible `A1_mle_fv` CRPS 0.02370 vs foil 0.02365 (-0.20%, fold win rate 50%; the pre-registered bar is a strict OOS improvement in ≥60% of folds; calibrated clause needs 5/6 at α=0.2 (got 3; the legacy ≥60% bar would fire 34.4% of the time on a NULL)). DROPPED.
- **bb_pct** — 🟡 no arm clears: best eligible `A1_mle_fv` CRPS 0.01303 vs foil 0.01300 (-0.24%, fold win rate 33%; the pre-registered bar is a strict OOS improvement in ≥60% of folds; calibrated clause needs 5/6 at α=0.2 (got 2; the legacy ≥60% bar would fire 34.4% of the time on a NULL)). DROPPED.

### 0b. WHY the null — is FV uninformative, or informative-but-REDUNDANT?

A bare 'it did not clear' cannot tell those apart, and they carry different lessons. The post-hoc diagnostic `D_fv_over_generic` (FV with the MLE column REMOVED, scored against the generic cohort-mean prior — **excluded from every gate's trial field**, MH2.1 (a)) separates them per metric:

| metric   |   FV alone (CRPS) |   generic prior (CRPS) | FV informative on its own?   | reading                                 |
|:---------|------------------:|-----------------------:|:-----------------------------|:----------------------------------------|
| gb_pct   |          0.041207 |               0.041119 | False                        | NO SIGNAL — does not beat a cohort mean |
| k_pct    |          0.02433  |               0.024558 | True                         | REDUNDANT — a SUBSTITUTE for our MLE    |
| bb_pct   |          0.014214 |               0.014175 | False                        | NO SIGNAL — does not beat a cohort mean |

⭐ **This is where E7.10 and E7.8 genuinely differ, and the difference is attributable rather than rhetorical.** E7.8 found pitcher FV **COMPLEMENTS** our MiLB performance read on 3-year dynasty FANTASY POINTS — a target dominated by *whether a prospect arrives and stays*, which is exactly what a scouting grade is built to forecast. E7.10's target is the realized RATE LINE of a pitcher who has ALREADY arrived: survivorship is conditioned away, and on that target the grade adds nothing our own translation does not already carry. Both readings can be true at once, and the pair is more useful than either alone: **use FV for WHO ARRIVES, use the MiLB-MLE for HOW HE PITCHES.**

> 📐 **On the score name:** the gate text above comes from the SHARED `h_harness.numeric_gate`, whose own primary score is MAE (it is the E7.15 slice harness). E7.10's primary score is **CRPS**, and the values quoted ARE CRPS — the label is corrected here rather than the number being left to read as something it is not. The harness's internal `oos_mae` / `mae_by_fold` keys are retained verbatim in the JSON so those shared functions run unmodified; `oos_crps` is the honest alias on every leaderboard.

## 1. The one design decision everything turns on — the MATCHED FOIL

Every FV arm is an in-fold regression, so it also gets a free intercept and slope on `mle_<m>`. Scored against the SERVED prior (`L0_mle_served`, the raw MLE mean) an FV arm could win on **recalibration of the MLE alone** and the win would be mis-attributed to the scouting grade. So the primary defender is **`C0_mle_recal`** — the identical regression MINUS the FV columns. It holds recalibration constant and varies only the FV channel (NF-D10 (g) / NF-D15 (g′)): a leaderboard rank cannot separate 'my feature is inert' from 'my feature is in a tie', and 'my arm won' is not 'it won for the reason I said'.

`L0_mle_served` is scored beside them, so **in-fold recalibration alone** shows up as its own finding rather than hiding inside an FV number:

| metric   |   CRPS L0 served |   CRPS C0 recalibrated | recalibration alone   |
|:---------|-----------------:|-----------------------:|:----------------------|
| gb_pct   |         0.031085 |               0.031582 | -1.60%                |
| k_pct    |         0.023667 |               0.023653 | +0.06%                |
| bb_pct   |         0.013005 |               0.013003 | +0.02%                |

⭐ **A SECONDARY FINDING WORTH KEEPING, because the matched foil is what makes it visible:** in-fold recalibration of the served MLE mean is **not free**. Where the `recalibration alone` column is NEGATIVE, re-fitting a slope and intercept on `mle_<m>` made the prior WORSE out of sample than serving the E7.3p mean verbatim — i.e. the E7.5p decision to serve the MLE mean unrecalibrated is, on this population, the right one and is now MEASURED rather than assumed (the E2.1-r reading of a null: the incumbent's choice becomes PROVEN). Had `L0` been used as the defender, this effect would have been silently folded into the FV verdict and attributed to the scouting grade.

## 2. Coverage gate — FV can only help where it exists

Of the labelled debuting STARTERS in cohorts THE BOARD could possibly have graded (debut ≥ 2019 — the board's first season is 2018), **74.6%** carry a strictly-prior-season FV grade. A pitcher FanGraphs never graded falls back to the E7.5p MLE prior — **never a silent drop**. Per debut cohort:

|   debut cohort |   labelled starters | FV coverage   |
|---------------:|--------------------:|:--------------|
|           2019 |                  50 | 68%           |
|           2020 |                  52 | 69%           |
|           2021 |                  55 | 78%           |
|           2022 |                  52 | 62%           |
|           2023 |                  56 | 82%           |
|           2024 |                  49 | 90%           |
|           2025 |                  44 | 73%           |

⚠️ **The denominator matters and the pooled figure is the wrong one.** Across ALL cohorts in the assembled frame the coverage reads 49.4%, but debut cohorts at or before 2018 have **0% by construction** — the board did not exist yet — so pooling them measures the board's START DATE, not its reach. That would be a coverage number for a quietly different population than the one it names (NF1.8). The 74.6% figure above is the one that answers 'would a debuting starter today have a grade?'; both are emitted in the coverage JSON.

⚠️ **The board is FanGraphs' GRADED population.** This study measures 'is the grade informative among the graded', never 'is the board's coverage complete'. The table above is the other half of that sentence.

## 3. Per-metric leaderboards, anchors and deflation

### `gb_pct`

Folds (debut cohorts scored): `[2020, 2021, 2022, 2023, 2024, 2025]` · rows scored 233 · rows per fold {2020: 36, 2021: 43, 2022: 32, 2023: 46, 2024: 44, 2025: 32} · FV in this population: mean 43.3, sd 5.13, 8 distinct values

**Leaderboard** (held-out **CRPS**, lower is better; `selectable` marks the declared 3-arm family that is the DSR trial field — foils and anchors are neither):

| arm                | uses_fv   |   oos_crps |   oos_pointscore_mae |   fold_win_rate |   pct_lift_vs_foil | selectable   |
|:-------------------|:----------|-----------:|---------------------:|----------------:|-------------------:|:-------------|
| L0_mle_served      | False     |   0.031085 |             0.043893 |        0.666667 |           1.57545  | False        |
| Z_fv_permuted      | True      |   0.03155  |             0.04426  |        0.5      |           0.101652 | False        |
| C0_mle_recal       | False     |   0.031582 |             0.044553 |        0        |           0        | False        |
| A1_mle_fv          | True      |   0.031745 |             0.044674 |        0.166667 |          -0.514002 | True         |
| A2_mle_fv_bucket   | True      |   0.032224 |             0.044938 |        0.166667 |          -2.03287  | True         |
| A3_mle_fv_eta_risk | True      |   0.040279 |             0.054645 |        0.166667 |         -27.5378   | True         |
| Z_cohort_mean      | False     |   0.041119 |             0.057921 |        0        |         -30.1975   | False        |
| D_fv_over_generic  | True      |   0.041207 |             0.057991 |        0        |         -30.4741   | False        |
| Z_sigma_sharp      | True      |   0.041731 |             0.044674 |        0        |         -32.1331   | False        |
| Z_sigma_wide       | True      |   0.133177 |             0.044674 |        0        |        -321.683    | False        |

**Anchors** — each declared with what a violation MEANS, before the run:

| anchor        | kind   | must   |     CRPS | vs defender   |   mean gap (−ve ⇒ anchor better) | folds it won   |   p (anchor systematically better) | SYSTEMATICALLY beat its defender?   |   % rows moved |
|:--------------|:-------|:-------|---------:|:--------------|---------------------------------:|:---------------|-----------------------------------:|:------------------------------------|---------------:|
| Z_fv_permuted | refute | LOSE   | 0.03155  | A1_mle_fv     |                        -0.000194 | 4/6            |                             0.2694 | False                               |            100 |
| Z_cohort_mean | block  | LOSE   | 0.041119 | A1_mle_fv     |                       nan        | None/None      |                           nan      |                                     |            100 |
| Z_sigma_sharp | block  | LOSE   | 0.041731 | A1_mle_fv     |                       nan        | None/None      |                           nan      |                                     |            100 |
| Z_sigma_wide  | block  | LOSE   | 0.133177 | A1_mle_fv     |                       nan        | None/None      |                           nan      |                                     |            100 |

⭐ **Read the PLACEBO row, not just its verdict.** `Z_fv_permuted` is the real FV arm with the grade SHUFFLED within each fold — same marginal, no player-specific content. Here it scores -0.000194 CRPS against the real grade (p=0.269 that it is systematically better). It does not formally violate the anchor, but a scrambled grade landing **indistinguishable from the real one** is itself the corroborating evidence for the null: whatever `A1_mle_fv` is fitting on this population, it is not the per-pitcher grade.

⭐ **`% rows moved` is not decoration.** An anchor that RAN but moved nothing is byte-identical to the arm it defends, so its 'it lost' is a pass on NOTHING — the most dangerous failure because the report looks healthy (NF1.7 (a)). An inert anchor BLOCKS the whole metric.

**Per-FORM peeking floor** (NF-D16 (g‴) — each arm floored by the peeking version of ITS OWN form, because `A1` NESTS `C0` and a single shared ceiling would veto a legitimately-better nested form as a false metric inversion):

| arm                |   arm CRPS |   its own peeking floor | holds (arm ≥ floor)   |
|:-------------------|-----------:|------------------------:|:----------------------|
| L0_mle_served      |   0.031085 |                0.030818 | True                  |
| C0_mle_recal       |   0.031582 |                0.030875 | True                  |
| A1_mle_fv          |   0.031745 |                0.030938 | True                  |
| A2_mle_fv_bucket   |   0.032224 |                0.031408 | True                  |
| A3_mle_fv_eta_risk |   0.040279 |                0.032573 | True                  |
| Z_fv_permuted      |   0.03155  |                0.030786 | True                  |
| Z_cohort_mean      |   0.041119 |                0.040369 | True                  |
| Z_sigma_sharp      |   0.041731 |                0.041145 | True                  |
| Z_sigma_wide       |   0.133177 |                0.133045 | True                  |
| D_fv_over_generic  |   0.041207 |                0.040459 | True                  |

**Is FV uninformative, or informative-but-redundant?** (`D_fv_over_generic` — FV with the MLE column REMOVED — vs `Z_cohort_mean`, the generic prior. ⚠️ A **POST-HOC DIAGNOSTIC, deliberately NOT a trial**: it is excluded from the eligible set, from PBO and from the DSR field, because an arm that exists to POLICE the reading must never set the gate's own bar (MH2.1 (a)).) FV-alone CRPS **0.041207** vs the generic prior **0.041119** ⇒ **FV is NOT informative even on its own** on this population — it does not beat a prior that knows nothing but the cohort mean. The null is not redundancy; the pre-debut grade simply does not predict a debuting starter's realized RATE line.

**Deflation** (NF1.8's four numbers, not PBO alone): PBO(eligible) **0.4** · Bailey degradation (median OOS gap) 0.0% · CONTENDER spread 26.886% · full-field spread 26.886% · DSR(eligible) **0.12716091139758984** (whole-field 5.504136617690036e-131).

↳ The contender spread is 26.886%, WIDE relative to the margin, and the in-sample winners are spread thinly (A1_mle_fv 80% (+0.000%), A2_mle_fv_bucket 15% (+1.511%), A3_mle_fv_eta_risk 5% (+26.886%)) — this is genuine instability, a search that learnt nothing, not a tie (NF1.8).

⚠️ **The whole-field DSR is not a second opinion — it is a measurement of the anchors** (NF-D14). The field deliberately contains `Z_sigma_wide`, which is ~300% away by construction, so the cross-trial Sharpe DISPERSION explodes and the whole-field figure collapses toward zero. The **eligible-set** figure is the one pre-registered to bind. ⚠️ The CONTENDER spread is likewise computed over a 3-arm eligible set that includes `A3_mle_fv_eta_risk`, the deliberately-richest arm — with only three arms the 'top quartile' IS the whole field, so this spread carries the same caveat one instrument over.

**Primary contrast** `C0_mle_recal − A1_mle_fv` per fold (>0 ⇒ the FV arm is better): `[0.000671, -0.001155, -0.000191, -0.000205, -4.1e-05, -5.3e-05]` · one-sided paired p **0.7366834511750033** · BH-FDR survives: **False**

### `k_pct`

Folds (debut cohorts scored): `[2020, 2021, 2022, 2023, 2024, 2025]` · rows scored 233 · rows per fold {2020: 36, 2021: 43, 2022: 32, 2023: 46, 2024: 44, 2025: 32} · FV in this population: mean 43.3, sd 5.13, 8 distinct values

**Leaderboard** (held-out **CRPS**, lower is better; `selectable` marks the declared 3-arm family that is the DSR trial field — foils and anchors are neither):

| arm                | uses_fv   |   oos_crps |   oos_pointscore_mae |   fold_win_rate |   pct_lift_vs_foil | selectable   |
|:-------------------|:----------|-----------:|---------------------:|----------------:|-------------------:|:-------------|
| C0_mle_recal       | False     |   0.023653 |             0.032937 |        0        |           0        | False        |
| L0_mle_served      | False     |   0.023667 |             0.033044 |        0.666667 |          -0.057234 | False        |
| A1_mle_fv          | True      |   0.023701 |             0.033039 |        0.5      |          -0.201298 | True         |
| A2_mle_fv_bucket   | True      |   0.023965 |             0.033535 |        0.333333 |          -1.32092  | True         |
| Z_fv_permuted      | True      |   0.024004 |             0.033469 |        0.5      |          -1.48225  | False        |
| D_fv_over_generic  | True      |   0.02433  |             0.033736 |        0.333333 |          -2.86308  | False        |
| Z_cohort_mean      | False     |   0.024558 |             0.034125 |        0.166667 |          -3.82783  | False        |
| A3_mle_fv_eta_risk | True      |   0.024677 |             0.034685 |        0.333333 |          -4.32797  | True         |
| Z_sigma_sharp      | True      |   0.030968 |             0.033039 |        0        |         -30.9262   | False        |
| Z_sigma_wide       | True      |   0.094128 |             0.033039 |        0        |        -297.956    | False        |

**Anchors** — each declared with what a violation MEANS, before the run:

| anchor        | kind   | must   |     CRPS | vs defender   |   mean gap (−ve ⇒ anchor better) | folds it won   |   p (anchor systematically better) | SYSTEMATICALLY beat its defender?   |   % rows moved |
|:--------------|:-------|:-------|---------:|:--------------|---------------------------------:|:---------------|-----------------------------------:|:------------------------------------|---------------:|
| Z_fv_permuted | refute | LOSE   | 0.024004 | A1_mle_fv     |                         0.000303 | 3/6            |                             0.7519 | False                               |            100 |
| Z_cohort_mean | block  | LOSE   | 0.024558 | A1_mle_fv     |                       nan        | None/None      |                           nan      |                                     |            100 |
| Z_sigma_sharp | block  | LOSE   | 0.030968 | A1_mle_fv     |                       nan        | None/None      |                           nan      |                                     |            100 |
| Z_sigma_wide  | block  | LOSE   | 0.094128 | A1_mle_fv     |                       nan        | None/None      |                           nan      |                                     |            100 |

⭐ **Read the PLACEBO row, not just its verdict.** `Z_fv_permuted` is the real FV arm with the grade SHUFFLED within each fold — same marginal, no player-specific content. Here it scores +0.000303 CRPS against the real grade (p=0.752 that it is systematically better). It does not formally violate the anchor, but a scrambled grade landing **indistinguishable from the real one** is itself the corroborating evidence for the null: whatever `A1_mle_fv` is fitting on this population, it is not the per-pitcher grade.

⭐ **`% rows moved` is not decoration.** An anchor that RAN but moved nothing is byte-identical to the arm it defends, so its 'it lost' is a pass on NOTHING — the most dangerous failure because the report looks healthy (NF1.7 (a)). An inert anchor BLOCKS the whole metric.

**Per-FORM peeking floor** (NF-D16 (g‴) — each arm floored by the peeking version of ITS OWN form, because `A1` NESTS `C0` and a single shared ceiling would veto a legitimately-better nested form as a false metric inversion):

| arm                |   arm CRPS |   its own peeking floor | holds (arm ≥ floor)   |
|:-------------------|-----------:|------------------------:|:----------------------|
| L0_mle_served      |   0.023667 |                0.023096 | True                  |
| C0_mle_recal       |   0.023653 |                0.023027 | True                  |
| A1_mle_fv          |   0.023701 |                0.023116 | True                  |
| A2_mle_fv_bucket   |   0.023965 |                0.023387 | True                  |
| A3_mle_fv_eta_risk |   0.024677 |                0.023658 | True                  |
| Z_fv_permuted      |   0.024004 |                0.023388 | True                  |
| Z_cohort_mean      |   0.024558 |                0.02431  | True                  |
| Z_sigma_sharp      |   0.030968 |                0.030282 | True                  |
| Z_sigma_wide       |   0.094128 |                0.094052 | True                  |
| D_fv_over_generic  |   0.02433  |                0.024176 | True                  |

**Is FV uninformative, or informative-but-redundant?** (`D_fv_over_generic` — FV with the MLE column REMOVED — vs `Z_cohort_mean`, the generic prior. ⚠️ A **POST-HOC DIAGNOSTIC, deliberately NOT a trial**: it is excluded from the eligible set, from PBO and from the DSR field, because an arm that exists to POLICE the reading must never set the gate's own bar (MH2.1 (a)).) FV-alone CRPS **0.024330** vs the generic prior **0.024558** ⇒ **FV IS informative in isolation** — so the null above is a REDUNDANCY finding: the grade carries real information that our own MiLB-MLE translation already contains (a SUBSTITUTE, in E7.8's vocabulary), not a worthless signal.

**Deflation** (NF1.8's four numbers, not PBO alone): PBO(eligible) **0.7** · Bailey degradation (median OOS gap) 0.4934% · CONTENDER spread 4.118% · full-field spread 4.118% · DSR(eligible) **0.2670450365290905** (whole-field 1.0884905481844337e-66).

↳ The contender spread is 4.118%, WIDE relative to the margin, and the in-sample winners are spread thinly (A1_mle_fv 60% (+0.000%), A2_mle_fv_bucket 25% (+1.117%), A3_mle_fv_eta_risk 15% (+4.118%)) — this is genuine instability, a search that learnt nothing, not a tie (NF1.8).

⚠️ **The whole-field DSR is not a second opinion — it is a measurement of the anchors** (NF-D14). The field deliberately contains `Z_sigma_wide`, which is ~300% away by construction, so the cross-trial Sharpe DISPERSION explodes and the whole-field figure collapses toward zero. The **eligible-set** figure is the one pre-registered to bind. ⚠️ The CONTENDER spread is likewise computed over a 3-arm eligible set that includes `A3_mle_fv_eta_risk`, the deliberately-richest arm — with only three arms the 'top quartile' IS the whole field, so this spread carries the same caveat one instrument over.

**Primary contrast** `C0_mle_recal − A1_mle_fv` per fold (>0 ⇒ the FV arm is better): `[-9.7e-05, -0.000144, 0.000287, 0.000689, 8.7e-05, -0.001107]` · one-sided paired p **0.5731314602281802** · BH-FDR survives: **False**

### `bb_pct`

Folds (debut cohorts scored): `[2020, 2021, 2022, 2023, 2024, 2025]` · rows scored 233 · rows per fold {2020: 36, 2021: 43, 2022: 32, 2023: 46, 2024: 44, 2025: 32} · FV in this population: mean 43.3, sd 5.13, 8 distinct values

**Leaderboard** (held-out **CRPS**, lower is better; `selectable` marks the declared 3-arm family that is the DSR trial field — foils and anchors are neither):

| arm                | uses_fv   |   oos_crps |   oos_pointscore_mae |   fold_win_rate |   pct_lift_vs_foil | selectable   |
|:-------------------|:----------|-----------:|---------------------:|----------------:|-------------------:|:-------------|
| A2_mle_fv_bucket   | True      |   0.012912 |             0.017752 |        0.5      |           0.695174 | True         |
| C0_mle_recal       | False     |   0.013003 |             0.018088 |        0        |           0        | False        |
| L0_mle_served      | False     |   0.013005 |             0.018268 |        0.5      |          -0.015729 | False        |
| A1_mle_fv          | True      |   0.013034 |             0.018073 |        0.333333 |          -0.23753  | True         |
| Z_fv_permuted      | True      |   0.013379 |             0.018565 |        0.166667 |          -2.89748  | False        |
| Z_cohort_mean      | False     |   0.014175 |             0.020086 |        0.166667 |          -9.01584  | False        |
| D_fv_over_generic  | True      |   0.014214 |             0.020135 |        0.166667 |          -9.31879  | False        |
| A3_mle_fv_eta_risk | True      |   0.015155 |             0.02101  |        0.166667 |         -16.5515   | True         |
| Z_sigma_sharp      | True      |   0.016943 |             0.018073 |        0        |         -30.3054   | False        |
| Z_sigma_wide       | True      |   0.052456 |             0.018073 |        0        |        -303.427    | False        |

**Anchors** — each declared with what a violation MEANS, before the run:

| anchor        | kind   | must   |     CRPS | vs defender   |   mean gap (−ve ⇒ anchor better) | folds it won   |   p (anchor systematically better) | SYSTEMATICALLY beat its defender?   |   % rows moved |
|:--------------|:-------|:-------|---------:|:--------------|---------------------------------:|:---------------|-----------------------------------:|:------------------------------------|---------------:|
| Z_fv_permuted | refute | LOSE   | 0.013379 | A1_mle_fv     |                         0.000346 | 2/6            |                             0.8675 | False                               |            100 |
| Z_cohort_mean | block  | LOSE   | 0.014175 | A1_mle_fv     |                       nan        | None/None      |                           nan      |                                     |            100 |
| Z_sigma_sharp | block  | LOSE   | 0.016943 | A1_mle_fv     |                       nan        | None/None      |                           nan      |                                     |            100 |
| Z_sigma_wide  | block  | LOSE   | 0.052456 | A1_mle_fv     |                       nan        | None/None      |                           nan      |                                     |            100 |

⭐ **Read the PLACEBO row, not just its verdict.** `Z_fv_permuted` is the real FV arm with the grade SHUFFLED within each fold — same marginal, no player-specific content. Here it scores +0.000346 CRPS against the real grade (p=0.868 that it is systematically better). It does not formally violate the anchor, but a scrambled grade landing **indistinguishable from the real one** is itself the corroborating evidence for the null: whatever `A1_mle_fv` is fitting on this population, it is not the per-pitcher grade.

⭐ **`% rows moved` is not decoration.** An anchor that RAN but moved nothing is byte-identical to the arm it defends, so its 'it lost' is a pass on NOTHING — the most dangerous failure because the report looks healthy (NF1.7 (a)). An inert anchor BLOCKS the whole metric.

**Per-FORM peeking floor** (NF-D16 (g‴) — each arm floored by the peeking version of ITS OWN form, because `A1` NESTS `C0` and a single shared ceiling would veto a legitimately-better nested form as a false metric inversion):

| arm                |   arm CRPS |   its own peeking floor | holds (arm ≥ floor)   |
|:-------------------|-----------:|------------------------:|:----------------------|
| L0_mle_served      |   0.013005 |                0.012245 | True                  |
| C0_mle_recal       |   0.013003 |                0.012359 | True                  |
| A1_mle_fv          |   0.013034 |                0.012382 | True                  |
| A2_mle_fv_bucket   |   0.012912 |                0.012429 | True                  |
| A3_mle_fv_eta_risk |   0.015155 |                0.012752 | True                  |
| Z_fv_permuted      |   0.013379 |                0.012695 | True                  |
| Z_cohort_mean      |   0.014175 |                0.013671 | True                  |
| Z_sigma_sharp      |   0.016943 |                0.016028 | True                  |
| Z_sigma_wide       |   0.052456 |                0.052375 | True                  |
| D_fv_over_generic  |   0.014214 |                0.013682 | True                  |

**Is FV uninformative, or informative-but-redundant?** (`D_fv_over_generic` — FV with the MLE column REMOVED — vs `Z_cohort_mean`, the generic prior. ⚠️ A **POST-HOC DIAGNOSTIC, deliberately NOT a trial**: it is excluded from the eligible set, from PBO and from the DSR field, because an arm that exists to POLICE the reading must never set the gate's own bar (MH2.1 (a)).) FV-alone CRPS **0.014214** vs the generic prior **0.014175** ⇒ **FV is NOT informative even on its own** on this population — it does not beat a prior that knows nothing but the cohort mean. The null is not redundancy; the pre-debut grade simply does not predict a debuting starter's realized RATE line.

**Deflation** (NF1.8's four numbers, not PBO alone): PBO(eligible) **0.6** · Bailey degradation (median OOS gap) 0.6341% · CONTENDER spread 17.367% · full-field spread 17.367% · DSR(eligible) **0.3479593224446911** (whole-field 7.755579120518639e-76).

↳ The contender spread is 17.367%, WIDE relative to the margin, and the in-sample winners are spread thinly (A2_mle_fv_bucket 70% (+0.000%), A1_mle_fv 30% (+0.939%)) — this is genuine instability, a search that learnt nothing, not a tie (NF1.8).

⚠️ **The whole-field DSR is not a second opinion — it is a measurement of the anchors** (NF-D14). The field deliberately contains `Z_sigma_wide`, which is ~300% away by construction, so the cross-trial Sharpe DISPERSION explodes and the whole-field figure collapses toward zero. The **eligible-set** figure is the one pre-registered to bind. ⚠️ The CONTENDER spread is likewise computed over a 3-arm eligible set that includes `A3_mle_fv_eta_risk`, the deliberately-richest arm — with only three arms the 'top quartile' IS the whole field, so this spread carries the same caveat one instrument over.

**Primary contrast** `C0_mle_recal − A1_mle_fv` per fold (>0 ⇒ the FV arm is better): `[-1.7e-05, -0.000131, 1.8e-05, -9e-06, 8e-06, -5.4e-05]` · one-sided paired p **0.8857982623679878** · BH-FDR survives: **False**

## 4. Reading the null against the DESIGN (MH2 — eight states, not two)

At **6 folds** the design itself fixes what could possibly have been detected — reported BEFORE any per-metric reading so the null is read against the design, not the other way round:

- fold-consistency clause: **5 of 6** wins required at α=0.2 (attainable: True). The legacy ≥60% bar would fire on a TRUE LIFT OF ZERO **34.4%** of the time — which is why the calibrated clause is the gate and the rate is only reported.
- one-sided fold-sign floor **0.01562** vs the strictest BH rung **0.0333** → certifiable: **True** (i.e. an effect of some size COULD have passed — the E7.14 'no effect of any size could clear' failure mode is avoided by design, not by luck).
- maximum attainable DSR at 6 folds: **0.9992** against the 0.95 gate.
- pre-registered practically-meaningful effect: a **3%** relative CRPS gain over the matched foil (basis: E7.5p's whole MLE-over-generic gain was −23.0% / −10.4% / −7.6%; set from a prior story's recorded result, before this run).

| metric   | state           |   folds have | folds needed   | extra cohorts   | max field size   | MDE (rel CRPS gain)   | re-test trigger   |
|:---------|:----------------|-------------:|:---------------|:----------------|:-----------------|:----------------------|:------------------|
| gb_pct   | GENUINE_ABSENCE |            6 |                |                 |                  | 2.50%                 |                   |
| k_pct    | GENUINE_ABSENCE |            6 |                |                 |                  | 3.43%                 |                   |
| bb_pct   | GENUINE_ABSENCE |            6 |                |                 |                  | 0.57%                 |                   |

- **gb_pct** — `gb_pct`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.
- **k_pct** — `k_pct`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.
- **bb_pct** — `bb_pct`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.

### 4b. Was the design powered for the effect it was looking for?

`classify_null` stops at `GENUINE_ABSENCE` before it reads the MDE — correctly, because no sample size rescues a negative point estimate. But the MDE is still computed, and it is what separates *"we saw nothing and could not have seen anything"* from *"we saw nothing and would have seen a decision-changing effect"*:

| metric   | observed effect (rel CRPS vs foil)   | MDE at 80% power   | pre-registered meaningful   | powered for it?   |
|:---------|:-------------------------------------|:-------------------|:----------------------------|:------------------|
| gb_pct   | -0.51%                               | 2.50%              | 3%                          | True              |
| k_pct    | -0.20%                               | 3.43%              | 3%                          | False             |
| bb_pct   | -0.24%                               | 0.57%              | 3%                          | True              |

So the null is not merely "nothing showed at this n" for the metrics whose MDE sits BELOW the pre-registered meaningful effect: for those, an FV term worth having would have been visible, and instead the point estimate is NEGATIVE. Where the MDE sits above it, that is stated rather than glossed — the observed sign is still negative there, which is why the state is `GENUINE_ABSENCE` and not `POWER_LIMITED`.

⚠️ **A `GENUINE_ABSENCE` gets NO re-test trigger** — no sample size rescues a negative point estimate. A `DSR_UNREACHABLE` gets a SMALLER-FIELD trigger and never a 'needs N more seasons' one, and per MH2.2 that smaller field is only admissible if it was itself PRE-REGISTERED — you get to pre-register a family, you do not get to discover one. **The declared family here is already the 3 FV forms; it must NOT be trimmed below that.**

## 5. Declared sensitivities

| sensitivity         | metric   |   n_folds |   n_scored | rel gain vs foil   | fold wins   |      p |
|:--------------------|:---------|----------:|-----------:|:-------------------|:------------|-------:|
| all_pitchers        | gb_pct   |         6 |        290 | -0.55%             | 2/6         | 0.768  |
| all_pitchers        | k_pct    |         6 |        290 | -0.46%             | 2/6         | 0.7864 |
| all_pitchers        | bb_pct   |         6 |        290 | -0.20%             | 2/6         | 0.8513 |
| same_season_allowed | gb_pct   |         7 |        314 | -0.94%             | 4/7         | 0.8131 |
| same_season_allowed | k_pct    |         7 |        314 | +0.02%             | 4/7         | 0.4912 |
| same_season_allowed | bb_pct   |         7 |        314 | -0.27%             | 4/7         | 0.7437 |

- **`all_pitchers`** drops the pre-debut start-share filter. A finding present here but absent on starters (or vice-versa) is informative about SCOPE, not a contradiction.
- **`same_season_allowed`** admits the DEBUT-season board. E7.7 serves the RETAINED past board, so a same-season grade can embed a post-debut revision — hindsight that biases TOWARD finding FV lift. It is reported, never the headline. If the looser rule wins and the strict one does not, the honest reading is HINDSIGHT, not signal.
- ⭐ **This is the sensitivity that carries the most weight for a NULL, and it points the same way.** A rule that permits hindsight is the most favourable reading FV can get here — and it still does not produce a positive, fold-consistent effect. A null that survives its own most-favourable variant is a considerably stronger null than one measured only under the strict rule.
- **`--strict-label-window`** (one fewer fold; only cohorts whose FULL 2-season label window has closed) is assembled as a third cohort file. See the amendment in the pre-registration for why the RATE target inverts E7.8's accumulate-horizon ceiling rule.

## 6. Limitations (stated in advance, in the pre-registration)

- **Small-N by construction** — one fold per debut cohort, ~40 rows per fold. This design can honestly rule out a LARGE effect; it cannot resolve a small one. §4 computes the MDE rather than asserting power.
- **Cohort-out, not strictly real-time** — a model tested on cohort *Y* trains on earlier cohorts whose 2-season label windows extend into *Y*. Same posture as E7.3p / E7.5p / E7.8 §5.
- **Pre-2026 as-of is approximate** — FanGraphs serves the RETAINED board (E7.7). Mitigated by the strictly-prior-SEASON rule; the looser rule is a reported sensitivity only.
- **The board is FanGraphs' graded population** (§2).
- **`gb_pct` is a CROSS-DEFINITION map** — MiLB ground-out share GO/(GO+AO) → Statcast GB/BIP, inherited from E7.3p; the regression learned the rescale.
- **Graduated pitchers are self-selected** (they reached the 150-TBF floor). That IS the served population, but it is not a random sample of call-ups. Stated, not corrected — from E7.3p.
- **`best_alpha = 0`** — a cold-start calibration prior, never a market bet.

