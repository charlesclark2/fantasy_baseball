# NF-INJ2c node 1 — the games-floor hypothesis: **REFUTED**

> ⛔ A DIAGNOSIS, not a bake-off: no arm is scored against a realized outcome and no gate is computed here. Generated 2026-08-29T22:33:53.572714+00:00 over folds 2019, 2020, 2021, 2022, 2023, 2024, 2025.

**`gsafe == proj_games` on EVERY row of EVERY diagnosed fold — the assignment's games floor never moved a divisor, so it cannot have produced a single violation. The hypothesis is refuted by a two-sided measurement, not by an absent effect: the mechanism could not act (NF1.9 / NF-D20).**

## 1. Could the floor act? (counted per fold, never assumed)

| fold | rows | eligible | min `proj_games` | non-finite | `g <= 0.25` | `games_floor_binding()` (recorded defn) | rows the KERNEL actually floored |
|---|---|---|---|---|---|---|---|
| 2019 | 678 | 619 | 0.966752 | 0 | 0 | 0 | 0 |
| 2020 | 714 | 645 | 0.948242 | 0 | 0 | 0 | 0 |
| 2021 | 734 | 665 | 1.215213 | 0 | 0 | 0 | 0 |
| 2022 | 753 | 682 | 0.881932 | 0 | 0 | 0 | 0 |
| 2023 | 729 | 669 | 0.861913 | 0 | 0 | 0 | 0 |
| 2024 | 698 | 645 | 0.826719 | 0 | 0 | 0 | 0 |
| 2025 | 746 | 688 | 0.814474 | 0 | 0 | 0 | 0 |

⚠️ the two right-hand columns are DIFFERENT definitions — `games_floor_binding()` counts `isfinite(g) & (g < 0.25)`, the kernel floors `~(isfinite(g) & (g > 0.25))`. Both are shown because "the floor is inert" is the claim under test and must not be read off the narrower one (NF1.7 (a)).

## 2. Every violation, attributed

| fold | arm | players | attributable | violations | by mechanism | clamp-lo rows | clamp-hi rows |
|---|---|---|---|---|---|---|---|
| 2019 | `mvp1_null` | 0 | 0 | 0 | — | 0 | 0 |
| 2019 | `incumbent` | 19 | 19 | 33 | M3_STAT_MIX_OR_PROMOTION=33 | 20 | 6 |
| 2019 | `points_rate_permute` | 2 | 2 | 2 | M3_STAT_MIX_OR_PROMOTION=2 | 2 | 1 |
| 2019 | `rate_refit` | 1 | 1 | 1 | M3_STAT_MIX_OR_PROMOTION=1 | 2 | 0 |
| 2019 | `points_rate_stratified` | 2 | 2 | 2 | M3_STAT_MIX_OR_PROMOTION=2 | 2 | 0 |
| 2019 | `rate_refit_stratified` | 1 | 1 | 1 | M3_STAT_MIX_OR_PROMOTION=1 | 2 | 0 |
| 2019 | `stratified` | 15 | 15 | 24 | M3_STAT_MIX_OR_PROMOTION=24 | 1 | 2 |
| 2019 | `feasibility_clamp` | 2 | 2 | 2 | M3_STAT_MIX_OR_PROMOTION=2 | 20 | 5 |
| 2020 | `mvp1_null` | 0 | 0 | 0 | — | 0 | 0 |
| 2020 | `incumbent` | 23 | 23 | 44 | M3_STAT_MIX_OR_PROMOTION=44 | 19 | 8 |
| 2020 | `points_rate_permute` | 0 | 0 | 0 | — | 1 | 1 |
| 2020 | `rate_refit` | 0 | 0 | 0 | — | 1 | 1 |
| 2020 | `points_rate_stratified` | 0 | 0 | 0 | — | 1 | 0 |
| 2020 | `rate_refit_stratified` | 0 | 0 | 0 | — | 1 | 0 |
| 2020 | `stratified` | 14 | 14 | 23 | M3_STAT_MIX_OR_PROMOTION=23 | 1 | 1 |
| 2020 | `feasibility_clamp` | 2 | 2 | 2 | M3_STAT_MIX_OR_PROMOTION=2 | 19 | 6 |
| 2021 | `mvp1_null` | 0 | 0 | 0 | — | 0 | 0 |
| 2021 | `incumbent` | 17 | 17 | 30 | M3_STAT_MIX_OR_PROMOTION=30 | 18 | 4 |
| 2021 | `points_rate_permute` | 0 | 0 | 0 | — | 1 | 0 |
| 2021 | `rate_refit` | 0 | 0 | 0 | — | 1 | 0 |
| 2021 | `points_rate_stratified` | 0 | 0 | 0 | — | 0 | 0 |
| 2021 | `rate_refit_stratified` | 1 | 1 | 1 | M3_STAT_MIX_OR_PROMOTION=1 | 0 | 0 |
| 2021 | `stratified` | 9 | 9 | 15 | M3_STAT_MIX_OR_PROMOTION=15 | 3 | 0 |
| 2021 | `feasibility_clamp` | 0 | 0 | 0 | — | 18 | 1 |
| 2022 | `mvp1_null` | 0 | 0 | 0 | — | 0 | 0 |
| 2022 | `incumbent` | 24 | 24 | 39 | M3_STAT_MIX_OR_PROMOTION=39 | 17 | 10 |
| 2022 | `points_rate_permute` | 0 | 0 | 0 | — | 3 | 0 |
| 2022 | `rate_refit` | 0 | 0 | 0 | — | 0 | 0 |
| 2022 | `points_rate_stratified` | 0 | 0 | 0 | — | 2 | 0 |
| 2022 | `rate_refit_stratified` | 0 | 0 | 0 | — | 1 | 0 |
| 2022 | `stratified` | 5 | 5 | 7 | M3_STAT_MIX_OR_PROMOTION=7 | 4 | 0 |
| 2022 | `feasibility_clamp` | 0 | 0 | 0 | — | 17 | 3 |
| 2023 | `mvp1_null` | 0 | 0 | 0 | — | 0 | 0 |
| 2023 | `incumbent` | 23 | 23 | 40 | M3_STAT_MIX_OR_PROMOTION=40 | 27 | 8 |
| 2023 | `points_rate_permute` | 0 | 0 | 0 | — | 1 | 2 |
| 2023 | `rate_refit` | 0 | 0 | 0 | — | 3 | 2 |
| 2023 | `points_rate_stratified` | 0 | 0 | 0 | — | 2 | 2 |
| 2023 | `rate_refit_stratified` | 0 | 0 | 0 | — | 2 | 2 |
| 2023 | `stratified` | 5 | 5 | 7 | M3_STAT_MIX_OR_PROMOTION=7 | 6 | 2 |
| 2023 | `feasibility_clamp` | 3 | 3 | 3 | M3_STAT_MIX_OR_PROMOTION=3 | 27 | 5 |
| 2024 | `mvp1_null` | 0 | 0 | 0 | — | 0 | 0 |
| 2024 | `incumbent` | 11 | 11 | 23 | M3_STAT_MIX_OR_PROMOTION=23 | 20 | 14 |
| 2024 | `points_rate_permute` | 0 | 0 | 0 | — | 0 | 0 |
| 2024 | `rate_refit` | 0 | 0 | 0 | — | 0 | 0 |
| 2024 | `points_rate_stratified` | 0 | 0 | 0 | — | 2 | 0 |
| 2024 | `rate_refit_stratified` | 0 | 0 | 0 | — | 1 | 0 |
| 2024 | `stratified` | 7 | 7 | 12 | M3_STAT_MIX_OR_PROMOTION=12 | 7 | 3 |
| 2024 | `feasibility_clamp` | 0 | 0 | 0 | — | 20 | 9 |
| 2025 | `mvp1_null` | 0 | 0 | 0 | — | 0 | 0 |
| 2025 | `incumbent` | 17 | 17 | 31 | M3_STAT_MIX_OR_PROMOTION=31 | 25 | 10 |
| 2025 | `points_rate_permute` | 0 | 0 | 0 | — | 3 | 0 |
| 2025 | `rate_refit` | 0 | 0 | 0 | — | 3 | 0 |
| 2025 | `points_rate_stratified` | 0 | 0 | 0 | — | 3 | 0 |
| 2025 | `rate_refit_stratified` | 0 | 0 | 0 | — | 3 | 0 |
| 2025 | `stratified` | 5 | 5 | 7 | M3_STAT_MIX_OR_PROMOTION=7 | 7 | 3 |
| 2025 | `feasibility_clamp` | 0 | 0 | 0 | — | 25 | 7 |

## 3. WHAT survives, not just how much — the residual's SHAPE

| arm | players/fold | folds with any | worst × over | median × over | min games on a violating row | median games | rows under 2 games |
|---|---|---|---|---|---|---|---|
| `mvp1_null` | 0.0 | 0/7 | None | None | None | None | 0 (None) |
| `incumbent` | 19.1429 | 7/7 | 2.51 | 1.28 | 0.815 | 3.0 | 82 (0.3417) |
| `points_rate_permute` | 0.2857 | 1/7 | 1.09 | 1.075 | 16.5 | 16.5 | 0 (0.0) |
| `rate_refit` | 0.1429 | 1/7 | 1.06 | 1.06 | 16.5 | 16.5 | 0 (0.0) |
| `points_rate_stratified` | 0.2857 | 1/7 | 1.1 | 1.095 | 16.5 | 16.5 | 0 (0.0) |
| `rate_refit_stratified` | 0.2857 | 2/7 | 1.1 | 1.06 | 8.0 | 12.25 | 0 (0.0) |
| `stratified` | 8.5714 | 7/7 | 1.85 | 1.18 | 0.815 | 3.5 | 35 (0.3684) |
| `feasibility_clamp` | 1.0 | 3/7 | 1.0 | 1.0 | 1.724 | 5.429 | 1 (0.1429) |

⭐ a COUNT cannot tell a rounding at the envelope edge from the founding NF-INJ1 defect, and the two license different clauses — NF-INJ1's headline row is *Easton Stick at 1.9 expected games with 82.7 pass attempts per game*, so "under 2 games" is the envelope's own founding case and ⛔ not a threshold invented here.


## 4. The violating rows themselves — the evidence NF-INJ2b's record did not keep

