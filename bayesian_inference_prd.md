# PRODUCT REQUIREMENTS DOCUMENT (PRD)
## Product: Diamond Edge — Bayesian Inference Upgrade

---

## 1. Overview

### Summary

Enhance the existing Diamond Edge MLB betting system with:

- Bayesian probability updating
- Uncertainty-aware modeling
- Distribution-based totals modeling
- Meta-model edge detection

This phase transforms the system from a "predictive ML model" into a **probabilistic decision engine** competing with market pricing.

### Context (Current State)

| Component | Status |
|---|---|
| Feature store | Complete (Phase 2) |
| ML models (XGBoost / NGBoost) | Complete (Phase 4) |
| Calibration (Platt scaling) | Complete (Card 7.C) |
| Betting layer (EV + Kelly) | Complete (Phase 6) |
| App + evaluation | Complete (Phase 6) |

**Key issue:** Mean edge is negative (~−0.017 to −0.036). The model is not outperforming the market.

### Goal

Improve edge generation by modeling:

- Posterior probabilities (not raw predictions)
- Uncertainty + variance
- Market-relative mispricing

---

## 2. Problem Statement

### Core Problem

The current system produces calibrated probabilities but does not explicitly model:

- Uncertainty
- Variance
- Bayesian belief updates

**Result:** Model competes directly with market. Market wins (efficient baseline — market Brier 0.2395 vs. model Brier 0.2423).

### Opportunity

Exploit inefficiencies in:

- Uncertainty (rookies, early season, debut starters)
- Bullpen state
- Run distribution (totals)
- Incomplete market updates

---

## 3. Scope

### In Scope

- Bayesian probability layer (market as prior)
- Uncertainty modeling + propagation
- Distribution modeling (totals)
- Bullpen posterior strength modeling
- Meta-model for +EV detection
- Feature-level stabilization weights

### Out of Scope

- Live betting
- Player props
- UI redesign
- Data mart rebuild

---

## 4. Architecture Changes (Delta Only)

### Current Pipeline

```
Features → ML Model → Calibration → Edge → Kelly → Output
```

### Updated Pipeline

```
Features → ML Model → Calibration → Bayesian Layer →
Distribution Modeling → Meta-Model → Bet Sizing → Output
```

---

## 5. Functional Requirements

### 5.1 Bayesian Probability Layer

**Objective:** Convert model + market into posterior probability.

**Inputs:**
- `calibrated_win_prob`
- `market_implied_prob`

**Logic:**
```
posterior_prob = w * model_prob + (1 - w) * market_prob
```

Where `w` = confidence weight (dynamic).

**Enhancements — weight depends on:**
- Sample size
- Feature stability
- Regime

**Outputs:**
- `posterior_win_prob`
- `posterior_total_prob`

---

### 5.2 Uncertainty Modeling

**Objective:** Quantify and propagate uncertainty.

**Player-Level:**
- `sample_size`
- `stabilization_weight`
- `player_variance`

**Game-Level:**
- `lineup_uncertainty_score`
- `pitcher_uncertainty_score`
- `game_uncertainty_score`

**Requirements:** Propagate uncertainty into posterior probabilities and bet sizing.

---

### 5.3 Distribution Modeling (Totals)

**Objective:** Model full run distribution (not just mean).

**Inputs:**
- Predicted total runs (mean)
- Feature-driven variance

**Outputs:**
- `expected_runs`
- `total_variance`
- `prob_over_X`
- `prob_under_X`

**Methods:**
- Normal approximation (MVP)
- Future: Poisson / Negative Binomial

---

### 5.4 Bullpen Posterior Model

**Objective:** Estimate real-time bullpen strength.

**Inputs:**
- Baseline bullpen stats
- Recent workload
- Leverage usage

**Outputs:**
- `bp_posterior_strength`
- `bp_fatigue_adjustment`

**Requirement:** Must affect totals distribution and win probability.

---

### 5.5 Feature Stabilization Layer

**Objective:** Handle small samples correctly.

