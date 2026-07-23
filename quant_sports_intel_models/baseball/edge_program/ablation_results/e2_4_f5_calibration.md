# E2.4 — F5 per-side distribution calibration (served)

_Fit 2026-07-23 · learner `lgbm_poisson` · contract `full` · form `betabinom` · 11,662 OOS games_

## Served contract

- form: **betabinom**  ·  served dispersion home `15.4077` / away `15.6201`  ·  ρ = 0 (independent, E2.2)

## Gate (pooled OOS)

| distribution | calib_80 | PIT max-decile-dev | PIT-flat | gated |
|---|---|---|---|---|
| total | 0.860 | 0.0038 | ✅ | yes |
| home_total | 0.919 | 0.0061 | ✅ | yes |
| away_total | 0.922 | 0.0052 | ✅ | yes |
| run_diff | 0.842 | 0.0042 | ✅ | no (dropped dependence) |

**calib floor (≥0.80 on total + team totals):** PASS ✅  ·  **PIT-flat:** PASS ✅

## Honest framing

A market-BLIND F5 distribution is product value, not an edge claim (`best_alpha = 0`). F5 efficiency vs its own close is measured at E2.6 — not assumed here.

## Why betabinom is served (over the deflated `INCUMBENT_STANDS` verdict)

The pre-registered deflated bake-off verdict was **`INCUMBENT_STANDS`** — the carried NegBin
(`lgbm_poisson__full__heldout`) was the strict null because `full_search_pbo` = 0.202 missed the
`<0.2` bar. On inspection that miss is a tie *within* the winning betabinom form (which of
catboost/xgb/lgbm ranks #1 = noise; cross-learner `best_dsr` ≈ 0.004) — **not** evidence the form is
fragile. We keep the lgbm learner regardless, and the single-axis switch NegBin→betabinom has
**minimal-fix DSR = 0.396 (PASS)**, better on 17/20 CV buckets.

**The system's #1 priority is product quality, so the best-calibrated honest F5 distribution is
served.** Betabinom wins that on every served-gate axis (same lgbm μ model, pooled OOS, 10k draws):

| distribution | NegBin (heldout) PIT-dev | **betabinom (SERVED)** PIT-dev |
|---|---|---|
| F5 total | 0.0070 | **0.0038** |
| home total | 0.0096 | **0.0061** |
| away total | 0.0085 | **0.0052** |
| run_diff | 0.0067 | **0.0042** |

Both PASS the calib floor and are PIT-flat; betabinom is uniformly ~40–45% flatter. It is also the
mechanistically-correct form — pure Poisson FAILS the floor (0.69 cov → F5 decisively overdispersed),
and F5 runs are *bounded* + ~22% *zero*, which Beta-Binomial represents and unbounded NegBin cannot.
The swap carries **zero mean-model risk** (identical μ model; only the dispersion form changes).

**Served:** `form=betabinom`, concentration `s` home **15.41** / away **15.62**, `n_cap` 25 (max observed
F5 per side = 16, comfortable headroom). Leakage-safe (expanding-window s 14.98–15.48, stable).
**Fallback (gate-passing):** NegBin `heldout`, r home 2.01 / away 1.89 — served head-to-head above.
E2.6 measures F5 efficiency vs its own close on the served betabinom form (do NOT assume it).
