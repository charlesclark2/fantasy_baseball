# E5.4 — HARD prop-edge gate (pitcher strikeouts)  ·  the cashability decision

## Verdict: **NULL — no cashable K-prop edge**
_CLEAN NULL: the K distribution is well-CALIBRATED (product value) but NOT PROFITABLE. Failing gate(s): PBO ≥ 0.2 (selection overfit / unstable); DSR < 0.95 (deflated Sharpe ≤ benchmark — edge vanishes once deflated for the config count); pre-committed broad-strategy ROI net of vig ≤ 0. The large prop vig (median book hold ≈ 6.9%, E5.3) eats the model-relative disagreement — gross 'edge' that the vig consumes is not edge. Consistent with H2H (dead ×5), the efficient main total (E13.8), and E5.3's blind-over EV ≈ −8.7%/$1. The K-prop softest-market hypothesis is CLOSED with integrity (calibration ≠ edge)._

> 🔒 **best_alpha = 0.** A calibrated K distribution (E5.2) is product value; whether it is PROFITABLE is decided ONLY here. The market/line/book SELECTION is part of the test — the grid is pre-registered, every config logged (`e5_4_config_grid_results.csv`), selection is in-fold (PBO/CSCV + held-out split), and every config counts in the DSR deflation.

## Gate scorecard (ALL required to ship)

| gate | requirement | result | pass |
|---|---|---|---|
| 1. Calibration floor | calib_80 ≥ 0.8 (purged CV) | served-glm calib_80 = **0.8104** | ✅ |
| 2a. PBO | < 0.2 | **0.421** (453 configs × 11 slices) | ❌ |
| 2b. DSR | ≥ 0.95 (deflated, 582 trials) | **0.246** (SR=+0.068 vs SR0=+0.113) | ❌ |
| 3a. Offline ROI net of vig | pre-committed broad strategy > 0 | **-3.14%** (44,851 bets) | ❌ |
| 3b. Held-out ROI (2023–24→2025–26) | OOS > 0 | **+1.08%** (228 bets) | ✅ |

