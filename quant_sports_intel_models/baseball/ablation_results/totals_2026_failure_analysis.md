# Totals — 2026 OOS Failure Analysis (post-10.6 investigation)

Context: 10.6 found challenger Brier 0.3091 / champion 0.3129 vs **market 0.2281** and naive 0.25 on 2026 — yet the challenger beat the market by +0.024 on 2023–25. A ~0.10 sign-change in one season ⇒ structural. This diagnoses fixable-vs-architectural.

## 1. Brier by month (2026) vs 2023–25 baseline
| month            |    n |   challenger_brier |   champion_brier |   actual_over_rate |
|:-----------------|-----:|-------------------:|-----------------:|-------------------:|
| 2026-04          |  209 |             0.2665 |           0.2464 |             0.5646 |
| 2026-05          |  388 |             0.3297 |           0.3477 |             0.3866 |
| 2026-06          |    9 |             0.2500 |           0.3761 |             0.6667 |
| 2023-25 baseline | 4678 |             0.2231 |         nan      |             0.4681 |
- Reference: market 0.2281, naive 0.25. Lower is better; >0.25 = worse than a coin flip.

## 2. Brier by signal coverage
| window   | coverage      |    n |   challenger_brier |
|:---------|:--------------|-----:|-------------------:|
| 2026     | coverage>=0.8 |  605 |             0.3072 |
| 2026     | coverage<0.8  |    1 |             0.0005 |
| 2023-25  | coverage>=0.8 | 4672 |             0.2231 |
| 2023-25  | coverage<0.8  |    6 |             0.2323 |

## 3. Layer 3 feature distribution shift (2026 vs 2021–25 training)
Standardized shift = (mean_2026 − mean_train)/std_train. |shift|≥0.5σ flagged. Top 15:
| feature                                  |   train_mean |   y2026_mean |   std_shift |
|:-----------------------------------------|-------------:|-------------:|------------:|
| home_matchup_advantage_mu_v1_uncertainty |        0.023 |        0.031 |       1.945 |
| home_matchup_advantage_sigma_v1          |        0.009 |        0.012 |       1.945 |
| away_matchup_advantage_sigma_v1          |        0.009 |        0.012 |       1.911 |
| away_matchup_advantage_mu_v1_uncertainty |        0.023 |        0.031 |       1.911 |
| away_matchup_advantage_mu_v1             |        0.000 |        0.006 |       1.006 |
| home_matchup_advantage_mu_v1             |        0.000 |        0.006 |       0.997 |
| home_bullpen_uncertainty_v2              |        5.009 |        5.407 |       0.253 |
| home_bullpen_mu_v2                       |        2.072 |        2.257 |       0.248 |
| away_bullpen_uncertainty_v2              |        4.967 |        5.329 |       0.239 |
| away_bullpen_mu_v2                       |        2.054 |        2.221 |       0.233 |
| run_env_mu_v4                            |        8.994 |        8.831 |      -0.233 |
| run_env_mu_v4_uncertainty                |       11.127 |       10.993 |      -0.166 |
| away_starter_suppression_sigma_v1        |        0.089 |        0.090 |       0.100 |
| away_starter_uncertainty_v1              |        0.228 |        0.230 |       0.100 |
| home_starter_suppression_sigma_v1        |        0.089 |        0.090 |       0.096 |

## 4. High-confidence bin [0.80,1.00] breakdown (2026)
- 82 games; mean predicted P(over) 0.895, actual over-rate 0.378.
| home_team   |   n |   actual_over_rate |   mean_pred |
|:------------|----:|-------------------:|------------:|
| DET         |   5 |              0.200 |       0.928 |
| PIT         |   5 |              0.600 |       0.910 |
| ATL         |   4 |              0.500 |       0.945 |
| MIN         |   4 |              0.500 |       0.860 |
| BAL         |   4 |              0.250 |       0.857 |
| BOS         |   4 |              0.000 |       0.894 |
| CHC         |   4 |              0.250 |       0.907 |
| TB          |   4 |              0.250 |       0.884 |
| SD          |   4 |              0.000 |       0.848 |
| KC          |   4 |              0.250 |       0.892 |
| NYY         |   4 |              0.750 |       0.948 |
| MIA         |   4 |              0.250 |       0.971 |

