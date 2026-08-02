# MH2.1 — conditional calibration: does the homoscedastic winner lose per-game variance?

> # 🔴 CORRECTION (2026-08-02) — THIS REPORT'S VERDICT IS RETRACTED. DO NOT CITE ITS FIGURES.
>
> The champion swap this report cleared was promoted and **rolled back the same day**. The finding
> below did not reproduce on the served population and **reversed in every window measurable**
> — see **`mh2_1_rollback.md`**, which supersedes this document.
>
> **The defect: the stratifier was never validated.** Everything below is computed over deciles of
> `plus_eb::ngboost_normal`'s predicted σ (the arm this report itself scores *worst*, 0.180), and
> nothing here asks whether those strata **separate realized dispersion**. The controls that are
> present — the σ-CV floor (0.0798 vs 0.02), the matched heteroscedastic foil, the flattened
> positive control, the 400-permutation null — all ask *"does σ vary, and can the instrument detect
> a known defect?"*, which is a different question. Re-run against a stratifier that demonstrably
> does separate realized dispersion (the served v6's own σ: realized SD 3.671 → 4.973 across
> deciles, +35%, ρ ≈ 0.66), the ordering flips: RMS |Var(z)−1| **0.2275 for the served NGBoost vs
> 0.2519 for the homoscedastic leader** on 459 games held out from the NGBoost's fit.
>
> ⭐ **A conditional-calibration result is a property of its stratifier.** A stratifier that does not
> demonstrably separate realized dispersion measures nothing, and this metric computed over it can
> be silently inverted — the E2.1-r inversion class raised one level, from the metric to the
> partition the metric is computed over.
>
> **Specifically retracted:** the verdict `INCUMBENT_VARIANCE_UNINFORMATIVE`; the RMS figures
> 0.0498 / 0.1582 / 0.1796 / 0.1069; "the incumbent's per-game σ is actively MISCALIBRATED"; "Var(z)
> 1.44 in the calmest decile"; and "on this evidence it is a calibration IMPROVEMENT."
>
> **Not retracted:** the *methodological* section below on why CRPS and PIT-KS cannot answer this
> (both are structurally blind to a homoscedastic model losing per-game variance) — that reasoning
> stands and is why the question was worth asking. Nor is the finding that a max−min-of-per-stratum
> statistic is noise-dominated. The MH2.1 CRPS bake-off result is likewise untouched.
>
> Retained below **verbatim, unedited**, as the record of what was measured and believed.

> ⚠️ **Not an edge claim.** `best_alpha = 0`. A calibration diagnostic; it says nothing about win rate, edge or ROI.

> 💸 **Snowflake-free and network-free** — reads only the local training-matrix parquet MH2.1's bake-off already cached, and HALTs rather than pulling if it is absent.

**VERDICT: `INCUMBENT_VARIANCE_UNINFORMATIVE`**

⭐ **THE VARIANCE OBJECTION IS REFUTED AT ITS SOURCE — and note this REVERSES the concern this script was built to test.** Deliberately FLATTENING the heteroscedastic arm's own per-game σ did not worsen its conditional calibration; it **improved** it (RMS |Var(z)−1| 0.1796 → 0.1069). So that per-game σ is not merely uninformative, it is actively MISCALIBRATED, and there is nothing for a homoscedastic arm to destroy.

Directly: the MH2.1 leader is **3.2× BETTER conditionally calibrated than the SERVED champion** (RMS |Var(z)−1| **0.0498** vs **0.1582**), with pooled Var(z) essentially perfect. The incumbent under-estimates σ worst in the games it calls calm. **The homoscedastic swap cannot be blocked on variance grounds — on this evidence it is a calibration IMPROVEMENT.**

- Window 2016–2026 · 8 purged folds · 21,006 rows · nominal central interval 80%
- Stratifier: **plus_eb::ngboost_normal predicted sigma (deciles)** · σ coefficient of variation **0.0798** · 400 permutations

## Why CRPS and PIT-KS could not answer this

CRPS is dominated by the MEAN, and PIT-KS is a **MARGINAL** statistic — a homoscedastic model that over-covers calm games by as much as it under-covers volatile ones has a **flat pooled PIT** and a clean PIT-KS while being badly miscalibrated CONDITIONALLY. The errors cancel in the pooled histogram. Stratifying by predicted volatility stops them cancelling.

## The statistic, and why it is a SLOPE and not a RANGE

For a conditionally-calibrated model the standardised residual `z = (y − μ)/σ` has **Var(z) = 1 in every stratum**. A homoscedastic arm divides by a constant, so Var(z) sits below 1 where the true spread is small and above 1 where it is large — a graded signal across σ-deciles, summarised by the OLS **slope** of Var(z) on the stratum index.

