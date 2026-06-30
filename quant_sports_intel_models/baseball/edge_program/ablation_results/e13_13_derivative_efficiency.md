# E13.13 — Derivative-Market Mispricing Evaluation (angles 1+2)

**Verdict: CLEAN NULL — all derivatives efficient** — 0 candidate(s) for E2.6.

Pure cached-data efficiency evaluation (NO model). Pre-registration: `e13_13_preregistration.md`. **Honest bar:** candidates ≠ edge — softer ≠ free (derivatives carry higher vig + lower limits); the cashability verdict is forward CLV net of the derivative's own vig at PBO<0.2/DSR>0 (E2.6/forward), NOT here.

## Coverage

- 214,920 closing quotes · 5,321 games · 17 books · seasons [2023, 2024, 2025, 2026]
- markets present: ['h2h_1st_5_innings', 'totals_1st_1_innings', 'totals_1st_5_innings']

## Deflation (anti-data-mining)

- static-strategy grid: 278 configs, 246 selectable (≥50 games; scored GAME-level — book quotes on one game are correlated, not independent bets)
- PBO (CSCV over ym slices): **0.000** (<0.2 required) 
- DSR (deflated by trial count): **0.855** (≥0.95 required); best static = `totals_1st_5_innings|always_under|majors|high_ge6p5` ROI 0.2805
- calibration FDR (q=0.1): 0/51 cells survive

## Angle 1 — efficiency ranking (pooled cells, sorted by least-efficient)

Brier floor for a centred coin-flip market = 0.25 (E13.8). brier≈0.25 + over/favorite-rate≈implied ⇒ efficient. `calib_bias` = realized − implied (✚ = event underpriced).