_Gate 3 is the OFFLINE cashability leg (necessary, not sufficient). The TRUE forward-CLV leg (decision-price vs the prop's own close) needs LIVE prop capture (not yet built) — see the forward plan below._

## 1. Calibration floor

- **Served-glm calib_80 (E1.1 purged walk-forward CV, E5.2): 0.8104** ≥ 0.8 → floor **MET**. Per season: {2023: 0.7455, 2024: 0.8528, 2025: 0.8556, 2026: 0.7622}.
- **At-the-line betting-probability reliability** (model_p_over_cond vs realized over, the number the bet rests on): ECE **0.0531**, Brier **0.2473** (n=63,606). Per season ECE: 2023:0.0549, 2024:0.0585, 2025:0.0556, 2026:0.0544.

## 2. Multiple-comparison-corrected overfitting gate

- **Full pre-registered grid:** 660 configs (book-group × line-bucket × conviction τ × anchor). Selectable (≥200 bets): 582. Every config logged in `e5_4_config_grid_results.csv`.
- **PBO (CSCV)** over the 453-config slate × 11 year-month slices = **0.421** (≥ 0.2 — IS-best does NOT persist OOS).
- **DSR** on the in-sample-best config, deflated for 582 trials = **0.246** (< 0.95 — Sharpe vanishes after deflation). observed SR +0.068, deflated benchmark SR0 +0.113, skew 1.429, kurt 6.1126.

## 3. Cashability — ROI net of the (large) prop vig

- **⭐ Pre-committed broad strategy (NO cherry-pick — favored side, all books, all lines, τ=0.04):** `all|all|tau0.04|book` → ROI **-3.14%** over 44,851 bets, NEGATIVE in every season (2023:-5.8%, 2024:-2.9%, 2025:-0.8%, 2026:-3.6%). This is the honest headline: the betting strategy loses the prop vig.
- **In-sample-best config (cherry-pick):** `barstool|mid_5p5|tau0.04|book` → ROI **+9.30%** over 214 bets — but this is the single best of 582 configs, and PBO/DSR deflate it away.
- **Held-out forward split** (select on [2023, 2024], evaluate on [2025, 2026]): best config runnable in BOTH halves = `betrivers|high_ge6p5|tau0.1|book` (IS +7.77%, n=392) → OOS **+1.08%** (n=228). Survives ✅.
- **The trap, illustrated:** the raw best-of-grid IS config `barstool|mid_5p5|tau0.04|book` (IS +9.30%, n=214) places **0 bets** out of sample — the in-sample 'edge' literally does not exist on new data.

## 4. Coverage / robustness

- Gated rows (de-viggable, outcome present): **63,606** (7,055 pitcher×dates, 14 books, seasons [2023, 2026]). Actual-K join 100.0%. Integer-line pushes: 0.
- Selectable-config ROI distribution: mean -2.80%, min -15.31%, max +9.30%, frac positive 20.3% (over 582 configs).

### Per-book favored-side ROI net of vig (τ=0.04)

| book | ROI net vig | n bets |
|---|---|---|
| fanatics | -0.71% | 1,528 |
| betonlineag | -1.90% | 4,394 |
| fanduel | -2.08% | 4,809 |
| bovada | -2.61% | 4,096 |
| draftkings | -2.73% | 4,931 |
| betmgm | -2.75% | 4,742 |
| pointsbetus | -3.00% | 1,467 |
| betrivers | -3.02% | 4,394 |
| unibet_us | -3.76% | 1,541 |
| pinnacle | -3.84% | 4,882 |
| barstool | -4.80% | 1,031 |
| mybookieag | -5.14% | 3,405 |
| superbook | -5.22% | 648 |
| williamhill_us | -5.48% | 2,983 |

### Top / bottom configs by IN-SAMPLE ROI (the cherry-pick the gate refuses to honour)

| rank | config | IS ROI | n bets |
|---|---|---|---|
| top 1 | `barstool|mid_5p5|tau0.04|book` | +9.30% | 214 |
| top 2 | `pointsbetus|low_le4p5|tau0.1|book` | +7.71% | 330 |
| top 3 | `barstool|low_le4p5|tau0.1|book` | +6.95% | 208 |
| top 4 | `barstool|mid_5p5|tau0.02|book` | +6.85% | 257 |
| top 5 | `pointsbetus|low_le4p5|tau0.1|pinnacle` | +6.52% | 293 |
| top 6 | `barstool|all|tau0.1|book` | +6.22% | 433 |
| top 7 | `betonlineag|low_le4p5|tau0.1|book` | +5.63% | 1,092 |
| top 8 | `betrivers|high_ge6p5|tau0.1|book` | +5.31% | 620 |
| bot 1 | `barstool|low_le4p5|tau0.02|book` | -11.30% | 583 |
| bot 2 | `superbook|low_le4p5|tau0.02|pinnacle` | -11.37% | 412 |
| bot 3 | `betrivers|mid_5p5|tau0.02|pinnacle` | -12.22% | 289 |
| bot 4 | `mybookieag|mid_5p5|tau0.02|pinnacle` | -12.34% | 978 |
| bot 5 | `barstool|all|tau0.04|pinnacle` | -14.15% | 223 |
| bot 6 | `barstool|all|tau0.02|pinnacle` | -14.35% | 274 |
| bot 7 | `fanatics|high_ge6p5|tau0.02|pinnacle` | -14.60% | 215 |
| bot 8 | `betrivers|high_ge6p5|tau0.02|pinnacle` | -15.31% | 222 |

_The top configs' positive IS ROI is exactly what PBO/DSR deflate away: if the IS-best does not persist OOS (PBO) and its Sharpe vanishes after deflating for how many configs were tried (DSR), the apparent edge is selection noise, not skill._

## Forward-CLV plan (the TRUE verdict — CLV cannot be backtested into truth)
- Historical closes give the NECESSARY offline ROI-net-of-vig leg only; the prop's own close is the bet price here, so CLV-vs-close is structurally 0 offline.
- Stand up an E13.5-style shadow harness: each morning score the served K distribution, log the favored-side decision-time price per book; at the prop's CLOSE record the closing price; accrue captured CLV + ROI net of vig over a rolling window.
- **Pre-registered ship gate:** ≥100 forward prop bets with POSITIVE captured CLV *and* ROI clearing the real prop hold → promote to the E5.5 surface + E10.2 uncertainty-aware sizing. Else the K-prop edge thesis stays CLOSED.
- Honest framing (best_alpha=0): any surface is "calibrated projection + transparent model-vs-market comparison," never a win-rate/edge claim. No auto-betting.

_🔬 The betting ROI above carries model in-sample optimism (served bundle fit on 2021–26; the CONFIG selection is held out, the MODEL is not). The leak-honest calibration is the E5.2 purged-CV calib_80; forward LIVE capture is the real cashability verdict._
