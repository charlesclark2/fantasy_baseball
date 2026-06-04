# Layer 4 — Selective Strategy (standalone OOS sweep)

_Formalizes the manual betting rules and measures edge on the bet-triggered subset._

**Gate-metric asymmetry (intentional):** Totals gate on **roi_110** — totals lines settle at -110 on both sides in the vast majority of cases, so flat -110 is faithful. H2H gates on **roi_devig** (each bet priced at its de-vigged fair odds) — moneyline prices vary by game, and a flat -110 *inflates* favorite/chalk bets (which pay < +100) and *deflates* underdog bets (which pay > +100). roi_devig is 0 under a perfectly-calibrated market, so a positive value means the bet side beat its own market price = genuine selection edge — but it is **vig-free**, i.e. an optimistic upper bound on realized book ROI.

## Totals — ALL seasons (oos_predictions_totals_v1.parquet)  (n_games=7269, markets=['totals'])

_Gate metric: **roi_110** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 0.50 | 0.12 | 4211 | 0.579 | 0.642 | +0.2250 | — | ✅ |
| 0.75 | 0.12 | 3747 | 0.515 | 0.651 | +0.2422 | — | ✅ |
| 1.00 | 0.12 | 3283 | 0.452 | 0.656 | +0.2526 | — | ✅ |
| 1.25 | 0.12 | 2804 | 0.386 | 0.669 | +0.2779 | — | ✅ |
| 1.50 | 0.12 | 2392 | 0.329 | 0.676 | +0.2906 | — | ✅ |
| 2.00 | 0.12 | 1700 ⭐ | 0.234 | 0.689 | +0.3150 | — | ✅ |

- **Layer 4: ✅ PASS** (gate=roi_110) — optimal totals_thr=2.0, h2h_thr=0.12: n_bets 1700, win_rate 0.689, roi_110 +0.3150.

**Totals @ default 1.0 run:**
- over: n=2135 win_rate 0.616 roi +0.1759
- under: n=1148 win_rate 0.731 roi +0.3952
- no-bet n=3874: uncertainty-zone |μ−line|<0.5 frac 0.292 (n=1131); view-below-threshold frac 0.708
- no-bet Brier: model 0.2395 vs market 0.2481

## Totals — season 2023 only  (n_games=2201, markets=['totals'])

_Gate metric: **roi_110** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 0.50 | 0.12 | 1224 | 0.556 | 0.651 | +0.2431 | — | ✅ |
| 0.75 | 0.12 | 1095 | 0.498 | 0.666 | +0.2710 | — | ✅ |
| 1.00 | 0.12 | 979 | 0.445 | 0.677 | +0.2929 | — | ✅ |
| 1.25 | 0.12 | 849 | 0.386 | 0.690 | +0.3177 | — | ✅ |
| 1.50 | 0.12 | 737 | 0.335 | 0.707 | +0.3496 | — | ✅ |
| 2.00 | 0.12 | 535 ⭐ | 0.243 | 0.712 | +0.3596 | — | ✅ |

- **Layer 4: ✅ PASS** (gate=roi_110) — optimal totals_thr=2.0, h2h_thr=0.12: n_bets 535, win_rate 0.712, roi_110 +0.3596.

**Totals @ default 1.0 run:**
- over: n=632 win_rate 0.634 roi +0.2113
- under: n=347 win_rate 0.755 roi +0.4414
- no-bet n=1198: uncertainty-zone |μ−line|<0.5 frac 0.270 (n=324); view-below-threshold frac 0.730
- no-bet Brier: model 0.2444 vs market 0.2502

## Totals — season 2024 only  (n_games=2199, markets=['totals'])

_Gate metric: **roi_110** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 0.50 | 0.12 | 1219 | 0.554 | 0.670 | +0.2795 | — | ✅ |
| 0.75 | 0.12 | 1070 | 0.487 | 0.679 | +0.2971 | — | ✅ |
| 1.00 | 0.12 | 891 | 0.405 | 0.679 | +0.2963 | — | ✅ |
| 1.25 | 0.12 | 741 | 0.337 | 0.704 | +0.3449 | — | ✅ |
| 1.50 | 0.12 | 611 | 0.278 | 0.710 | +0.3560 | — | ✅ |
| 2.00 | 0.12 | 384 ⭐ | 0.175 | 0.734 | +0.4020 | — | ✅ |

- **Layer 4: ✅ PASS** (gate=roi_110) — optimal totals_thr=2.0, h2h_thr=0.12: n_bets 384, win_rate 0.734, roi_110 +0.4020.