### 2019 · `incumbent`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| JIMMY GAROPPOLO | QB | passAtt | 350.6 | 3.5 | 3.5 | False | 3.0848 | — | 100.18 | 45.44 | 2.2 | 15.7119 | 48.4657 | `M3_STAT_MIX_OR_PROMOTION` |
| JIMMY GAROPPOLO | QB | passYds | 2680.1 | 3.5 | 3.5 | False | 3.0848 | — | 765.75 | 371.2 | 2.06 | 15.7119 | 48.4657 | `M3_STAT_MIX_OR_PROMOTION` |
| KYLE LAULETTA | QB | passAtt | 183.2 | 2.0 | 2.0 | False | 3.5 | HI | 91.6 | 45.44 | 2.02 | 11.5731 | 40.511 | `M3_STAT_MIX_OR_PROMOTION` |
| CARDALE JONES | QB | passAtt | 84.6 | 0.9668 | 0.9668 | False | 2.7672 | — | 87.53 | 45.44 | 1.93 | 14.216 | 39.3701 | `M3_STAT_MIX_OR_PROMOTION` |
| CARSON WENTZ | QB | passAtt | 612.5 | 7.5 | 7.5 | False | 2.1358 | — | 81.67 | 45.44 | 1.8 | 18.9776 | 40.5334 | `M3_STAT_MIX_OR_PROMOTION` |
| KYLE LAULETTA | QB | passYds | 1296.6 | 2.0 | 2.0 | False | 3.5 | HI | 648.28 | 371.2 | 1.75 | 11.5731 | 40.511 | `M3_STAT_MIX_OR_PROMOTION` |
| NICK FOLES | QB | passAtt | 316.2 | 4.0 | 4.0 | False | 2.5696 | — | 79.06 | 45.44 | 1.74 | 13.5658 | 34.8662 | `M3_STAT_MIX_OR_PROMOTION` |
| CARDALE JONES | QB | passYds | 625.0 | 0.9668 | 0.9668 | False | 2.7672 | — | 646.54 | 371.2 | 1.74 | 14.216 | 39.3701 | `M3_STAT_MIX_OR_PROMOTION` |
| TYLER BRAY | QB | passAtt | 74.5 | 0.9668 | 0.9668 | False | 2.5843 | — | 77.02 | 45.44 | 1.69 | 13.8978 | 35.9407 | `M3_STAT_MIX_OR_PROMOTION` |
| KYLE ALLEN | QB | passAtt | 223.2 | 3.0 | 3.0 | False | 2.4595 | — | 74.39 | 45.44 | 1.64 | 16.0738 | 39.5291 | `M3_STAT_MIX_OR_PROMOTION` |
| CARSON WENTZ | QB | passYds | 4452.7 | 7.5 | 7.5 | False | 2.1358 | — | 593.69 | 371.2 | 1.6 | 18.9776 | 40.5334 | `M3_STAT_MIX_OR_PROMOTION` |
| JAMEIS WINSTON | QB | passAtt | 532.5 | 7.5 | 7.5 | False | 1.9122 | — | 70.99 | 45.44 | 1.56 | 18.2149 | 34.8294 | `M3_STAT_MIX_OR_PROMOTION` |
| NICK FOLES | QB | passYds | 2238.1 | 4.0 | 4.0 | False | 2.5696 | — | 559.53 | 371.2 | 1.51 | 13.5658 | 34.8662 | `M3_STAT_MIX_OR_PROMOTION` |
| TYLER BRAY | QB | passYds | 539.9 | 0.9668 | 0.9668 | False | 2.5843 | — | 558.46 | 371.2 | 1.5 | 13.8978 | 35.9407 | `M3_STAT_MIX_OR_PROMOTION` |
| KYLE ALLEN | QB | passYds | 1674.3 | 3.0 | 3.0 | False | 2.4595 | — | 558.09 | 371.2 | 1.5 | 16.0738 | 39.5291 | `M3_STAT_MIX_OR_PROMOTION` |
| DEREK ANDERSON | QB | passAtt | 132.5 | 2.0 | 2.0 | False | 2.1978 | — | 66.23 | 45.44 | 1.46 | 12.7639 | 28.0582 | `M3_STAT_MIX_OR_PROMOTION` |
| JAMEIS WINSTON | QB | passYds | 4054.2 | 7.5 | 7.5 | False | 1.9122 | — | 540.56 | 371.2 | 1.46 | 18.2149 | 34.8294 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT MOORE | QB | passAtt | 123.1 | 1.9335 | 1.9335 | False | 1.9058 | — | 63.65 | 45.44 | 1.4 | 14.9235 | 28.4395 | `M3_STAT_MIX_OR_PROMOTION` |
| CAM NEWTON | QB | passAtt | 542.1 | 9.0 | 9.0 | False | 1.7068 | — | 60.24 | 45.44 | 1.33 | 19.3363 | 33.0028 | `M3_STAT_MIX_OR_PROMOTION` |
| DEREK ANDERSON | QB | passYds | 956.0 | 2.0 | 2.0 | False | 2.1978 | — | 478.0 | 371.2 | 1.29 | 12.7639 | 28.0582 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT MOORE | QB | passYds | 894.0 | 1.9335 | 1.9335 | False | 1.9058 | — | 462.37 | 371.2 | 1.25 | 14.9235 | 28.4395 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT RYAN | QB | passAtt | 565.9 | 10.0 | 10.0 | False | 1.5015 | — | 56.59 | 45.44 | 1.25 | 20.3368 | 30.5366 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT RYAN | QB | passYds | 4524.2 | 10.0 | 10.0 | False | 1.5015 | — | 452.42 | 371.2 | 1.22 | 20.3368 | 30.5366 | `M3_STAT_MIX_OR_PROMOTION` |
| JOE FLACCO | QB | passAtt | 350.8 | 6.5 | 6.5 | False | 1.3422 | — | 53.96 | 45.44 | 1.19 | 15.6588 | 21.0174 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passAtt | 507.4 | 9.5 | 9.5 | False | 1.6106 | — | 53.42 | 45.44 | 1.18 | 21.2424 | 34.211 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passYds | 4073.6 | 9.5 | 9.5 | False | 1.6106 | — | 428.8 | 371.2 | 1.16 | 21.2424 | 34.211 | `M3_STAT_MIX_OR_PROMOTION` |
| CAM NEWTON | QB | passYds | 3833.5 | 9.0 | 9.0 | False | 1.7068 | — | 425.94 | 371.2 | 1.15 | 19.3363 | 33.0028 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE RUDOCK | QB | passAtt | 84.5 | 1.6113 | 1.6113 | False | 2.289 | — | 52.42 | 45.44 | 1.15 | 10.287 | 23.5545 | `M3_STAT_MIX_OR_PROMOTION` |
| COOPER RUSH | QB | passAtt | 76.3 | 1.5 | 1.5 | False | 1.7077 | — | 50.84 | 45.44 | 1.12 | 13.9814 | 23.8686 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passAtt | 462.1 | 9.5 | 9.5 | False | 1.4817 | — | 48.64 | 45.44 | 1.07 | 19.5479 | 28.9631 | `M3_STAT_MIX_OR_PROMOTION` |
| ANDREW LUCK | QB | passAtt | 790.0 | 16.5 | 16.5 | False | 1.2478 | — | 47.88 | 45.44 | 1.05 | 19.6985 | 24.5805 | `M3_STAT_MIX_OR_PROMOTION` |
| ANDY DALTON | QB | passAtt | 303.9 | 6.5 | 6.5 | False | 1.3034 | — | 46.75 | 45.44 | 1.03 | 16.6909 | 21.7556 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE RUDOCK | QB | passYds | 609.9 | 1.6113 | 1.6113 | False | 2.289 | — | 378.52 | 371.2 | 1.02 | 10.287 | 23.5545 | `M3_STAT_MIX_OR_PROMOTION` |

### 2019 · `points_rate_permute`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ANDREW LUCK | QB | passAtt | 814.7 | 16.5 | 16.5 | False | 1.2868 | — | 49.38 | 45.44 | 1.09 | 19.6985 | 25.349 | `M3_STAT_MIX_OR_PROMOTION` |
| LAMAR JACKSON | QB | rushAtt | 205.3 | 16.5 | 16.5 | False | 1.5522 | — | 12.44 | 11.73 | 1.06 | 11.9603 | 18.5643 | `M3_STAT_MIX_OR_PROMOTION` |

### 2019 · `rate_refit`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LAMAR JACKSON | QB | rushAtt | 205.3 | 16.5 | 16.5 | False | 1.5522 | — | 12.44 | 11.73 | 1.06 | 11.9603 | 18.5643 | `M3_STAT_MIX_OR_PROMOTION` |

### 2019 · `points_rate_stratified`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LAMAR JACKSON | QB | rushAtt | 212.9 | 16.5 | 16.5 | False | 1.6092 | — | 12.9 | 11.73 | 1.1 | 11.9603 | 19.2453 | `M3_STAT_MIX_OR_PROMOTION` |
| ANDREW LUCK | QB | passAtt | 814.7 | 16.5 | 16.5 | False | 1.2868 | — | 49.38 | 45.44 | 1.09 | 19.6985 | 25.349 | `M3_STAT_MIX_OR_PROMOTION` |

### 2019 · `rate_refit_stratified`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LAMAR JACKSON | QB | rushAtt | 212.9 | 16.5 | 16.5 | False | 1.6092 | — | 12.9 | 11.73 | 1.1 | 11.9603 | 19.2453 | `M3_STAT_MIX_OR_PROMOTION` |

### 2019 · `stratified`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CARDALE JONES | QB | passAtt | 79.7 | 0.9668 | 0.9668 | False | 2.606 | — | 82.43 | 45.44 | 1.81 | 14.216 | 37.0714 | `M3_STAT_MIX_OR_PROMOTION` |
| NICK FOLES | QB | passAtt | 309.8 | 4.0 | 4.0 | False | 2.5176 | — | 77.45 | 45.44 | 1.7 | 13.5658 | 34.1584 | `M3_STAT_MIX_OR_PROMOTION` |
| CARDALE JONES | QB | passYds | 588.6 | 0.9668 | 0.9668 | False | 2.606 | — | 608.87 | 371.2 | 1.64 | 14.216 | 37.0714 | `M3_STAT_MIX_OR_PROMOTION` |
| NICK FOLES | QB | passYds | 2192.8 | 4.0 | 4.0 | False | 2.5176 | — | 548.19 | 371.2 | 1.48 | 13.5658 | 34.1584 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT RYAN | QB | passAtt | 565.9 | 10.0 | 10.0 | False | 1.5015 | — | 56.59 | 45.44 | 1.25 | 20.3368 | 30.5366 | `M3_STAT_MIX_OR_PROMOTION` |
| TYLER BRAY | QB | passAtt | 54.7 | 0.9668 | 0.9668 | False | 1.9 | — | 56.63 | 45.44 | 1.25 | 13.8978 | 26.4223 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT RYAN | QB | passYds | 4524.2 | 10.0 | 10.0 | False | 1.5015 | — | 452.42 | 371.2 | 1.22 | 20.3368 | 30.5366 | `M3_STAT_MIX_OR_PROMOTION` |
| DEREK ANDERSON | QB | passAtt | 108.7 | 2.0 | 2.0 | False | 1.8033 | — | 54.34 | 45.44 | 1.2 | 12.7639 | 23.021 | `M3_STAT_MIX_OR_PROMOTION` |
| KYLE LAULETTA | QB | passAtt | 109.1 | 2.0 | 2.0 | False | 2.0833 | — | 54.53 | 45.44 | 1.2 | 11.5731 | 24.1131 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passAtt | 510.5 | 9.5 | 9.5 | False | 1.637 | — | 53.74 | 45.44 | 1.18 | 19.5479 | 31.9984 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passAtt | 507.4 | 9.5 | 9.5 | False | 1.6106 | — | 53.42 | 45.44 | 1.18 | 21.2424 | 34.211 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passYds | 4073.6 | 9.5 | 9.5 | False | 1.6106 | — | 428.8 | 371.2 | 1.16 | 21.2424 | 34.211 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT MOORE | QB | passAtt | 99.3 | 1.9335 | 1.9335 | False | 1.5385 | — | 51.38 | 45.44 | 1.13 | 14.9235 | 22.9606 | `M3_STAT_MIX_OR_PROMOTION` |
| TYLER BRAY | QB | passYds | 396.9 | 0.9668 | 0.9668 | False | 1.9 | — | 410.58 | 371.2 | 1.11 | 13.8978 | 26.4223 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passYds | 3880.4 | 9.5 | 9.5 | False | 1.637 | — | 408.46 | 371.2 | 1.1 | 19.5479 | 31.9984 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE RUDOCK | QB | passAtt | 79.0 | 1.6113 | 1.6113 | False | 2.1418 | — | 49.05 | 45.44 | 1.08 | 10.287 | 22.0357 | `M3_STAT_MIX_OR_PROMOTION` |
| DEREK ANDERSON | QB | passYds | 784.4 | 2.0 | 2.0 | False | 1.8033 | — | 392.2 | 371.2 | 1.06 | 12.7639 | 23.021 | `M3_STAT_MIX_OR_PROMOTION` |
| ANDREW LUCK | QB | passAtt | 790.0 | 16.5 | 16.5 | False | 1.2478 | — | 47.88 | 45.44 | 1.05 | 19.6985 | 24.5805 | `M3_STAT_MIX_OR_PROMOTION` |
| KYLE LAULETTA | QB | passYds | 771.8 | 2.0 | 2.0 | False | 2.0833 | — | 385.88 | 371.2 | 1.04 | 11.5731 | 24.1131 | `M3_STAT_MIX_OR_PROMOTION` |
| JOE FLACCO | QB | passAtt | 304.5 | 6.5 | 6.5 | False | 1.1652 | — | 46.85 | 45.44 | 1.03 | 15.6588 | 18.2479 | `M3_STAT_MIX_OR_PROMOTION` |
| CARSON WENTZ | QB | passAtt | 350.7 | 7.5 | 7.5 | False | 1.2227 | — | 46.75 | 45.44 | 1.03 | 18.9776 | 23.2057 | `M3_STAT_MIX_OR_PROMOTION` |
| PHILIP RIVERS | QB | passAtt | 439.7 | 9.5 | 9.5 | False | 1.2901 | — | 46.28 | 45.44 | 1.02 | 17.8568 | 23.0367 | `M3_STAT_MIX_OR_PROMOTION` |
| ANDY DALTON | QB | passAtt | 302.2 | 6.5 | 6.5 | False | 1.2964 | — | 46.49 | 45.44 | 1.02 | 16.6909 | 21.6383 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT MOORE | QB | passYds | 721.7 | 1.9335 | 1.9335 | False | 1.5385 | — | 373.25 | 371.2 | 1.01 | 14.9235 | 22.9606 | `M3_STAT_MIX_OR_PROMOTION` |

