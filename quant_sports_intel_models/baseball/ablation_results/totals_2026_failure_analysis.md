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

## 8. Recency-adaptation diagnostic — FAIL (4th independent confirmation, 2026-06-04)

After Epic 16 (sequential posteriors) completed, we re-opened the question raised in §6/§7: could the
sequential/recency architecture **rescue** Layer 3 totals by making the run-environment signal
regime-adaptive (so it tracks the within-2026 down-shift the static model missed)? Run as a **diagnostic
with a pre-committed kill criterion**, no build work permitted until the criterion was assessed.

**Pre-committed kill criterion (locked before any code):** PASS only if some recency scheme — trailing-N
games (N∈{5,10,15,20}) or EW decay (λ∈{0.85,0.90,0.95}) — reliably pulls the run-env estimate **below
8.80 by ~game-20 of May 2026 while the static training-era signal stays above 9.00**. If every scheme is
still ≥8.80 at that point, FAIL → close Epic 10, pivot to Epic 17.

**Method:** MCP analytical check on existing data only (no retrain). `baseball_data.betting.mart_game_results`
(actual total = home+away final score) ⋈ `baseball_data.betting_features.feature_pregame_sub_model_signals`
(`run_env_mu_v4`), 2026 regular season. Computed league-wide trailing-N and EW recency means of actual total
runs through the season; sampled at May 10 / 20 / 30.

**Ground truth (2026):** monthly actual mean total — Mar 8.62 / **Apr 9.09** / **May 8.61** / Jun 9.54.
Static `run_env_mu_v4` mean — Mar 8.69 / **Apr 8.66** / **May 8.88** / Jun 9.02. (Corroborates §3: run_env
2026 mean 8.83, −0.23σ vs train 8.99 — the signal tracked *down*, it was never the high component.)

**Recency estimates as of start of checkpoint day** (May truth = 8.61; ±0.3 band [8.31, 8.91]):

| Estimate | May 10 | May 20 (decision) | May 30 |
|---|---:|---:|---:|
| Trailing-5  | 5.80 | 8.00 | 9.80 |
| Trailing-10 | 5.40 | 8.40 | 9.80 |
| Trailing-15 | 5.80 | 9.80 | 9.60 |
| Trailing-20 | 7.15 | 9.25 | 10.30 |
| EW λ=0.85 | 6.94 | 9.05 | 9.99 |
| EW λ=0.90 | 7.48 | 9.27 | 9.90 |
| EW λ=0.95 | 8.05 | 9.48 | 9.52 |
| Static run_env (recent mean) | 9.04 | 9.04 | 9.21 |

**KILL-CRITERION RESULT: FAIL.** Three independent grounds:

1. **Premise falsified — run_env is not the over-predicting component.** `run_env_mu_v4` averages 8.66
   (Apr) / 8.88 (May), already near truth and below 9.00 monthly. The "9.06 over-prediction" was the
   **combiner** μ̄ (run_env + offense + bullpen via LTV), not run_env. A sequential/recency run_env cannot
   fix a totals over-prediction it does not cause.
2. **The schemes that momentarily read <8.80 at May 20 (trail-5 8.00, trail-10 8.40) are noise, not
   tracking** — those same schemes read 5.40–5.80 on May 10 (3+ runs low) and 9.80 on May 30 (1.2 high).
   They cross *through* the truth; they do not track it. All longer/EW schemes are 9.0–9.5 at May 20.
3. **The regime move is below the noise floor.** April→May shift = **0.48 runs**; short-window recency
   swings **4+ runs** across two-week spans and weekly actual spans 8.05–9.60 (1.55). No window length
   filters the noise while preserving a 0.48-run signal — long windows reproduce the static seasonal mean
   (no adaptation), short windows are pure noise. The market wins by being a far lower-variance estimator,
   not by adapting faster. (Robust to the "game-20" interpretation: if it meant the 20th game of May ≈ May 1,
   the windows are full of high late-April games → even more clearly >8.80.)

