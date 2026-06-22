# Market-Anchored Residual Model — home_win (post_lineup)  [E13.1]

8161 games 2021–2026 · 19 market-blind feats · 3 purged folds · anchor = vig-free opening P(home) · ROI hold = 0.045

## Verdict: **KILL (CLV ≠ cashable)**
_CLV proxy positive but ROI net of vig <=0 — the captured CLV does NOT clear the book hold. Same failure mode as the E4 kill (2026-06-18). Record and stop._

- **Winning residual config:** `gbm_d4_lr0.05`
- At |lean| > 0.02: **3234 bets**, 51.1% CLV-positive, mean captured CLV **+0.03 prob-pts**, **ROI net of vig -1.48%**
- PBO across slate (CSCV): **nan**  (n/a)
- DSR on excess-over-drift return: **0.000** (SR=-0.067 vs SR0=+0.045, n_trials=7, n=3234)

## CLV proxy by conviction (winner) — captured = sign(lean)·clv_home_ml
| |lean|> | n_bets | %CLV-pos | mean captured CLV | ROI net vig |
|---|---|---|---|---|
| 0.0 | 3798 | 50.7% | +0.02pp | -1.39% |
| 0.01 | 3505 | 50.7% | +0.02pp | -1.84% |
| 0.02 | 3234 | 51.1% | +0.03pp | -1.48% |
| 0.03 | 2939 | 50.8% | +0.01pp | -0.64% |
| 0.05 | 2438 | 50.7% | +0.00pp | -0.93% |

## Per-season CLV (winner, at eval τ) — forward-honesty / stability check
| season | n | %CLV-pos | mean captured CLV |
|---|---|---|---|
| 2024 | 1278 | 49.0% | -0.07pp |
| 2025 | 1307 | 51.8% | +0.06pp |
| 2026 | 649 | 53.6% | +0.19pp |

## Additive-to vs replace — CLV proxy at eval τ, all configs
| config | %CLV-pos | mean captured CLV | ROI net vig | Brier vs market | beats mkt? |
|---|---|---|---|---|---|
| `gbm_d3_lr0.05` | 50.3% | -0.01pp | -2.33% | +0.0088 |  |
| `gbm_d4_lr0.05` | 51.1% | +0.03pp | -1.48% | +0.0113 |  |
| `gbm_d5_lr0.03` | 50.7% | +0.02pp | -0.53% | +0.0089 |  |
| `glm_a0.003_l0.5` | 47.8% | -0.11pp | +1.83% | +0.0008 |  |
| `glm_a0.01_l0.5` | 47.3% | -0.11pp | +0.98% | +0.0003 |  |
| `glm_a0.03_l0.2` | 46.6% | -0.15pp | +0.09% | +0.0002 |  |
| `point_model_market_blind` | 55.0% | +0.24pp | -0.63% | +0.0050 |  |
| `anchor_only_market` | — | — | — | +0.0000 |  |

## Forward-validation plan (CLV cannot be backtested into truth)
- Score the `gbm_d4_lr0.05` residual config live each morning (post-A1.11 serving), log lean + the OPEN vig-free line per game.
- At close, record `clv_home_ml`; accrue captured CLV + ROI net of vig over a rolling window.
- **Gate (pre-registered):** >=100 forward games with POSITIVE captured CLV *and* ROI clearing the real book hold → promote to advisory. Else KILL the residual thesis.
- Honest framing (best_alpha=0): advisory is "spots the market misprices, proven by CLV," never "we predict games." No auto-betting.

_Offline CLV/ROI here is the LEADING indicator + discipline check, NOT a go-live. E4 (the cross-book thesis) had a real CLV signal that died at the vig — read the ROI column, not the CLV column, before believing this._