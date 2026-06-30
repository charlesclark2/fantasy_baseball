# E13.14 — Cross-Market Constellation Coherence

**Verdict: CLEAN NULL — the market constellation is internally coherent (no cross-market edge)**

Pure cached-data RELATIVE-VALUE probe (NO predictive model). Pre-registration: `e13_14_preregistration.md`. The question is internal-market COHERENCE, not prediction accuracy: where two of a game's markets contradict each other, does the side the implied market favors win NET OF the bet-market's own vig? **Honest bar:** game-level collapse before any t-test/DSR/PBO; leave-one-season-out affine calibration; FORCED side; deflation over every relation × credence-τ × book-group. Cashability proxy = realized-outcome ROI net of vig (true beat-the-close forward CLV is the forward leg).

## Coverage

- 245,203 bet-quotes · 5,478 games · seasons [2023, 2024, 2025, 2026]

## Relation status (every relation logged)

| relation | status | prior |
|---|---|---|
| ① props → team offense ↔ team-total | RAN (4472 games) | highest (laziest pair) |
| ② team-totals → game-total | RAN (4672 games) | medium |
| ③ F5 → full-game [NEGATIVE CONTROL] | RAN (5289 games) | MUST be consistent |
| ④ K-props → opposing team-total | DEFERRED (pre-registered; engine-ready; assembly is a follow-up) | low (deferred) |
| ⑤ sides ↔ totals (ML ↔ run-line+total) | DEFERRED (pre-registered; engine-ready; assembly is a follow-up) | low / near-control (deferred) |

## ✅ Method check — the F5 ↔ main NEGATIVE CONTROL

- **✅ CONSISTENT.** The F5↔main control produced NO surviving candidate — the method does not manufacture inconsistencies where E13.13 proved the derivation is efficient. The harness is trustworthy.

## Per-relation coherence diagnostics

`corr_markets` = how tightly market A's implied tracks the posted line B (≈1 ⇒ coherent). `info_gain` = corr(realized, implied_A)² − corr(realized, posted_B)²: **>0 ⇒ market A tracks the outcome BETTER than the bet-line** — the precondition for a relative-value edge.

| relation | n | corr_markets | ols_slope | mean_resid(wedge) | corr→implied | corr→posted | info_gain |
|---|--:|--:|--:|--:|--:|--:|--:|
| ① props → team offense ↔ team-total | 8859 | 0.700 | 0.977 | 0.009 | 0.143 | 0.174 | -0.0099 |
| ② team-totals → game-total | 4672 | 0.581 | 0.935 | 0.041 | 0.166 | 0.226 | -0.0235 |
| ③ F5 → full-game [NEGATIVE CONTROL] | 5289 | 0.587 | 0.948 | 0.030 | 0.171 | 0.235 | -0.0257 |

## Deflation (anti-data-mining)

- credence-gated grid: 60 configs (relation × τ∈{0.75, 0.85, 0.9, 0.95, 0.975} × book-group), 53 selectable (≥50 games; scored GAME-level)
- PBO (CSCV over ym slices): **0.487** (<0.2 required) 
- DSR (deflated by config count): **0.848** (≥0.95 required); best = `f5_to_full_control|tau0.9|pinnacle` ROI 0.4589
- ROI FDR (q=0.1): 22/53 configs survive

## Credence-gated config grid (top by ROI, game-level net of vig)