**Logic:**
```
stabilized_feature = w * current + (1 - w) * prior
Where: w = n / (n + k)
```

**Requirements:** Per-feature stabilization constants with different `k` for K%, wOBA, ISO.

---

### 5.6 Meta-Model (EV Detection)

**Objective:** Predict probability of profitable bet.

**Inputs:**
- Posterior probabilities
- Market probabilities
- Uncertainty metrics
- Line movement features

**Output:** `p_positive_ev`

**Decision Rule:** Bet only if `p_positive_ev > threshold`.

---

### 5.7 Bet Sizing Enhancements

**Objective:** Incorporate uncertainty into sizing.

**Inputs:**
- Edge
- Uncertainty
- Calibration confidence

**Logic:** Reduce size when high variance or low confidence.

**Output:** `adjusted_kelly_fraction`

---

## 6. Success Metrics

### Model Metrics

- Brier score ↓
- ECE ↓
- Log loss ↓

### Betting Metrics

- Mean edge > 0
- ROI > 0
- Sharpe ratio ↑

### Target Benchmarks

- Beat market baseline Brier (~0.2395)
- Positive mean edge > +0.01

---

## 7. Design Principles

1. **Market is baseline truth** — do not ignore it, update it
2. **Model distributions, not points** — totals especially
3. **Uncertainty drives sizing** — not just edge
4. **Selectivity over volume** — fewer, higher-confidence bets

---

## 8. Implementation Roadmap

| Phase | Focus | Description |
|---|---|---|
| **Bayesian Overlay** | Fast Win | Posterior probability blending; dynamic weighting |
| **Uncertainty Layer** | Stabilization | Stabilization weights; n_eff features; uncertainty propagation |
| **Distribution Modeling** | Totals | Totals variance; probability of over/under |
| **Meta-Model** | EV Classifier | Train EV classifier; integrate into pipeline |
| **Bullpen Modeling Upgrade** | Posterior bullpen | Posterior bullpen strength; fatigue modeling |

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Overfitting from too many layers | Cross-validation at each layer; ablation testing |
| Miscalibration | Monitor ECE continuously after each model change |
| Data sparsity (rookies, early season) | Use priors aggressively; feature stabilization layer |

---

## 10. Definition of Done

The system is complete when:

- Posterior probabilities outperform raw model on Brier score
- Mean betting edge becomes positive (> +0.01)
- Uncertainty is reflected in bet sizing
- Totals predictions improve via distribution modeling

---

---

# Appendix: Consistency and Feasibility Review

> This section documents how the PRD above maps to the current Diamond Edge codebase and Phase 7 plan, flags conflicts, and assesses feasibility of each major component. Reviewed against `project_context.md`, `betting_ml/evaluation/postmortem_v0.md`, and `plan_specs/phase_7/`.

---

## A. What Is Already Implemented

Several PRD components are **already live** or **partially live** in the codebase. These require extension rather than net-new builds.

| PRD Component | Current Status | Where |
|---|---|---|
| Bayesian probability layer | Live — `compute_posterior()` in `predict_today.py`; blends model + market at `alpha` weight | Card 4.13 / `predict_today.py` |
| Dynamic alpha weighting | Partially live — `best_alpha` loaded from Snowflake `alpha_tuning_results` with file fallback | Card 7.A (complete) |
| Distribution modeling (totals) | Partially live — NGBoost with LogNormal distribution outputs a full parametric distribution; `prob_over_X` is derivable from it | Card 4.12d / `betting_ml/models/` |
| Platt calibration | Live — `calibrator.joblib` Platt scaler loaded at startup, applies to each game | Card 7.C (complete) |
| Bullpen workload + effectiveness | Live in feature store — `mart_bullpen_workload`, `mart_bullpen_effectiveness` | Phase 2 / dbt mart layer |
| Rolling window reliability flags | Live — `home_games_played_7d/30d/std`, `home_starter_appearances_30d/std` | Card 4.3 (complete) |
| Feature stabilization concept | Partially live — `has_full_data` filter + rolling reliability flags; no explicit `w = n/(n+k)` shrinkage in pipeline | Cards 4.3 / 4.6 |
| Kelly sizing | Live — `compute_kelly()` in `predict_today.py` | Phase 6 |

