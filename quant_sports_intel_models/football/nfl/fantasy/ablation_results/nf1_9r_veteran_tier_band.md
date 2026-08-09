# NF1.9-R — the VETERAN 80% interval re-selected on the DRAFTABLE-TIER population (§0.5 bake-off)

**Generated:** 2026-08-08T21:17:37.873909+00:00 · **held-out target seasons:** 2013–2025 (13) · **configs scored:** 21 · **held-out TIER veteran-seasons:** 2028 (universe 8398) · **tier:** top 156/season by the INCUMBENT's own point (derived, never typed) · **wall time:** 57.4s

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`. What is selected is the WIDTH AND SHAPE of the veteran interval ON THE DRAFTABLE TIER; the point projection is untouched, non-tier rows keep the NF1.9 band byte-identical (overlay arms), and ⛔ NOTHING SERVES from this story — `_VET_TIER_RECAL = False`; the flip is a post-merge operator step with its own soak + `run_interval_revalidation` re-run.

## 0. The defect, and the reproduction of the record it rests on

The motivating record said 'the SERVED veteran band covers ~0.50 on the tier'. Measured here: the ~0.50 belongs to the **pre-NF1.9 NORMAL band** — the band NF1.9 already replaced, which the panel carries as `served_p10`/`served_p90` and NF-RECAL1's C3 read as its incumbent. The band actually on the wire (`knn_norm k300`) reads materially better on the tier (rows below). The zero-atom mechanism is still real — 31% of universe outcomes sit at exactly 0 vs ~7.5% of the tier, so the tier is where a band has to genuinely work — but the MAGNITUDE of the served defect is the table's, not the record's ~0.50.

| population                                                            |    n |   nominal |   coverage |   below p10 |   above p90 |   p10 at 0 |   mean width |    IS80 |
|:----------------------------------------------------------------------|-----:|----------:|-----------:|------------:|------------:|-----------:|-------------:|--------:|
| TIER — the PRE-NF1.9 normal band (the motivating figure's true owner) | 2028 |     0.800 |      0.481 |       0.230 |       0.289 |      0.002 |      120.090 | nan     |
| TIER — the NF1.9 served band (INCUMBENT)                              | 2028 |     0.800 |      0.833 |       0.064 |       0.103 |      0.341 |      239.660 | 298.075 |
| UNIVERSE — the same band (NF1.9's own validated read)                 | 8398 |     0.800 |      0.890 |     nan     |     nan     |    nan     |      124.930 | 160.888 |
| … tier at FB                                                          |    4 |     0.800 |      0.500 |     nan     |     nan     |    nan     |       78.800 | 155.950 |
| … tier at QB                                                          |  465 |     0.800 |      0.856 |     nan     |     nan     |    nan     |      283.000 | 342.950 |
| … tier at RB                                                          |  489 |     0.800 |      0.824 |     nan     |     nan     |    nan     |      237.200 | 309.020 |
| … tier at TE                                                          |  249 |     0.800 |      0.739 |     nan     |     nan     |    nan     |      159.200 | 239.900 |
| … tier at WR                                                          |  821 |     0.800 |      0.855 |     nan     |     nan     |    nan     |      241.700 | 284.480 |

⭐⭐ **THE PREMISE CHECK OVERTURNS THE MOTIVATING ATTRIBUTION.** The recorded ~0.50 tier coverage reproduces TO THE DIGIT (0.5046 vs 0.5046) — against the **pre-NF1.9 NORMAL band**, which is what the panel's `served_p10`/`served_p90` columns carry (documented in `VET_PANEL_COLS` as 'the LITERAL emitted pre-NF1.9 band') and what NF-RECAL1's C3 actually read as its 'incumbent band'. The band ON THE WIRE since NF1.9 shipped is `knn_norm k300` (`calibrated_per_player`), and ITS 2019–2025 tier coverage is **0.8452**. The incumbent arm also reproduces NF1.9's recorded universe IS80 (160.888 vs 160.888, Δ 0.00%), so the incumbent here is the served band, not a straw man. This is NF-RECAL1's own §0 discipline (re-measure the motivating defect before fitting anything) landing one story later — on the story NF-RECAL1 itself commissioned.

## 0b. The population — the tier, fixed by the incumbent's own projection

The tier is the top **156/season** veterans by the **INCUMBENT's own point** (`TIER_ANCHOR = incumbent_projection`, inherited from NF-RECAL1 §0; the size is DERIVED from the shipped 12-team standard preset's skill roster spots). ⛔ Anchoring on the realized outcome is forbidden — NF-RECAL1 measured it manufacturing −64.80 mean bias from −12.85 on these very rows. Folds are NF1.9's own 2013–2025 window: NF-RECAL1's 2019 restriction came from its C2 placement constraint's merged boards, and a band cannot move a rank, so that limit does not apply here (NF-RECAL1 §5 named 13 folds as the metric-recomputable wide window).

| reading                                     |    value |
|:--------------------------------------------|---------:|
| held-out TIER veteran-seasons (scored here) | 2028.000 |
| held-out UNIVERSE veteran-seasons (sibling) | 8398.000 |
| tier share realizing EXACTLY 0 PPR          |    0.071 |
| universe share realizing EXACTLY 0 PPR      |    0.318 |

## 1. The pre-registered floors

Row-pooled per NF1.8 (never a mean of per-class means). TIER: pooled ≥ 0.8 and per-position ≥ 0.8 at positions with ≥ 400 tier rows. **FB, TE** fall below that count and are REPORTED AND CARRIED, not gated — deriving a fallback floor for them here, beside a known breach, is exactly what NF-D22 exists to do separately and cleanly. UNIVERSE guard: the winner as served must still meet NF1.9's own standing floors.

| scope                                    | position   |   floor |    n |
|:-----------------------------------------|:-----------|--------:|-----:|
| TIER                                     | QB         |   0.800 |  465 |
| TIER                                     | RB         |   0.800 |  489 |
| TIER                                     | WR         |   0.800 |  821 |
| TIER (carried, NOT gated — NF-D22's job) | FB         | nan     |    4 |
| TIER (carried, NOT gated — NF-D22's job) | TE         | nan     |  249 |
| UNIVERSE guard                           | QB         |   0.800 | 1116 |
| UNIVERSE guard                           | RB         |   0.800 | 2018 |
| UNIVERSE guard                           | TE         |   0.800 | 1801 |
| UNIVERSE guard                           | WR         |   0.800 | 3164 |

## 2. The anchor set

| anchor              |   TIER IS80 |   tier cov |   mean width |
|:--------------------|------------:|-----------:|-------------:|
| oracle_knn          |     303.517 |      0.827 |      241.360 |
| oracle_own_family   |     346.929 |      0.722 |      204.680 |
| matched_n_candidate |     350.127 |      0.724 |      205.380 |
| zero_width          |     716.260 |      0.001 |        0.100 |
| max_width           |     404.712 |      0.991 |      403.850 |
| const_width_tier    |     325.218 |      0.813 |      260.950 |
| permuted_own        |     412.512 |      0.654 |      202.170 |
| permuted_alt        |     405.619 |      0.669 |      204.710 |
| oracle_point        |       0.084 |      0.995 |        0.040 |

- ✅ **permutation oracle respected** — the winner beats its OWN configuration fitted on SHUFFLED outcomes (412.512 vs 297.579) — the metric rewards information
- ✅ **peeking oracle respected AT MATCHED n** — the peeking own-configuration oracle (tier IS80 346.929) beats the winner's own arm trained on a single prior season (350.127) — at equal family AND equal resolution, knowing the answer helps (NF1.7 lesson 2 / NF1.9 (f))
- ⚠️ **same-family peeking oracle (UNMATCHED n — orientation only)** — the winner (297.579) BEATS the peeking oracle (346.929) — expected at unmatched n and NOT an inversion (the oracle fits ~156 held-out rows; the winner trains on every prior season); the matched-n check above is the valid form
- ✅ **zero-width degenerate loses** — sharpness was not bought by under-covering
- ✅ **max-width degenerate loses** — the selection is not a coverage exercise in disguise
- ✅ **const-width (tier-trained) degenerate loses** — conditioning on the player WITHIN the tier earns its place
- ✅ **incumbent beaten on the tier** — the selected band beats the served NF1.9 band on the tier
- ✅ **tier floors met** — pooled + every constrained position (QB 0.8559≥0.80, RB 0.8221≥0.80, WR 0.8514≥0.80)
- ✅ **universe guard met** — the winner AS SERVED still meets NF1.9's standing universe floors (QB 0.8539≥0.80, RB 0.8831≥0.80, TE 0.8817≥0.80, WR 0.9033≥0.80)
- ✅ **NF1.9 universe record reproduced** — the incumbent arm reproduces NF1.9's recorded universe IS80 (160.888 vs 160.888, Δ 0.00%)
- ✅ **motivating ~0.50 figure ATTRIBUTED (to the pre-NF1.9 normal band)** — the panel's pre-NF1.9 NORMAL band covers 0.5046 on the 2019–2025 tier — NF-RECAL1's recorded 0.5046 to the digit; the SERVED knn band's own tier coverage there is 0.8452
- ⚠️ **premise: SERVED band below the tier floor** — the served knn band's 2019–2025 tier coverage is 0.8452 — NOT below the 0.80 floor. **The motivating premise does not reproduce against the band actually on the wire** (the ~0.50 belongs to the pre-NF1.9 normal approximation); what remains is a re-selection QUESTION, answered by the gate below, not a standing defect

### ⭐ The proof the floors are CONSTRAINTS and not the selector

| degenerate       |   TIER IS80 |   tier cov | passes every TIER floor?   | floors missed                                                                     | loses to the winner?   |
|:-----------------|------------:|-----------:|:---------------------------|:----------------------------------------------------------------------------------|:-----------------------|
| max_width        |     404.712 |      0.991 | YES                        | —                                                                                 | yes                    |
| const_width_tier |     325.218 |      0.813 | no                         | tier WR 0.7917<0.800                                                              | yes                    |
| zero_width       |     716.260 |      0.001 | no                         | tier pooled 0.001<0.80, tier QB 0.0<0.800, tier RB 0.002<0.800, tier WR 0.0<0.800 | yes                    |

⭐ A CONSTRAINT a degenerate satisfies is fine — the metric then eliminates it; a CRITERION a degenerate wins is fatal (E2.1-r). `max_width` satisfying the floors while losing the metric is the proof the floor did not become the selector; `const_width_tier` losing is the proof per-player conditioning WITHIN the tier earns its place.

## 3. Power on the tier — and the groups too thin to gate

| position   |   n |   tier coverage (INCUMBENT) |   binomial SE |   class-clustered SE |   min_not_significantly_below |   z vs nominal | significantly below nominal?   |   P(reject | truly nominal) |
|:-----------|----:|----------------------------:|--------------:|---------------------:|------------------------------:|---------------:|:-------------------------------|----------------------------:|
| FB         |   4 |                       0.500 |         0.200 |                0.500 |                         0.471 |         -1.500 | NO                             |                       0.590 |
| QB         | 465 |                       0.856 |         0.018 |                0.015 |                         0.769 |          3.010 | NO                             |                       0.472 |
| RB         | 489 |                       0.824 |         0.018 |                0.016 |                         0.770 |          1.330 | NO                             |                       0.509 |
| TE         | 249 |                       0.739 |         0.025 |                0.022 |                         0.758 |         -2.410 | yes                            |                       0.513 |
| WR         | 821 |                       0.855 |         0.014 |                0.014 |                         0.777 |          3.950 | NO                             |                       0.486 |

The binomial SE is the design quantity the min-n rule is derived from; the CLASS-CLUSTERED SE (per-season coverage spread ÷ √seasons) is the honest one — tier rows share seasons. `P(reject | truly nominal)` ≈ 0.5 for a hard point-estimate floor at ANY n (NF1.8): more rows buy detection of a smaller true shortfall, not a lower false-reject rate.

## 4. Results — all configs (sorted by TIER IS80; universe sibling beside it)

| config                                                       |   TIER IS80 |   tier cov |   cov FB |   cov QB |   cov RB |   cov TE |   cov WR |   below p10 |   above p90 |   tier width |   fallback % |   UNIV IS80 |   univ cov | eligible                                                                |
|:-------------------------------------------------------------|------------:|-----------:|---------:|---------:|---------:|---------:|---------:|------------:|------------:|-------------:|-------------:|------------:|-----------:|:------------------------------------------------------------------------|
| knn_norm k200 (whole-board re-selection)                     |     297.579 |      0.831 |    0.500 |    0.856 |    0.822 |    0.743 |    0.851 |       0.069 |       0.100 |      237.660 |        0.000 |     161.092 |      0.885 | yes                                                                     |
| cqr_tier[pos,width] (conformal on the served band)           |     297.648 |      0.835 |    0.500 |    0.852 |    0.816 |    0.815 |    0.844 |       0.068 |       0.098 |      242.560 |        0.000 |     160.785 |      0.890 | yes                                                                     |
| cqr_tier[pos,add] (conformal on the served band)             |     297.663 |      0.836 |    0.500 |    0.852 |    0.816 |    0.819 |    0.845 |       0.067 |       0.097 |      242.630 |        0.000 |     160.789 |      0.890 | yes                                                                     |
| knn_tier k200 (tier-fit neighbourhood)                       |     297.855 |      0.819 |    0.500 |    0.815 |    0.755 |    0.892 |    0.838 |       0.076 |       0.105 |      231.670 |        0.200 |     160.835 |      0.886 | NO: tier RB 0.7546<0.800                                                |
| cqr_tier[mag,width] (conformal on the served band)           |     297.987 |      0.826 |    0.500 |    0.843 |    0.822 |    0.735 |    0.849 |       0.069 |       0.104 |      237.800 |        0.000 |     160.867 |      0.888 | yes                                                                     |
| cqr_tier[mag,add] (conformal on the served band)             |     298.028 |      0.827 |    0.500 |    0.845 |    0.822 |    0.735 |    0.849 |       0.069 |       0.104 |      237.810 |        0.000 |     160.877 |      0.888 | yes                                                                     |
| knn_norm k300 (INCUMBENT — the NF1.9 served band)            |     298.075 |      0.833 |    0.500 |    0.856 |    0.824 |    0.739 |    0.855 |       0.064 |       0.103 |      239.660 |        0.000 |     160.888 |      0.890 | n/a (incumbent)                                                         |
| cqr_tier[pool,add] (conformal on the served band)            |     298.075 |      0.833 |    0.500 |    0.856 |    0.824 |    0.739 |    0.855 |       0.064 |       0.103 |      239.660 |        0.000 |     160.888 |      0.890 | yes                                                                     |
| cqr_tier[pool,width] (conformal on the served band)          |     298.075 |      0.833 |    0.500 |    0.856 |    0.824 |    0.739 |    0.855 |       0.064 |       0.103 |      239.660 |        0.000 |     160.888 |      0.890 | yes                                                                     |
| scale_tier (null: served band ×m, fitted on the SCORE)       |     298.075 |      0.833 |    0.500 |    0.856 |    0.824 |    0.739 |    0.855 |       0.064 |       0.103 |      239.660 |        0.000 |     160.888 |      0.890 | yes                                                                     |
| cov_tier (null: served band ×m, fitted to a COVERAGE TARGET) |     298.231 |      0.773 |    0.500 |    0.781 |    0.769 |    0.715 |    0.789 |       0.112 |       0.115 |      227.700 |        0.000 |     160.926 |      0.875 | NO: tier pooled 0.7727<0.80; tier QB 0.7806<0.800; tier RB 0.7689<0.800 |
| knn_norm k500 (whole-board re-selection)                     |     299.290 |      0.840 |    0.500 |    0.865 |    0.834 |    0.723 |    0.866 |       0.052 |       0.108 |      242.640 |        0.000 |     161.130 |      0.891 | yes                                                                     |
| knn_pos_tier k100 (per-position tier-fit)                    |     299.434 |      0.784 |    0.500 |    0.774 |    0.797 |    0.755 |    0.793 |       0.090 |       0.126 |      227.390 |        2.100 |     161.217 |      0.878 | NO: tier pooled 0.7845<0.80; tier QB 0.7742<0.800; tier RB 0.7975<0.800 |
| knn_norm k100 (whole-board re-selection)                     |     300.095 |      0.822 |    0.250 |    0.832 |    0.795 |    0.759 |    0.854 |       0.075 |       0.103 |      233.360 |        0.000 |     162.752 |      0.878 | NO: tier RB 0.7955<0.800                                                |
| knn_tier k100 (tier-fit neighbourhood)                       |     300.480 |      0.810 |    0.500 |    0.813 |    0.744 |    0.879 |    0.828 |       0.083 |       0.107 |      228.780 |        0.200 |     161.469 |      0.884 | NO: tier RB 0.7444<0.800                                                |
| qreg_sqrt_tier (direct-learned foil, tier-fit)               |     302.390 |      0.803 |    1.000 |    0.725 |    0.783 |    0.904 |    0.828 |       0.088 |       0.109 |      253.940 |        0.000 |     161.930 |      0.883 | NO: tier QB 0.7247<0.800; tier RB 0.7832<0.800                          |
| knn_pos_tier k50 (per-position tier-fit)                     |     303.733 |      0.775 |    0.500 |    0.763 |    0.781 |    0.759 |    0.784 |       0.101 |       0.124 |      220.820 |        2.100 |     162.255 |      0.876 | NO: tier pooled 0.7751<0.80; tier QB 0.7634<0.800; tier RB 0.7812<0.800 |
| knn_norm k50 (whole-board re-selection)                      |     304.272 |      0.796 |    0.250 |    0.800 |    0.779 |    0.727 |    0.827 |       0.095 |       0.109 |      227.330 |        0.000 |     164.841 |      0.865 | NO: tier pooled 0.7959<0.80; tier RB 0.7791<0.800                       |
| knn_tier k50 (tier-fit neighbourhood)                        |     304.387 |      0.791 |    0.500 |    0.778 |    0.730 |    0.875 |    0.810 |       0.096 |       0.113 |      220.560 |        0.200 |     162.413 |      0.880 | NO: tier pooled 0.7909<0.80; tier QB 0.7785<0.800; tier RB 0.7301<0.800 |
| qreg_tier (direct-learned foil, tier-fit)                    |     304.496 |      0.802 |    1.000 |    0.731 |    0.777 |    0.900 |    0.826 |       0.089 |       0.110 |      256.050 |        0.000 |     162.439 |      0.882 | NO: tier QB 0.7312<0.800; tier RB 0.7771<0.800                          |
| knn_pos_tier k25 (per-position tier-fit)                     |     314.146 |      0.745 |    0.500 |    0.725 |    0.767 |    0.771 |    0.736 |       0.128 |       0.128 |      208.630 |        2.100 |     164.769 |      0.868 | NO: tier pooled 0.7446<0.80; tier QB 0.7247<0.800; tier RB 0.7669<0.800 |

`eligible` applies §1's three clauses (tier pooled · tier per-position · universe guard). `fallback %` — for an OVERLAY arm — is the share of TIER rows the overlay DECLINED (those rows keep the served NF1.9 band, i.e. partly the very band this story re-prices).

### ⭐ Was a new tier fit needed, or just a wider served band?

| arm                                               |   TIER IS80 |   tier cov |   below p10 |   above p90 |   tier width |
|:--------------------------------------------------|------------:|-----------:|------------:|------------:|-------------:|
| INCUMBENT — the served NF1.9 band                 |     298.075 |      0.833 |       0.064 |       0.103 |      239.660 |
| NULL — served band ×m fitted on the SCORE         |     298.075 |      0.833 |       0.064 |       0.103 |      239.660 |
| NULL — served band ×m fitted to a COVERAGE TARGET |     298.231 |      0.773 |       0.112 |       0.115 |      227.700 |
| WINNER — knn_norm k200 (whole-board re-selection) |     297.579 |      0.831 |       0.069 |       0.100 |      237.660 |

The two nulls price the naive fixes: `scale_tier` is 'just widen the served band' fitted on the same proper score the selection uses; `cov_tier` is the same machinery fitted to HIT nominal coverage — the E2.1-r inversion with a number attached. A winner that beats both earned its shape; a winner that merely ties `scale_tier` says the served band's SHAPE was fine and only its WIDTH was wrong on the tier.

### ⭐ What the tier-conditioning bought (the conformal foil ladder)

| arm                                               |   TIER IS80 |   tier cov |   cov FB |   cov QB |   cov RB |   cov TE |   cov WR |   tier width |
|:--------------------------------------------------|------------:|-----------:|---------:|---------:|---------:|---------:|---------:|-------------:|
| cqr_tier[pos,add]                                 |     297.663 |      0.836 |    0.500 |    0.852 |    0.816 |    0.819 |    0.845 |      242.630 |
| cqr_tier[mag,add]                                 |     298.028 |      0.827 |    0.500 |    0.845 |    0.822 |    0.735 |    0.849 |      237.810 |
| cqr_tier[pool,add]                                |     298.075 |      0.833 |    0.500 |    0.856 |    0.824 |    0.739 |    0.855 |      239.660 |
| WINNER — knn_norm k200 (whole-board re-selection) |     297.579 |      0.831 |    0.500 |    0.856 |    0.822 |    0.743 |    0.851 |      237.660 |

The conformal ladder separates WHAT the tier-conditioning bought: `pool` calibrates one quantile over the whole tier (the foil), `pos` adds position-conditioning (Mondrian), `mag` adds projection-magnitude conditioning within the tier. NF1.8's lesson: report the foil beside the conditioned arm, so 'the conditioning earned it' is attributable, not asserted. On the UNIVERSE this whole layer was a mathematical no-op (~29% of conformity scores exactly 0); on the tier it can act — these rows are the measurement. Measured here: the POOLED foil is a numerical NO-OP on the tier too (byte-identical to the incumbent — the pooled conformity quantile pins at ~0 because the tier-pooled base band already over-covers slightly), while the POSITION-conditioned arm genuinely acts.

⭐ **The observation that outlives the null:** the Mondrian arm lifts the CARRIED, UN-GATED TE group's tier coverage 0.739 → 0.8193 at essentially equal score (297.663 vs 298.075) — i.e. a mechanism that CAN act on the one group sitting below nominal exists. ⛔ It is NOT promoted here: TE has no registered floor (n = 249 < 400), and selecting an arm on an un-gated group's coverage is a floor nobody registered (E2.1-r by the back door). Recorded for NF-D22 — once a power-derived floor exists for thin groups, this is the arm its re-test should score first.

## 5. Deflation

| search       |   configs |   PBO |   median logit |   os_gap_pct (Bailey degradation) |   os_gap p90 % |   contender spread % (top quartile) |   splits |
|:-------------|----------:|------:|---------------:|----------------------------------:|---------------:|------------------------------------:|---------:|
| WHOLE field  |        21 | 0.507 |         -0.182 |                             0.586 |          2.081 |                               0.140 |     1716 |
| ELIGIBLE set |         9 | 0.422 |          0.405 |                             0.234 |          0.592 |                               0.140 |     1716 |

**PBO(eligible) = 0.4219** over 1716 balanced season splits (whole field 0.507), Bailey degradation 0.234% (p90 0.592%), contender spread 0.14%.

### Which arms actually win the in-sample halves (ELIGIBLE set)

| config                                             |   IS-half wins |   share |   full-sample IS80 |   Δ vs best % |
|:---------------------------------------------------|---------------:|--------:|-------------------:|--------------:|
| knn_norm k200 (whole-board re-selection)           |            869 |   0.506 |            297.579 |         0.000 |
| cqr_tier[pos,width] (conformal on the served band) |            383 |   0.223 |            297.648 |         0.020 |
| cqr_tier[pos,add] (conformal on the served band)   |            195 |   0.114 |            297.663 |         0.030 |
| cqr_tier[mag,width] (conformal on the served band) |            145 |   0.084 |            297.987 |         0.140 |
| knn_norm k500 (whole-board re-selection)           |            100 |   0.058 |            299.290 |         0.570 |
| cqr_tier[pool,add] (conformal on the served band)  |             20 |   0.012 |            298.075 |         0.170 |
| cqr_tier[mag,add] (conformal on the served band)   |              4 |   0.002 |            298.028 |         0.150 |

**DSR (whole field, the pre-registered binding reading): 0.0171** · contender-set DSR 0.4833 · pooled one-sided paired p = 0.3117 (α = 0.1). Per-position disclosure (BH-FDR q = 0.1, never gating): {'FB': {'p': None, 'bh_fdr_survives': False}, 'QB': {'p': 0.4269, 'bh_fdr_survives': False}, 'RB': {'p': 0.2579, 'bh_fdr_survives': False}, 'TE': {'p': 0.4813, 'bh_fdr_survives': False}, 'WR': {'p': 0.4024, 'bh_fdr_survives': False}}

## 6. Selection

**RECORDED NULL — THE SERVED BAND STANDS, AND THE PREMISE IS CORRECTED.** The motivating '~0.50 on the tier' belongs to the PRE-NF1.9 normal band (reproduced to the digit, §0); the band on the wire covers 0.8328 on the full-window tier and meets every gated tier floor. The best pre-registered arm (`knn_norm k200 (whole-board re-selection)`) leads the incumbent by only 0.17% on tier IS80 — a TIE, and the deflation gate says so (PBO(eligible) 0.4219, DSR 0.0171, pooled p 0.3117): *which* arm wins is noise. Per NF1.8/E2.1-r, a high PBO over a tied field is the NULL — the outcome is that the served band's tier adequacy is now PROVEN AND DISCLOSED rather than unmeasured, not that a better band was found and lost. ⛔ Nothing is wired; `_VET_TIER_RECAL` stays False with no selected overlay.

### The tie among ELIGIBLE arms

| config                                                 |   TIER IS80 |   Δ vs winner % |   tier cov |   fallback % |   tier width |
|:-------------------------------------------------------|------------:|----------------:|-----------:|-------------:|-------------:|
| knn_norm k200 (whole-board re-selection)               |     297.579 |           0.000 |      0.831 |        0.000 |      237.660 |
| cqr_tier[pos,width] (conformal on the served band)     |     297.648 |           0.020 |      0.835 |        0.000 |      242.560 |
| cqr_tier[pos,add] (conformal on the served band)       |     297.663 |           0.030 |      0.836 |        0.000 |      242.630 |
| cqr_tier[mag,width] (conformal on the served band)     |     297.987 |           0.140 |      0.826 |        0.000 |      237.800 |
| cqr_tier[mag,add] (conformal on the served band)       |     298.028 |           0.150 |      0.827 |        0.000 |      237.810 |
| cqr_tier[pool,add] (conformal on the served band)      |     298.075 |           0.170 |      0.833 |        0.000 |      239.660 |
| cqr_tier[pool,width] (conformal on the served band)    |     298.075 |           0.170 |      0.833 |        0.000 |      239.660 |
| scale_tier (null: served band ×m, fitted on the SCORE) |     298.075 |           0.170 |      0.833 |        0.000 |      239.660 |
| knn_norm k500 (whole-board re-selection)               |     299.290 |           0.570 |      0.840 |        0.000 |      242.640 |

The top 9 eligible arm(s) sit within 1% on the primary metric. A genuine tie is broken on the program's own DEFECT metric (the fallback rate — an overlay that declines tier rows leaves them on the band this story re-prices), never on coverage headroom above the floor (monotone in widening — the `max_width` degenerate wins that criterion while being useless).

### Per-position coverage — TIER and UNIVERSE, row-pooled, slack in ROWS

| arm                                               |   tier cov FB |   tier cov QB |   tier cov RB |   tier cov TE |   tier cov WR | tier slack FB (rows)   |   tier slack QB (rows) |   tier slack RB (rows) | tier slack TE (rows)   |   tier slack WR (rows) |   univ cov FB |   univ cov QB |   univ cov RB |   univ cov TE |   univ cov WR |
|:--------------------------------------------------|--------------:|--------------:|--------------:|--------------:|--------------:|:-----------------------|-----------------------:|-----------------------:|:-----------------------|-----------------------:|--------------:|--------------:|--------------:|--------------:|--------------:|
| INCUMBENT (NF1.9 served)                          |         0.500 |         0.856 |         0.824 |         0.739 |         0.855 |                        |                     25 |                     11 |                        |                     45 |         0.860 |         0.858 |         0.886 |         0.888 |         0.907 |
| WINNER (knn_norm k200 (whole-board re-selection)) |         0.500 |         0.856 |         0.822 |         0.743 |         0.851 |                        |                     25 |                     10 |                        |                     42 |         0.853 |         0.854 |         0.883 |         0.882 |         0.903 |

⭐ Floor margins in ROWS (NF1.8): tier **QB** 25, **RB** 10, **WR** 42 · universe **QB** 60, **RB** 167, **TE** 147, **WR** 326. A coverage decimal hides how few outcomes a floor rests on.

## 7. Per-season detail (winner vs incumbent, TIER IS80)

|   target_season |   TIER IS80 (winner) |   TIER IS80 (incumbent) |
|----------------:|---------------------:|------------------------:|
|        2013.000 |              304.490 |                 306.056 |
|        2014.000 |              289.442 |                 291.680 |
|        2015.000 |              297.598 |                 304.120 |
|        2016.000 |              296.130 |                 293.249 |
|        2017.000 |              288.168 |                 286.415 |
|        2018.000 |              336.353 |                 340.315 |
|        2019.000 |              311.524 |                 314.744 |
|        2020.000 |              304.126 |                 297.366 |
|        2021.000 |              299.098 |                 296.803 |
|        2022.000 |              288.300 |                 285.812 |
|        2023.000 |              291.456 |                 293.864 |
|        2024.000 |              268.816 |                 270.405 |
|        2025.000 |              293.031 |                 294.148 |

## 8. Serving state + the standing re-validation

⛔ **CODE-READY, NOT DEPLOYED.** The selection is recorded as data here and wired behind `season_projection._VET_TIER_RECAL = False` — the served board is byte-identical until an operator flips it, re-exports, and re-runs `run_interval_revalidation` (which a band re-selection REQUIRES — the same gate that refused NF-D21 and NF-RECAL1). The standing annual re-validation should, post-flip, score the tier read beside the universe read; a tier floor breach is a re-selection trigger, never a floor adjustment.

## 9. Honest limitations

- **The point projection and the NF1.5 ordering are untouched** — this story prices tier uncertainty; it does not fix the tier's measured level coldness (that is NF-RECAL1's successor B2/B3's job).
- **FB, TE carried un-gated** on the tier (n < 400) — reported per-position coverage stands, but no floor claim is made there; a power-derived fallback floor is NF-D22's job.
- **A floor is not an out-of-sample guarantee** — met on 2013–2025; 2026 onward is what the standing re-validation exists for.
- **The class-clustered SE exceeds the binomial SE** at most positions: season-to-season environment shifts are the dominant residual uncertainty and no per-player band removes them.
- **`cov_tier` is a foil, not a candidate to fear** — its coverage column must never be read as a recommendation (E2.1-r).
- **No edge claim** — `best_alpha = 0`; an honest interval is a projection-quality property.