**Totals @ default 1.0 run:**
- over: n=454 win_rate 0.628 roi +0.1984
- under: n=437 win_rate 0.732 roi +0.3980
- no-bet n=1271: uncertainty-zone |μ−line|<0.5 frac 0.279 (n=355); view-below-threshold frac 0.721
- no-bet Brier: model 0.2416 vs market 0.2482

## Totals — season 2025 only  (n_games=2201, markets=['totals'])

_Gate metric: **roi_110** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 0.50 | 0.12 | 1262 | 0.573 | 0.656 | +0.2526 | — | ✅ |
| 0.75 | 0.12 | 1122 | 0.510 | 0.668 | +0.2744 | — | ✅ |
| 1.00 | 0.12 | 993 | 0.451 | 0.680 | +0.2977 | — | ✅ |
| 1.25 | 0.12 | 837 | 0.380 | 0.697 | +0.3297 | — | ✅ |
| 1.50 | 0.12 | 705 | 0.320 | 0.702 | +0.3404 | — | ✅ |
| 2.00 | 0.12 | 522 ⭐ | 0.237 | 0.738 | +0.4080 | — | ✅ |

- **Layer 4: ✅ PASS** (gate=roi_110) — optimal totals_thr=2.0, h2h_thr=0.12: n_bets 522, win_rate 0.738, roi_110 +0.4080.

**Totals @ default 1.0 run:**
- over: n=762 win_rate 0.652 roi +0.2452
- under: n=231 win_rate 0.771 roi +0.4711
- no-bet n=1168: uncertainty-zone |μ−line|<0.5 frac 0.298 (n=348); view-below-threshold frac 0.702
- no-bet Brier: model 0.2290 vs market 0.2476

## Totals — season 2026 only  (n_games=668, markets=['totals'])

_Gate metric: **roi_110** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 0.50 | 0.12 | 506 | 0.757 | 0.514 | -0.0190 | — | ✅ |
| 0.75 | 0.12 | 460 | 0.689 | 0.507 | -0.0330 | — | ✅ |
| 1.00 | 0.12 | 420 | 0.629 | 0.502 | -0.0409 | — | ✅ |
| 1.25 | 0.12 | 377 | 0.564 | 0.493 | -0.0581 | — | ✅ |
| 1.50 | 0.12 | 339 | 0.507 | 0.493 | -0.0595 | — | ✅ |
| 2.00 | 0.12 | 259 | 0.388 | 0.475 | -0.0934 | — | ✅ |

- **Layer 4: ❌ FAIL** (gate=roi_110) — no threshold with roi_110>0 AND n_bets≥50.

**Totals @ default 1.0 run:**
- over: n=287 win_rate 0.460 roi -0.1220
- under: n=133 win_rate 0.594 roi +0.1340
- no-bet n=237: uncertainty-zone |μ−line|<0.5 frac 0.439 (n=104); view-below-threshold frac 0.561
- no-bet Brier: model 0.2512 vs market 0.2429

## H2H — ALL seasons (oos_predictions_h2h_v2.parquet)  (n_games=3908, markets=['h2h'])

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 3336 | 0.854 | 0.678 | +0.2950 | +0.3132 | ✅ |
| 1.00 | 0.08 | 3034 | 0.776 | 0.682 | +0.3013 | +0.3388 | ✅ |
| 1.00 | 0.10 | 2856 | 0.731 | 0.683 | +0.3041 | +0.3549 | ✅ |
| 1.00 | 0.12 | 2696 | 0.690 | 0.684 | +0.3065 | +0.3712 | ✅ |
| 1.00 | 0.15 | 2430 | 0.622 | 0.679 | +0.2963 | +0.3893 | ✅ |
| 1.00 | 0.20 | 2024 ⭐ | 0.518 | 0.665 | +0.2696 | +0.4148 | ✅ |

- **Layer 4: ✅ PASS** (gate=roi_devig) — optimal totals_thr=1.0, h2h_thr=0.2: n_bets 2024, win_rate 0.665, roi_devig +0.4148. — ⚠️ roi_devig is **vig-free (optimistic upper bound)**; a roi_devig PASS is **evaluation-pending, NOT deployable** (real book ROI is lower, and the model still fails L1/L3 vs the credible market).

**H2H @ default 0.12** (roi_110 = flat -110; roi_devig = priced at de-vigged fair odds, the honest edge test):
- direction_flip: n=1422 win_rate 0.609 roi_110 +0.1626 roi_devig +0.4264
- magnitude: n=1274 win_rate 0.768 roi_110 +0.4670 roi_devig +0.3096
- no-bet Brier: model 0.2200 vs market 0.2238