**Key implication:** The PRD's "Bayesian Layer" is not a new concept for this project — it is an extension of the existing layer. The architectural delta is modest. The critical challenge is not the architecture; it is that `best_alpha = 0.0` (log-loss rises monotonically as model weight increases). The market currently dominates. The Bayesian layer will not add value until the underlying model probability quality improves past the market's Brier of 0.2395.

---

## B. Naming Conflict with Existing Plan Spec Cards

The PRD introduces internal phase labels ("Phase 7A" through "Phase 7E") that **conflict with the existing card naming convention** in `plan_specs/phase_7/`. In the current plan:

| Existing Card | What It Is |
|---|---|
| Card 7.A | Alpha grid rerun (complete) |
| Card 7.B | Weather features |
| Card 7.C | Home-win calibration (complete) |
| Card 7.D | Model retraining cadence |
| Card 7.E | FanGraphs ingestion |
| ... | (Cards 7.F through 7.S defined) |

The PRD's "Phase 7A — Bayesian Overlay" is distinct from the project's Card 7.A. **Recommendation:** When translating this PRD into plan specs, use new card identifiers (e.g., `BA_bayesian_overlay`, `BB_uncertainty_layer`, etc.) or a separate sequence to avoid collision.

---

## C. Component-Level Feasibility Assessment

### C.1 Bayesian Probability Layer (Section 5.1)

**Feasibility: High — architecture already exists.**

The `compute_posterior()` function already implements the blending formula. Extensions needed:

- Make `w` a function of sample size and feature stability (currently a scalar `alpha`)
- The dynamic weight concept maps directly to the stabilization weights in Section 5.5
- **Blocker:** The model must achieve Brier < 0.2395 before `w > 0` adds value. Until then, the optimal dynamic `w` will converge to 0 for every game.

### C.2 Uncertainty Modeling (Section 5.2)

**Feasibility: Medium — some inputs available, propagation is novel.**

- `sample_size` / `player_variance`: The rolling reliability flags (games_played_7d/30d/std, starter_appearances_30d/std) already supply sample size. Per-player variance requires computing prediction interval widths from the NGBoost distribution — directly available from `ngboost_tuned` model artifacts.
- `lineup_uncertainty_score` / `pitcher_uncertainty_score`: Aggregatable from existing per-slot sample sizes.
- `game_uncertainty_score`: Net-new computation but straightforward as a weighted average of lineup and pitcher uncertainty scores.
- Propagating uncertainty into `compute_kelly()` is feasible — reduce the Kelly fraction by a `(1 - uncertainty_penalty)` factor.

### C.3 Distribution Modeling (Totals) (Section 5.3)

**Feasibility: High — NGBoost already produces this.**

The production totals model is `ngboost_tuned` with `dist=LogNormal` (Card 4.12d). It already outputs `prob_over_X` for any line directly. What is missing:

- Surfacing `prob_over_X` and `prob_under_X` in `predict_today.py` output and `daily_model_predictions`
- Writing `total_variance` to Snowflake for monitoring
- The Poisson/Negative Binomial path would require re-fitting with a different distribution class — treat as a stretch goal

**Note:** The PRD lists "Normal approximation (MVP)" but the current model uses LogNormal, which is strictly more appropriate given the right-tail shape documented in Notebook 01.

### C.4 Bullpen Posterior Model (Section 5.4)

**Feasibility: Medium — data exists, new modeling layer needed.**

- Baseline bullpen stats: `mart_bullpen_effectiveness` (xwOBA, K%, BB% over 14/30d)
- Workload: `mart_bullpen_workload` (pitches, relievers used, leverage appearances over 1/3/7d)
- What is missing: a model that combines baseline + fatigue into a single `bp_posterior_strength` estimate with uncertainty

Card 7.Q (`Q_bullpen_fatigue_avail.yaml`) covers the fatigue/availability angle. The posterior strength concept is additive on top of that card.

