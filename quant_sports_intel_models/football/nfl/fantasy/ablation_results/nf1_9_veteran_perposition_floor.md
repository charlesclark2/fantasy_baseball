# NF1.9 — the VETERAN 80% interval, measured and re-selected under a PER-POSITION coverage FLOOR (§0.5 bake-off)

**Generated:** 2026-07-30T04:37:59.798373+00:00 · **held-out target seasons:** 2013–2025 (13) · **configs scored:** 75 · **held-out veteran-seasons:** 8398 · **bake-off wall time:** 319.8s

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. What is selected is the WIDTH AND SHAPE of the veteran interval; the POINT projection is untouched and asserted unchanged (§6).

## 0. The gap: 90% of the board had never been measured

The NF1.4 → NF1.7 → NF1.8 arc validated intervals for the **81 rookies** on the 2026 board. The **703 veterans** carried `point ± 1.2816·season_sd` — a NORMAL APPROXIMATION off game-to-game scoring variance plus a games-played term, labelled `uncertainty_type = "empirical"` — and no veteran interval-coverage number existed in ANY ablation report. NF1.7's own §7 said so explicitly: *"Veteran coverage is not comparable … so only the WIDTH is compared."* It had never been measured, so it had never been wrong.

| population                                             |   n (held-out) |   nominal |   realized coverage |   below p10 |   above p90 |   mean 80% width |    IS80 |
|:-------------------------------------------------------|---------------:|----------:|--------------------:|------------:|------------:|-----------------:|--------:|
| VETERANS — the served normal approximation (INCUMBENT) |           8398 |     0.800 |               0.545 |       0.272 |       0.183 |           73.080 | 205.961 |
| … at FB                                                |            299 |     0.800 |               0.415 |     nan     |     nan     |           19.500 |  62.420 |
| … at QB                                                |           1116 |     0.800 |               0.682 |     nan     |     nan     |          123.500 | 274.890 |
| … at RB                                                |           2018 |     0.800 |               0.549 |     nan     |     nan     |           76.300 | 233.960 |
| … at TE                                                |           1801 |     0.800 |               0.536 |     nan     |     nan     |           47.700 | 146.440 |
| … at WR                                                |           3164 |     0.800 |               0.511 |     nan     |     nan     |           72.800 | 211.240 |

⭐ **It misses on BOTH tails at once** — 27.2% of held-out veteran-seasons land BELOW p10 and 18.3% ABOVE p90, against 10% + 10% nominal. That two-sided pattern is the diagnosis, not just the symptom: a SYMMETRIC band on a RIGHT-SKEWED target cannot fit both tails, so widening σ can only trade one miss for the other. §4 puts a number on that with the two variance-rescaling nulls.

### 🚨 The population is the whole ballgame

Every other veteran backtest in this program joins the realized season `how="inner"` and keeps `g >= 6` (`holdout_backtest`, `score_vs_realized`, the NF1.2/NF1.5 feature pools). That is CORRECT for a rank read and FATAL for an interval read: it drops exactly the veterans whose season was ended by injury, benching or release — the left tail the band exists to price. This panel LEFT-joins and scores a projected veteran with no realized row as a real **0**. **26.2% of projected veteran-seasons are zero-game seasons.** NF1.4 made the identical population fix for rookies; this is that fix on the other 90% of the board.

| reading                                                           | value        |
|:------------------------------------------------------------------|:-------------|
| projected veteran-seasons in the panel                            | 11885        |
| … that played ZERO games in the target season                     | 3118 (26.2%) |
| … that played < 6 games (what every other veteran backtest DROPS) | 4927 (41.5%) |
| held-out veteran-seasons scored here                              | 8398         |

## 0b. 🚨 COVERAGE IS STRUCTURALLY NON-BINDING ON THIS POPULATION — the E2.1-r landmine in a new population

⚠️ **Read this before reading any coverage number below.** **30.8% of projected veteran-seasons realize EXACTLY 0 PPR** (26.2% play no games at all), and the served band's lower bound is floored at 0, so a point mass sits exactly ON the bound. Three consequences, all structural rather than incidental:

1. **The LEFT tail is nearly un-missable.** The shipped arm's below-p10 rate is 0.025 against a nominal 0.10 — not because the lower bound is well calibrated but because an outcome sitting ON the bound counts as covered. **83% of the shipped band's lower bounds are 0.**
2. **So coverage ≈ 1 − P(y > p90) for ANY honest band, and a 0.80 coverage TARGET would be INVERTED** — the only way to hit 0.80 exactly would be to deliberately under-cover the right tail, i.e. to make the band worse on purpose. This is precisely CLAUDE.md's E2.1-r rule ('inclusive bounds inflate a CORRECTLY-specified model's coverage; gate on a proper score and keep coverage as a FLOOR, never a target') arriving in a new population. The peeking oracle — which knows the answers — itself covers **0.8733**, so a correctly-specified band lands near that, not at 0.80.
   ⚠️ **CORRECTION TO AN EASY ASSUMPTION, because it is not quite true:** a fantasy season CAN be negative — **102 of 11885 veteran-seasons (0.86%) realize below 0** (min -7.28 PPR; 86 of them QBs, where interceptions and fumbles outweigh a snap or two of production). The `lo ≥ 0` clip therefore makes those 0.86% of rows UNCOVERABLE by construction, in this band and in the rookie band that shares the contract. The clip is kept deliberately — a displayed negative p10 is worse for a drafter than a bounded 0.86%-of-rows blind spot — but it is a real ceiling on achievable coverage and it is stated rather than assumed away.
3. **The per-position coverage floor is therefore a REAL constraint that turns out NON-BINDING**, and the conformal layer is a no-op for the same reason: the (1−α) quantile of the conformity scores is pinned at EXACTLY 0 by the atom (~29% of training scores are exactly 0), so a Mondrian adjustment has nothing it can move. Both facts are reported rather than hidden — the whole selection is carried by the interval score, exactly as pre-registered, and the honest per-tail diagnostic is the `above p90` column (nominal 0.10), which is reported beside every arm and per position but **never selected on**.

|   projection decile |       n |   mean projected PPR |   share playing ZERO games |   empirical q10 of the realized season |   empirical q50 |   empirical q90 |
|--------------------:|--------:|---------------------:|---------------------------:|---------------------------------------:|----------------:|----------------:|
|               1.000 | 840.000 |               10.200 |                      0.488 |                                  0.000 |           0.000 |          17.900 |
|               2.000 | 840.000 |               17.400 |                      0.445 |                                  0.000 |           0.000 |          26.400 |
|               3.000 | 840.000 |               22.500 |                      0.420 |                                  0.000 |           0.000 |          45.200 |
|               4.000 | 839.000 |               28.600 |                      0.347 |                                  0.000 |           3.400 |          67.900 |
|               5.000 | 840.000 |               35.500 |                      0.301 |                                  0.000 |           7.700 |          83.300 |
|               6.000 | 840.000 |               45.600 |                      0.248 |                                  0.000 |          19.800 |         117.800 |
|               7.000 | 839.000 |               60.700 |                      0.190 |                                  0.000 |          38.400 |         146.500 |
|               8.000 | 840.000 |               83.200 |                      0.130 |                                  0.000 |          83.300 |         183.100 |
|               9.000 | 840.000 |              116.900 |                      0.089 |                                  0.600 |         126.200 |         246.500 |
|              10.000 | 840.000 |              195.800 |                      0.033 |                                 83.800 |         219.400 |         330.600 |