### 2019 · `feasibility_clamp`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| JOE FLACCO | QB | passAtt | 295.4 | 6.5 | 6.5 | False | 1.1302 | — | 45.44 | 45.44 | 1.0 | 15.6588 | 17.6979 | `M3_STAT_MIX_OR_PROMOTION` |
| ANDY DALTON | QB | passAtt | 295.4 | 6.5 | 6.5 | False | 1.267 | — | 45.44 | 45.44 | 1.0 | 16.6909 | 21.1496 | `M3_STAT_MIX_OR_PROMOTION` |

### 2020 · `incumbent`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CAM NEWTON | QB | passAtt | 342.1 | 3.0 | 3.0 | False | 3.5 | HI | 114.04 | 45.44 | 2.51 | 16.2028 | 56.7063 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHONE KIZER | QB | passAtt | 251.4 | 2.2126 | 2.2126 | False | 3.5 | HI | 113.63 | 45.44 | 2.5 | 14.4246 | 50.4996 | `M3_STAT_MIX_OR_PROMOTION` |
| BRANDON ALLEN | QB | passAtt | 270.4 | 2.5 | 2.5 | False | 3.3525 | — | 108.16 | 45.44 | 2.38 | 14.5192 | 48.6819 | `M3_STAT_MIX_OR_PROMOTION` |
| CAM NEWTON | QB | passYds | 2457.7 | 3.0 | 3.0 | False | 3.5 | HI | 819.23 | 371.2 | 2.21 | 16.2028 | 56.7063 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHONE KIZER | QB | passYds | 1712.4 | 2.2126 | 2.2126 | False | 3.5 | HI | 773.93 | 371.2 | 2.08 | 14.4246 | 50.4996 | `M3_STAT_MIX_OR_PROMOTION` |
| BRANDON ALLEN | QB | passYds | 1863.6 | 2.5 | 2.5 | False | 3.3525 | — | 745.45 | 371.2 | 2.01 | 14.5192 | 48.6819 | `M3_STAT_MIX_OR_PROMOTION` |
| DREW LOCK | QB | passAtt | 370.1 | 4.5 | 4.5 | False | 2.3659 | — | 82.25 | 45.44 | 1.81 | 16.2534 | 38.4512 | `M3_STAT_MIX_OR_PROMOTION` |
| CODY KESSLER | QB | passAtt | 176.9 | 2.2126 | 2.2126 | False | 2.7459 | — | 79.95 | 45.44 | 1.76 | 12.2092 | 33.5252 | `M3_STAT_MIX_OR_PROMOTION` |
| CHAD KELLY | QB | passAtt | 73.7 | 0.9482 | 0.9482 | False | 2.6211 | — | 77.7 | 45.44 | 1.71 | 14.3828 | 37.7251 | `M3_STAT_MIX_OR_PROMOTION` |
| WILL GRIER | QB | passAtt | 154.6 | 2.0 | 2.0 | False | 2.2741 | — | 77.3 | 45.44 | 1.7 | 13.0658 | 29.7131 | `M3_STAT_MIX_OR_PROMOTION` |
| CHAD KELLY | QB | passYds | 537.3 | 0.9482 | 0.9482 | False | 2.6211 | — | 566.66 | 371.2 | 1.53 | 14.3828 | 37.7251 | `M3_STAT_MIX_OR_PROMOTION` |
| DREW LOCK | QB | passYds | 2561.4 | 4.5 | 4.5 | False | 2.3659 | — | 569.19 | 371.2 | 1.53 | 16.2534 | 38.4512 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE RUDOCK | QB | passAtt | 106.0 | 1.5804 | 1.5804 | False | 3.3405 | — | 67.09 | 45.44 | 1.48 | 9.2072 | 30.7782 | `M3_STAT_MIX_OR_PROMOTION` |
| RYAN FINLEY | QB | passAtt | 234.9 | 3.5 | 3.5 | False | 2.2195 | — | 67.12 | 45.44 | 1.48 | 13.1182 | 29.1175 | `M3_STAT_MIX_OR_PROMOTION` |
| NICK FOLES | QB | passAtt | 193.1 | 3.0 | 3.0 | False | 1.9502 | — | 64.35 | 45.44 | 1.42 | 14.594 | 28.46 | `M3_STAT_MIX_OR_PROMOTION` |
| KYLE LAULETTA | QB | passAtt | 81.6 | 1.2643 | 1.2643 | False | 2.6386 | — | 64.51 | 45.44 | 1.42 | 11.1193 | 29.3595 | `M3_STAT_MIX_OR_PROMOTION` |
| CODY KESSLER | QB | passYds | 1157.4 | 2.2126 | 2.2126 | False | 2.7459 | — | 523.12 | 371.2 | 1.41 | 12.2092 | 33.5252 | `M3_STAT_MIX_OR_PROMOTION` |
| WILL GRIER | QB | passYds | 1016.9 | 2.0 | 2.0 | False | 2.2741 | — | 508.47 | 371.2 | 1.37 | 13.0658 | 29.7131 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT RYAN | QB | passAtt | 575.0 | 9.5 | 9.5 | False | 1.4848 | — | 60.53 | 45.44 | 1.33 | 20.0409 | 29.7566 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE RUDOCK | QB | passYds | 765.3 | 1.5804 | 1.5804 | False | 3.3405 | — | 484.22 | 371.2 | 1.3 | 9.2072 | 30.7782 | `M3_STAT_MIX_OR_PROMOTION` |
| NICK MULLENS | QB | passAtt | 147.5 | 2.5 | 2.5 | False | 1.9291 | — | 58.99 | 45.44 | 1.3 | 14.4828 | 27.9372 | `M3_STAT_MIX_OR_PROMOTION` |
| DWAYNE HASKINS | QB | passAtt | 311.3 | 5.5 | 5.5 | False | 1.9702 | — | 56.61 | 45.44 | 1.25 | 12.4112 | 24.4554 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT RYAN | QB | passYds | 4329.2 | 9.5 | 9.5 | False | 1.4848 | — | 455.7 | 371.2 | 1.23 | 20.0409 | 29.7566 | `M3_STAT_MIX_OR_PROMOTION` |
| KYLE LAULETTA | QB | passYds | 576.8 | 1.2643 | 1.2643 | False | 2.6386 | — | 456.18 | 371.2 | 1.23 | 11.1193 | 29.3595 | `M3_STAT_MIX_OR_PROMOTION` |
| NICK FOLES | QB | passYds | 1352.2 | 3.0 | 3.0 | False | 1.9502 | — | 450.74 | 371.2 | 1.21 | 14.594 | 28.46 | `M3_STAT_MIX_OR_PROMOTION` |
| C.J. BEATHARD | QB | passAtt | 172.2 | 3.1608 | 3.1608 | False | 1.8155 | — | 54.47 | 45.44 | 1.2 | 13.8235 | 25.1022 | `M3_STAT_MIX_OR_PROMOTION` |
| RYAN FINLEY | QB | passYds | 1560.4 | 3.5 | 3.5 | False | 2.2195 | — | 445.84 | 371.2 | 1.2 | 13.1182 | 29.1175 | `M3_STAT_MIX_OR_PROMOTION` |
| CAM NEWTON | QB | rushAtt | 41.8 | 3.0 | 3.0 | False | 3.5 | HI | 13.93 | 11.73 | 1.19 | 16.2028 | 56.7063 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passAtt | 512.0 | 9.5 | 9.5 | False | 1.8055 | — | 53.9 | 45.44 | 1.19 | 18.2626 | 32.973 | `M3_STAT_MIX_OR_PROMOTION` |
| NICK MULLENS | QB | passYds | 1098.2 | 2.5 | 2.5 | False | 1.9291 | — | 439.26 | 371.2 | 1.18 | 14.4828 | 27.9372 | `M3_STAT_MIX_OR_PROMOTION` |
| CARSON WENTZ | QB | passAtt | 558.0 | 10.5 | 10.5 | False | 1.4174 | — | 53.14 | 45.44 | 1.17 | 18.7743 | 26.6103 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passAtt | 477.4 | 9.0 | 9.0 | False | 1.6606 | — | 53.05 | 45.44 | 1.17 | 19.9587 | 33.1457 | `M3_STAT_MIX_OR_PROMOTION` |
| KEVIN HOGAN | QB | passAtt | 130.8 | 2.5286 | 2.5286 | False | 2.0222 | — | 51.72 | 45.44 | 1.14 | 11.9463 | 24.1591 | `M3_STAT_MIX_OR_PROMOTION` |
| BEN ROETHLISBERGER | QB | passAtt | 463.0 | 9.0 | 9.0 | False | 1.362 | — | 51.44 | 45.44 | 1.13 | 18.0674 | 24.6085 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passYds | 3945.7 | 9.5 | 9.5 | False | 1.8055 | — | 415.34 | 371.2 | 1.12 | 18.2626 | 32.973 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passYds | 3732.3 | 9.0 | 9.0 | False | 1.6606 | — | 414.7 | 371.2 | 1.12 | 19.9587 | 33.1457 | `M3_STAT_MIX_OR_PROMOTION` |
| NATHAN PETERMAN | QB | passAtt | 96.8 | 1.8965 | 1.8965 | False | 2.0054 | — | 51.06 | 45.44 | 1.12 | 9.9904 | 20.0352 | `M3_STAT_MIX_OR_PROMOTION` |
| TEDDY BRIDGEWATER | QB | passAtt | 328.9 | 6.5 | 6.5 | False | 2.1845 | — | 50.6 | 45.44 | 1.11 | 10.746 | 23.472 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHONE KIZER | QB | rushAtt | 27.5 | 2.2126 | 2.2126 | False | 3.5 | HI | 12.42 | 11.73 | 1.06 | 14.4246 | 50.4996 | `M3_STAT_MIX_OR_PROMOTION` |
| DWAYNE HASKINS | QB | passYds | 2171.5 | 5.5 | 5.5 | False | 1.9702 | — | 394.82 | 371.2 | 1.06 | 12.4112 | 24.4554 | `M3_STAT_MIX_OR_PROMOTION` |
| … and 4 more | | | | | | | | | | | | | | |

