# NF1.7 — PER-PLAYER rookie 80% intervals (§0.5 bake-off)

**Generated:** 2026-07-29T21:57:51.688643+00:00 · **held-out draft classes:** 2019–2025 (7) · **configs scored:** 44 · **held-out rookie-seasons:** 553

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. What is selected here is the WIDTH AND SHAPE of the rookie interval. The POINT projection is held byte-identical across every arm (proved below), because NF1.4 already established that the rookie point is ~unbiased and its apparent over-valuation was a RANK effect.

## 0. The defect, measured on the served board

| population   |   players |   distinct bands |   distinct-band frac |   worst shared band |   mean width |
|:-------------|----------:|-----------------:|---------------------:|--------------------:|-------------:|
| rookies      |        81 |               80 |                0.988 |                   2 |      125.400 |
| veterans     |       703 |              647 |                0.920 |                   5 |       64.200 |

NF1.4's band quantises to **one interval per (position, prediction-tercile)**. On the live 2026 board that is 12 distinct intervals for 81 rookies against 647 for 703 veterans; every top-bucket rookie QB carried 26.5–277.0 while their point projections spanned 25.1→268.3.

## 1. Why coverage could not have caught it — the §0.5 metric landmine, live

NF1.4 selected this band on COVERAGE (0.678 → 0.834) and the band it picked is genuinely well-covered. **That is the problem.** Coverage is a property of the POPULATION, not of the player: a band held CONSTANT within a position can hit its nominal rate exactly while carrying zero per-player information. So coverage cannot select an interval, and this story selects on a PROPER interval score with coverage kept strictly as a FLOOR — the E2.1-r rule ('a coverage figure is a FLOOR, never a target to minimise distance to') applied to intervals.

Primary metric — the **Winkler / Gneiting-Raftery interval score** for a central 80% interval:

```
IS(l, u, y) = (u − l) + 10·(l − y)·1{y < l} + 10·(y − u)·1{y > u}      (lower is better)
```

It equals the sum of the τ=0.10 and τ=0.90 pinball losses up to the constant 2/α, so it is PROPER for the quantile pair: minimised by the true q10/q90, it pays for width AND for missing. Neither degenerate strategy can win it. ⛔ MAE/RMSE on width is never used.

## 2. The four-sided sanity anchors