⭐ **And this is why the fix had to be a new SHAPE, and why a `p10 = 0` for everyone would ALSO be wrong.** The empirical conditional q10 is genuinely 0 for the bottom eight deciles — a mid-tier veteran's honest 10th percentile IS nothing — but it is clearly POSITIVE at the top (83.8 PPR in the top decile, where only 0.033 play no games). A band that floors every veteran at 0 throws that away and carries no per-player left-tail information — the NF1.7 defect in a new guise. A band that prices every veteran symmetrically off `season_sd`, as the incumbent does, gets the bottom eight deciles badly wrong. The pre-registered NEIGHBOURHOOD arms (`knn_pos`/`knn_norm`) are the instrument that can express both, because an empirical quantile of comparable players' outcomes handles a point mass natively; the parametric foil has to force one linear q10 through a target that is 0 for most of its range. §4's leaderboard is where that is settled, on the metric, rather than argued.

## 1. The pre-registered PER-POSITION floor

**Tier 1 (primary):** pooled coverage ≥ 0.80 **and** every position with ≥ 400 held-out veteran-seasons ≥ the nominal 0.80.

**Tier 2 (documented fallback, used only if Tier 1 admits nothing):** the structurally-thin positions (FB — ~30 projected a season) relax to `nominal − 1.645·SE(n)`. Derived from SAMPLE SIZE alone, a design quantity known before any result, which is what stops it being a floor reverse-engineered from the answer.

**TIER USED: 1** — 74 of 74 per-player configs clear the Tier-1 hard nominal floor at every position, so the pre-registered Tier-2 relaxation was NOT needed.

| position   |   floor |   n (held-out veteran-seasons) |
|:-----------|--------:|-------------------------------:|
| QB         |   0.800 |                           1116 |
| RB         |   0.800 |                           2018 |
| TE         |   0.800 |                           1801 |
| WR         |   0.800 |                           3164 |

## 2. The anchor set — four guards, carried from NF1.7/NF1.8