**DECISION (2026-06-04): Epic 10 formally CLOSED.** This is the **fourth** independent confirmation that the
totals architecture cannot out-adapt the market on within-season regime (after: §6 regime-bias root cause,
§7 matchup-drop ablation, and the leakage-free combiner re-eval). Sequential/recency patching of the static
combiner is rejected — the regime-adaptation problem requires a fundamentally different inference approach.
Effort moves to **Epic 17 (PyMC hierarchical / full-Bayesian layer)** as the next architectural investment
for totals. Diagnostic recorded as Story 10.8 in `implementation_guide.md`.

## 9. Sequential sub-model enrichment — HOLD / no change (Epic 16B gate, 2026-06-04)

Epic 16B retrained the three Layer 3 sub-models (offense_v2 run_diff, bullpen_v2, starter_v1 + starter_ip_v1)
against sequential/Empirical-Bayes features (Epic 16) to test whether per-team recency signals close the +0.40
mean bias reported in §8. Gate criterion: **mean combined-μ ≤ 8.85 on May-2026 → PASS (proceed to full Layer 3
re-eval, 16B.6); > 8.85 → FAIL → Epic 17 confirmed.**

**Retrain verdicts (all HOLD NONSEQ):**

| Sub-model | Target | Sequential gate | Verdict |
|---|---|---|---|
| offense_v2 | run_diff | seq NLL did not beat nonseq | HOLD |
| bullpen_v2 | both sub-models | seq NLL did not beat nonseq | HOLD |
| starter_v1 | xwoba_against | seq NLL Δ = −0.0005 (worse) | HOLD |
| starter_ip_v1 | outs_recorded | seq NLL Δ = −0.0013 (worse) | HOLD |

All canonical `.pkl` models remain at their non-sequential versions. Stacking weights recomputed from
the unchanged signals (total_runs: bullpen 0.337 / offense 0.332 / run_env 0.331 — near-equal thirds).

**16B.5 gate result (diagnose_16b5_gate.py, in-sample Poisson GLM, May-2026, 419 games):**

| Metric | Value |
|---|---:|
| mean combined-μ | **9.0135** |
| mean actual | 8.6086 |
| mean bias | +0.4049 |
| Gate (≤ 8.85) | **FAIL** |

Per-signal GLM-predicted means (May-2026): bullpen 9.30 / offense 8.88 / run_env 8.86.
All-2026 mean combined-μ: 9.0065 (actual 8.9384).

**DECISION (2026-06-04): Epic 16B → HOLD on all sub-models. 16B.6 skipped. Epic 17 confirmed.**
The sequential posteriors (EB anchored + chained) add noise at the margin; no sub-model's sequential
challenger cleared its NLL gate, so the Layer 3 signal set is unchanged from pre-16B. The +0.40
mean bias on May-2026 is intact, confirming this is the **fifth** independent measurement showing the
combiner overestimates scoring relative to what materialised. Epic 17 (PyMC hierarchical / full-Bayesian
layer) is the designated next step.

## 10. Epic 17 PyMC hierarchical NegBin — CLOSED (7th independent confirmation, 2026-06-05)

Epic 17 was the final architectural investment for totals within the log-link Negative Binomial framework:
a PyMC 5 hierarchical model with per-team run-scoring effects, 5-season hierarchy, and NUTS full inference.
Three NUTS variants were evaluated with a pre-committed kill criterion of **May-2026 PPM ≤ 8.81**.

### NUTS run history

| Run | Description | May-2026 PPM | Bias | Result |
|---|---|---:|---:|---|
| v1 (Candidate B signals, in-sample) | Baseline NUTS, mart_sub_model_signals bullpen (2021-2026, mean~2.35) | 8.8607 | +0.177 | FAIL (−0.051 miss) |
| v2 (Candidate A signals, OOS) | Walk-forward OOS bullpen (2021-2025 train, 2026 eval, mean~1.56) | 9.3023 | +0.618 | FAIL |
| v3 (Jensen correction + rolling regressor) | Analytical Jensen offset -β²σ²/2 on all signals; rolling_league_runs_14d regressor | **9.2819** | +0.598 | **FAIL** |

**Note:** v2 vs v1 difference explained separately — v1 used Candidate B (in-sample for 2026, artificially low bullpen z-scores) which by chance partially offset the Jensen floor. OOS Candidate A signals restored the true bullpen z-score distribution and revealed the structural bias.