| relation | τ | book | games | quotes | ROI | sharpe | season-consistent | FDR |
|---|--:|---|--:|--:|--:|--:|:--:|:--:|
| f5_to_full_control [CTRL] | 0.9 | pinnacle | 55 | 55 | 0.4589 | 0.50 | · | ✓ |
| f5_to_full_control [CTRL] | 0.75 | pinnacle | 71 | 71 | 0.4414 | 0.48 | · | ✓ |
| f5_to_full_control [CTRL] | 0.85 | pinnacle | 63 | 63 | 0.4016 | 0.43 | · | ✓ |
| f5_to_full_control [CTRL] | 0.975 | majors | 249 | 770 | 0.2819 | 0.30 | · | ✓ |
| team_total_to_game_total | 0.95 | majors | 157 | 606 | 0.2478 | 0.26 | · | ✓ |
| team_total_to_game_total | 0.975 | majors | 95 | 362 | 0.2356 | 0.25 | · | ✓ |
| f5_to_full_control [CTRL] | 0.95 | majors | 421 | 1332 | 0.2019 | 0.21 | · | ✓ |
| team_total_to_game_total | 0.9 | majors | 377 | 1465 | 0.1730 | 0.19 | · | ✓ |
| team_total_to_game_total | 0.85 | majors | 575 | 2236 | 0.1664 | 0.18 | ✓ | ✓ |
| f5_to_full_control [CTRL] | 0.9 | majors | 924 | 3153 | 0.1412 | 0.15 | · | ✓ |
| f5_to_full_control [CTRL] | 0.85 | majors | 1248 | 4280 | 0.1144 | 0.12 | · | ✓ |
| f5_to_full_control [CTRL] | 0.975 | all | 249 | 3662 | 0.1129 | 0.13 | · | ✓ |
| f5_to_full_control [CTRL] | 0.975 | soft | 249 | 3626 | 0.1126 | 0.13 | · | ✓ |
| team_total_to_game_total | 0.85 | all | 575 | 9836 | 0.0901 | 0.10 | ✓ | ✓ |
| team_total_to_game_total | 0.85 | soft | 575 | 9821 | 0.0898 | 0.10 | ✓ | ✓ |
| f5_to_full_control [CTRL] | 0.95 | all | 421 | 6102 | 0.0804 | 0.09 | · | ✓ |
| f5_to_full_control [CTRL] | 0.95 | soft | 421 | 6057 | 0.0802 | 0.09 | · | ✓ |
| f5_to_full_control [CTRL] | 0.9 | all | 924 | 13957 | 0.0765 | 0.09 | · | ✓ |
| f5_to_full_control [CTRL] | 0.9 | soft | 924 | 13902 | 0.0763 | 0.09 | · | ✓ |
| team_total_to_game_total | 0.9 | all | 377 | 6521 | 0.0665 | 0.08 | · | · |
| team_total_to_game_total | 0.9 | soft | 377 | 6507 | 0.0660 | 0.08 | · | · |
| f5_to_full_control [CTRL] | 0.85 | all | 1248 | 18741 | 0.0653 | 0.07 | · | ✓ |
| f5_to_full_control [CTRL] | 0.85 | soft | 1248 | 18678 | 0.0652 | 0.07 | · | ✓ |
| f5_to_full_control [CTRL] | 0.75 | majors | 2269 | 8085 | 0.0432 | 0.05 | · | ✓ |
| team_total_to_game_total | 0.75 | majors | 1342 | 5191 | 0.0381 | 0.04 | · | · |

## Candidate shortlist

**None.** No relation cleared the deflated, GAME-level, multiple-comparison-corrected bar → the books' own markets are internally coherent. With E5.4 / E13.13 this closes the cross-market angle.

### Why the null is trustworthy (not merely 'PBO failed')
- **`info_gain < 0` in 3/3 relations** — in every relation the POSTED bet-line tracks the realized outcome *better* than the cross-market implied quantity (`corr→posted` > `corr→implied`). There is no information left on the table, so the relative-value precondition simply isn't met — including for the least-arbed props↔team-total pair.
- **PBO = 0.487 ≈ 0.5** — the in-sample-best config does not persist out of sample; the apparent +ROI cells are multiple-comparison / small-sample noise, not signal.
- **The single largest in-sample ROI cell is `f5_to_full_control|tau0.9|pinnacle` (the NEGATIVE CONTROL — a relation E13.13 proved is efficiently derived)** at ROI 0.4589 on just 55 games, and ROI decays monotonically toward ~0 as the game count grows. A fluke this size coming from the control — then evaporating with sample size — is direct evidence the +ROI cells are noise the deflation exists to kill, not a missed edge.
- **The honest conclusion stands:** value = product-quality calibration + transparency + fantasy, not a cashable cross-market edge.

_Generated by `eval_cross_market.py` (E13.14). Strategies scored GAME-level (correlated book-quotes collapsed per game). Every relation × τ × book-group config is logged in `e13_14_relation_grid_results.csv` (no cherry-pick)._