### 2020 · `stratified`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DREW LOCK | QB | passAtt | 291.4 | 4.5 | 4.5 | False | 1.8629 | — | 64.76 | 45.44 | 1.43 | 16.2534 | 30.2728 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT RYAN | QB | passAtt | 575.0 | 9.5 | 9.5 | False | 1.4848 | — | 60.53 | 45.44 | 1.33 | 20.0409 | 29.7566 | `M3_STAT_MIX_OR_PROMOTION` |
| RYAN FINLEY | QB | passAtt | 196.8 | 3.5 | 3.5 | False | 1.8597 | — | 56.24 | 45.44 | 1.24 | 13.1182 | 24.3964 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT RYAN | QB | passYds | 4329.2 | 9.5 | 9.5 | False | 1.4848 | — | 455.7 | 371.2 | 1.23 | 20.0409 | 29.7566 | `M3_STAT_MIX_OR_PROMOTION` |
| DREW LOCK | QB | passYds | 2016.8 | 4.5 | 4.5 | False | 1.8629 | — | 448.17 | 371.2 | 1.21 | 16.2534 | 30.2728 | `M3_STAT_MIX_OR_PROMOTION` |
| C.J. BEATHARD | QB | passAtt | 172.2 | 3.1608 | 3.1608 | False | 1.8155 | — | 54.47 | 45.44 | 1.2 | 13.8235 | 25.1022 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passAtt | 512.0 | 9.5 | 9.5 | False | 1.8055 | — | 53.9 | 45.44 | 1.19 | 18.2626 | 32.973 | `M3_STAT_MIX_OR_PROMOTION` |
| CHAD KELLY | QB | passAtt | 51.4 | 0.9482 | 0.9482 | False | 1.8296 | — | 54.23 | 45.44 | 1.19 | 14.3828 | 26.3282 | `M3_STAT_MIX_OR_PROMOTION` |
| CARSON WENTZ | QB | passAtt | 558.0 | 10.5 | 10.5 | False | 1.4174 | — | 53.14 | 45.44 | 1.17 | 18.7743 | 26.6103 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passAtt | 477.4 | 9.0 | 9.0 | False | 1.6606 | — | 53.05 | 45.44 | 1.17 | 19.9587 | 33.1457 | `M3_STAT_MIX_OR_PROMOTION` |
| BEN ROETHLISBERGER | QB | passAtt | 463.0 | 9.0 | 9.0 | False | 1.362 | — | 51.44 | 45.44 | 1.13 | 18.0674 | 24.6085 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passYds | 3945.7 | 9.5 | 9.5 | False | 1.8055 | — | 415.34 | 371.2 | 1.12 | 18.2626 | 32.973 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passYds | 3732.3 | 9.0 | 9.0 | False | 1.6606 | — | 414.7 | 371.2 | 1.12 | 19.9587 | 33.1457 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE RUDOCK | QB | passAtt | 76.7 | 1.5804 | 1.5804 | False | 2.4156 | — | 48.52 | 45.44 | 1.07 | 9.2072 | 22.2514 | `M3_STAT_MIX_OR_PROMOTION` |
| CHAD KELLY | QB | passYds | 375.1 | 0.9482 | 0.9482 | False | 1.8296 | — | 395.53 | 371.2 | 1.07 | 14.3828 | 26.3282 | `M3_STAT_MIX_OR_PROMOTION` |
| C.J. BEATHARD | QB | passYds | 1224.9 | 3.1608 | 3.1608 | False | 1.8155 | — | 387.54 | 371.2 | 1.04 | 13.8235 | 25.1022 | `M3_STAT_MIX_OR_PROMOTION` |
| DWAYNE HASKINS | QB | passAtt | 260.3 | 5.5 | 5.5 | False | 1.6472 | — | 47.33 | 45.44 | 1.04 | 12.4112 | 20.4468 | `M3_STAT_MIX_OR_PROMOTION` |
| WILL GRIER | QB | passAtt | 94.2 | 2.0 | 2.0 | False | 1.3856 | — | 47.1 | 45.44 | 1.04 | 13.0658 | 18.0989 | `M3_STAT_MIX_OR_PROMOTION` |
| KYLE LAULETTA | QB | passAtt | 59.4 | 1.2643 | 1.2643 | False | 1.9215 | — | 46.98 | 45.44 | 1.03 | 11.1193 | 21.3795 | `M3_STAT_MIX_OR_PROMOTION` |
| BEN ROETHLISBERGER | QB | passYds | 3394.9 | 9.0 | 9.0 | False | 1.362 | — | 377.21 | 371.2 | 1.02 | 18.0674 | 24.6085 | `M3_STAT_MIX_OR_PROMOTION` |
| CARSON WENTZ | QB | passYds | 3952.3 | 10.5 | 10.5 | False | 1.4174 | — | 376.41 | 371.2 | 1.01 | 18.7743 | 26.6103 | `M3_STAT_MIX_OR_PROMOTION` |
| RYAN FINLEY | QB | passYds | 1307.5 | 3.5 | 3.5 | False | 1.8597 | — | 373.56 | 371.2 | 1.01 | 13.1182 | 24.3964 | `M3_STAT_MIX_OR_PROMOTION` |
| MATTHEW STAFFORD | QB | passAtt | 545.6 | 12.0 | 12.0 | False | 1.2073 | — | 45.46 | 45.44 | 1.0 | 18.4557 | 22.2802 | `M3_STAT_MIX_OR_PROMOTION` |

### 2020 · `feasibility_clamp`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TEDDY BRIDGEWATER | QB | passAtt | 295.4 | 6.5 | 6.5 | False | 1.9617 | — | 45.44 | 45.44 | 1.0 | 10.746 | 21.0789 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHONE KIZER | QB | passAtt | 100.5 | 2.2126 | 2.2126 | False | 1.3996 | — | 45.44 | 45.44 | 1.0 | 14.4246 | 20.1886 | `M3_STAT_MIX_OR_PROMOTION` |

### 2021 · `incumbent`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| WILL GRIER | QB | passAtt | 130.8 | 1.2152 | 1.2152 | False | 3.5 | HI | 107.61 | 45.44 | 2.37 | 11.8595 | 41.4919 | `M3_STAT_MIX_OR_PROMOTION` |
| JOSH JOHNSON | QB | passAtt | 184.5 | 1.8228 | 1.8228 | False | 3.5 | HI | 101.19 | 45.44 | 2.23 | 14.305 | 50.084 | `M3_STAT_MIX_OR_PROMOTION` |
| JOHN WOLFORD | QB | passAtt | 194.1 | 2.0 | 2.0 | False | 3.2493 | — | 97.05 | 45.44 | 2.14 | 13.8427 | 44.9893 | `M3_STAT_MIX_OR_PROMOTION` |
| Tommy Stevens | QB | passAtt | 192.9 | 2.0 | 2.0 | False | 3.5 | HI | 96.44 | 45.44 | 2.12 | 13.9877 | 48.9671 | `M3_STAT_MIX_OR_PROMOTION` |
| JOSH JOHNSON | QB | passYds | 1274.8 | 1.8228 | 1.8228 | False | 3.5 | HI | 699.37 | 371.2 | 1.88 | 14.305 | 50.084 | `M3_STAT_MIX_OR_PROMOTION` |
| WILL GRIER | QB | passYds | 846.6 | 1.2152 | 1.2152 | False | 3.5 | HI | 696.63 | 371.2 | 1.88 | 11.8595 | 41.4919 | `M3_STAT_MIX_OR_PROMOTION` |
| Tommy Stevens | QB | passYds | 1380.2 | 2.0 | 2.0 | False | 3.5 | HI | 690.11 | 371.2 | 1.86 | 13.9877 | 48.9671 | `M3_STAT_MIX_OR_PROMOTION` |
| JOHN WOLFORD | QB | passYds | 1348.7 | 2.0 | 2.0 | False | 3.2493 | — | 674.33 | 371.2 | 1.82 | 13.8427 | 44.9893 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE LUTON | QB | passAtt | 262.8 | 3.5 | 3.5 | False | 2.0647 | — | 75.1 | 45.44 | 1.65 | 14.5189 | 29.9735 | `M3_STAT_MIX_OR_PROMOTION` |
| JAMEIS WINSTON | QB | passAtt | 275.5 | 4.0 | 4.0 | False | 2.3116 | — | 68.87 | 45.44 | 1.52 | 14.5721 | 33.6809 | `M3_STAT_MIX_OR_PROMOTION` |
| JAMEIS WINSTON | QB | passYds | 2078.8 | 4.0 | 4.0 | False | 2.3116 | — | 519.71 | 371.2 | 1.4 | 14.5721 | 33.6809 | `M3_STAT_MIX_OR_PROMOTION` |
| BRANDON ALLEN | QB | passAtt | 216.0 | 3.5 | 3.5 | False | 1.8542 | — | 61.71 | 45.44 | 1.36 | 14.5565 | 26.9957 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE LUTON | QB | passYds | 1721.6 | 3.5 | 3.5 | False | 2.0647 | — | 491.88 | 371.2 | 1.33 | 14.5189 | 29.9735 | `M3_STAT_MIX_OR_PROMOTION` |
| DAK PRESCOTT | QB | passAtt | 620.5 | 10.5 | 10.5 | False | 1.6818 | — | 59.09 | 45.44 | 1.3 | 18.9507 | 31.8726 | `M3_STAT_MIX_OR_PROMOTION` |
| JA'MARCUS BRADLEY | WR | tgt | 66.4 | 4.0 | 4.0 | False | 3.0633 | — | 16.61 | 12.75 | 1.3 | 7.7204 | 23.6474 | `M3_STAT_MIX_OR_PROMOTION` |
| JOSH JOHNSON | QB | rushAtt | 27.3 | 1.8228 | 1.8228 | False | 3.5 | HI | 15.0 | 11.73 | 1.28 | 14.305 | 50.084 | `M3_STAT_MIX_OR_PROMOTION` |
| TYROD TAYLOR | QB | passAtt | 171.9 | 3.0 | 3.0 | False | 2.3923 | — | 57.31 | 45.44 | 1.26 | 11.5861 | 27.7244 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passAtt | 529.8 | 9.5 | 9.5 | False | 1.8717 | — | 55.77 | 45.44 | 1.23 | 18.3514 | 34.3487 | `M3_STAT_MIX_OR_PROMOTION` |
| DAK PRESCOTT | QB | passYds | 4741.0 | 10.5 | 10.5 | False | 1.6818 | — | 451.53 | 371.2 | 1.22 | 18.9507 | 31.8726 | `M3_STAT_MIX_OR_PROMOTION` |
| BRETT HUNDLEY | QB | passAtt | 79.9 | 1.519 | 1.519 | False | 2.3803 | — | 52.57 | 45.44 | 1.16 | 10.9646 | 26.0828 | `M3_STAT_MIX_OR_PROMOTION` |
| TUA TAGOVAILOA | QB | passAtt | 366.6 | 7.0 | 7.0 | False | 1.6709 | — | 52.37 | 45.44 | 1.15 | 14.9054 | 24.9057 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passYds | 4034.2 | 9.5 | 9.5 | False | 1.8717 | — | 424.65 | 371.2 | 1.14 | 18.3514 | 34.3487 | `M3_STAT_MIX_OR_PROMOTION` |
| BRIAN HOYER | QB | passAtt | 77.2 | 1.5 | 1.5 | False | 1.7674 | — | 51.48 | 45.44 | 1.13 | 13.8859 | 24.5361 | `M3_STAT_MIX_OR_PROMOTION` |
| BRANDON ALLEN | QB | passYds | 1470.1 | 3.5 | 3.5 | False | 1.8542 | — | 420.03 | 371.2 | 1.13 | 14.5565 | 26.9957 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT RYAN | QB | passAtt | 493.2 | 10.0 | 10.0 | False | 1.2614 | — | 49.32 | 45.44 | 1.09 | 18.8149 | 23.7337 | `M3_STAT_MIX_OR_PROMOTION` |
| TYROD TAYLOR | QB | passYds | 1215.7 | 3.0 | 3.0 | False | 2.3923 | — | 405.23 | 371.2 | 1.09 | 11.5861 | 27.7244 | `M3_STAT_MIX_OR_PROMOTION` |
| JIMMY GAROPPOLO | QB | passAtt | 247.8 | 5.0 | 5.0 | False | 1.5023 | — | 49.55 | 45.44 | 1.09 | 16.6308 | 24.9863 | `M3_STAT_MIX_OR_PROMOTION` |
| MICHAEL THOMAS | WR | rec | 62.2 | 6.5976 | 6.5976 | False | 1.5933 | — | 9.42 | 8.79 | 1.07 | 14.6724 | 23.3778 | `M3_STAT_MIX_OR_PROMOTION` |
| JA'MARCUS BRADLEY | WR | rec | 36.4 | 4.0 | 4.0 | False | 3.0633 | — | 9.11 | 8.79 | 1.04 | 7.7204 | 23.6474 | `M3_STAT_MIX_OR_PROMOTION` |
| JIMMY GAROPPOLO | QB | passYds | 1901.3 | 5.0 | 5.0 | False | 1.5023 | — | 380.27 | 371.2 | 1.02 | 16.6308 | 24.9863 | `M3_STAT_MIX_OR_PROMOTION` |