### Root cause decomposition (v3 final run)

| Component | PPM contribution | Analysis |
|---|---:|---|
| Structural Jensen floor (β_bullpen=0.172, σ_z≈1.0) | +0.170 | E[exp(β·z)] > exp(β·μ) at β=0.172; irreducible without correction |
| True 2026 bullpen signal elevation (z_bullpen_may=+0.22) | +0.343 | Real shift vs 2022-2025 training mean; not contamination |
| Jensen correction applied (v3) | −0.020 | Reduction small due to model recalibrating mu_log_league upward |
| Rolling league runs (beta_rolling≈0) | ~0 | Within-season regime shift not learnable at current signal-to-noise |
| delta_2026 (HDI [-0.097, +0.095]) | ~0 | Consistent with zero; model cannot distinguish 2026 from training |

**Architectural verdict:** The structural Jensen floor at β_bullpen=0.172 places the NegBin log-link predictor at baseline + 0.170 = 8.87 > 8.81 threshold before any signal contribution. This is irreducible within the log-link architecture at this β. The Jensen correction (v3) analytically removes the floor, but the beta posterior remains at 0.172 so the model re-learns an equivalent shift through other parameters (mu_log_league increased 0.017 log-units after the correction). The 2026 bullpen elevation (+0.343) is a real OOS signal, not contamination — beta_rolling=0.0045 (95% HDI entirely overlapping zero) confirms the model has no way to counteract it.

### Key v3 diagnostics

- **Convergences:** 2 divergences (threshold < 160) — PASS; R-hat ≤ 1.0 — PASS; ESS_bulk ≥ 1602 — PASS
- **beta_bullpen:** 0.172 [0.163, 0.182] P(correct)=1.00
- **beta_rolling:** 0.0045 [−0.006, +0.015] P(correct)=0.79 WARN — posterior indistinguishable from zero
- **rolling_z_may:** −0.508 (May-2026 scoring was below training mean) — signal directionally correct but β≈0
- **delta_2026:** −0.0012 (HDI: [−0.097, +0.095]) — season intercept consistent with zero; 2026 in-distribution

### Formal closure

**DECISION (2026-06-05): Epic 17 totals formally CLOSED.** This is the **seventh** independent confirmation
that the totals architecture cannot beat the May-2026 scoring regime with available signals:

1. §6 — regime-bias root cause (OVER bias vs correctly-priced market)
2. §7 — matchup-drop ablation (regime confirmed, cluster-mismatch ruled out)
3. §8 — recency-adaptation diagnostic (4th: sequential run_env below noise floor)
4. §9 — Epic 16B sequential sub-model enrichment gate (5th: combined-μ=9.01, +0.40 bias unchanged)
5. Epic 11 H2H diagnostic — no edge vs 2026 Bovada market (parallel closure)
6. Layer 3 leakage-fix re-eval (6th: leakage fixed but no edge; 2024-25 market degraded)
7. **Epic 17 NUTS v3 Jensen+rolling (7th: PPM=9.2819, β_rolling≈0)**

### Re-open criteria (formally registered)

The totals architecture may be re-opened under either condition:

**(a) Full 2026 season data for honest delta_2026.** March-April calibration (866 rows) cannot capture the
May scoring dip. With a complete season, delta_2026 would be estimated from 5,000+ rows and could absorb
the structural regime shift. The HDI would narrow from ±0.10 to ±0.02–0.03, potentially pulling May PPM
below 8.81 even without architectural changes. Re-evaluate after October 2026.

**(b) Sub-model signals capturing within-season scoring regime shifts.** rolling_league_runs_14d
(beta=0.0045, P(correct)=0.79) is not informative — the 14-day window is too noisy at MLB game-to-game
variance. Signals needed: lagged actual league run rate with tighter smoothing (e.g., ELO-style decay on
per-team run environment), or direct market-anchored run-environment signal. Current sub-model signals
(bullpen_v2, offense_v2, starter_v1, run_env_v4) are all game-level predictors of team quality, not
within-season scoring-environment trackers. A new signal type — not a new model architecture — is the
unblocking condition.