| anchor              | what it is                                                                                                                                                    |    IS80 |   pooled cov80 |   mean width |
|:--------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------|--------:|---------------:|-------------:|
| permuted_own        | ⭐ PERMUTATION ORACLE — the WINNER'S OWN arm, same family and resolution, fitted on SHUFFLED training outcomes. Must LOSE.                                    | 251.861 |          0.898 |      196.380 |
| permuted_alt        | PERMUTATION ORACLE in a DIFFERENT candidate family, so the check is never the only arm that fitted. Must LOSE.                                                | 250.347 |          0.901 |      198.180 |
| oracle_own_family   | PEEKING oracle in the WINNER'S OWN family, fitted on the held-out season's truth. Valid as a floor only against a MATCHED-n arm (next row).                   | 179.810 |          0.829 |      112.150 |
| matched_n_candidate | ⭐ the winner's OWN arm trained on ONE prior season, so its resolution matches the oracle's. The oracle must beat THIS — that is the well-posed oracle floor. | 182.924 |          0.832 |      114.300 |
| oracle_knn          | peeking oracle, neighbourhood family. Orientation.                                                                                                            | 159.678 |          0.873 |      117.910 |
| zero_width          | DEGENERATE — width 0 at the point. MAXIMALLY sharp ⇒ a naive sharpness metric would crown it. Must LOSE.                                                      | 407.373 |          0.001 |        0.100 |
| max_width           | DEGENERATE — [0, the position's max realized veteran season]. Coverage ≈ 1 ⇒ a coverage TARGET would love it. Must LOSE.                                      | 391.862 |          0.990 |      391.600 |
| const_width         | DEGENERATE — ONE band per position, no conditioning at all. Must LOSE.                                                                                        | 237.720 |          0.899 |      191.170 |
| oracle_point        | the trivial infimum (zero width AT the realized value) — orientation only, not a discriminator.                                                               |   0.082 |          0.991 |        0.020 |

⭐ **The oracle the checks lean on is a PERMUTATION** (`permuted_*`): the same family, on the same rows, fitted against a SHUFFLE of the training outcomes instead of the truth. Knowing the answer must score better than not knowing it. Unlike a peeking fitted oracle this is well-posed at ANY sample size — family and resolution are held exactly equal and only the information content moves. The same-family peeking oracles are reported and checked too, for orientation.

- ✅ **permutation oracle respected** — the winner beats its OWN family fitted on SHUFFLED outcomes (251.861 vs 160.888) — the metric rewards information, not width
- ✅ **peeking oracle respected AT MATCHED n** — the peeking same-family oracle (IS80 179.81, fitted on the held-out season only) beats the winner's OWN arm trained on a single prior season (IS80 182.924) — so at EQUAL family AND EQUAL resolution, knowing the answer helps. This is the valid form of the oracle floor (NF1.7 lesson 2)
- ⚠️ **same-family peeking oracle respected (UNMATCHED n — orientation only)** — the winner (160.888) BEATS the peeking oracle (179.81) — **expected here and NOT a metric inversion**: the oracle can only be fitted on the held-out season (~646 rows) while the winner trains on ~7236, and 'peeking can only help' holds only at EQUAL family AND EQUAL resolution (NF1.7 lesson 2). The matched-n check above is the valid form and it PASSES; the permutation oracle is the one the gate leans on
- ✅ **zero-width degenerate loses** — sharpness was not bought by under-covering
- ✅ **max-width degenerate loses** — the selection is not a coverage exercise in disguise — see the table below
- ✅ **const-width degenerate loses** — conditioning on the player earns its place
- ✅ **incumbent beaten** — the selected band beats the served normal approximation
- ✅ **per-position floor met** — every constrained position clears its floor (QB 0.8575≥0.800, RB 0.8865≥0.800, TE 0.8884≥0.800, WR 0.9068≥0.800)
- ✅ **served band reproduced** — the INCUMBENT arm is the band the board actually emitted (max drift 0.0e+00)

### ⭐ The proof the per-position floor is a CONSTRAINT and not the selector

| degenerate                         |    IS80 |   pooled cov80 | passes EVERY per-position floor?   | floors missed                                                                      | loses to the winner?   |
|:-----------------------------------|--------:|---------------:|:-----------------------------------|:-----------------------------------------------------------------------------------|:-----------------------|
| max_width                          | 391.862 |          0.990 | YES                                | —                                                                                  | yes                    |
| const_width                        | 237.720 |          0.899 | YES                                | —                                                                                  | yes                    |
| zero_width                         | 407.373 |          0.001 | no                                 | pooled 0.0011<0.80, QB 0.0<0.800, RB 0.001<0.800, TE 0.0017<0.800, WR 0.0003<0.800 | yes                    |
| SHIPPED — knn_norm k300 · sdgain 0 | 160.888 |          0.890 | YES                                | —                                                                                  | —                      |

⭐ **`max_width` satisfies every per-position floor and still loses by a wide margin** — that is the whole argument that adding a per-position floor did not turn this into a coverage exercise. A CRITERION a degenerate wins cannot select an interval (E2.1-r); a CONSTRAINT a degenerate satisfies is fine, because the metric then eliminates it. It is also why the floor is not tightened above nominal 'for safety': every notch above nominal moves the eligible set toward `max_width` and away from an honest band.

## 3. Power — and how it differs from NF1.8

| position   |    n |   coverage (INCUMBENT) |   binomial SE |   class-clustered SE |   min_not_significantly_below |   z vs nominal | significantly below nominal?   |   P(reject | truly nominal) |
|:-----------|-----:|-----------------------:|--------------:|---------------------:|------------------------------:|---------------:|:-------------------------------|----------------------------:|
| FB         |  299 |                  0.415 |         0.023 |                0.029 |                         0.762 |        -16.660 | yes                            |                       0.512 |
| QB         | 1116 |                  0.682 |         0.012 |                0.012 |                         0.780 |         -9.860 | yes                            |                       0.488 |
| RB         | 2018 |                  0.549 |         0.009 |                0.015 |                         0.785 |        -28.230 | yes                            |                       0.500 |
| TE         | 1801 |                  0.536 |         0.009 |                0.015 |                         0.784 |        -28.030 | yes                            |                       0.491 |
| WR         | 3164 |                  0.511 |         0.007 |                0.019 |                         0.788 |        -40.580 | yes                            |                       0.504 |

⭐ **This is where NF1.9 differs most from NF1.8, and it is worth stating plainly.** NF1.8's per-position floor rested on **81 rookie-seasons** at QB, with a binomial SE of 0.044, a `P(reject | truly nominal)` of ~0.5 and **one row of slack**; its own report had to warn that 'nobody should treat QB now covers 0.815 as a stable property'. The veteran panel carries **FB** n=299, **QB** n=1116, **RB** n=2018, **TE** n=1801, **WR** n=3164 held-out seasons, so the SEs above are ~0.007–0.023 and the incumbent's shortfall (0.5448 vs 0.80) is **58 SE** below nominal — not a thin-sample question at all. Two consequences: the floor here is a genuine test rather than partly noise selection, and the CLASS-CLUSTERED SE column becomes the binding one (seasons, not players, are the independent unit — a season-wide injury or scoring-environment shift moves every player in a season together, and no amount of per-player recalibration removes that).

## 4. Results — all configs (sorted by the primary metric)

| config                                              |    IS80 |   cov80 |   cov FB |   cov QB |   cov RB |   cov TE |   cov WR |   >p90 FB |   >p90 QB |   >p90 RB |   >p90 TE |   >p90 WR |   below p10 |   above p90 |   mean width |   fallback % | eligible        |
|:----------------------------------------------------|--------:|--------:|---------:|---------:|---------:|---------:|---------:|----------:|----------:|----------:|----------:|----------:|------------:|------------:|-------------:|-------------:|:----------------|
| knn_norm k300 · sdgain 0                            | 160.888 |   0.890 |    0.860 |    0.858 |    0.886 |    0.888 |    0.907 |     0.104 |     0.062 |     0.099 |     0.093 |     0.078 |       0.025 |       0.085 |      124.930 |        0.000 | yes             |
| knn_norm k200 · sdgain 0                            | 161.092 |   0.885 |    0.853 |    0.854 |    0.883 |    0.882 |    0.903 |     0.104 |     0.063 |     0.101 |     0.097 |     0.081 |       0.027 |       0.088 |      124.180 |        0.000 | yes             |
| knn_norm k500 · sdgain 0                            | 161.130 |   0.891 |    0.863 |    0.863 |    0.887 |    0.887 |    0.910 |     0.104 |     0.060 |     0.101 |     0.099 |     0.080 |       0.021 |       0.087 |      125.960 |        0.000 | yes             |
| knn_norm k300 · sdgain 0.1                          | 161.296 |   0.891 |    0.863 |    0.862 |    0.888 |    0.889 |    0.908 |     0.100 |     0.059 |     0.099 |     0.093 |     0.078 |       0.024 |       0.084 |      126.010 |        0.000 | yes             |
| knn_norm k200 · sdgain 0.1                          | 161.470 |   0.887 |    0.860 |    0.858 |    0.883 |    0.882 |    0.904 |     0.100 |     0.061 |     0.101 |     0.097 |     0.080 |       0.026 |       0.087 |      125.250 |        0.000 | yes             |
| knn_norm k500 · sdgain 0.1                          | 161.552 |   0.893 |    0.866 |    0.866 |    0.889 |    0.888 |    0.911 |     0.100 |     0.058 |     0.099 |     0.098 |     0.080 |       0.021 |       0.086 |      127.050 |        0.000 | yes             |
| knn_norm k300 · sdgain 0.2                          | 161.858 |   0.893 |    0.863 |    0.865 |    0.889 |    0.890 |    0.909 |     0.100 |     0.057 |     0.097 |     0.092 |     0.076 |       0.024 |       0.083 |      127.260 |        0.000 | yes             |
| knn_pos k100 · sdgain 0                             | 161.988 |   0.874 |    0.913 |    0.823 |    0.871 |    0.896 |    0.879 |     0.084 |     0.097 |     0.107 |     0.078 |     0.094 |       0.032 |       0.094 |      121.300 |        0.000 | yes             |
| knn_norm k200 · sdgain 0.2                          | 162.040 |   0.888 |    0.860 |    0.863 |    0.886 |    0.883 |    0.905 |     0.100 |     0.057 |     0.098 |     0.096 |     0.080 |       0.026 |       0.085 |      126.490 |        0.000 | yes             |
| knn_norm k500 · sdgain 0.2                          | 162.125 |   0.894 |    0.866 |    0.867 |    0.890 |    0.888 |    0.911 |     0.100 |     0.057 |     0.098 |     0.097 |     0.079 |       0.021 |       0.085 |      128.310 |        0.000 | yes             |
| knn_pos k200 · sdgain 0                             | 162.165 |   0.880 |    0.896 |    0.825 |    0.879 |    0.901 |    0.886 |     0.100 |     0.104 |     0.108 |     0.081 |     0.090 |       0.025 |       0.095 |      124.240 |        0.000 | yes             |
| knn_pos k100 · sdgain 0.1                           | 162.322 |   0.876 |    0.913 |    0.827 |    0.873 |    0.897 |    0.880 |     0.084 |     0.093 |     0.106 |     0.078 |     0.092 |       0.032 |       0.092 |      122.360 |        0.000 | yes             |
| knn_pos k200 · sdgain 0.1                           | 162.596 |   0.881 |    0.896 |    0.829 |    0.881 |    0.902 |    0.886 |     0.100 |     0.100 |     0.107 |     0.081 |     0.089 |       0.025 |       0.094 |      125.320 |        0.000 | yes             |
| knn_norm k100 · sdgain 0                            | 162.752 |   0.878 |    0.829 |    0.842 |    0.871 |    0.878 |    0.899 |     0.107 |     0.069 |     0.110 |     0.099 |     0.084 |       0.030 |       0.092 |      122.470 |        0.000 | yes             |
| qreg_sqrt_perpos α0.01 · sdgain 0                   | 162.827 |   0.905 |    0.896 |    0.864 |    0.893 |    0.923 |    0.918 |     0.100 |     0.082 |     0.103 |     0.077 |     0.081 |       0.009 |       0.086 |      132.640 |        0.000 | yes             |
| knn_pos k100 · sdgain 0.2                           | 162.828 |   0.878 |    0.913 |    0.831 |    0.874 |    0.898 |    0.881 |     0.084 |     0.090 |     0.105 |     0.077 |     0.091 |       0.031 |       0.091 |      123.590 |        0.000 | yes             |
| knn_norm k100 · sdgain 0.1                          | 163.080 |   0.879 |    0.833 |    0.848 |    0.873 |    0.878 |    0.900 |     0.107 |     0.067 |     0.109 |     0.099 |     0.084 |       0.029 |       0.092 |      123.520 |        0.000 | yes             |
| knn_pos k200 · sdgain 0.2                           | 163.176 |   0.882 |    0.896 |    0.830 |    0.882 |    0.902 |    0.887 |     0.100 |     0.100 |     0.106 |     0.081 |     0.088 |       0.025 |       0.093 |      126.580 |        0.000 | yes             |
| knn_pos k300 · sdgain 0                             | 163.218 |   0.884 |    0.893 |    0.819 |    0.886 |    0.907 |    0.892 |     0.104 |     0.119 |     0.106 |     0.084 |     0.089 |       0.019 |       0.097 |      125.250 |        0.000 | yes             |
| qreg_sqrt_perpos α0.01 · sdgain 0.1                 | 163.303 |   0.906 |    0.900 |    0.866 |    0.894 |    0.924 |    0.919 |     0.097 |     0.081 |     0.102 |     0.075 |     0.080 |       0.009 |       0.085 |      133.770 |        0.000 | yes             |
| knn_norm k100 · sdgain 0.2                          | 163.644 |   0.881 |    0.836 |    0.850 |    0.875 |    0.881 |    0.901 |     0.107 |     0.066 |     0.107 |     0.096 |     0.083 |       0.029 |       0.090 |      124.730 |        0.000 | yes             |
| knn_pos k300 · sdgain 0.1                           | 163.668 |   0.886 |    0.896 |    0.824 |    0.888 |    0.907 |    0.893 |     0.100 |     0.115 |     0.105 |     0.083 |     0.087 |       0.019 |       0.095 |      126.350 |        0.000 | yes             |
| qreg_sqrt α0 · sdgain 0                             | 163.761 |   0.911 |    0.913 |    0.866 |    0.897 |    0.930 |    0.925 |     0.084 |     0.081 |     0.100 |     0.069 |     0.074 |       0.009 |       0.080 |      133.900 |        0.000 | yes             |
| qreg_sqrt_perpos α0.01 · sdgain 0.2                 | 163.983 |   0.907 |    0.900 |    0.868 |    0.895 |    0.924 |    0.920 |     0.097 |     0.078 |     0.101 |     0.075 |     0.079 |       0.009 |       0.084 |      135.090 |        0.000 | yes             |
| qreg_sqrt α0 · sdgain 0.1                           | 163.993 |   0.913 |    0.916 |    0.870 |    0.899 |    0.931 |    0.926 |     0.080 |     0.076 |     0.098 |     0.069 |     0.073 |       0.009 |       0.079 |      134.870 |        0.000 | yes             |
| knn_pos k300 · sdgain 0.2                           | 164.277 |   0.886 |    0.896 |    0.824 |    0.888 |    0.907 |    0.894 |     0.100 |     0.115 |     0.104 |     0.083 |     0.087 |       0.019 |       0.094 |      127.620 |        0.000 | yes             |
| qreg_sqrt α0 · sdgain 0.2                           | 164.368 |   0.914 |    0.920 |    0.873 |    0.899 |    0.931 |    0.928 |     0.077 |     0.073 |     0.097 |     0.068 |     0.071 |       0.009 |       0.077 |      136.000 |        0.000 | yes             |
| qreg_sqrt α0.01 · sdgain 0                          | 165.319 |   0.908 |    0.886 |    0.850 |    0.895 |    0.938 |    0.922 |     0.110 |     0.097 |     0.101 |     0.061 |     0.077 |       0.009 |       0.083 |      134.840 |        0.000 | yes             |
| qreg_sqrt+cqr[pos,add] · sdgain 0                   | 165.319 |   0.908 |    0.886 |    0.850 |    0.895 |    0.938 |    0.922 |     0.110 |     0.097 |     0.101 |     0.061 |     0.077 |       0.009 |       0.083 |      134.840 |        0.000 | yes             |
| qreg_sqrt+cqr[pos,width] · sdgain 0                 | 165.319 |   0.908 |    0.886 |    0.850 |    0.895 |    0.938 |    0.922 |     0.110 |     0.097 |     0.101 |     0.061 |     0.077 |       0.009 |       0.083 |      134.840 |        0.000 | yes             |
| qreg_sqrt+cqr[pool,add] · sdgain 0                  | 165.319 |   0.908 |    0.886 |    0.850 |    0.895 |    0.938 |    0.922 |     0.110 |     0.097 |     0.101 |     0.061 |     0.077 |       0.009 |       0.083 |      134.840 |        0.000 | yes             |
| qreg_sqrt+cqr[pool,width] · sdgain 0                | 165.319 |   0.908 |    0.886 |    0.850 |    0.895 |    0.938 |    0.922 |     0.110 |     0.097 |     0.101 |     0.061 |     0.077 |       0.009 |       0.083 |      134.840 |        0.000 | yes             |
| qreg_sqrt α0.01 · sdgain 0.1                        | 165.922 |   0.909 |    0.886 |    0.850 |    0.896 |    0.940 |    0.923 |     0.110 |     0.096 |     0.100 |     0.060 |     0.076 |       0.009 |       0.082 |      136.070 |        0.000 | yes             |
| qreg_sqrt+cqr[pos,add] · sdgain 0.1                 | 165.922 |   0.909 |    0.886 |    0.850 |    0.896 |    0.940 |    0.923 |     0.110 |     0.096 |     0.100 |     0.060 |     0.076 |       0.009 |       0.082 |      136.070 |        0.000 | yes             |
| qreg_sqrt+cqr[pos,width] · sdgain 0.1               | 165.922 |   0.909 |    0.886 |    0.850 |    0.896 |    0.940 |    0.923 |     0.110 |     0.096 |     0.100 |     0.060 |     0.076 |       0.009 |       0.082 |      136.070 |        0.000 | yes             |
| qreg_sqrt+cqr[pool,add] · sdgain 0.1                | 165.922 |   0.909 |    0.886 |    0.850 |    0.896 |    0.940 |    0.923 |     0.110 |     0.096 |     0.100 |     0.060 |     0.076 |       0.009 |       0.082 |      136.070 |        0.000 | yes             |
| qreg_sqrt+cqr[pool,width] · sdgain 0.1              | 165.922 |   0.909 |    0.886 |    0.850 |    0.896 |    0.940 |    0.923 |     0.110 |     0.096 |     0.100 |     0.060 |     0.076 |       0.009 |       0.082 |      136.070 |        0.000 | yes             |
| qreg_perpos α0.01 · sdgain 0                        | 166.422 |   0.907 |    0.900 |    0.857 |    0.896 |    0.931 |    0.918 |     0.097 |     0.090 |     0.100 |     0.068 |     0.081 |       0.009 |       0.084 |      136.040 |        0.000 | yes             |
| qreg_sqrt α0.01 · sdgain 0.2                        | 166.726 |   0.910 |    0.886 |    0.852 |    0.898 |    0.940 |    0.923 |     0.110 |     0.094 |     0.099 |     0.060 |     0.075 |       0.009 |       0.081 |      137.510 |        0.000 | yes             |
| qreg_sqrt+cqr[pos,add] · sdgain 0.2                 | 166.726 |   0.910 |    0.886 |    0.852 |    0.898 |    0.940 |    0.923 |     0.110 |     0.094 |     0.099 |     0.060 |     0.075 |       0.009 |       0.081 |      137.510 |        0.000 | yes             |
| qreg_sqrt+cqr[pos,width] · sdgain 0.2               | 166.726 |   0.910 |    0.886 |    0.852 |    0.898 |    0.940 |    0.923 |     0.110 |     0.094 |     0.099 |     0.060 |     0.075 |       0.009 |       0.081 |      137.510 |        0.000 | yes             |
| qreg_sqrt+cqr[pool,add] · sdgain 0.2                | 166.726 |   0.910 |    0.886 |    0.852 |    0.898 |    0.940 |    0.923 |     0.110 |     0.094 |     0.099 |     0.060 |     0.075 |       0.009 |       0.081 |      137.510 |        0.000 | yes             |
| qreg_sqrt+cqr[pool,width] · sdgain 0.2              | 166.726 |   0.910 |    0.886 |    0.852 |    0.898 |    0.940 |    0.923 |     0.110 |     0.094 |     0.099 |     0.060 |     0.075 |       0.009 |       0.081 |      137.510 |        0.000 | yes             |
| qreg_perpos α0.01 · sdgain 0.1                      | 167.159 |   0.900 |    0.900 |    0.851 |    0.890 |    0.925 |    0.909 |     0.097 |     0.089 |     0.099 |     0.067 |     0.080 |       0.017 |       0.083 |      137.250 |        0.000 | yes             |
| knn_pos k500 · sdgain 0                             | 167.913 |   0.887 |    0.913 |    0.812 |    0.887 |    0.910 |    0.898 |     0.084 |     0.133 |     0.107 |     0.089 |     0.089 |       0.014 |       0.099 |      127.850 |        0.000 | yes             |
| qreg_perpos α0.01 · sdgain 0.2                      | 168.077 |   0.900 |    0.900 |    0.851 |    0.891 |    0.925 |    0.909 |     0.097 |     0.088 |     0.097 |     0.067 |     0.079 |       0.017 |       0.083 |      138.660 |        0.000 | yes             |
| knn_pos k500 · sdgain 0.1                           | 168.529 |   0.888 |    0.913 |    0.813 |    0.888 |    0.911 |    0.898 |     0.084 |     0.132 |     0.106 |     0.088 |     0.088 |       0.014 |       0.098 |      129.090 |        0.000 | yes             |
| knn_pos k500 · sdgain 0.2                           | 169.332 |   0.889 |    0.913 |    0.814 |    0.889 |    0.913 |    0.899 |     0.084 |     0.131 |     0.105 |     0.086 |     0.087 |       0.014 |       0.097 |      130.520 |        0.000 | yes             |
| qreg α0 · sdgain 0                                  | 170.999 |   0.920 |    0.960 |    0.850 |    0.901 |    0.956 |    0.931 |     0.037 |     0.097 |     0.095 |     0.043 |     0.068 |       0.009 |       0.072 |      143.550 |        0.000 | yes             |
| normal_scaled (null: σ×m, fitted on the SCORE)      | 171.285 |   0.878 |    0.799 |    0.806 |    0.874 |    0.904 |    0.899 |     0.084 |     0.068 |     0.090 |     0.069 |     0.068 |       0.048 |       0.074 |      134.540 |        0.000 | yes             |
| qreg α0 · sdgain 0.1                                | 171.593 |   0.910 |    0.920 |    0.852 |    0.895 |    0.937 |    0.923 |     0.037 |     0.094 |     0.094 |     0.043 |     0.067 |       0.019 |       0.071 |      144.650 |        0.000 | yes             |
| qreg α0 · sdgain 0.2                                | 172.397 |   0.910 |    0.923 |    0.854 |    0.896 |    0.935 |    0.923 |     0.033 |     0.092 |     0.093 |     0.042 |     0.065 |       0.021 |       0.069 |      145.930 |        0.000 | yes             |
| normal_cov (null: σ×m, fitted to a COVERAGE TARGET) | 172.500 |   0.818 |    0.776 |    0.802 |    0.819 |    0.808 |    0.833 |     0.084 |     0.072 |     0.119 |     0.117 |     0.104 |       0.077 |       0.105 |      115.640 |        0.000 | yes             |
| ratio_q · sdgain 0                                  | 173.065 |   0.912 |    0.903 |    0.884 |    0.899 |    0.934 |    0.918 |     0.094 |     0.062 |     0.098 |     0.066 |     0.081 |       0.009 |       0.079 |      143.120 |        0.000 | yes             |
| ratio_q · sdgain 0.1                                | 173.357 |   0.913 |    0.903 |    0.887 |    0.900 |    0.934 |    0.919 |     0.094 |     0.059 |     0.096 |     0.065 |     0.080 |       0.009 |       0.078 |      144.130 |        0.000 | yes             |
| ratio_q · sdgain 0.2                                | 173.847 |   0.915 |    0.906 |    0.889 |    0.901 |    0.936 |    0.921 |     0.090 |     0.057 |     0.095 |     0.064 |     0.078 |       0.009 |       0.077 |      145.310 |        0.000 | yes             |
| qreg α0.01 · sdgain 0                               | 177.300 |   0.914 |    0.883 |    0.808 |    0.908 |    0.959 |    0.932 |     0.114 |     0.138 |     0.088 |     0.041 |     0.067 |       0.009 |       0.077 |      146.050 |        0.000 | yes             |
| qreg+cqr[pos,add] · sdgain 0                        | 177.300 |   0.914 |    0.883 |    0.808 |    0.908 |    0.959 |    0.932 |     0.114 |     0.138 |     0.088 |     0.041 |     0.067 |       0.009 |       0.077 |      146.050 |        0.000 | yes             |
| qreg+cqr[pos,width] · sdgain 0                      | 177.300 |   0.914 |    0.883 |    0.808 |    0.908 |    0.959 |    0.932 |     0.114 |     0.138 |     0.088 |     0.041 |     0.067 |       0.009 |       0.077 |      146.050 |        0.000 | yes             |
| qreg+cqr[pool,add] · sdgain 0                       | 177.300 |   0.914 |    0.883 |    0.808 |    0.908 |    0.959 |    0.932 |     0.114 |     0.138 |     0.088 |     0.041 |     0.067 |       0.009 |       0.077 |      146.050 |        0.000 | yes             |
| qreg+cqr[pool,width] · sdgain 0                     | 177.300 |   0.914 |    0.883 |    0.808 |    0.908 |    0.959 |    0.932 |     0.114 |     0.138 |     0.088 |     0.041 |     0.067 |       0.009 |       0.077 |      146.050 |        0.000 | yes             |
| qreg α0.01 · sdgain 0.1                             | 178.318 |   0.911 |    0.819 |    0.811 |    0.909 |    0.953 |    0.931 |     0.114 |     0.135 |     0.087 |     0.039 |     0.066 |       0.013 |       0.076 |      147.600 |        0.000 | yes             |
| qreg+cqr[pos,add] · sdgain 0.1                      | 178.318 |   0.911 |    0.819 |    0.811 |    0.909 |    0.953 |    0.931 |     0.114 |     0.135 |     0.087 |     0.039 |     0.066 |       0.013 |       0.076 |      147.600 |        0.000 | yes             |
| qreg+cqr[pos,width] · sdgain 0.1                    | 178.318 |   0.911 |    0.819 |    0.811 |    0.909 |    0.953 |    0.931 |     0.114 |     0.135 |     0.087 |     0.039 |     0.066 |       0.013 |       0.076 |      147.600 |        0.000 | yes             |
| qreg+cqr[pool,add] · sdgain 0.1                     | 178.318 |   0.911 |    0.819 |    0.811 |    0.909 |    0.953 |    0.931 |     0.114 |     0.135 |     0.087 |     0.039 |     0.066 |       0.013 |       0.076 |      147.600 |        0.000 | yes             |
| qreg+cqr[pool,width] · sdgain 0.1                   | 178.318 |   0.911 |    0.819 |    0.811 |    0.909 |    0.953 |    0.931 |     0.114 |     0.135 |     0.087 |     0.039 |     0.066 |       0.013 |       0.076 |      147.600 |        0.000 | yes             |
| qreg α0.01 · sdgain 0.2                             | 179.610 |   0.911 |    0.819 |    0.812 |    0.910 |    0.953 |    0.932 |     0.114 |     0.134 |     0.085 |     0.039 |     0.065 |       0.013 |       0.075 |      149.400 |        0.000 | yes             |
| qreg+cqr[pos,add] · sdgain 0.2                      | 179.610 |   0.911 |    0.819 |    0.812 |    0.910 |    0.953 |    0.932 |     0.114 |     0.134 |     0.085 |     0.039 |     0.065 |       0.013 |       0.075 |      149.400 |        0.000 | yes             |
| qreg+cqr[pos,width] · sdgain 0.2                    | 179.610 |   0.911 |    0.819 |    0.812 |    0.910 |    0.953 |    0.932 |     0.114 |     0.134 |     0.085 |     0.039 |     0.065 |       0.013 |       0.075 |      149.400 |        0.000 | yes             |
| qreg+cqr[pool,add] · sdgain 0.2                     | 179.610 |   0.911 |    0.819 |    0.812 |    0.910 |    0.953 |    0.932 |     0.114 |     0.134 |     0.085 |     0.039 |     0.065 |       0.013 |       0.075 |      149.400 |        0.000 | yes             |
| qreg+cqr[pool,width] · sdgain 0.2                   | 179.610 |   0.911 |    0.819 |    0.812 |    0.910 |    0.953 |    0.932 |     0.114 |     0.134 |     0.085 |     0.039 |     0.065 |       0.013 |       0.075 |      149.400 |        0.000 | yes             |
| ratio_q_floor · sdgain 0                            | 187.088 |   0.957 |    0.973 |    0.907 |    0.956 |    0.970 |    0.967 |     0.023 |     0.039 |     0.040 |     0.029 |     0.032 |       0.009 |       0.034 |      174.220 |        0.000 | yes             |
| ratio_q_floor · sdgain 0.1                          | 188.042 |   0.958 |    0.973 |    0.909 |    0.957 |    0.971 |    0.967 |     0.023 |     0.038 |     0.039 |     0.029 |     0.032 |       0.009 |       0.033 |      175.740 |        0.000 | yes             |
| ratio_q_floor · sdgain 0.2                          | 189.253 |   0.959 |    0.973 |    0.910 |    0.958 |    0.972 |    0.968 |     0.023 |     0.036 |     0.038 |     0.028 |     0.031 |       0.009 |       0.032 |      177.500 |        0.000 | yes             |
| normal (INCUMBENT — the served band)                | 205.961 |   0.545 |    0.415 |    0.682 |    0.549 |    0.536 |    0.511 |     0.167 |     0.134 |     0.201 |     0.179 |     0.192 |       0.272 |       0.183 |       73.080 |      100.000 | n/a (incumbent) |

`eligible` applies the floors of §1. `fallback %` is the share of held-out veterans whose per-player fit was REFUSED and who therefore carried the SERVED NORMAL band — for veterans that is the more severe defect, because the fallback IS the broken incumbent. `below p10` / `above p90` split the miss by tail.

### ⭐ Was a new SHAPE needed, or just a bigger sigma?

| arm                                            |    IS80 |   cov80 |   below p10 |   above p90 |   mean width |   cov FB |   cov QB |   cov RB |   cov TE |   cov WR |
|:-----------------------------------------------|--------:|--------:|------------:|------------:|-------------:|---------:|---------:|---------:|---------:|---------:|
| INCUMBENT — normal, σ as served                | 205.961 |   0.545 |       0.272 |       0.183 |       73.080 |    0.415 |    0.682 |    0.549 |    0.536 |    0.511 |
| NULL — normal, σ×m fitted on the SCORE         | 171.285 |   0.878 |       0.048 |       0.074 |      134.540 |    0.799 |    0.806 |    0.874 |    0.904 |    0.899 |
| NULL — normal, σ×m fitted to a COVERAGE TARGET | 172.500 |   0.818 |       0.077 |       0.105 |      115.640 |    0.776 |    0.802 |    0.819 |    0.808 |    0.833 |
| SHIPPED — knn_norm k300 · sdgain 0             | 160.888 |   0.890 |       0.025 |       0.085 |      124.930 |    0.860 |    0.858 |    0.886 |    0.888 |    0.907 |

⭐ **A bigger sigma is not the fix, and the two nulls are how we know.** `normal_scaled` — the same symmetric band with a per-position multiplier fitted on the SAME proper score the selection uses — reaches coverage 0.8779 at IS80 171.285 and a mean width of 134.54 PPR (1.84× the incumbent's). `normal_cov` — the NAIVE fix, the identical machinery fitted to HIT nominal coverage in-fold — gets coverage 0.8178 but pays IS80 172.5, i.e. +7.2% against the shipped arm at a mean width of 115.64 PPR. **That gap is the E2.1-r rule with a number attached: fitting a band to a coverage TARGET buys the coverage and pays for it in usefulness.** The shipped arm reaches its floor with a band 1.08× the width of the coverage-fitted null because it puts the width where the risk actually is — asymmetrically, and per player.

## 5. Deflation — CSCV / PBO over held-out-season splits

| search                                               |   configs |   PBO |   median logit |   os_gap_pct (Bailey degradation) |   os_gap p90 % |   contender spread % (top quartile) |   splits |
|:-----------------------------------------------------|----------:|------:|---------------:|----------------------------------:|---------------:|------------------------------------:|---------:|
| WHOLE field (every config scored)                    |        75 | 0.000 |          3.192 |                             0.213 |          0.441 |                               1.430 |     1716 |
| ELIGIBLE set — the search the selection actually ran |        74 | 0.000 |          3.178 |                             0.213 |          0.441 |                               1.430 |     1716 |

Whole-field spread (best→worst IS80) = 160.888 → 205.961 (28.0%).

Read per NF1.8's lesson rather than PBO alone: **`os_gap_pct`** is Bailey's PERFORMANCE DEGRADATION (how much worse the in-sample winner actually SCORES out-of-sample than the out-of-sample best — the decision-relevant question, not the rank question); **`contender_spread_pct`** is the spread over the top QUARTILE only, i.e. among arms that could plausibly be selected; and the **FLIP DISTRIBUTION** below shows WHICH arms win the in-sample halves. A PBO near 0.5 whose flip mass sits on two arms a fraction of a percent apart is a TIE; the same PBO spread thinly over a dozen unrelated arms is a search that learnt nothing. PBO compresses that distinction away, and a whole-field spread computed over a field that CONTAINS its own nulls measures the nulls, not the contest.

### Which arms actually win the in-sample halves (ELIGIBLE set)

| config                   |   IS-half wins |   share |   full-sample IS80 |   Δ vs best % |
|:-------------------------|---------------:|--------:|-------------------:|--------------:|
| knn_norm k300 · sdgain 0 |            928 |   0.541 |            161.645 |         0.000 |
| knn_norm k200 · sdgain 0 |            469 |   0.273 |            161.820 |         0.110 |
| knn_norm k500 · sdgain 0 |            286 |   0.167 |            161.880 |         0.150 |
| knn_pos k100 · sdgain 0  |             29 |   0.017 |            162.800 |         0.710 |
| knn_pos k200 · sdgain 0  |              4 |   0.002 |            162.953 |         0.810 |

**Verdict: PBO(eligible) = 0.0 over 1716 balanced season splits, median out-of-sample degradation 0.213% (p90 0.441%), contender spread 1.43%.** The flip mass concentrates on `knn_norm k300 · sdgain 0` (54% of halves) and `knn_norm k200 · sdgain 0` (27%), 0.11% apart on the full sample — a TIE between them, which per CLAUDE.md is the NULL: *which* of them wins is noise, and what the story establishes is the FLOOR, not the leaderboard's top row.

## 6. Selection

**SHIPPED: `knn_norm k300 · sdgain 0`** — IS80 160.888 · pooled coverage 0.8897 · mean width 124.93 · fallback 0.0%.

**The refit EARNS its place.** `knn_norm k300 · sdgain 0` cuts the held-out interval score from 205.961 (the served normal approximation) to 160.888 (21.9% better) while lifting pooled coverage 0.5448 → 0.8897 (floor 0.80) and clearing the nominal floor at EVERY constrained position: FB 0.4147 → 0.8595, QB 0.6819 → 0.8575, RB 0.5486 → 0.8865, TE 0.5358 → 0.8884, WR 0.5114 → 0.9068. The tail split goes 0.2724/0.1828 → 0.025/0.0853 (below p10 / above p90, nominal 0.10 each). The POINT projection is untouched.

### ⭐ What the per-position conformal layer bought (the FOIL comparison)

| arm                                |    IS80 |   cov80 |   cov FB |   cov QB |   cov RB |   cov TE |   cov WR |   mean width |
|:-----------------------------------|--------:|--------:|---------:|---------:|---------:|---------:|---------:|-------------:|
| SHIPPED — knn_norm k300 · sdgain 0 | 160.888 |   0.890 |    0.860 |    0.858 |    0.886 |    0.888 |    0.907 |      124.930 |

The POOLED conformal calibration is the pre-registered FOIL: identical machinery, one shared quantile instead of one per position. Reporting both is what separates 'conformal helped' from 'PER-POSITION conditioning helped' — NF1.8's pooled foil was a numerical NO-OP, which is what made its Mondrian gain attributable rather than asserted.

⚠️ **And the honest limit of any in-fold calibration:** it cannot see a NEXT-SEASON gap. Small fitted adjustments are evidence that the residual miscalibration is season-to-season variation rather than a fittable per-player error — which is exactly why §8's standing re-validation exists instead of a promise that the floor holds forever.

### The tie among ELIGIBLE arms — and why it is not re-picked on coverage headroom

| config                     |    IS80 |   Δ IS80 vs shipped % |   pooled cov80 |   min per-position headroom |   fallback % |   mean width |
|:---------------------------|--------:|----------------------:|---------------:|----------------------------:|-------------:|-------------:|
| knn_norm k300 · sdgain 0   | 160.888 |                 0.000 |          0.890 |                       0.057 |        0.000 |      124.930 |
| knn_norm k200 · sdgain 0   | 161.092 |                 0.130 |          0.885 |                       0.054 |        0.000 |      124.180 |
| knn_norm k500 · sdgain 0   | 161.130 |                 0.150 |          0.891 |                       0.063 |        0.000 |      125.960 |
| knn_norm k300 · sdgain 0.1 | 161.296 |                 0.250 |          0.891 |                       0.062 |        0.000 |      126.010 |
| knn_norm k200 · sdgain 0.1 | 161.470 |                 0.360 |          0.887 |                       0.057 |        0.000 |      125.250 |
| knn_norm k500 · sdgain 0.1 | 161.552 |                 0.410 |          0.893 |                       0.066 |        0.000 |      127.050 |
| knn_norm k300 · sdgain 0.2 | 161.858 |                 0.600 |          0.893 |                       0.065 |        0.000 |      127.260 |
| knn_pos k100 · sdgain 0    | 161.988 |                 0.680 |          0.874 |                       0.023 |        0.000 |      121.300 |
| knn_norm k200 · sdgain 0.2 | 162.040 |                 0.720 |          0.888 |                       0.063 |        0.000 |      126.490 |
| knn_norm k500 · sdgain 0.2 | 162.125 |                 0.770 |          0.894 |                       0.067 |        0.000 |      128.310 |
| knn_pos k200 · sdgain 0    | 162.165 |                 0.790 |          0.880 |                       0.025 |        0.000 |      124.240 |
| knn_pos k100 · sdgain 0.1  | 162.322 |                 0.890 |          0.876 |                       0.027 |        0.000 |      122.360 |

The top **12** ELIGIBLE configs sit within 1% of each other on the primary metric. When the leaders genuinely tie, *which* of them wins is noise.

⚠️ **The tie has a coverage asymmetry, and it is declined:** `knn_norm k500 · sdgain 0.2` carries more headroom above the per-position floors (+0.067) than the shipped arm (+0.057). **We do not re-pick on it.** 'Prefer more headroom above the floor' is MONOTONE IN WIDENING — the `max_width` degenerate wins it outright (§2) while being useless. Re-picking a tie on a criterion a degenerate wins is the E2.1-r inversion facing the other way. The floor is a CONSTRAINT; the interval score SELECTS; a genuine tie is broken on the program's own DEFECT metric (the FALLBACK rate — an arm that reverts rows to the normal band is partly the very band this story replaces), never on the constraint's own headroom.

### Per-position coverage and WIDTH — incumbent vs shipped

| arm                                |   cov FB |   cov QB |   cov RB |   cov TE |   cov WR | slack FB (rows)   |   slack QB (rows) |   slack RB (rows) |   slack TE (rows) |   slack WR (rows) |   width FB |   width QB |   width RB |   width TE |   width WR |
|:-----------------------------------|---------:|---------:|---------:|---------:|---------:|:------------------|------------------:|------------------:|------------------:|------------------:|-----------:|-----------:|-----------:|-----------:|-----------:|
| INCUMBENT (normal approximation)   |    0.415 |    0.682 |    0.549 |    0.536 |    0.511 |                   |              -132 |              -508 |              -476 |              -914 |     19.500 |    123.500 |     76.300 |     47.700 |     72.800 |
| SHIPPED (knn_norm k300 · sdgain 0) |    0.860 |    0.858 |    0.886 |    0.888 |    0.907 |                   |                64 |               174 |               159 |               337 |     33.100 |    174.600 |    132.600 |     83.800 |    134.700 |

⭐ **The floor margins are stated in ROWS, not coverage decimals** (the NF1.8 lesson: a coverage decimal hides how few outcomes a per-position floor rests on). Here they are **QB** 64, **RB** 174, **TE** 159, **WR** 337 — the tightest is QB with 64 covered veteran-seasons of slack, against NF1.8's rookie RB margin of **0 rows**. The margins are comfortable because the population is 9× larger, not because the band is more certain.

### The POINT projection is unchanged

⭐ **NF1.9 changes the interval and NOTHING ELSE.** Structurally: every arm in this bake-off reads the SAME `point` column out of the panel — the served `proj_fp_ppr` — and the band emitters can only write `fp_ppr_p10`/`fp_ppr_p90`, so a point drift is not merely absent, it is unreachable. Three checks, at three levels:

1. **In-repo, mechanical:** `test_the_band_configuration_cannot_reach_the_point_projection` reads `project_veterans` and asserts `band_model` is referenced exactly once in the executable code BEFORE the interval block (the signature) and that the interval block assigns no `proj_*` column — a runtime assertion could only cover the configs it happened to run.
2. **Board level, measured:** the served 2026 board rebuilt with the band ON vs OFF gives **max |Δ proj_fp_ppr| = 8.5e-13** and EXACTLY ZERO drift on every other numeric column (784 rows, identical row set).
3. ⚠️ **And that is asserted at `< 1e-9`, NOT as byte-equality** — the NF1.8 lesson: `np.polyfit` (LAPACK lstsq) returns ULP-different coefficients when the same rows arrive in a different ORDER, and a DuckDB read without a total `ORDER BY` is not order-stable across processes. 8.5e-13 PPR on a ~300-PPR projection is ~2 ULP of float64 — process-level float noise from a warmed cache, not a model change, and reporting it as one would be the false alarm NF1.8's operator re-export already paid for once.

## 7. Per-season detail (shipped config)

|   target_season |   IS80 (shipped) |   IS80 (incumbent) |
|----------------:|-----------------:|-------------------:|
|        2013.000 |          175.804 |            226.169 |
|        2014.000 |          175.267 |            220.611 |
|        2015.000 |          186.972 |            231.189 |
|        2016.000 |          172.006 |            227.845 |
|        2017.000 |          160.797 |            201.171 |
|        2018.000 |          172.810 |            233.733 |
|        2019.000 |          166.659 |            209.303 |
|        2020.000 |          160.758 |            210.706 |
|        2021.000 |          164.573 |            204.711 |
|        2022.000 |          143.954 |            190.078 |
|        2023.000 |          150.831 |            188.692 |
|        2024.000 |          142.882 |            189.230 |
|        2025.000 |          128.069 |            156.612 |

## 8. ⭐ The STANDING ANNUAL RE-VALIDATION

⚠️ **A per-position coverage floor is INVISIBLE at serving time.** Coverage needs realized outcomes, so nothing in the daily/seasonal path can notice the floor breaking — it would degrade silently for years, which is precisely how the veteran band went unmeasured through five stories. So NF1.9 ships a STANDING ANNUAL RE-VALIDATION rather than a one-off number:

```
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_interval_revalidation \
  --rebuild-panel
```

Run it once a season, after the completed season's outcomes land in the NFL marts. It re-scores **both** populations' shipped bands on the newly-available season, checks every per-position floor, and **exits non-zero on a breach — a RE-SELECTION TRIGGER, not a log line**. ⚠️ **RB is the position to watch on the rookie side (NF1.8 left it with ZERO rows of slack); on the veteran side the tightest margin is reported above.** A breach means re-running the relevant bake-off, not adjusting the floor.

## 9. Honest limitations

- **The POINT projection is untouched, so a mis-ranked veteran stays mis-ranked.** This story prices uncertainty; it does not improve the level or the ordering, and must not be read as having done so.
- **A floor is not an out-of-sample guarantee.** It is met on held-out target seasons 2013–2025; 2026 onward is extrapolation, which is what §8's standing re-validation exists for.
- **The CLASS-CLUSTERED SE exceeds the binomial SE at most positions** (§3): season-to-season variation — a league-wide scoring or injury environment — is the dominant residual uncertainty, and no per-player recalibration can remove it.
- **The band conditions only on base-season quantities** (the served point, the served season sd, expected games, base-season games, snap share, the returner flag, position). It cannot see camp, a holdout, a training-camp injury or a scheme change, all of which are real veteran uncertainty.
- **The panel's zero-game rows are scored as a realized 0 PPR, which is right for a fantasy interval and wrong for a 'how good is this player' read.** A veteran who is cut in August is genuinely a 0 for a drafter; he is not a 0 as a football player. Every number here is the drafter's question.
- **`normal_cov` is in the field as a foil, not a candidate to fear.** Its purpose is to put a number on the E2.1-r inversion; a future session must not read its coverage column as a recommendation.
- **No edge claim.** An honest interval is a projection-quality property, not a market edge.