### 2021 · `rate_refit_stratified`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CARSON WENTZ | QB | passAtt | 371.3 | 8.0 | 8.0 | False | 1.2548 | — | 46.41 | 45.44 | 1.02 | 17.5181 | 21.9814 | `M3_STAT_MIX_OR_PROMOTION` |

### 2021 · `stratified`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| WILL GRIER | QB | passAtt | 93.2 | 1.2152 | 1.2152 | False | 2.495 | — | 76.71 | 45.44 | 1.69 | 11.8595 | 29.5726 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE LUTON | QB | passAtt | 245.2 | 3.5 | 3.5 | False | 1.9261 | — | 70.06 | 45.44 | 1.54 | 14.5189 | 27.9625 | `M3_STAT_MIX_OR_PROMOTION` |
| JAMEIS WINSTON | QB | passAtt | 255.4 | 4.0 | 4.0 | False | 2.1432 | — | 63.85 | 45.44 | 1.41 | 14.5721 | 31.2303 | `M3_STAT_MIX_OR_PROMOTION` |
| BRANDON ALLEN | QB | passAtt | 216.0 | 3.5 | 3.5 | False | 1.8542 | — | 61.71 | 45.44 | 1.36 | 14.5565 | 26.9957 | `M3_STAT_MIX_OR_PROMOTION` |
| WILL GRIER | QB | passYds | 603.5 | 1.2152 | 1.2152 | False | 2.495 | — | 496.59 | 371.2 | 1.34 | 11.8595 | 29.5726 | `M3_STAT_MIX_OR_PROMOTION` |
| JAMEIS WINSTON | QB | passYds | 1927.4 | 4.0 | 4.0 | False | 2.1432 | — | 481.84 | 371.2 | 1.3 | 14.5721 | 31.2303 | `M3_STAT_MIX_OR_PROMOTION` |
| DAK PRESCOTT | QB | passAtt | 620.5 | 10.5 | 10.5 | False | 1.6818 | — | 59.09 | 45.44 | 1.3 | 18.9507 | 31.8726 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE LUTON | QB | passYds | 1606.0 | 3.5 | 3.5 | False | 1.9261 | — | 458.84 | 371.2 | 1.24 | 14.5189 | 27.9625 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passAtt | 529.8 | 9.5 | 9.5 | False | 1.8717 | — | 55.77 | 45.44 | 1.23 | 18.3514 | 34.3487 | `M3_STAT_MIX_OR_PROMOTION` |
| DAK PRESCOTT | QB | passYds | 4741.0 | 10.5 | 10.5 | False | 1.6818 | — | 451.53 | 371.2 | 1.22 | 18.9507 | 31.8726 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passYds | 4034.2 | 9.5 | 9.5 | False | 1.8717 | — | 424.65 | 371.2 | 1.14 | 18.3514 | 34.3487 | `M3_STAT_MIX_OR_PROMOTION` |
| BRANDON ALLEN | QB | passYds | 1470.1 | 3.5 | 3.5 | False | 1.8542 | — | 420.03 | 371.2 | 1.13 | 14.5565 | 26.9957 | `M3_STAT_MIX_OR_PROMOTION` |
| MATT RYAN | QB | passAtt | 493.2 | 10.0 | 10.0 | False | 1.2614 | — | 49.32 | 45.44 | 1.09 | 18.8149 | 23.7337 | `M3_STAT_MIX_OR_PROMOTION` |
| BRETT HUNDLEY | QB | passAtt | 71.0 | 1.519 | 1.519 | False | 2.1169 | — | 46.75 | 45.44 | 1.03 | 10.9646 | 23.2011 | `M3_STAT_MIX_OR_PROMOTION` |
| JIMMY GAROPPOLO | QB | passAtt | 232.4 | 5.0 | 5.0 | False | 1.4089 | — | 46.47 | 45.44 | 1.02 | 16.6308 | 23.4333 | `M3_STAT_MIX_OR_PROMOTION` |

### 2022 · `incumbent`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| JAKE LUTON | QB | passAtt | 212.5 | 2.0578 | 2.0578 | False | 3.5 | HI | 103.29 | 45.44 | 2.27 | 10.942 | 38.2971 | `M3_STAT_MIX_OR_PROMOTION` |
| WILL GRIER | QB | passAtt | 109.0 | 1.1759 | 1.1759 | False | 3.1706 | — | 92.67 | 45.44 | 2.04 | 10.6173 | 33.6519 | `M3_STAT_MIX_OR_PROMOTION` |
| KELLEN MOND | QB | passAtt | 127.0 | 1.5 | 1.5 | False | 3.5 | HI | 84.67 | 45.44 | 1.86 | 11.0365 | 38.6277 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE LUTON | QB | passYds | 1377.2 | 2.0578 | 2.0578 | False | 3.5 | HI | 669.23 | 371.2 | 1.8 | 10.942 | 38.2971 | `M3_STAT_MIX_OR_PROMOTION` |
| MIKE WHITE | QB | passAtt | 242.1 | 3.0 | 3.0 | False | 2.7026 | — | 80.72 | 45.44 | 1.78 | 11.7542 | 31.7615 | `M3_STAT_MIX_OR_PROMOTION` |
| EASTON STICK | QB | passAtt | 70.1 | 0.8819 | 0.8819 | False | 3.5 | HI | 79.5 | 45.44 | 1.75 | 10.4146 | 36.4398 | `M3_STAT_MIX_OR_PROMOTION` |
| TREY LANCE | QB | passAtt | 374.5 | 5.0 | 5.0 | False | 3.5 | HI | 74.91 | 45.44 | 1.65 | 12.9084 | 45.1815 | `M3_STAT_MIX_OR_PROMOTION` |
| MICHAEL THOMAS | WR | rec | 103.6 | 7.394 | 7.394 | False | 2.4262 | — | 14.02 | 8.79 | 1.59 | 14.0678 | 34.1317 | `M3_STAT_MIX_OR_PROMOTION` |
| WILL GRIER | QB | passYds | 695.1 | 1.1759 | 1.1759 | False | 3.1706 | — | 591.08 | 371.2 | 1.59 | 10.6173 | 33.6519 | `M3_STAT_MIX_OR_PROMOTION` |
| KELLEN MOND | QB | passYds | 885.1 | 1.5 | 1.5 | False | 3.5 | HI | 590.08 | 371.2 | 1.59 | 11.0365 | 38.6277 | `M3_STAT_MIX_OR_PROMOTION` |
| MIKE WHITE | QB | passYds | 1729.8 | 3.0 | 3.0 | False | 2.7026 | — | 576.6 | 371.2 | 1.55 | 11.7542 | 31.7615 | `M3_STAT_MIX_OR_PROMOTION` |
| TREY LANCE | QB | passYds | 2821.7 | 5.0 | 5.0 | False | 3.5 | HI | 564.34 | 371.2 | 1.52 | 12.9084 | 45.1815 | `M3_STAT_MIX_OR_PROMOTION` |
| EASTON STICK | QB | passYds | 494.7 | 0.8819 | 0.8819 | False | 3.5 | HI | 560.91 | 371.2 | 1.51 | 10.4146 | 36.4398 | `M3_STAT_MIX_OR_PROMOTION` |
| TREY LANCE | QB | rushAtt | 87.3 | 5.0 | 5.0 | False | 3.5 | HI | 17.46 | 11.73 | 1.49 | 12.9084 | 45.1815 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM EHLINGER | QB | passAtt | 168.1 | 2.5 | 2.5 | False | 3.5 | HI | 67.26 | 45.44 | 1.48 | 9.0969 | 31.8353 | `M3_STAT_MIX_OR_PROMOTION` |
| MICHAEL THOMAS | WR | tgt | 138.2 | 7.394 | 7.394 | False | 2.4262 | — | 18.69 | 12.75 | 1.47 | 14.0678 | 34.1317 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passAtt | 497.9 | 8.0 | 8.0 | False | 2.2075 | — | 62.24 | 45.44 | 1.37 | 16.4974 | 36.4167 | `M3_STAT_MIX_OR_PROMOTION` |
| MICHAEL THOMAS | WR | recYds | 1208.2 | 7.394 | 7.394 | False | 2.4262 | — | 163.41 | 122.75 | 1.33 | 14.0678 | 34.1317 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passAtt | 194.9 | 3.2338 | 3.2338 | False | 1.962 | — | 60.28 | 45.44 | 1.33 | 19.2528 | 37.7776 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passYds | 1593.2 | 3.2338 | 3.2338 | False | 1.962 | — | 492.67 | 371.2 | 1.33 | 19.2528 | 37.7776 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM EHLINGER | QB | passYds | 1189.8 | 2.5 | 2.5 | False | 3.5 | HI | 475.92 | 371.2 | 1.28 | 9.0969 | 31.8353 | `M3_STAT_MIX_OR_PROMOTION` |
| RUSSELL WILSON | QB | passYds | 3765.9 | 8.0 | 8.0 | False | 2.2075 | — | 470.74 | 371.2 | 1.27 | 16.4974 | 36.4167 | `M3_STAT_MIX_OR_PROMOTION` |
| TUA TAGOVAILOA | QB | passAtt | 454.1 | 8.5 | 8.5 | False | 1.9808 | — | 53.42 | 45.44 | 1.18 | 12.4413 | 24.6454 | `M3_STAT_MIX_OR_PROMOTION` |
| JACOB EASON | QB | passAtt | 80.3 | 1.5 | 1.5 | False | 2.2898 | — | 53.53 | 45.44 | 1.18 | 10.2665 | 23.5161 | `M3_STAT_MIX_OR_PROMOTION` |
| NICK MULLENS | QB | passAtt | 129.4 | 2.5 | 2.5 | False | 1.8477 | — | 51.78 | 45.44 | 1.14 | 12.5105 | 23.112 | `M3_STAT_MIX_OR_PROMOTION` |
| JOSH JOHNSON | QB | passAtt | 154.1 | 3.0 | 3.0 | False | 2.0201 | — | 51.36 | 45.44 | 1.13 | 12.3323 | 24.9066 | `M3_STAT_MIX_OR_PROMOTION` |
| BRETT RYPIEN | QB | passAtt | 77.0 | 1.5 | 1.5 | False | 1.9045 | — | 51.33 | 45.44 | 1.13 | 12.2729 | 23.3717 | `M3_STAT_MIX_OR_PROMOTION` |
| JAMEIS WINSTON | QB | passAtt | 280.4 | 5.5 | 5.5 | False | 1.9852 | — | 50.99 | 45.44 | 1.12 | 13.5888 | 26.9756 | `M3_STAT_MIX_OR_PROMOTION` |
| DAVIS WEBB | QB | passAtt | 73.2 | 1.5 | 1.5 | False | 2.1101 | — | 48.82 | 45.44 | 1.07 | 10.6637 | 22.5048 | `M3_STAT_MIX_OR_PROMOTION` |
| JOSHUA DOBBS | QB | passAtt | 70.9 | 1.4699 | 1.4699 | False | 1.9177 | — | 48.26 | 45.44 | 1.06 | 11.6688 | 22.3753 | `M3_STAT_MIX_OR_PROMOTION` |
| JORDAN MATTHEWS | TE | tgt | 34.6 | 3.3225 | 3.3225 | False | 3.5 | HI | 10.41 | 9.94 | 1.05 | 3.118 | 10.9162 | `M3_STAT_MIX_OR_PROMOTION` |
| TIM BOYLE | QB | passAtt | 140.2 | 3.0 | 3.0 | False | 2.4045 | — | 46.73 | 45.44 | 1.03 | 8.0219 | 19.283 | `M3_STAT_MIX_OR_PROMOTION` |
| JAMEIS WINSTON | QB | passYds | 2091.8 | 5.5 | 5.5 | False | 1.9852 | — | 380.32 | 371.2 | 1.02 | 13.5888 | 26.9756 | `M3_STAT_MIX_OR_PROMOTION` |
| Kristian Wilkerson | WR | tgt | 73.4 | 5.6344 | 5.6344 | False | 3.5 | HI | 13.02 | 12.75 | 1.02 | 7.4014 | 25.8994 | `M3_STAT_MIX_OR_PROMOTION` |
| NATHAN PETERMAN | QB | passAtt | 68.7 | 1.5 | 1.5 | False | 2.005 | — | 45.81 | 45.44 | 1.01 | 10.5438 | 21.1409 | `M3_STAT_MIX_OR_PROMOTION` |
| JOHN WOLFORD | QB | passAtt | 114.2 | 2.5 | 2.5 | False | 2.1279 | — | 45.7 | 45.44 | 1.01 | 9.4237 | 20.0476 | `M3_STAT_MIX_OR_PROMOTION` |
| JACOB EASON | QB | passYds | 562.7 | 1.5 | 1.5 | False | 2.2898 | — | 375.16 | 371.2 | 1.01 | 10.2665 | 23.5161 | `M3_STAT_MIX_OR_PROMOTION` |
| JUSTIN FIELDS | QB | passAtt | 367.7 | 8.0 | 8.0 | False | 2.0497 | — | 45.96 | 45.44 | 1.01 | 10.8644 | 22.2687 | `M3_STAT_MIX_OR_PROMOTION` |
| JOSH JOHNSON | QB | passYds | 1114.4 | 3.0 | 3.0 | False | 2.0201 | — | 371.45 | 371.2 | 1.0 | 12.3323 | 24.9066 | `M3_STAT_MIX_OR_PROMOTION` |