| market | book | n | brier | vig | over/fav-rate | implied | calib_bias | z | FDR | MAE |
|---|---|--:|--:|--:|--:|--:|--:|--:|:--:|--:|
| totals_1st_5_innings | superbook | 845 | 0.250 | 0.046 | 0.502 | 0.499 | 0.002 | 0.14 | · | 2.58 |
| totals_1st_5_innings | betus | 4921 | 0.250 | 0.069 | 0.496 | 0.500 | -0.005 | -0.63 | · | 2.53 |
| totals_1st_5_innings | bovada | 5341 | 0.250 | 0.068 | 0.499 | 0.500 | -0.001 | -0.14 | · | 2.55 |
| totals_1st_5_innings | williamhill_us | 3746 | 0.250 | 0.066 | 0.503 | 0.500 | 0.002 | 0.29 | · | 2.56 |
| totals_1st_5_innings | betonlineag | 5259 | 0.250 | 0.046 | 0.495 | 0.501 | -0.005 | -0.77 | · | 2.55 |
| totals_1st_5_innings | draftkings | 620 | 0.250 | 0.068 | 0.499 | 0.501 | -0.002 | -0.08 | · | 2.73 |
| totals_1st_5_innings | mybookieag | 4009 | 0.250 | 0.050 | 0.502 | 0.500 | 0.002 | 0.23 | · | 2.55 |
| totals_1st_1_innings | superbook | 223 | 0.249 | 0.066 | 0.462 | 0.484 | -0.022 | -0.66 | · | 0.99 |
| totals_1st_5_innings | lowvig | 2135 | 0.249 | 0.046 | 0.497 | 0.500 | -0.003 | -0.31 | · | 2.54 |
| totals_1st_1_innings | betonlineag | 1530 | 0.249 | 0.070 | 0.488 | 0.481 | 0.007 | 0.57 | · | 1.07 |
| totals_1st_1_innings | betmgm | 2041 | 0.249 | 0.061 | 0.493 | 0.486 | 0.007 | 0.63 | · | 1.07 |
| totals_1st_1_innings | williamhill_us | 1945 | 0.249 | 0.065 | 0.494 | 0.485 | 0.009 | 0.79 | · | 1.07 |
| totals_1st_1_innings | majors | 5645 | 0.249 | 0.062 | 0.489 | 0.486 | 0.003 | 0.51 | · | 1.07 |
| totals_1st_5_innings | fanduel | 5029 | 0.249 | 0.065 | 0.492 | 0.497 | -0.005 | -0.75 | · | 2.56 |
| totals_1st_1_innings | fanduel | 1659 | 0.248 | 0.060 | 0.480 | 0.487 | -0.008 | -0.62 | · | 1.06 |
| totals_1st_1_innings | pinnacle | 2571 | 0.248 | 0.039 | 0.497 | 0.488 | 0.009 | 0.89 | · | 1.07 |
| totals_1st_5_innings | barstool | 437 | 0.248 | 0.055 | 0.519 | 0.500 | 0.020 | 0.82 | · | 2.85 |
| totals_1st_5_innings | soft | 41352 | 0.248 | 0.060 | 0.499 | 0.501 | -0.002 | -0.91 | · | 2.58 |
| totals_1st_5_innings | all | 41358 | 0.248 | 0.060 | 0.499 | 0.501 | -0.002 | -0.91 | · | 2.58 |
| totals_1st_5_innings | betrivers | 698 | 0.248 | 0.055 | 0.507 | 0.501 | 0.006 | 0.31 | · | 2.73 |
| totals_1st_5_innings | unibet_us | 698 | 0.248 | 0.055 | 0.507 | 0.501 | 0.006 | 0.31 | · | 2.73 |
| totals_1st_5_innings | wynnbet | 976 | 0.247 | 0.049 | 0.502 | 0.500 | 0.002 | 0.11 | · | 2.54 |
| totals_1st_5_innings | majors | 14743 | 0.246 | 0.066 | 0.505 | 0.508 | -0.003 | -0.72 | · | 2.59 |
| totals_1st_5_innings | pinnacle | 6 | 0.245 | 0.034 | 0.400 | 0.493 | -0.093 | -0.43 | · | 4.08 |
| totals_1st_5_innings | pointsbetus | 1290 | 0.245 | 0.067 | 0.440 | 0.452 | -0.012 | -0.84 | · | 2.69 |
| h2h_1st_5_innings | pointsbetus | 1279 | 0.244 | 0.067 | 0.564 | 0.529 | -0.007 | -0.45 | · | — |
| h2h_1st_5_innings | unibet_us | 1528 | 0.243 | 0.055 | 0.560 | 0.530 | -0.007 | -0.52 | · | — |
| h2h_1st_5_innings | barstool | 804 | 0.243 | 0.054 | 0.572 | 0.532 | -0.009 | -0.47 | · | — |
| h2h_1st_5_innings | williamhill_us | 3702 | 0.242 | 0.057 | 0.566 | 0.530 | 0.004 | 0.46 | · | — |
| h2h_1st_5_innings | betrivers | 5278 | 0.242 | 0.061 | 0.563 | 0.529 | 0.003 | 0.35 | · | — |
| h2h_1st_5_innings | mybookieag | 3936 | 0.242 | 0.052 | 0.558 | 0.528 | -0.000 | -0.06 | · | — |
| h2h_1st_5_innings | betmgm | 5265 | 0.242 | 0.059 | 0.562 | 0.528 | 0.003 | 0.41 | · | — |
| h2h_1st_5_innings | fanduel | 4988 | 0.242 | 0.055 | 0.561 | 0.528 | 0.002 | 0.21 | · | — |
| h2h_1st_5_innings | betus | 4851 | 0.242 | 0.040 | 0.560 | 0.529 | 0.002 | 0.21 | · | — |
| h2h_1st_5_innings | majors | 19202 | 0.242 | 0.058 | 0.562 | 0.528 | 0.003 | 0.84 | · | — |
| h2h_1st_5_innings | all | 52712 | 0.242 | 0.054 | 0.562 | 0.529 | 0.002 | 1.02 | · | — |
| h2h_1st_5_innings | soft | 52712 | 0.242 | 0.054 | 0.562 | 0.529 | 0.002 | 1.02 | · | — |
| h2h_1st_5_innings | bovada | 5231 | 0.242 | 0.067 | 0.560 | 0.528 | 0.003 | 0.36 | · | — |
| h2h_1st_5_innings | betonlineag | 5193 | 0.242 | 0.039 | 0.560 | 0.529 | 0.003 | 0.35 | · | — |
| h2h_1st_5_innings | draftkings | 5247 | 0.241 | 0.062 | 0.561 | 0.528 | 0.005 | 0.61 | · | — |
| h2h_1st_5_innings | wynnbet | 969 | 0.241 | 0.050 | 0.559 | 0.529 | 0.005 | 0.27 | · | — |
| totals_1st_5_innings | betmgm | 5348 | 0.241 | 0.066 | 0.520 | 0.524 | -0.005 | -0.67 | · | 2.63 |
| h2h_1st_5_innings | lowvig | 2116 | 0.241 | 0.038 | 0.568 | 0.530 | -0.007 | -0.59 | · | — |
| totals_1st_1_innings | all | 13390 | 0.240 | 0.059 | 0.451 | 0.451 | 0.001 | 0.12 | · | 1.10 |
| h2h_1st_5_innings | fanatics | 1482 | 0.240 | 0.067 | 0.576 | 0.526 | 0.019 | 1.34 | · | — |
| h2h_1st_5_innings | superbook | 843 | 0.239 | 0.039 | 0.571 | 0.529 | 0.029 | 1.59 | · | — |
| totals_1st_1_innings | soft | 10819 | 0.238 | 0.064 | 0.441 | 0.442 | -0.001 | -0.30 | · | 1.11 |
| totals_1st_1_innings | barstool | 170 | 0.233 | 0.060 | 0.453 | 0.447 | 0.006 | 0.17 | · | 1.12 |
| totals_1st_1_innings | unibet_us | 397 | 0.228 | 0.055 | 0.383 | 0.382 | 0.001 | 0.05 | · | 1.17 |
| totals_1st_1_innings | betrivers | 981 | 0.223 | 0.056 | 0.354 | 0.382 | -0.028 | -1.84 | · | 1.12 |
| totals_1st_1_innings | bovada | 1873 | 0.206 | 0.068 | 0.309 | 0.317 | -0.008 | -0.74 | · | 1.25 |