## H2H — season 2024 only  (n_games=1621, markets=['h2h'])

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 1406 | 0.867 | 0.680 | +0.2981 | +0.3254 | ✅ |
| 1.00 | 0.08 | 1297 | 0.800 | 0.688 | +0.3130 | +0.3531 | ✅ |
| 1.00 | 0.10 | 1230 | 0.759 | 0.686 | +0.3100 | +0.3611 | ✅ |
| 1.00 | 0.12 | 1171 | 0.722 | 0.688 | +0.3140 | +0.3770 | ✅ |
| 1.00 | 0.15 | 1064 | 0.656 | 0.680 | +0.2990 | +0.3870 | ✅ |
| 1.00 | 0.20 | 877 ⭐ | 0.541 | 0.666 | +0.2713 | +0.4109 | ✅ |

- **Layer 4: ✅ PASS** (gate=roi_devig) — optimal totals_thr=1.0, h2h_thr=0.2: n_bets 877, win_rate 0.666, roi_devig +0.4109. — ⚠️ roi_devig is **vig-free (optimistic upper bound)**; a roi_devig PASS is **evaluation-pending, NOT deployable** (real book ROI is lower, and the model still fails L1/L3 vs the credible market).

**H2H @ default 0.12** (roi_110 = flat -110; roi_devig = priced at de-vigged fair odds, the honest edge test):
- direction_flip: n=616 win_rate 0.622 roi_110 +0.1870 roi_devig +0.4189
- magnitude: n=555 win_rate 0.762 roi_110 +0.4550 roi_devig +0.3304
- no-bet Brier: model 0.2319 vs market 0.2356

## H2H — season 2025 only  (n_games=1659, markets=['h2h'])

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 1373 | 0.828 | 0.696 | +0.3293 | +0.3641 | ✅ |
| 1.00 | 0.08 | 1222 | 0.737 | 0.704 | +0.3436 | +0.4031 | ✅ |
| 1.00 | 0.10 | 1142 | 0.688 | 0.712 | +0.3591 | +0.4320 | ✅ |
| 1.00 | 0.12 | 1062 | 0.640 | 0.716 | +0.3662 | +0.4548 | ✅ |
| 1.00 | 0.15 | 949 | 0.572 | 0.718 | +0.3700 | +0.4859 | ✅ |
| 1.00 | 0.20 | 804 ⭐ | 0.485 | 0.710 | +0.3558 | +0.5193 | ✅ |

- **Layer 4: ✅ PASS** (gate=roi_devig) — optimal totals_thr=1.0, h2h_thr=0.2: n_bets 804, win_rate 0.710, roi_devig +0.5193. — ⚠️ roi_devig is **vig-free (optimistic upper bound)**; a roi_devig PASS is **evaluation-pending, NOT deployable** (real book ROI is lower, and the model still fails L1/L3 vs the credible market).

**H2H @ default 0.12** (roi_110 = flat -110; roi_devig = priced at de-vigged fair odds, the honest edge test):
- direction_flip: n=573 win_rate 0.681 roi_110 +0.2994 roi_devig +0.5540
- magnitude: n=489 win_rate 0.757 roi_110 +0.4445 roi_devig +0.3387
- no-bet Brier: model 0.2236 vs market 0.2295

## H2H — season 2026 only  (n_games=628, markets=['h2h'])

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 557 | 0.887 | 0.630 | +0.2030 | +0.1573 | ✅ |
| 1.00 | 0.08 | 515 | 0.820 | 0.614 | +0.1714 | +0.1499 | ✅ |
| 1.00 | 0.10 | 484 | 0.771 | 0.607 | +0.1597 | +0.1572 | ✅ |
| 1.00 | 0.12 | 463 | 0.737 | 0.603 | +0.1504 | +0.1648 | ✅ |
| 1.00 | 0.15 | 417 | 0.664 | 0.588 | +0.1216 | +0.1751 | ✅ |
| 1.00 | 0.20 | 343 ⭐ | 0.546 | 0.557 | +0.0631 | +0.1799 | ✅ |

- **Layer 4: ✅ PASS** (gate=roi_devig) — optimal totals_thr=1.0, h2h_thr=0.2: n_bets 343, win_rate 0.557, roi_devig +0.1799. — ⚠️ roi_devig is **vig-free (optimistic upper bound)**; a roi_devig PASS is **evaluation-pending, NOT deployable** (real book ROI is lower, and the model still fails L1/L3 vs the credible market).

**H2H @ default 0.12** (roi_110 = flat -110; roi_devig = priced at de-vigged fair odds, the honest edge test):
- direction_flip: n=233 win_rate 0.399 roi_110 -0.2380 roi_devig +0.1326
- magnitude: n=230 win_rate 0.809 roi_110 +0.5439 roi_devig +0.1974
- no-bet Brier: model 0.1742 vs market 0.1707