### 2022 · `stratified`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| WILL GRIER | QB | passAtt | 86.1 | 1.1759 | 1.1759 | False | 2.5051 | — | 73.22 | 45.44 | 1.61 | 10.6173 | 26.5977 | `M3_STAT_MIX_OR_PROMOTION` |
| WILL GRIER | QB | passYds | 549.2 | 1.1759 | 1.1759 | False | 2.5051 | — | 467.02 | 371.2 | 1.26 | 10.6173 | 26.5977 | `M3_STAT_MIX_OR_PROMOTION` |
| EASTON STICK | QB | passAtt | 49.1 | 0.8819 | 0.8819 | False | 2.4515 | — | 55.68 | 45.44 | 1.23 | 10.4146 | 25.519 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE LUTON | QB | passAtt | 110.9 | 2.0578 | 2.0578 | False | 1.8256 | — | 53.87 | 45.44 | 1.19 | 10.942 | 19.9719 | `M3_STAT_MIX_OR_PROMOTION` |
| KELLEN MOND | QB | passAtt | 77.3 | 1.5 | 1.5 | False | 2.1301 | — | 51.53 | 45.44 | 1.13 | 11.0365 | 23.5119 | `M3_STAT_MIX_OR_PROMOTION` |
| EASTON STICK | QB | passYds | 346.5 | 0.8819 | 0.8819 | False | 2.4515 | — | 392.88 | 371.2 | 1.06 | 10.4146 | 25.519 | `M3_STAT_MIX_OR_PROMOTION` |
| KIRK COUSINS | QB | passAtt | 468.3 | 10.0 | 10.0 | False | 1.6016 | — | 46.83 | 45.44 | 1.03 | 15.6701 | 25.0971 | `M3_STAT_MIX_OR_PROMOTION` |

### 2023 · `incumbent`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DESHAUN WATSON | QB | passAtt | 427.5 | 4.0 | 4.0 | False | 3.5 | HI | 106.88 | 45.44 | 2.35 | 16.5729 | 58.0075 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM HOWELL | QB | passAtt | 151.5 | 1.5 | 1.5 | False | 3.5 | HI | 100.99 | 45.44 | 2.22 | 15.2352 | 53.3165 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passYds | 3167.8 | 4.0 | 4.0 | False | 3.5 | HI | 791.95 | 371.2 | 2.13 | 16.5729 | 58.0075 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM HOWELL | QB | passYds | 1089.0 | 1.5 | 1.5 | False | 3.5 | HI | 726.02 | 371.2 | 1.96 | 15.2352 | 53.3165 | `M3_STAT_MIX_OR_PROMOTION` |
| EASTON STICK | QB | passAtt | 59.1 | 0.8619 | 0.8619 | False | 2.7916 | — | 68.51 | 45.44 | 1.51 | 11.4633 | 31.9728 | `M3_STAT_MIX_OR_PROMOTION` |
| DAVID BLOUGH | QB | passAtt | 197.1 | 3.0 | 3.0 | False | 2.6703 | — | 65.7 | 45.44 | 1.45 | 10.8097 | 28.8625 | `M3_STAT_MIX_OR_PROMOTION` |
| TREVOR SIEMIAN | QB | passAtt | 190.4 | 3.0 | 3.0 | False | 2.3939 | — | 63.47 | 45.44 | 1.4 | 12.4159 | 29.7199 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | rushAtt | 63.4 | 4.0 | 4.0 | False | 3.5 | HI | 15.85 | 11.73 | 1.35 | 16.5729 | 58.0075 | `M3_STAT_MIX_OR_PROMOTION` |
| DAVIS WEBB | QB | passAtt | 87.6 | 1.5 | 1.5 | False | 2.1196 | — | 58.37 | 45.44 | 1.28 | 13.0843 | 27.7377 | `M3_STAT_MIX_OR_PROMOTION` |
| EASTON STICK | QB | passYds | 410.5 | 0.8619 | 0.8619 | False | 2.7916 | — | 476.24 | 371.2 | 1.28 | 11.4633 | 31.9728 | `M3_STAT_MIX_OR_PROMOTION` |
| TREY LANCE | QB | passAtt | 174.5 | 3.0 | 3.0 | False | 2.207 | — | 58.17 | 45.44 | 1.28 | 13.2909 | 29.3374 | `M3_STAT_MIX_OR_PROMOTION` |
| DESMOND RIDDER | QB | passAtt | 232.3 | 4.0 | 4.0 | False | 2.0935 | — | 58.07 | 45.44 | 1.28 | 11.799 | 24.7045 | `M3_STAT_MIX_OR_PROMOTION` |
| DAVID BLOUGH | QB | passYds | 1367.1 | 3.0 | 3.0 | False | 2.6703 | — | 455.71 | 371.2 | 1.23 | 10.8097 | 28.8625 | `M3_STAT_MIX_OR_PROMOTION` |
| COOPER KUPP | WR | rec | 69.8 | 6.4994 | 6.4994 | False | 2.2141 | — | 10.74 | 8.79 | 1.22 | 13.3465 | 29.5508 | `M3_STAT_MIX_OR_PROMOTION` |
| JACOB EASON | QB | passAtt | 83.3 | 1.5 | 1.5 | False | 2.1197 | — | 55.52 | 45.44 | 1.22 | 11.9488 | 25.3183 | `M3_STAT_MIX_OR_PROMOTION` |
| TUA TAGOVAILOA | QB | passAtt | 467.8 | 8.5 | 8.5 | False | 1.857 | — | 55.04 | 45.44 | 1.21 | 15.1881 | 28.2021 | `M3_STAT_MIX_OR_PROMOTION` |
| TIM BOYLE | QB | passAtt | 81.3 | 1.5 | 1.5 | False | 2.1503 | — | 54.18 | 45.44 | 1.19 | 11.2969 | 24.2828 | `M3_STAT_MIX_OR_PROMOTION` |
| CALVIN RIDLEY | WR | tgt | 103.9 | 6.8353 | 6.8353 | False | 2.1431 | — | 15.2 | 12.75 | 1.19 | 12.2841 | 26.328 | `M3_STAT_MIX_OR_PROMOTION` |
| TREVOR SIEMIAN | QB | passYds | 1296.1 | 3.0 | 3.0 | False | 2.3939 | — | 432.04 | 371.2 | 1.16 | 12.4159 | 29.7199 | `M3_STAT_MIX_OR_PROMOTION` |
| JUSTIN FIELDS | QB | rushAtt | 128.1 | 9.5 | 9.5 | False | 1.7872 | — | 13.49 | 11.73 | 1.15 | 16.1334 | 28.8332 | `M3_STAT_MIX_OR_PROMOTION` |
| COOPER KUPP | WR | tgt | 94.1 | 6.4994 | 6.4994 | False | 2.2141 | — | 14.48 | 12.75 | 1.14 | 13.3465 | 29.5508 | `M3_STAT_MIX_OR_PROMOTION` |
| BRANDON ALLEN | QB | passAtt | 77.2 | 1.5 | 1.5 | False | 2.057 | — | 51.44 | 45.44 | 1.13 | 11.5252 | 23.6957 | `M3_STAT_MIX_OR_PROMOTION` |
| TUA TAGOVAILOA | QB | passYds | 3562.3 | 8.5 | 8.5 | False | 1.857 | — | 419.09 | 371.2 | 1.13 | 15.1881 | 28.2021 | `M3_STAT_MIX_OR_PROMOTION` |
| KYLE ALLEN | QB | passAtt | 151.3 | 3.0 | 3.0 | False | 1.6971 | — | 50.42 | 45.44 | 1.11 | 13.0207 | 22.0937 | `M3_STAT_MIX_OR_PROMOTION` |
| TREY LANCE | QB | passYds | 1231.8 | 3.0 | 3.0 | False | 2.207 | — | 410.6 | 371.2 | 1.11 | 13.2909 | 29.3374 | `M3_STAT_MIX_OR_PROMOTION` |
| JOSH JOHNSON | QB | passAtt | 100.1 | 2.0 | 2.0 | False | 2.123 | — | 50.06 | 45.44 | 1.1 | 11.1986 | 23.7781 | `M3_STAT_MIX_OR_PROMOTION` |
| CALVIN RIDLEY | WR | rec | 64.9 | 6.8353 | 6.8353 | False | 2.1431 | — | 9.49 | 8.79 | 1.08 | 12.2841 | 26.328 | `M3_STAT_MIX_OR_PROMOTION` |
| Kristian Wilkerson | WR | tgt | 73.6 | 5.4289 | 5.4289 | False | 3.5 | HI | 13.56 | 12.75 | 1.06 | 7.6908 | 26.9215 | `M3_STAT_MIX_OR_PROMOTION` |
| COOPER KUPP | WR | recYds | 840.6 | 6.4994 | 6.4994 | False | 2.2141 | — | 129.33 | 122.75 | 1.05 | 13.3465 | 29.5508 | `M3_STAT_MIX_OR_PROMOTION` |
| JACOB EASON | QB | passYds | 586.7 | 1.5 | 1.5 | False | 2.1197 | — | 391.17 | 371.2 | 1.05 | 11.9488 | 25.3183 | `M3_STAT_MIX_OR_PROMOTION` |
| AJ MCCARRON | QB | passAtt | 80.7 | 1.7238 | 1.7238 | False | 2.0905 | — | 46.83 | 45.44 | 1.03 | 10.6463 | 22.2462 | `M3_STAT_MIX_OR_PROMOTION` |
| DAVIS WEBB | QB | passYds | 575.4 | 1.5 | 1.5 | False | 2.1196 | — | 383.57 | 371.2 | 1.03 | 13.0843 | 27.7377 | `M3_STAT_MIX_OR_PROMOTION` |
| KYLE TRASK | QB | passAtt | 116.6 | 2.5 | 2.5 | False | 1.9151 | — | 46.63 | 45.44 | 1.03 | 10.8784 | 20.8235 | `M3_STAT_MIX_OR_PROMOTION` |
| DESMOND RIDDER | QB | passYds | 1536.6 | 4.0 | 4.0 | False | 2.0935 | — | 384.15 | 371.2 | 1.03 | 11.799 | 24.7045 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM HOWELL | QB | rushAtt | 17.9 | 1.5 | 1.5 | False | 3.5 | HI | 11.95 | 11.73 | 1.02 | 15.2352 | 53.3165 | `M3_STAT_MIX_OR_PROMOTION` |
| P.J. WALKER | QB | passAtt | 230.5 | 5.0 | 5.0 | False | 2.0756 | — | 46.09 | 45.44 | 1.01 | 9.0179 | 18.719 | `M3_STAT_MIX_OR_PROMOTION` |
| CHRIS STREVELER | QB | passAtt | 68.8 | 1.5 | 1.5 | False | 1.7615 | — | 45.84 | 45.44 | 1.01 | 12.2735 | 21.6231 | `M3_STAT_MIX_OR_PROMOTION` |
| JUSTIN FIELDS | QB | rushYds | 845.8 | 9.5 | 9.5 | False | 1.7872 | — | 89.03 | 88.0 | 1.01 | 16.1334 | 28.8332 | `M3_STAT_MIX_OR_PROMOTION` |
| SEAN MANNION | QB | passAtt | 65.4 | 1.4365 | 1.4365 | False | 1.4618 | — | 45.5 | 45.44 | 1.0 | 13.9991 | 20.4486 | `M3_STAT_MIX_OR_PROMOTION` |
| TIM BOYLE | QB | passYds | 558.4 | 1.5 | 1.5 | False | 2.1503 | — | 372.24 | 371.2 | 1.0 | 11.2969 | 24.2828 | `M3_STAT_MIX_OR_PROMOTION` |