## Angle 1 — pre-registered static directional strategies (net of offered vig)

ROI = mean per-$1 PnL net of the offered vig (the retail-bias / shading probe). A +ROI here is a CANDIDATE only if season-sign-consistent AND its edge survives FDR across all static configs (q=0.1) AND the grid's in-sample-best persists OOS (PBO<0.2) — else it is multiple-comparison noise (the E5.4 trap). Per-bet DSR is reported above as global context (a single binary bet's Sharpe is tiny → DSR is harsh).
Static-edge FDR: 0/246 static configs survive.

| market | strategy | book | bucket | games | quotes | ROI | sharpe | season-consistent |
|---|---|---|---|--:|--:|--:|--:|:--:|
| totals_1st_5_innings | always_under | majors | high_ge6p5 | 55 | 107 | 0.2805 | 0.34 | ✓ |
| totals_1st_5_innings | always_under | fanduel | high_ge6p5 | 51 | 51 | 0.2687 | 0.32 | ✓ |
| totals_1st_5_innings | always_under | wynnbet | mid_5to6 | 65 | 65 | 0.1274 | 0.14 | · |
| totals_1st_5_innings | always_under | all | high_ge6p5 | 98 | 328 | 0.0695 | 0.08 | · |
| totals_1st_5_innings | always_under | soft | high_ge6p5 | 98 | 328 | 0.0695 | 0.08 | · |
| totals_1st_5_innings | always_under | superbook | mid_5to6 | 163 | 163 | 0.0610 | 0.07 | · |
| h2h_1st_5_innings | always_home | superbook | all | 843 | 843 | 0.0132 | 0.02 | · |
| totals_1st_5_innings | always_over | mybookieag | mid_5to6 | 1067 | 1073 | -0.0037 | -0.00 | · |
| totals_1st_5_innings | always_under | lowvig | mid_5to6 | 517 | 519 | -0.0045 | -0.01 | · |
| totals_1st_1_innings | always_under | betrivers | all | 981 | 981 | -0.0056 | -0.01 | · |
| totals_1st_1_innings | always_under | betrivers | low_le4p5 | 981 | 981 | -0.0056 | -0.01 | · |
| totals_1st_5_innings | always_over | superbook | low_le4p5 | 677 | 679 | -0.0078 | -0.01 | · |
| totals_1st_5_innings | always_over | barstool | low_le4p5 | 344 | 346 | -0.0089 | -0.01 | · |
| totals_1st_5_innings | always_over | barstool | all | 434 | 437 | -0.0126 | -0.01 | · |
| totals_1st_5_innings | always_over | barstool | mid_5to6 | 81 | 81 | -0.0167 | -0.02 | · |
| h2h_1st_5_innings | always_dog | betonlineag | all | 5193 | 5193 | -0.0195 | -0.02 | · |
| totals_1st_1_innings | always_under | superbook | all | 223 | 223 | -0.0200 | -0.02 | · |
| totals_1st_1_innings | always_under | superbook | low_le4p5 | 223 | 223 | -0.0200 | -0.02 | · |
| totals_1st_1_innings | always_over | pinnacle | all | 2571 | 2571 | -0.0210 | -0.02 | · |
| totals_1st_1_innings | always_over | pinnacle | low_le4p5 | 2571 | 2571 | -0.0210 | -0.02 | · |
| h2h_1st_5_innings | always_dog | betus | all | 4851 | 4851 | -0.0215 | -0.02 | · |
| totals_1st_5_innings | always_under | pointsbetus | high_ge6p5 | 60 | 60 | -0.0224 | -0.03 | · |
| h2h_1st_5_innings | always_dog | unibet_us | all | 1528 | 1528 | -0.0238 | -0.02 | ✓ |
| h2h_1st_5_innings | always_away | lowvig | all | 2116 | 2116 | -0.0241 | -0.02 | · |
| totals_1st_5_innings | always_over | bovada | mid_5to6 | 1455 | 1464 | -0.0244 | -0.03 | · |