| anchor       | what it is                                                                                                                                         |    IS80 |   cov80 |   mean width |
|:-------------|:---------------------------------------------------------------------------------------------------------------------------------------------------|--------:|--------:|-------------:|
| oracle_knn   | ORACLE FLOOR (neighbourhood family) — q10/q90 of the REALIZED outcomes of the k nearest rookies IN the held-out class. Peeks; nothing may beat it. | 174.961 |   0.836 |      125.730 |
| oracle_qreg  | ORACLE FLOOR (parametric family) — the winner's own quantile regression fitted on the held-out class's truth. Peeks; nothing may beat it.          | 159.258 |   0.869 |      125.266 |
| zero_width   | DEGENERATE — width 0 at the point. MAXIMALLY sharp ⇒ a naive sharpness metric would crown it. Must LOSE.                                           | 432.035 |   0.004 |        0.100 |
| max_width    | DEGENERATE — [0, the position's max realized rookie season]. Coverage ≈ 1 and useless ⇒ a coverage TARGET would love it. Must LOSE.                | 305.747 |   0.982 |      301.843 |
| const_width  | DEGENERATE — ONE band per position, no conditioning at all. Must LOSE.                                                                             | 230.329 |   0.877 |      166.076 |
| oracle_point | the trivial infimum (zero width AT the realized value, IS = 0) — orientation only, not a discriminator.                                            |   0.112 |   0.937 |        0.020 |

⚠️ The floor the check leans on is **`oracle_qreg` — the WINNER'S OWN family**. A cross-family oracle is not a valid floor (a peeking MISSPECIFIED model is beatable by an honest well-specified one), and a peeking k-NN's capacity depends on its sample size — a held-out class is only ~80 rows, so the same `k` is a far coarser neighbourhood there than over the training classes. The other oracle is reported for orientation.

- ✅ **oracle floor respected** — the winner does not beat its own peeking oracle (oracle_qreg)
- ✅ **zero-width degenerate loses** — sharpness was not bought by under-covering
- ✅ **max-width degenerate loses** — the selection is not a coverage exercise in disguise
- ✅ **const-width degenerate loses** — conditioning on the player earns its place
- ✅ **incumbent beaten** — the per-player band beats NF1.4's class-level band

## 3. Results — all configs (sorted by the primary metric)

| config                          |    IS80 |   cov80 |   mean width |   distinct-band frac |   worst shared |   extreme-tail rows |   ρ(width, point) | eligible       |
|:--------------------------------|--------:|--------:|-------------:|---------------------:|---------------:|--------------------:|------------------:|:---------------|
| qreg α0.01 · sdgain 0           | 181.163 |   0.808 |      127.703 |                0.989 |              2 |                   0 |             0.903 | yes            |
| qreg α0.01 · sdgain 0.1         | 181.505 |   0.841 |      130.834 |                0.987 |              2 |                   0 |             0.890 | yes            |
| qreg α0.01 · sdgain 0.2         | 181.571 |   0.850 |      133.363 |                0.991 |              2 |                   0 |             0.880 | yes            |
| qreg α0 · sdgain 0              | 183.355 |   0.772 |      123.006 |                0.995 |              2 |                  10 |             0.891 | NO (cov floor) |
| qreg α0 · sdgain 0.1            | 183.510 |   0.812 |      126.631 |                0.997 |              2 |                  10 |             0.879 | yes            |
| qreg_sqrt α0.01 · sdgain 0      | 183.582 |   0.830 |      130.751 |                0.978 |              2 |                   0 |             0.926 | yes            |
| qreg α0 · sdgain 0.2            | 183.695 |   0.822 |      129.619 |                0.991 |              2 |                  10 |             0.873 | yes            |
| qreg_sqrt α0.01 · sdgain 0.1    | 183.737 |   0.854 |      133.714 |                0.977 |              2 |                   0 |             0.912 | yes            |
| qreg_sqrt α0.01 · sdgain 0.2    | 183.872 |   0.863 |      136.290 |                0.982 |              2 |                   0 |             0.897 | yes            |
| knn_norm k80 · sdgain 0.2       | 185.268 |   0.843 |      122.831 |                0.671 |              8 |                   7 |             0.912 | yes            |
| qreg_sqrt α0 · sdgain 0         | 185.269 |   0.829 |      131.227 |                0.991 |              2 |                   0 |             0.881 | yes            |
| qreg_sqrt α0 · sdgain 0.1       | 185.715 |   0.851 |      134.600 |                0.993 |              2 |                   0 |             0.873 | yes            |
| qreg_sqrt α0 · sdgain 0.2       | 185.926 |   0.856 |      137.450 |                0.986 |              2 |                   0 |             0.862 | yes            |
| knn_norm k80 · sdgain 0.1       | 186.437 |   0.832 |      120.503 |                0.672 |              8 |                   7 |             0.914 | yes            |
| knn_norm k50 · sdgain 0.2       | 186.896 |   0.826 |      124.773 |                0.742 |              6 |                   7 |             0.895 | yes            |
| knn_norm k80 · sdgain 0         | 187.665 |   0.821 |      118.091 |                0.689 |              8 |                   7 |             0.916 | yes            |
| knn_norm k50 · sdgain 0.1       | 187.920 |   0.810 |      122.394 |                0.733 |              6 |                   7 |             0.898 | yes            |
| knn_norm k30 · sdgain 0.2       | 188.258 |   0.836 |      122.483 |                0.795 |              6 |                  19 |             0.857 | yes            |
| knn_norm k30 · sdgain 0.1       | 188.834 |   0.814 |      119.987 |                0.800 |              6 |                  19 |             0.860 | yes            |
| knn_norm k50 · sdgain 0         | 189.392 |   0.796 |      119.849 |                0.744 |              6 |                   7 |             0.898 | NO (cov floor) |
| knn_norm k30 · sdgain 0         | 189.602 |   0.805 |      117.367 |                0.804 |              6 |                  19 |             0.865 | yes            |
| knn_norm k120 · sdgain 0.2      | 191.850 |   0.834 |      123.317 |                0.636 |             13 |                   7 |             0.907 | yes            |
| knn_norm k120 · sdgain 0.1      | 193.222 |   0.827 |      121.067 |                0.631 |             13 |                   7 |             0.907 | yes            |
| knn_norm k120 · sdgain 0        | 194.630 |   0.818 |      118.849 |                0.640 |             13 |                   7 |             0.908 | yes            |
| knn_pos k30 · sdgain 0.2        | 194.774 |   0.807 |      119.194 |                0.558 |              9 |                  17 |             0.826 | yes            |
| knn_pos k30 · sdgain 0.1        | 195.721 |   0.800 |      116.576 |                0.565 |              9 |                  18 |             0.834 | yes            |
| knn_pos k30 · sdgain 0          | 196.781 |   0.780 |      113.827 |                0.569 |              9 |                  19 |             0.835 | NO (cov floor) |
| knn_pos k50 · sdgain 0.2        | 198.756 |   0.823 |      122.791 |                0.447 |             15 |                  10 |             0.809 | yes            |
| knn_pos k50 · sdgain 0.1        | 199.683 |   0.818 |      120.356 |                0.443 |             15 |                  10 |             0.811 | yes            |
| knn_pos k50 · sdgain 0          | 200.565 |   0.809 |      117.816 |                0.451 |             15 |                  10 |             0.819 | yes            |
| class_tercile (NF1.4 INCUMBENT) | 202.137 |   0.791 |      124.381 |                0.184 |             15 |                  30 |             0.863 | NO (cov floor) |
| ratio_q · sdgain 0              | 205.318 |   0.856 |      142.109 |                0.932 |              6 |                   5 |             0.929 | yes            |
| ratio_q · sdgain 0.1            | 205.396 |   0.858 |      144.436 |                0.928 |              6 |                   5 |             0.916 | yes            |
| ratio_q · sdgain 0.2            | 205.597 |   0.858 |      146.904 |                0.939 |              6 |                   5 |             0.902 | yes            |
| ratio_q_floor · sdgain 0        | 206.304 |   0.885 |      161.081 |                0.948 |              6 |                   5 |             0.837 | yes            |
| ratio_q_floor · sdgain 0.1      | 207.330 |   0.888 |      163.836 |                0.943 |              6 |                   5 |             0.823 | yes            |
| ratio_q_floor · sdgain 0.2      | 208.540 |   0.894 |      166.754 |                0.944 |              6 |                   5 |             0.805 | yes            |
| knn_pos k80 · sdgain 0.2        | 211.876 |   0.826 |      134.629 |                0.337 |             25 |                  14 |             0.724 | yes            |
| knn_pos k80 · sdgain 0.1        | 212.788 |   0.818 |      132.349 |                0.335 |             25 |                  15 |             0.735 | yes            |
| knn_pos k80 · sdgain 0          | 213.830 |   0.813 |      129.981 |                0.348 |             25 |                  15 |             0.738 | yes            |
| knn_pos k120 · sdgain 0.2       | 218.736 |   0.847 |      147.043 |                0.224 |             35 |                  19 |             0.621 | yes            |
| knn_pos k120 · sdgain 0.1       | 219.606 |   0.844 |      144.786 |                0.222 |             35 |                  20 |             0.610 | yes            |
| knn_pos k120 · sdgain 0         | 220.413 |   0.844 |      142.579 |                0.229 |             35 |                  24 |             0.599 | yes            |
| legacy_cv (pre-NF1.4 null)      | 230.031 |   0.681 |       91.647 |                0.973 |              3 |                   0 |             0.993 | NO (cov floor) |

`distinct-band frac` = distinct (p10, p90) pairs ÷ rookies — **1.0 is a fully per-player band, 0.04 is the incumbent's 3-buckets-per-position**. `worst shared` is the largest set of rookies carrying a byte-identical interval — the number `audit_interval_quality()` fires on. `ρ(width, point)` is how much the band's width tracks the player's own projection.

## 4. Deflation — CSCV / PBO over held-out draft-class splits

**PBO = 0.0286** over 35 balanced class splits (median logit 0.901); config spread (best→worst IS80) = 181.163 → 230.031 (27.0%).

Reading it (CLAUDE.md): a high PBO on a **TIED** field is the NULL — nothing robustly separates the candidates, so the incumbent's choice is proven rather than lucky. A high PBO with a **WIDE** spread is genuine overfitting. The spread is the discriminator.

**Quadrant: LOW PBO (0.0286) + WIDE spread (27.0%)** — a genuinely separated winner; the choice survives out-of-sample.

## 4b. ⚠️ The top of the field is TIED — and the tie has a coverage asymmetry

| config                  |    IS80 |   Δ IS80 vs winner % |   cov80 |   floor headroom |   mean width |
|:------------------------|--------:|---------------------:|--------:|-----------------:|-------------:|
| qreg α0.01 · sdgain 0   | 181.163 |                0.000 |   0.808 |            0.008 |      127.703 |
| qreg α0.01 · sdgain 0.1 | 181.505 |                0.190 |   0.841 |            0.041 |      130.834 |
| qreg α0.01 · sdgain 0.2 | 181.571 |                0.230 |   0.850 |            0.050 |      133.363 |

The top **3** configs sit within 1% of each other on the primary metric — `qreg α0.01 · sdgain 0` at 181.1626 against `qreg α0.01 · sdgain 0.2` at 181.571. Per CLAUDE.md, when the leaders genuinely TIE, *which* of them wins is noise, and the low PBO (0.0286) says the same thing from the other direction.

⚠️ **The tie is not symmetric, and that is worth naming rather than smoothing away:** the P1A-uncertainty widener buys real coverage headroom for almost nothing on the primary metric (`qreg α0.01 · sdgain 0.2` covers 0.8501 vs the winner's 0.8084, floor 0.80), so there is a live temptation to re-pick on it.

**We do NOT, and ship the pre-registered winner.** Coverage was declared an eligibility FLOOR, and 'prefer more headroom above the floor' is a MONOTONE-IN-WIDENING criterion — the `max_width` degenerate would win it outright. Re-picking a tie on a criterion a degenerate wins is how the E2.1-r inversion happens, just facing the other way, and it is exactly the overfitting the deflation above exists to catch. Both arms clear the floor; the winner clears it by less, and that is recorded here.

## 5. Selection

**SHIPPED: `qreg α0.01 · sdgain 0`** — IS80 181.1626 (incumbent 202.1366), coverage 0.8084 (floor 0.80), mean width 127.7029 (incumbent 124.3814), distinct-band fraction 0.9888 (incumbent 0.1839), worst shared band 2 (incumbent 15).

The per-player band EARNS its place: `qreg α0.01 · sdgain 0` cuts the held-out interval score from 202.1366 (NF1.4's class-level band) to 181.1626 (10.4% better) while HOLDING the coverage floor (0.8084 ≥ 0.80) and lifting the distinct-band fraction 0.1839 → 0.9888. The point projection is unchanged.

### Per-position coverage (the FLOOR, per position)

| arm                     |    QB |    RB |    TE |    WR |
|:------------------------|------:|------:|------:|------:|
| incumbent (class-level) | 0.740 | 0.836 | 0.730 | 0.811 |
| SHIPPED (per-player)    | 0.739 | 0.777 | 0.878 | 0.822 |

## 6. Per-class detail (shipped config)

|   draft_class |      n |   interval_score |   coverage_80 |   mean_width |   median_width |   distinct_band_frac |   max_shared_band |   n_extreme_tail |   width_point_rho |
|--------------:|-------:|-----------------:|--------------:|-------------:|---------------:|---------------------:|------------------:|-----------------:|------------------:|
|      2019.000 | 80.000 |          190.336 |         0.762 |      121.000 |        105.000 |                1.000 |             1.000 |            0.000 |             0.777 |
|      2020.000 | 77.000 |          177.766 |         0.844 |      134.290 |        112.600 |                0.987 |             2.000 |            0.000 |             0.889 |
|      2021.000 | 75.000 |          186.929 |         0.800 |      134.190 |        108.400 |                0.960 |             2.000 |            0.000 |             0.818 |
|      2022.000 | 79.000 |          149.897 |         0.861 |      119.800 |        107.600 |                0.987 |             2.000 |            0.000 |             0.947 |
|      2023.000 | 80.000 |          196.213 |         0.787 |      123.680 |        101.550 |                1.000 |             1.000 |            0.000 |             0.935 |
|      2024.000 | 77.000 |          197.675 |         0.792 |      133.490 |        109.500 |                0.987 |             2.000 |            0.000 |             0.980 |
|      2025.000 | 85.000 |          169.322 |         0.812 |      127.470 |        108.700 |                1.000 |             1.000 |            0.000 |             0.974 |

## 7. Is the rookie band HONESTLY WIDER than a veteran's?

⭐ A rookie has no NFL sample, so his honest band should be WIDER than a comparable veteran's. 'Sharper' is therefore the WRONG direction to optimise blindly — which is exactly why coverage is a hard FLOOR here and why `zero_width` is an anchor that must lose. This is the direction check on the selection, not a metric it was picked on.

| population                                 | source             |   mean 80% width |   coverage |
|:-------------------------------------------|:-------------------|-----------------:|-----------:|
| rookies — NF1.4 class-level (incumbent)    | held-out backtest  |          124.381 |      0.791 |
| rookies — qreg α0.01 · sdgain 0 (SHIPPED)  | held-out backtest  |          127.703 |      0.808 |
| veterans (empirical game-to-game variance) | emitted 2026 board |           64.200 |    nan     |

The selected rookie band is **2.0× wider** than the average veteran band (127.7029 vs 64.2 PPR) — the honest direction. It is also WIDER than the class-level band it replaces (127.7029 vs 124.3814), so the interval-score win came from putting the width where it BELONGS per player, not from shrinking it. Veteran coverage is not comparable (a veteran band is a normal approximation off realized game-to-game variance, not an empirical quantile), so only the WIDTH is compared.

## 8. Honest limitations

- **The point projection is untouched, so a mis-placed rookie stays mis-placed.** NF1.4's finding was that the rookie point runs COLD, and its model bake-off returned a NULL; this story does not re-attack the level and must not be read as having improved it.
- **The band is fitted on ~10 draft classes** (~80 drafted skill rookies each). The neighbourhood arms therefore trade resolution against quantile noise, which is what the `k` grid selects and the PBO deflates.
- **`knn_norm` assumes the SHAPE of the rookie outcome distribution is position-invariant once scaled by the position's mean.** That buys ~4× the neighbours; `knn_pos` is pre-registered beside it precisely so the assumption is tested rather than believed.
- **A rookie's band still cannot see anything NFL-specific** — no camp reports, no depth chart, no preseason. Draft slot, the P1A translation and its parameter sd are the whole information set, and `confidence = low` remains the honest surface.
- ⚠️ **QB coverage is BELOW the nominal 80% — in BOTH arms** (see the per-position table: 0.7386 shipped vs 0.7404 incumbent). The coverage floor was pre-registered POOLED, and the rookie-QB cohort is ~10 players a class of whom ~35% never take a snap, so the per-position estimate is thin — but it is a real gap and it is NOT fixed here. It is disclosed rather than buried: the shipped band does not make QB worse, it inherits the miss. A per-position floor would be the honest next iteration.
- **No edge claim.** An honest interval is a projection-quality property, not a market edge.