⚠️ **The first cut of this script used `max − min` of per-stratum coverage and it did not work.** That range is noise-dominated and its expectation GROWS with the number of strata: at ~320 rows per decile a *perfectly* calibrated model posts an expected max−min of **0.069** (p95 0.100), which swallowed every real signal and made the instrument read blind. A range over k noisy estimates measures k and n, not miscalibration. The slope pools every stratum, has a null centred at zero, and is tested here by **permuting the stratum labels** — which destroys the σ↔Var(z) relationship while preserving each arm's marginal z-distribution and each stratum's size, giving an exact null with no distributional assumption.

## Var(z) by predicted-σ decile — 1.000 everywhere is perfect

| σ decile | mean σ | n | `incumbent::ngboost_normal` | `plus_eb::ngboost_normal` | `plus_eb::glm_elasticnet` | `plus_eb::ngboost_FLATTENED` |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 3.891 | 1,465 | 1.369 | 1.442 | 0.970 | 1.076 |
| 1 | 4.083 | 1,465 | 1.233 | 1.271 | 1.001 | 1.108 |
| 2 | 4.166 | 1,465 | 1.065 | 1.076 | 0.905 | 0.984 |
| 3 | 4.231 | 1,464 | 1.127 | 1.139 | 0.992 | 1.079 |
| 4 | 4.277 | 1,465 | 1.102 | 1.108 | 0.990 | 1.081 |
| 5 | 4.317 | 1,465 | 1.035 | 1.031 | 0.951 | 1.028 |
| 6 | 4.378 | 1,464 | 1.104 | 1.104 | 1.042 | 1.136 |
| 7 | 4.423 | 1,465 | 1.065 | 1.018 | 1.010 | 1.085 |
| 8 | 4.526 | 1,465 | 1.029 | 0.974 | 1.008 | 1.091 |
| 9 | 4.659 | 1,465 | 1.108 | 0.938 | 1.102 | 1.221 |

| statistic | `incumbent::ngboost_normal` | `plus_eb::ngboost_normal` | `plus_eb::glm_elasticnet` | `plus_eb::ngboost_FLATTENED` |
|---|---:|---:|---:|---:|
| **Var(z) slope per decile** | -0.02373 | -0.04297 | +0.01133 | +0.01093 |
| pooled Var(z) | 1.1242 | 1.1109 | 0.9972 | 1.0900 |
| pooled coverage | 0.7875 | 0.7898 | 0.8166 | 0.7931 |
| pooled PIT-KS (the blind one) | 0.0562 | 0.0588 | 0.0521 | 0.0583 |
| pooled CRPS | 2.5203 | 2.5068 | 2.4908 | 2.5053 |

### ⚠️ The anchors — read these BEFORE the leader's numbers

- **NEGATIVE CONTROL / MATCHED FOIL** `plus_eb::ngboost_normal` (same features as the leader, heteroscedastic) is the baseline; every slope below is stated as a DIFFERENCE from it (its own slope: -0.04297).
- **POSITIVE CONTROL** `plus_eb::ngboost_FLATTENED` — the foil's own means with its per-game σ replaced by a constant of the SAME average variance, so it differs in exactly one respect: whether σ moves game to game. Slope vs foil **+0.05390**, z = **51.66**, p = 0.0025.
- Instrument detects the defect: **True** — if this were False, nothing in this report could be concluded (NF1.7 (a): a check that cannot fail is not a check).
- σ coefficient of variation **0.0798** (floor 0.02) — if σ is effectively constant there is no per-game variance to lose and the whole question is moot (NF1.9).
- **MH2.1 LEADER** `plus_eb::glm_elasticnet` (homoscedastic): slope vs foil **+0.05430**, z = **39.04**, p = 0.0025, i.e. **101%** of the full flattening penalty.

Because the foil shares the leader's FEATURES and differs only in its variance model, any gap between them is attributable to the variance model rather than to the `plus_eb` block (NF-D15 g′).

## Secondary stratification — by predicted-mean decile

| statistic | `incumbent::ngboost_normal` | `plus_eb::ngboost_normal` | `plus_eb::glm_elasticnet` | `plus_eb::ngboost_FLATTENED` |
|---|---:|---:|---:|---:|
| Var(z) slope | +0.01303 | +0.00902 | +0.02966 | +0.03357 |
| pooled coverage | 0.7875 | 0.7898 | 0.8166 | 0.7931 |

## Secondary stratification — by park tercile

| statistic | `incumbent::ngboost_normal` | `plus_eb::ngboost_normal` | `plus_eb::glm_elasticnet` | `plus_eb::ngboost_FLATTENED` |
|---|---:|---:|---:|---:|
| Var(z) slope | +0.02777 | +0.02907 | +0.07615 | +0.08453 |
| pooled coverage | 0.7875 | 0.7898 | 0.8166 | 0.7931 |