### 2023 · `stratified`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DESHAUN WATSON | QB | passAtt | 243.2 | 4.0 | 4.0 | False | 1.9914 | — | 60.81 | 45.44 | 1.34 | 16.5729 | 33.002 | `M3_STAT_MIX_OR_PROMOTION` |
| DESMOND RIDDER | QB | passAtt | 223.2 | 4.0 | 4.0 | False | 2.0118 | — | 55.8 | 45.44 | 1.23 | 11.799 | 23.7371 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passYds | 1802.3 | 4.0 | 4.0 | False | 1.9914 | — | 450.59 | 371.2 | 1.21 | 16.5729 | 33.002 | `M3_STAT_MIX_OR_PROMOTION` |
| JUSTIN FIELDS | QB | rushAtt | 128.1 | 9.5 | 9.5 | False | 1.7872 | — | 13.49 | 11.73 | 1.15 | 16.1334 | 28.8332 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM HOWELL | QB | passAtt | 75.5 | 1.5 | 1.5 | False | 1.7448 | — | 50.34 | 45.44 | 1.11 | 15.2352 | 26.5849 | `M3_STAT_MIX_OR_PROMOTION` |
| KIRK COUSINS | QB | passAtt | 509.4 | 10.5 | 10.5 | False | 1.4564 | — | 48.52 | 45.44 | 1.07 | 16.4899 | 24.0163 | `M3_STAT_MIX_OR_PROMOTION` |
| JUSTIN FIELDS | QB | rushYds | 845.8 | 9.5 | 9.5 | False | 1.7872 | — | 89.03 | 88.0 | 1.01 | 16.1334 | 28.8332 | `M3_STAT_MIX_OR_PROMOTION` |

### 2023 · `feasibility_clamp`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AJ MCCARRON | QB | passAtt | 78.3 | 1.7238 | 1.7238 | False | 2.0285 | — | 45.44 | 45.44 | 1.0 | 10.6463 | 21.5851 | `M3_STAT_MIX_OR_PROMOTION` |
| P.J. WALKER | QB | passAtt | 227.2 | 5.0 | 5.0 | False | 2.0462 | — | 45.44 | 45.44 | 1.0 | 9.0179 | 18.4531 | `M3_STAT_MIX_OR_PROMOTION` |
| Kristian Wilkerson | WR | tgt | 69.2 | 5.4289 | 5.4289 | False | 3.292 | — | 12.75 | 12.75 | 1.0 | 7.6908 | 25.3228 | `M3_STAT_MIX_OR_PROMOTION` |

### 2024 · `incumbent`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ANTHONY RICHARDSON | QB | passAtt | 334.9 | 4.0 | 4.0 | False | 3.5 | HI | 83.72 | 45.44 | 1.84 | 14.194 | 49.6789 | `M3_STAT_MIX_OR_PROMOTION` |
| CASE KEENUM | QB | passAtt | 164.0 | 2.0 | 2.0 | False | 3.5 | HI | 81.98 | 45.44 | 1.8 | 9.7363 | 34.0822 | `M3_STAT_MIX_OR_PROMOTION` |
| TREY LANCE | QB | passAtt | 132.2 | 1.6534 | 1.6534 | False | 3.5 | HI | 79.97 | 45.44 | 1.76 | 11.0622 | 38.7298 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM EHLINGER | QB | passAtt | 117.8 | 1.5 | 1.5 | False | 3.5 | HI | 78.54 | 45.44 | 1.73 | 9.83 | 34.4051 | `M3_STAT_MIX_OR_PROMOTION` |
| Jeff Driskel | QB | passAtt | 114.0 | 1.5 | 1.5 | False | 3.5 | HI | 75.97 | 45.44 | 1.67 | 9.8397 | 34.4255 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passAtt | 297.9 | 4.0 | 4.0 | False | 2.7761 | — | 74.47 | 45.44 | 1.64 | 12.7372 | 35.3594 | `M3_STAT_MIX_OR_PROMOTION` |
| KIRK COUSINS | QB | passAtt | 444.0 | 6.0 | 6.0 | False | 2.2668 | — | 74.0 | 45.44 | 1.63 | 15.6271 | 35.428 | `M3_STAT_MIX_OR_PROMOTION` |
| BRANDON ALLEN | QB | passAtt | 59.9 | 0.8267 | 0.8267 | False | 3.3551 | — | 72.4 | 45.44 | 1.59 | 9.5651 | 32.076 | `M3_STAT_MIX_OR_PROMOTION` |
| ANTHONY RICHARDSON | QB | passYds | 2341.4 | 4.0 | 4.0 | False | 3.5 | HI | 585.35 | 371.2 | 1.58 | 14.194 | 49.6789 | `M3_STAT_MIX_OR_PROMOTION` |
| TREY LANCE | QB | passYds | 944.2 | 1.6534 | 1.6534 | False | 3.5 | HI | 571.03 | 371.2 | 1.54 | 11.0622 | 38.7298 | `M3_STAT_MIX_OR_PROMOTION` |
| ANDY DALTON | QB | passAtt | 169.9 | 2.5 | 2.5 | False | 2.8597 | — | 67.96 | 45.44 | 1.5 | 10.3723 | 29.6578 | `M3_STAT_MIX_OR_PROMOTION` |
| CASE KEENUM | QB | passYds | 1116.4 | 2.0 | 2.0 | False | 3.5 | HI | 558.21 | 371.2 | 1.5 | 9.7363 | 34.0822 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM EHLINGER | QB | passYds | 818.0 | 1.5 | 1.5 | False | 3.5 | HI | 545.37 | 371.2 | 1.47 | 9.83 | 34.4051 | `M3_STAT_MIX_OR_PROMOTION` |
| KIRK COUSINS | QB | passYds | 3212.7 | 6.0 | 6.0 | False | 2.2668 | — | 535.45 | 371.2 | 1.44 | 15.6271 | 35.428 | `M3_STAT_MIX_OR_PROMOTION` |
| Jeff Driskel | QB | passYds | 799.8 | 1.5 | 1.5 | False | 3.5 | HI | 533.23 | 371.2 | 1.44 | 9.8397 | 34.4255 | `M3_STAT_MIX_OR_PROMOTION` |
| BRANDON ALLEN | QB | passYds | 418.1 | 0.8267 | 0.8267 | False | 3.3551 | — | 505.7 | 371.2 | 1.36 | 9.5651 | 32.076 | `M3_STAT_MIX_OR_PROMOTION` |
| DESHAUN WATSON | QB | passYds | 2013.6 | 4.0 | 4.0 | False | 2.7761 | — | 503.4 | 371.2 | 1.36 | 12.7372 | 35.3594 | `M3_STAT_MIX_OR_PROMOTION` |
| ANDY DALTON | QB | passYds | 1203.0 | 2.5 | 2.5 | False | 2.8597 | — | 481.19 | 371.2 | 1.3 | 10.3723 | 29.6578 | `M3_STAT_MIX_OR_PROMOTION` |
| ANTHONY RICHARDSON | QB | rushAtt | 57.6 | 4.0 | 4.0 | False | 3.5 | HI | 14.39 | 11.73 | 1.23 | 14.194 | 49.6789 | `M3_STAT_MIX_OR_PROMOTION` |
| WILL LEVIS | QB | passAtt | 300.1 | 5.5 | 5.5 | False | 2.1878 | — | 54.57 | 45.44 | 1.2 | 10.7051 | 23.4187 | `M3_STAT_MIX_OR_PROMOTION` |
| TREY LANCE | QB | rushAtt | 21.8 | 1.6534 | 1.6534 | False | 3.5 | HI | 13.17 | 11.73 | 1.12 | 11.0622 | 38.7298 | `M3_STAT_MIX_OR_PROMOTION` |
| JAREN HALL | QB | passAtt | 124.5 | 2.5 | 2.5 | False | 2.5909 | — | 49.8 | 45.44 | 1.1 | 8.275 | 21.4508 | `M3_STAT_MIX_OR_PROMOTION` |
| WILL LEVIS | QB | passYds | 2125.2 | 5.5 | 5.5 | False | 2.1878 | — | 386.39 | 371.2 | 1.04 | 10.7051 | 23.4187 | `M3_STAT_MIX_OR_PROMOTION` |

### 2024 · `stratified`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Jeff Driskel | QB | passAtt | 107.4 | 1.5 | 1.5 | False | 3.299 | — | 71.61 | 45.44 | 1.58 | 9.8397 | 32.4421 | `M3_STAT_MIX_OR_PROMOTION` |
| TREY LANCE | QB | passAtt | 113.7 | 1.6534 | 1.6534 | False | 3.0106 | — | 68.79 | 45.44 | 1.51 | 11.0622 | 33.3161 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM EHLINGER | QB | passAtt | 100.3 | 1.5 | 1.5 | False | 2.9798 | — | 66.87 | 45.44 | 1.47 | 9.83 | 29.2909 | `M3_STAT_MIX_OR_PROMOTION` |
| CASE KEENUM | QB | passAtt | 122.6 | 2.0 | 2.0 | False | 2.6164 | — | 61.29 | 45.44 | 1.35 | 9.7363 | 25.4828 | `M3_STAT_MIX_OR_PROMOTION` |
| Jeff Driskel | QB | passYds | 753.9 | 1.5 | 1.5 | False | 3.299 | — | 502.6 | 371.2 | 1.35 | 9.8397 | 32.4421 | `M3_STAT_MIX_OR_PROMOTION` |
| TREY LANCE | QB | passYds | 812.1 | 1.6534 | 1.6534 | False | 3.0106 | — | 491.18 | 371.2 | 1.32 | 11.0622 | 33.3161 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM EHLINGER | QB | passYds | 696.5 | 1.5 | 1.5 | False | 2.9798 | — | 464.31 | 371.2 | 1.25 | 9.83 | 29.2909 | `M3_STAT_MIX_OR_PROMOTION` |
| BRANDON ALLEN | QB | passAtt | 46.7 | 0.8267 | 0.8267 | False | 2.6162 | — | 56.46 | 45.44 | 1.24 | 9.5651 | 25.0145 | `M3_STAT_MIX_OR_PROMOTION` |
| CASE KEENUM | QB | passYds | 834.6 | 2.0 | 2.0 | False | 2.6164 | — | 417.29 | 371.2 | 1.12 | 9.7363 | 25.4828 | `M3_STAT_MIX_OR_PROMOTION` |
| BRANDON ALLEN | QB | passYds | 326.0 | 0.8267 | 0.8267 | False | 2.6162 | — | 394.32 | 371.2 | 1.06 | 9.5651 | 25.0145 | `M3_STAT_MIX_OR_PROMOTION` |
| WILL LEVIS | QB | passAtt | 252.3 | 5.5 | 5.5 | False | 1.839 | — | 45.87 | 45.44 | 1.01 | 10.7051 | 19.6854 | `M3_STAT_MIX_OR_PROMOTION` |
| JAKE FROMM | QB | passAtt | 238.5 | 5.2359 | 5.2359 | False | 2.02 | — | 45.56 | 45.44 | 1.0 | 8.4633 | 17.1001 | `M3_STAT_MIX_OR_PROMOTION` |

