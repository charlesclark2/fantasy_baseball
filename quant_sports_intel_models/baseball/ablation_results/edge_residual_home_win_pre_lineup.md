# Market-Anchored Residual Model — home_win (pre_lineup)  [E13.1]

8161 games 2021–2026 · 154 market-blind feats · 3 purged folds · anchor = vig-free opening P(home) · ROI hold = 0.045

## Verdict: **KILL (no CLV edge)**
_no positive in-sample CLV proxy on the selected config under purged CV — the residual lean does not anticipate the close. Record the kill._

- **Winning residual config:** `gbm_d3_lr0.05`
- At |lean| > 0.02: **3096 bets**, 49.9% CLV-positive, mean captured CLV **+0.01 prob-pts**, **ROI net of vig +1.22%**
- PBO across slate (CSCV): **nan**  (n/a)
- DSR on excess-over-drift return: **0.000** (SR=-0.076 vs SR0=+0.040, n_trials=7, n=3096)

## CLV proxy by conviction (winner) — captured = sign(lean)·clv_home_ml
| |lean|> | n_bets | %CLV-pos | mean captured CLV | ROI net vig |
|---|---|---|---|---|
| 0.0 | 3798 | 49.8% | -0.01pp | +1.53% |
| 0.01 | 3437 | 49.4% | -0.01pp | +1.37% |
| 0.02 | 3096 | 49.9% | +0.01pp | +1.22% |
| 0.03 | 2766 | 49.6% | +0.01pp | +1.94% |
| 0.05 | 2188 | 49.4% | +0.01pp | +2.44% |

## Per-season CLV (winner, at eval τ) — forward-honesty / stability check
| season | n | %CLV-pos | mean captured CLV |
|---|---|---|---|
| 2024 | 1258 | 50.6% | +0.02pp |
| 2025 | 1245 | 49.2% | -0.01pp |
| 2026 | 593 | 49.9% | +0.07pp |

## Additive-to vs replace — CLV proxy at eval τ, all configs
| config | %CLV-pos | mean captured CLV | ROI net vig | Brier vs market | beats mkt? |
|---|---|---|---|---|---|
| `gbm_d3_lr0.05` | 49.9% | +0.01pp | +1.22% | +0.0054 |  |
| `gbm_d4_lr0.05` | 48.5% | -0.05pp | +1.78% | +0.0069 |  |
| `gbm_d5_lr0.03` | 49.2% | -0.04pp | +1.73% | +0.0052 |  |
| `glm_a0.003_l0.5` | 49.6% | -0.02pp | -1.02% | +0.0038 |  |
| `glm_a0.01_l0.5` | 49.7% | -0.02pp | -0.58% | +0.0012 |  |
| `glm_a0.03_l0.2` | 49.7% | -0.01pp | +0.37% | +0.0008 |  |
| `point_model_market_blind` | 53.7% | +0.17pp | +2.16% | +0.0032 |  |
| `anchor_only_market` | — | — | — | +0.0000 |  |

## Forward-validation plan (CLV cannot be backtested into truth)
- Score the `gbm_d3_lr0.05` residual config live each morning (post-A1.11 serving), log lean + the OPEN vig-free line per game.
- At close, record `clv_home_ml`; accrue captured CLV + ROI net of vig over a rolling window.
- **Gate (pre-registered):** >=100 forward games with POSITIVE captured CLV *and* ROI clearing the real book hold → promote to advisory. Else KILL the residual thesis.
- Honest framing (best_alpha=0): advisory is "spots the market misprices, proven by CLV," never "we predict games." No auto-betting.

_Offline CLV/ROI here is the LEADING indicator + discipline check, NOT a go-live. E4 (the cross-book thesis) had a real CLV signal that died at the vig — read the ROI column, not the CLV column, before believing this._