## Angle 2 — mechanical-derivation deviation map

Does the book derive the F5/NRFI line by a fixed rule off the consensus main close? `book_slope` ≈ `true_slope` ⇒ the mechanical derivation tracks reality (efficient). **Caveat:** the `runs`-space row (F5 totals `line_vs_realized_runs`) has a structurally large `z` — that residual is the mean-vs-median line convention CONFOUND (totals lines balance action near the median; realized runs are right-skewed), NOT a deviation signal. Only the `prob`-space rows (NRFI / h2h) are clean deviation tests; this map is diagnostic — exploitability is decided by the unit-correct Angle-1 static ROI net of vig.

| market | kind | space | n | book_slope | true_slope | mean_resid | z | ½·hold |
|---|---|---|--:|--:|--:|--:|--:|--:|
| totals_1st_5_innings | line_vs_realized_runs | runs | 5290 | 0.579 | 0.564 | 0.491 | 10.93 | 0.033 |
| totals_1st_1_innings | yrfi_prob | prob | 2552 | 0.023 | 0.024 | 0.008 | 0.86 | 0.030 |
| h2h_1st_5_innings | home_prob | prob | 4531 | 0.864 | 0.941 | 0.003 | 0.39 | 0.028 |

## Candidate shortlist for E2.6

**None.** No derivative cleared the deflated, GAME-level, multiple-comparison-corrected bar → with E5.4 this closes the derivative-edge hope. The honest conclusion stands: value = product-quality calibration + transparency + fantasy, not a cashable derivative edge. Strongest near-miss = `totals_1st_5_innings|always_under|majors|high_ge6p5` (55 games, ROI 0.2805, roi_p 0.0062) — it does NOT survive FDR across the 246 configs and sits in the extreme F5 line tail (lowest-limit corner); at quote-level it looked far larger, but that was the correlated-book-quote inflation the game-level scoring removes. (Forward live capture per E2.0b-fix can still re-open via E2.6 if a prospective CLV signal appears.)

_Generated by `eval_derivatives.py` (E13.13, angles 1+2). Strategies scored GAME-level (correlated book-quotes collapsed per game). Every cell + config is logged in `e13_13_market_grid_results.csv` (no cherry-pick)._