### 2025 · `incumbent`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EASTON STICK | QB | passAtt | 187.3 | 1.9004 | 1.9004 | False | 3.2553 | — | 98.55 | 45.44 | 2.17 | 13.432 | 43.7153 | `M3_STAT_MIX_OR_PROMOTION` |
| BAILEY ZAPPE | QB | passAtt | 128.3 | 1.5 | 1.5 | False | 3.5 | HI | 85.55 | 45.44 | 1.88 | 10.694 | 37.4288 | `M3_STAT_MIX_OR_PROMOTION` |
| CASE KEENUM | QB | passAtt | 91.4 | 1.086 | 1.086 | False | 3.5 | HI | 84.13 | 45.44 | 1.85 | 9.619 | 33.6387 | `M3_STAT_MIX_OR_PROMOTION` |
| EASTON STICK | QB | passYds | 1238.6 | 1.9004 | 1.9004 | False | 3.2553 | — | 651.76 | 371.2 | 1.76 | 13.432 | 43.7153 | `M3_STAT_MIX_OR_PROMOTION` |
| LOGAN WOODSIDE | QB | passAtt | 64.8 | 0.8145 | 0.8145 | False | 3.5 | HI | 79.57 | 45.44 | 1.75 | 10.143 | 35.4882 | `M3_STAT_MIX_OR_PROMOTION` |
| JOSHUA DOBBS | QB | passAtt | 231.8 | 3.0 | 3.0 | False | 2.7412 | — | 77.27 | 45.44 | 1.7 | 13.3827 | 36.681 | `M3_STAT_MIX_OR_PROMOTION` |
| Mike White | QB | passAtt | 112.0 | 1.5 | 1.5 | False | 3.1596 | — | 74.65 | 45.44 | 1.64 | 10.4601 | 33.0537 | `M3_STAT_MIX_OR_PROMOTION` |
| BRETT RYPIEN | QB | passAtt | 78.4 | 1.086 | 1.086 | False | 2.8208 | — | 72.2 | 45.44 | 1.59 | 10.2862 | 29.0458 | `M3_STAT_MIX_OR_PROMOTION` |
| BAILEY ZAPPE | QB | passYds | 860.5 | 1.5 | 1.5 | False | 3.5 | HI | 573.69 | 371.2 | 1.55 | 10.694 | 37.4288 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM EHLINGER | QB | passAtt | 56.3 | 0.8145 | 0.8145 | False | 2.5563 | — | 69.15 | 45.44 | 1.52 | 12.1653 | 31.0866 | `M3_STAT_MIX_OR_PROMOTION` |
| CASE KEENUM | QB | passYds | 589.3 | 1.086 | 1.086 | False | 3.5 | HI | 542.64 | 371.2 | 1.46 | 9.619 | 33.6387 | `M3_STAT_MIX_OR_PROMOTION` |
| LOGAN WOODSIDE | QB | passYds | 438.2 | 0.8145 | 0.8145 | False | 3.5 | HI | 537.98 | 371.2 | 1.45 | 10.143 | 35.4882 | `M3_STAT_MIX_OR_PROMOTION` |
| JOSHUA DOBBS | QB | passYds | 1527.5 | 3.0 | 3.0 | False | 2.7412 | — | 509.16 | 371.2 | 1.37 | 13.3827 | 36.681 | `M3_STAT_MIX_OR_PROMOTION` |
| Mike White | QB | passYds | 754.4 | 1.5 | 1.5 | False | 3.1596 | — | 502.95 | 371.2 | 1.35 | 10.4601 | 33.0537 | `M3_STAT_MIX_OR_PROMOTION` |
| JEFF DRISKEL | QB | passAtt | 88.3 | 1.5 | 1.5 | False | 2.3459 | — | 58.89 | 45.44 | 1.3 | 11.6722 | 27.3951 | `M3_STAT_MIX_OR_PROMOTION` |
| TEDDY BRIDGEWATER | QB | passAtt | 77.0 | 1.3575 | 1.3575 | False | 2.1928 | — | 56.75 | 45.44 | 1.25 | 11.9034 | 26.1071 | `M3_STAT_MIX_OR_PROMOTION` |
| BRETT RYPIEN | QB | passYds | 501.3 | 1.086 | 1.086 | False | 2.8208 | — | 461.63 | 371.2 | 1.24 | 10.2862 | 29.0458 | `M3_STAT_MIX_OR_PROMOTION` |
| SAM EHLINGER | QB | passYds | 374.2 | 0.8145 | 0.8145 | False | 2.5563 | — | 459.43 | 371.2 | 1.24 | 12.1653 | 31.0866 | `M3_STAT_MIX_OR_PROMOTION` |
| NATE SUDFELD | QB | passAtt | 60.2 | 1.086 | 1.086 | False | 2.7153 | — | 55.41 | 45.44 | 1.22 | 9.2786 | 25.2024 | `M3_STAT_MIX_OR_PROMOTION` |
| TUA TAGOVAILOA | QB | passAtt | 399.1 | 7.5 | 7.5 | False | 1.7617 | — | 53.21 | 45.44 | 1.17 | 14.5719 | 25.6717 | `M3_STAT_MIX_OR_PROMOTION` |
| TANNER MCKEE | QB | passAtt | 155.3 | 3.0 | 3.0 | False | 1.8262 | — | 51.78 | 45.44 | 1.14 | 14.2487 | 26.0218 | `M3_STAT_MIX_OR_PROMOTION` |
| BRYCE PERKINS | QB | passAtt | 94.8 | 1.9004 | 1.9004 | False | 3.1069 | — | 49.89 | 45.44 | 1.1 | 7.2531 | 22.5271 | `M3_STAT_MIX_OR_PROMOTION` |
| TREVOR SIEMIAN | QB | passAtt | 93.5 | 1.9004 | 1.9004 | False | 2.0093 | — | 49.19 | 45.44 | 1.08 | 8.4185 | 16.9049 | `M3_STAT_MIX_OR_PROMOTION` |
| TUA TAGOVAILOA | QB | passYds | 3014.3 | 7.5 | 7.5 | False | 1.7617 | — | 401.91 | 371.2 | 1.08 | 14.5719 | 25.6717 | `M3_STAT_MIX_OR_PROMOTION` |
| JEFF DRISKEL | QB | passYds | 595.0 | 1.5 | 1.5 | False | 2.3459 | — | 396.69 | 371.2 | 1.07 | 11.6722 | 27.3951 | `M3_STAT_MIX_OR_PROMOTION` |
| EASTON STICK | QB | rushAtt | 24.0 | 1.9004 | 1.9004 | False | 3.2553 | — | 12.61 | 11.73 | 1.07 | 13.432 | 43.7153 | `M3_STAT_MIX_OR_PROMOTION` |
| JUSTIN FIELDS | QB | rushAtt | 93.9 | 7.5 | 7.5 | False | 2.2628 | — | 12.52 | 11.73 | 1.07 | 12.6335 | 28.5881 | `M3_STAT_MIX_OR_PROMOTION` |
| TEDDY BRIDGEWATER | QB | passYds | 531.7 | 1.3575 | 1.3575 | False | 2.1928 | — | 391.72 | 371.2 | 1.06 | 11.9034 | 26.1071 | `M3_STAT_MIX_OR_PROMOTION` |
| NATE SUDFELD | QB | passYds | 406.9 | 1.086 | 1.086 | False | 2.7153 | — | 374.66 | 371.2 | 1.01 | 9.2786 | 25.2024 | `M3_STAT_MIX_OR_PROMOTION` |
| JUSTIN FIELDS | QB | passAtt | 342.5 | 7.5 | 7.5 | False | 2.2628 | — | 45.67 | 45.44 | 1.01 | 12.6335 | 28.5881 | `M3_STAT_MIX_OR_PROMOTION` |
| RASHEE RICE | WR | rec | 52.2 | 5.9192 | 5.9192 | False | 2.4038 | — | 8.82 | 8.79 | 1.0 | 9.9853 | 23.9999 | `M3_STAT_MIX_OR_PROMOTION` |

### 2025 · `stratified`

| player | pos | stat | season | g | gsafe | floored | scale | clamp | implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CASE KEENUM | QB | passAtt | 91.4 | 1.086 | 1.086 | False | 3.5 | HI | 84.13 | 45.44 | 1.85 | 9.619 | 33.6387 | `M3_STAT_MIX_OR_PROMOTION` |
| LOGAN WOODSIDE | QB | passAtt | 64.4 | 0.8145 | 0.8145 | False | 3.4778 | — | 79.06 | 45.44 | 1.74 | 10.143 | 35.2628 | `M3_STAT_MIX_OR_PROMOTION` |
| CASE KEENUM | QB | passYds | 589.3 | 1.086 | 1.086 | False | 3.5 | HI | 542.64 | 371.2 | 1.46 | 9.619 | 33.6387 | `M3_STAT_MIX_OR_PROMOTION` |
| LOGAN WOODSIDE | QB | passYds | 435.4 | 0.8145 | 0.8145 | False | 3.4778 | — | 534.58 | 371.2 | 1.44 | 10.143 | 35.2628 | `M3_STAT_MIX_OR_PROMOTION` |
| BAILEY ZAPPE | QB | passAtt | 81.0 | 1.5 | 1.5 | False | 2.2088 | — | 53.99 | 45.44 | 1.19 | 10.694 | 23.6133 | `M3_STAT_MIX_OR_PROMOTION` |
| EASTON STICK | QB | passAtt | 94.1 | 1.9004 | 1.9004 | False | 1.6359 | — | 49.52 | 45.44 | 1.09 | 13.432 | 21.9683 | `M3_STAT_MIX_OR_PROMOTION` |
| Mike White | QB | passAtt | 73.7 | 1.5 | 1.5 | False | 2.0801 | — | 49.15 | 45.44 | 1.08 | 10.4601 | 21.7607 | `M3_STAT_MIX_OR_PROMOTION` |


## 5. Reading — what this licenses, and what it does not

**The hypothesis is REFUTED.** `gsafe == proj_games` on EVERY row of EVERY diagnosed fold — the assignment's games floor never moved a divisor, so it cannot have produced a single violation. The hypothesis is refuted by a two-sided measurement, not by an absent effect: the mechanism could not act (NF1.9 / NF-D20). The floor's own recorded self-check (`games_floor_binding()`) agrees, and so does the WIDER definition the kernel actually applies, so the refutation does not rest on the narrower count.

⭐ **THE RESIDUALS ARE TWO DIFFERENT POPULATIONS, and only one of them is the kind of thing a tolerance is for.**

* **The rate-assignment arms** (`points_rate_permute`, `rate_refit`, `points_rate_stratified`, `rate_refit_stratified`) leave at worst **1.1×** the all-time envelope, on players carrying at least **8.0** expected games, with **0** violating rows on a player under 2 expected games, at most **0.2857** players per fold. Every one is the SAME shape: the multiset a rate arm preserves is the FANTASY-POINT rate multiset, not each counting stat's own rate, so a full-season dual-threat QB promoted to another QB's points rate carries his own stat MIX up with him and grazes a single counting ceiling. That is a mechanism-level edge effect on the envelope boundary — the thing a declared tolerance can be designed around, ⛔ though designing one is a PM decision this node does not take.

* **`stratified` is not that.** It leaves **8.5714** players per fold on **7/7** folds, worst **1.85×** over, on a row with **0.815** expected games, and **35** of its violating rows (0.3684) sit on a player under 2 expected games. The incumbent's own residual is **19.1429** players per fold, worst **2.51×**, **0.3417** under 2 games. ⇒ **`stratified` is the incumbent's defect at lower VOLUME, not a different defect** — the same rows, the same magnitudes, the same low-availability concentration. NF-INJ1's founding row is *Easton Stick at 1.9 expected games with 82.7 pass attempts per game*; `stratified` still serves rows of exactly that shape (and Easton Stick himself is among them on the 2025 fold). A tolerance wide enough to admit them would not be a tolerance, it would be the guard switched off.

⛔ **This node takes no decision.** It establishes a mechanism and refutes one; the coherence clause, its attribution rule and any tolerance are the PM's to re-scope, and the NF-INJ2c spec makes that explicit: a refuted node-1 STOPS the story here rather than letting a pre-registration be written around a mechanism that was never there.