## 5. Go / No-Go recommendation
- **Cold-start signal:** challenger Brier 2026-04 0.2665 → 2026-06 0.2500 — **does not materially improve** (not a simple cold-start).
- **Coverage:** Brier(<0.8) − Brier(>=0.8) = -0.3067 — coverage is NOT the main driver.
- **Feature shift:** 6 signal(s) shifted ≥0.5σ from training in 2026 (top: home_matchup_advantage_mu_v1_uncertainty +1.94σ) — distribution shift / freshness is a plausible root cause (FIXABLE).
- **High-confidence failure:** 82 games with p_over≥0.80 predicted 0.895 but hit 0.378 — the calibration break is concentrated in over-confident OVER bets.

**Decision:** if the drivers above are early-season cold-start, low coverage, or feature freshness, the 2026 failure is FIXABLE within the current architecture → proceed to 10.7 shadow once addressed. If features are in-distribution, coverage is balanced, and the damage does not concentrate/recover, the failure is more fundamental → revisit architecture (Phase 9) before building pipeline.

## 6. Root cause + deployable-posterior check (decisive)

Cold-start, coverage, and feature-freshness are all REJECTED as the primary driver
(coverage has no 2026 variation — 605 games ≥0.8 vs 1 below; the big feature shifts are
tiny-magnitude matchup signals; Brier does not recover April→June). The real driver is in
**Section 1 + the directional check below:**

- **A within-2026 run-scoring REGIME SHIFT.** Over-rate: **April 56.5% → May 38.7%** (vs
  46.8% on 2023–25). The model carries a training-era OVER lean; April rewarded it, May's
  low-scoring regime crushed it (the 82 high-confidence OVER bets hit 37.8%).
- **Persistent OVER bias vs a correctly-priced market.** mean P(over): raw model **0.522**,
  blended **0.507**, market **0.458**, **actual 0.449**. Bovada tracked the under-leaning
  2026 environment; the market-blind model did not.
- **The deployable (alpha=0.70 blended) posterior still loses:** 2026 Brier
  raw 0.3087 → **blended 0.2781** — better, but STILL worse than naive 0.2500 and far from
  market 0.2279. The 30% Bovada component tempers but does not fix the bias.
- **⚠️ This is NOT challenger-specific: champion v4 is ALSO worse than naive on 2026 (0.3129).**
  BOTH totals models are below break-even on the live season — totals betting as a capability
  is not currently profitable, independent of the champion-vs-challenger question.

**Verdict: the 2026 failure is a directional-bias / regime-adaptation problem, NOT a trivial
cold-start/coverage/freshness fix and NOT (yet) proven architectural.** The market-blind model
under-tracks a real within-season scoring shift the market prices correctly. Recommended next
step is a **targeted de-bias / recency-aware recalibration** (not a full rearchitecture), re-
evaluated on 2026 — and totals promotion (either model) stays paused until a model beats naive
on the current season. ~600 games over 2 May-heavy months means some instability, but the
signal (both models < naive even after blending) is consistent and real.

## 7. Decision gate result — matchup-drop ablation (CONCLUSIVE)

To separate the two competing explanations (7.M cluster-mismatch vs. regime-adaptation), the
8 `matchup_advantage` signals were dropped and the model re-run walk-forward (`totals_v2_nomatchup`,
36 features, same hyperparameters). Binary gate: does the alpha-blended 2026 Brier beat naive?

| 2026 (593 Bovada-settled) | v1 (with matchup) | v2 (matchup dropped) |
|---|---:|---:|
| blended Brier (α=0.70) | 0.2781 | **0.2773** |
| raw Brier | 0.3087 | 0.3079 |
| mean P(over) | 0.507 | 0.505 |
| market / actual P(over) | 0.458 / 0.449 | 0.458 / 0.449 |

**GATE: FAIL — blended Brier 0.2773 ≥ naive 0.2500 (Δ vs v1: −0.0008, negligible).** Dropping the
matchup signals changed almost nothing; the +1.9σ matchup "shift" was a tiny-magnitude red herring.
**The 7.M cluster-mismatch is ruled out. Regime-adaptation is confirmed as the complete story:** the
market-blind model carries a persistent OVER bias (0.505 vs actual 0.449) that the 30% Bovada blend
cannot overcome, and neither totals model beats naive or the market on 2026.

**DECISION (2026-06-02): pause totals.** Do not promote either model; set `totals_paused = true` on
the bet permission gate; redirect to Epic 11 (H2H). Revisit totals with full-season data or a
recency-aware / market-anchored redesign — not before.