**Consistency check:** The existing `feature_pregame_team_features` already includes bullpen workload and effectiveness features. The new layer should produce a derived signal rather than replacing the raw features.

### C.5 Feature Stabilization Layer (Section 5.5)

**Feasibility: High — standard sabermetric technique, partially scaffolded.**

The `w = n / (n + k)` formula is a textbook regressed-to-prior stabilization point. Appropriate `k` values for MLB:

| Stat | Approximate stabilization k |
|---|---|
| K% (batter) | ~60 PA |
| wOBA | ~150 PA |
| ISO | ~160 PA |
| ERA | ~950 IP (very noisy) |
| xFIP | ~70 IP |

These constants are well-established in sabermetric literature and can be hard-coded. The feature layer already has `games_played` counts to compute `n`. This is a Python-side transform in preprocessing, not a dbt change.

### C.6 Meta-Model for EV Detection (Section 5.6)

**Feasibility: Medium — novel to the project, requires labeled training data.**

This is the most conceptually distinct component. A classifier predicting `p_positive_ev` requires:

- **Training labels:** Historical games where edge > 0 and bet resolved profitably — derivable from `daily_model_predictions` with `actual_outcome` + `h2h_edge`. Currently ~941 has_odds rows (small).
- **Feature inputs:** Posterior probabilities, market probabilities, uncertainty metrics, line movement features — all feasible to compute.
- **Risk:** With only ~941 labeled examples (growing at ~6 games/day), early-season training will be severely sample-limited. The classifier will have high variance until ~2,000+ labeled rows accumulate (approximately late August 2026 at current pace).

**Recommendation:** Defer meta-model training until end-of-2026-season data accumulates. Use a simple threshold rule (`posterior_edge > threshold AND uncertainty < threshold`) as a proxy until then. This is lower risk than training an underpowered classifier.

### C.7 Bet Sizing Enhancements (Section 5.7)

**Feasibility: High — additive to existing Kelly implementation.**

`compute_kelly()` already exists in `predict_today.py`. Adding an uncertainty-scaling factor is a straightforward multiplicative adjustment. The inputs (`edge`, `uncertainty`, `calibration confidence`) will be available from Sections 5.2 and 5.1.

---

## D. Critical Dependency: Model Must Beat the Market First

The postmortem established `best_alpha = 0.0` — the market is the best predictor at all times. The Bayesian blending layer, meta-model, and uncertainty-adjusted Kelly sizing are **all downstream of model probability quality**. None of them materially help if the underlying model Brier remains above 0.2395.

**The PRD's success criteria (mean edge > +0.01) is contingent on the Phase 7 feature expansion cards (7.B, 7.E, 7.F, 7.H, 7.J) moving model Brier below market baseline.** The recommended sequencing is:

1. Phase 7 feature cards (weather, FanGraphs, umpires) → improve model Brier
2. Re-run alpha grid → confirm `best_alpha > 0` before investing in dynamic weighting
3. Then implement the dynamic Bayesian layer, uncertainty propagation, and meta-model

Implementing the Bayesian architecture first (without improving underlying features) risks significant engineering effort with zero measurable impact on edge.

---

## E. Items Requiring Clarification Before Spec Writing

1. **Normal vs. LogNormal for totals**: PRD specifies "Normal approximation (MVP)." Production model uses LogNormal. Clarify whether to switch back or adopt LogNormal as the distribution model.

2. **Meta-model training cutoff**: Confirm minimum sample size requirement for the EV classifier before training begins. Suggest 1,500–2,000 labeled rows as a gate.

3. **Dynamic alpha scope**: Should `w` vary per-game (based on that game's uncertainty score) or per-context-bucket (e.g., early season vs. mid-season)? Per-game is more powerful but harder to tune without overfitting.

4. **Bullpen posterior vs. existing features**: `feature_pregame_team_features` already passes bullpen xwOBA and workload directly to the model. Confirm whether the goal is to create a derived `bp_posterior_strength` feature to replace those inputs or to add it as an additional column alongside them.
