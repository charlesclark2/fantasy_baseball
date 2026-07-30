# NF1.8 — the rookie 80% interval under a PER-POSITION coverage FLOOR (§0.5 bake-off)

**Generated:** 2026-07-30T01:37:03.838805+00:00 · **held-out draft classes:** 2019–2025 (7) · **configs scored:** 80 · **held-out rookie-seasons:** 553

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. What is selected is the WIDTH AND SHAPE of the rookie interval; the POINT projection is held byte-identical across every arm (proved below).

## 0. Why NF1.7 needed this follow-up

NF1.7 replaced NF1.4's class-level rookie band with a per-player one, selected on a PROPER interval score with a pre-registered **POOLED** coverage floor of 0.80. Pooled coverage rose 0.791 → 0.808 and the floor was met. But the coverage **redistributed** rather than improving uniformly:

| position   |   n (held-out) |   incumbent (NF1.4 class-level) |   NF1.7 (pooled floor) | ≥ nominal 0.80?   |
|:-----------|---------------:|--------------------------------:|-----------------------:|:------------------|
| QB         |             81 |                           0.741 |                  0.741 | NO                |
| RB         |            148 |                           0.831 |                  0.777 | NO                |
| TE         |            100 |                           0.720 |                  0.870 | yes               |
| WR         |            224 |                           0.812 |                  0.826 | yes               |

That was not a gate miss — the floor was pooled, and pooled cleared it. It is, however, the same class of blind spot as NF1.4's, one level up: **pooled coverage is a POPULATION property that one position can pay for on another's behalf.** A band can hold 80% overall while systematically under-covering the position whose outcome distribution it fits worst, and rookie QB is exactly that position. So the floor moves per-position.

⭐ **What does NOT change:** the SELECTION metric is still the interval score. Coverage — pooled or per-position — is an ELIGIBILITY FLOOR, never a target (E2.1-r). §2 proves that directly: the `max_width` degenerate satisfies EVERY per-position floor and still loses.

### ⚠️ One metric-convention change, and it is load-bearing

NF1.7 averaged each metric over the held-out CLASSES (a mean of per-class means). NF1.8 pools over ROWS, for two reasons: (a) a per-position floor **cannot** be a mean of per-class means — NF1.7 required ≥3 rows for a position to enter a class's mean, so a position thin in one class was silently DROPPED and the floor would be evaluated on a quietly different population than the one it claims to protect; (b) a rookie-season is the unit the floor is about, so each should weigh the same. Both conventions are reported for every config below.

| config                            |   IS80 (row-pooled — NF1.8) |   IS80 (class-mean — NF1.7) |      Δ |
|:----------------------------------|----------------------------:|----------------------------:|-------:|
| qreg α0.01 · sdgain 0             |                     180.989 |                     181.163 | -0.174 |
| class_tercile (NF1.4 INCUMBENT)   |                     201.763 |                     202.137 | -0.374 |
| qreg_sqrt+cqr[pos,add] · sdgain 0 |                     183.407 |                     183.539 | -0.132 |

## 1. The pre-registered PER-POSITION floor

**Tier 1 (primary):** pooled coverage ≥ 0.80 **and** every position with ≥ 30 held-out rookie-seasons ≥ the nominal 0.80.

**Tier 2 (documented fallback, used only if Tier 1 admits nothing):** the structurally-thin positions (QB) relax to `nominal − 1.645·SE(n)` — 'not significantly below nominal, one-sided at 95%'. Derived from SAMPLE SIZE alone (a design quantity known before any result), which is what stops it being a floor reverse-engineered from the answer. Every other position keeps the hard nominal floor.

**TIER USED: 1** — 24 of 78 per-player configs clear the Tier-1 hard nominal floor at every position, so the pre-registered Tier-2 fallback was NOT needed — the QB floor is the full nominal 0.80.

| position   |   floor |   n (held-out rookie-seasons) |
|:-----------|--------:|------------------------------:|
| QB         |   0.800 |                            81 |
| RB         |   0.800 |                           148 |
| TE         |   0.800 |                           100 |
| WR         |   0.800 |                           224 |

## 2. The anchor set — four guards, carried from NF1.7

| anchor            | what it is                                                                                                                      |    IS80 |   pooled cov80 |   mean width |   cov QB |   cov RB |   cov TE |   cov WR |
|:------------------|:--------------------------------------------------------------------------------------------------------------------------------|--------:|---------------:|-------------:|---------:|---------:|---------:|---------:|
| permuted_own      | ⭐ PERMUTATION ORACLE — the WINNER'S OWN arm, same family and same resolution, fitted on SHUFFLED training outcomes. Must LOSE. | 227.242 |          0.881 |      169.500 |    0.840 |    0.865 |    0.940 |    0.879 |
| permuted_knn_norm | PERMUTATION ORACLE (neighbourhood family). Must LOSE.                                                                           | 225.820 |          0.868 |      161.970 |    0.827 |    0.872 |    0.870 |    0.879 |
| oracle_qreg       | peeking same-family oracle (parametric) — fitted on the held-out class's truth. Nothing may beat it.                            | 159.271 |          0.870 |      125.450 |    0.815 |    0.858 |    0.930 |    0.871 |
| oracle_knn        | peeking same-family oracle (neighbourhood). Orientation.                                                                        | 174.793 |          0.835 |      125.830 |    0.790 |    0.824 |    0.870 |    0.844 |
| zero_width        | DEGENERATE — width 0 at the point. MAXIMALLY sharp ⇒ a naive sharpness metric would crown it. Must LOSE.                        | 431.998 |          0.004 |        0.100 |    0.000 |    0.000 |    0.010 |    0.004 |
| max_width         | DEGENERATE — [0, the position's max realized rookie season]. Coverage ≈ 1 ⇒ a coverage TARGET would love it. Must LOSE.         | 305.995 |          0.982 |      302.160 |    0.951 |    0.993 |    0.970 |    0.991 |
| const_width       | DEGENERATE — ONE band per position, no conditioning at all. Must LOSE.                                                          | 230.006 |          0.877 |      166.090 |    0.852 |    0.892 |    0.910 |    0.862 |
| oracle_point      | the trivial infimum (zero width AT the realized value) — orientation only, not a discriminator.                                 |   0.113 |          0.937 |        0.020 |    0.963 |    0.912 |    0.940 |    0.942 |

⭐ **The oracle is a PERMUTATION** (`permuted_*`): the same family, on the same rows, fitted against a SHUFFLE of the training outcomes instead of the truth. Knowing the answer must score better than not knowing it. Unlike a peeking fitted oracle this is well-posed at ANY sample size — family and resolution are held exactly equal and only the information content moves — which is the NF1.7 lesson that a peeking MISSPECIFIED oracle, or a peeking k-NN fitted on ~80 test rows, is legitimately beatable by an honest in-fold arm. The same-family peeking oracles are still reported and still checked, for orientation.

- ✅ **permutation oracle respected** — the winner beats its OWN family fitted on SHUFFLED outcomes (permuted_own: 227.242 vs 183.407) — the metric rewards information, not width
- ✅ **same-family peeking oracle respected** — the winner does not beat a peeking fit of its own family (oracle_qreg)
- ✅ **zero-width degenerate loses** — sharpness was not bought by under-covering
- ✅ **max-width degenerate loses** — the selection is not a coverage exercise in disguise — see the table below
- ✅ **const-width degenerate loses** — conditioning on the player earns its place
- ✅ **incumbent beaten** — the selected band beats NF1.4's class-level band
- ✅ **per-position floor met** — every position clears its floor (QB 0.8148≥0.800, RB 0.8041≥0.800, TE 0.9≥0.800, WR 0.8348≥0.800)
- ✅ **point projection unchanged** — the served rookie point is byte-identical to NF1.7's (max drift 0.0e+00)

### ⭐ The proof the per-position floor is a CONSTRAINT and not the selector

| degenerate                                  |    IS80 | passes EVERY per-position floor?   | floors missed                                                                  | loses to the winner?   |
|:--------------------------------------------|--------:|:-----------------------------------|:-------------------------------------------------------------------------------|:-----------------------|
| max_width                                   | 305.995 | YES                                | —                                                                              | yes                    |
| const_width                                 | 230.006 | YES                                | —                                                                              | yes                    |
| zero_width                                  | 431.998 | no                                 | pooled 0.0036<0.80, QB 0.0<0.800, RB 0.0<0.800, TE 0.01<0.800, WR 0.0045<0.800 | yes                    |
| SHIPPED — qreg_sqrt+cqr[pos,add] · sdgain 0 | 183.407 | YES                                | —                                                                              | —                      |

⭐ **`max_width` satisfies every per-position floor and still loses by a wide margin** — that is the whole argument that adding a per-position floor did not turn this into a coverage exercise. A criterion a degenerate wins cannot select an interval (E2.1-r); a CONSTRAINT a degenerate satisfies is fine, because the degenerate is then eliminated by the metric. This is also why the floor is not tightened above nominal 'for safety': every notch above nominal moves the eligible set closer to `max_width` and further from an honest band.

## 3. Power — what a per-position floor can and cannot resolve

| position   |   n |   coverage (NF1.7 winner) |   binomial SE |   class-clustered SE |   min_not_significantly_below |   z vs nominal | significantly below nominal?   |   P(reject | truly nominal) |
|:-----------|----:|--------------------------:|--------------:|---------------------:|------------------------------:|---------------:|:-------------------------------|----------------------------:|
| QB         |  81 |                     0.741 |         0.044 |                0.031 |                         0.727 |         -1.330 | NO                             |                       0.456 |
| RB         | 148 |                     0.777 |         0.033 |                0.045 |                         0.746 |         -0.700 | NO                             |                       0.500 |
| TE         | 100 |                     0.870 |         0.040 |                0.024 |                         0.734 |          1.750 | NO                             |                       0.441 |
| WR         | 224 |                     0.826 |         0.027 |                0.043 |                         0.756 |          0.970 | NO                             |                       0.513 |

⚠️ **Read this before reading the selection.** QB carries only **81** held-out rookie-seasons across 7 classes, so the binomial SE of its coverage at nominal is **0.044** — NF1.7's 0.7407 sits 1.3 SE below 0.80, i.e. **not significantly below nominal**. The same is true of **QB, RB**: both fail the HARD nominal floor while NOT being significantly below nominal. Three consequences, all honest:

1. **A hard per-position floor at nominal is partly selecting on NOISE.** The exact `P(reject | truly nominal)` column shows a perfectly-calibrated arm is rejected ~50% of the time at EVERY position — and that rate barely moves with n. Sample size does not buy a lower false-reject rate; it buys the ability to detect a SMALLER true shortfall. This is why every config counts toward the deflation in §5 and why the pre-registered Tier-2 floor exists.
2. **The gap is nevertheless worth constraining, because the floor turned out CHEAP.** Its cost is reported in §6 in interval-score points. Had that cost been large, the honest answer would have been to leave NF1.7's band alone and keep disclosing the QB gap — which is exactly what NF1.7 did, and would have been the right call again.
3. **The floor is not tightened above nominal 'for safety'.** Every notch above nominal moves the eligible set toward `max_width` (§2), which satisfies any coverage floor and is useless.

The CLASS-CLUSTERED SE is the more honest column: where it exceeds the binomial SE (RB and WR here), class-to-class variation — not per-player miscalibration — is the dominant uncertainty, and no amount of in-fold recalibration can remove it. §6 shows that directly.

## 4. Results — all configs (sorted by the primary metric)

| config                                 |    IS80 |   IS80 (NF1.7 conv.) |   cov80 |   cov QB |   cov RB |   cov TE |   cov WR |   mean width |   distinct-band frac |   worst shared |   fallback % | eligible                                                                                 |
|:---------------------------------------|--------:|---------------------:|--------:|---------:|---------:|---------:|---------:|-------------:|---------------------:|---------------:|-------------:|:-----------------------------------------------------------------------------------------|
| qreg+cqr[pos,width] · sdgain 0         | 180.811 |              180.980 |   0.816 |    0.778 |    0.784 |    0.870 |    0.826 |      128.020 |                0.946 |              3 |        0.000 | NO: QB 0.7778<0.800; RB 0.7838<0.800                                                     |
| qreg+cqr[pos,add] · sdgain 0           | 180.817 |              180.987 |   0.816 |    0.778 |    0.784 |    0.870 |    0.826 |      127.900 |                0.939 |              4 |        0.000 | NO: QB 0.7778<0.800; RB 0.7838<0.800                                                     |
| qreg+cqr[pool,width] · sdgain 0        | 180.974 |              181.148 |   0.812 |    0.753 |    0.784 |    0.870 |    0.826 |      127.760 |                0.931 |              4 |        0.000 | NO: QB 0.7531<0.800; RB 0.7838<0.800                                                     |
| qreg+cqr[pool,add] · sdgain 0          | 180.982 |              181.156 |   0.814 |    0.753 |    0.784 |    0.880 |    0.826 |      127.690 |                0.939 |              3 |        0.000 | NO: QB 0.7531<0.800; RB 0.7838<0.800                                                     |
| qreg α0.01 · sdgain 0                  | 180.989 |              181.163 |   0.808 |    0.741 |    0.777 |    0.870 |    0.826 |      127.590 |                0.933 |              4 |        0.000 | NO: QB 0.7407<0.800; RB 0.777<0.800                                                      |
| qreg+cqr[pos,width] · sdgain 0.1       | 181.136 |              181.330 |   0.846 |    0.778 |    0.784 |    0.930 |    0.875 |      131.120 |                0.890 |              4 |        0.000 | NO: QB 0.7778<0.800; RB 0.7838<0.800                                                     |
| qreg+cqr[pos,add] · sdgain 0.1         | 181.143 |              181.338 |   0.846 |    0.778 |    0.784 |    0.930 |    0.875 |      131.000 |                0.890 |              4 |        0.000 | NO: QB 0.7778<0.800; RB 0.7838<0.800                                                     |
| qreg+cqr[pos,width] · sdgain 0.2       | 181.193 |              181.414 |   0.852 |    0.778 |    0.784 |    0.960 |    0.875 |      133.630 |                0.915 |              3 |        0.000 | NO: QB 0.7778<0.800; RB 0.7838<0.800                                                     |
| qreg+cqr[pos,add] · sdgain 0.2         | 181.200 |              181.421 |   0.852 |    0.778 |    0.784 |    0.960 |    0.875 |      133.510 |                0.906 |              3 |        0.000 | NO: QB 0.7778<0.800; RB 0.7838<0.800                                                     |
| qreg+cqr[pool,width] · sdgain 0.1      | 181.293 |              181.493 |   0.843 |    0.753 |    0.784 |    0.930 |    0.875 |      130.850 |                0.900 |              4 |        0.000 | NO: QB 0.7531<0.800; RB 0.7838<0.800                                                     |
| qreg+cqr[pool,add] · sdgain 0.1        | 181.301 |              181.500 |   0.843 |    0.753 |    0.784 |    0.930 |    0.875 |      130.800 |                0.904 |              4 |        0.000 | NO: QB 0.7531<0.800; RB 0.7838<0.800                                                     |
| qreg α0.01 · sdgain 0.1                | 181.306 |              181.505 |   0.841 |    0.753 |    0.777 |    0.930 |    0.875 |      130.710 |                0.900 |              4 |        0.000 | NO: QB 0.7531<0.800; RB 0.777<0.800                                                      |
| qreg+cqr[pool,width] · sdgain 0.2      | 181.327 |              181.553 |   0.852 |    0.778 |    0.784 |    0.960 |    0.875 |      133.350 |                0.895 |              4 |        0.000 | NO: QB 0.7778<0.800; RB 0.7838<0.800                                                     |
| qreg+cqr[pool,add] · sdgain 0.2        | 181.333 |              181.559 |   0.852 |    0.778 |    0.784 |    0.960 |    0.875 |      133.310 |                0.904 |              3 |        0.000 | NO: QB 0.7778<0.800; RB 0.7838<0.800                                                     |
| qreg α0.01 · sdgain 0.2                | 181.346 |              181.571 |   0.850 |    0.778 |    0.777 |    0.960 |    0.875 |      133.220 |                0.900 |              3 |        0.000 | NO: QB 0.7778<0.800; RB 0.777<0.800                                                      |
| qreg α0 · sdgain 0                     | 183.258 |              183.355 |   0.772 |    0.753 |    0.750 |    0.760 |    0.799 |      122.870 |                0.964 |              3 |        0.000 | NO: pooled 0.7722<0.80; QB 0.7531<0.800; RB 0.75<0.800; TE 0.76<0.800; WR 0.7991<0.800   |
| qreg α0 · sdgain 0.1                   | 183.381 |              183.510 |   0.812 |    0.753 |    0.750 |    0.850 |    0.857 |      126.470 |                0.955 |              3 |        0.000 | NO: QB 0.7531<0.800; RB 0.75<0.800                                                       |
| qreg_sqrt+cqr[pos,add] · sdgain 0      | 183.407 |              183.539 |   0.835 |    0.815 |    0.804 |    0.900 |    0.835 |      130.750 |                0.893 |              3 |        0.000 | yes                                                                                      |
| qreg_sqrt+cqr[pos,width] · sdgain 0    | 183.429 |              183.561 |   0.835 |    0.815 |    0.804 |    0.900 |    0.835 |      130.800 |                0.891 |              4 |        0.000 | yes                                                                                      |
| qreg_sqrt α0.01 · sdgain 0             | 183.451 |              183.582 |   0.830 |    0.778 |    0.804 |    0.900 |    0.835 |      130.620 |                0.893 |              4 |        0.000 | NO: QB 0.7778<0.800                                                                      |
| qreg_sqrt+cqr[pool,add] · sdgain 0     | 183.451 |              183.582 |   0.830 |    0.778 |    0.804 |    0.900 |    0.835 |      130.620 |                0.893 |              4 |        0.000 | NO: QB 0.7778<0.800                                                                      |
| qreg_sqrt+cqr[pool,width] · sdgain 0   | 183.451 |              183.582 |   0.830 |    0.778 |    0.804 |    0.900 |    0.835 |      130.620 |                0.893 |              4 |        0.000 | NO: QB 0.7778<0.800                                                                      |
| qreg α0 · sdgain 0.2                   | 183.541 |              183.695 |   0.821 |    0.753 |    0.750 |    0.860 |    0.875 |      129.440 |                0.931 |              3 |        0.000 | NO: QB 0.7531<0.800; RB 0.75<0.800                                                       |
| qreg_sqrt+cqr[pos,add] · sdgain 0.1    | 183.550 |              183.705 |   0.857 |    0.827 |    0.804 |    0.950 |    0.862 |      133.690 |                0.848 |              4 |        0.000 | yes                                                                                      |
| qreg_sqrt+cqr[pos,width] · sdgain 0.1  | 183.572 |              183.727 |   0.857 |    0.827 |    0.804 |    0.950 |    0.862 |      133.740 |                0.859 |              4 |        0.000 | yes                                                                                      |
| qreg_sqrt+cqr[pool,width] · sdgain 0.1 | 183.580 |              183.735 |   0.854 |    0.802 |    0.804 |    0.950 |    0.862 |      133.570 |                0.855 |              4 |        0.000 | yes                                                                                      |
| qreg_sqrt+cqr[pool,add] · sdgain 0.1   | 183.581 |              183.736 |   0.854 |    0.802 |    0.804 |    0.950 |    0.862 |      133.570 |                0.855 |              4 |        0.000 | yes                                                                                      |
| qreg_sqrt α0.01 · sdgain 0.1           | 183.582 |              183.737 |   0.854 |    0.802 |    0.804 |    0.950 |    0.862 |      133.560 |                0.855 |              4 |        0.000 | yes                                                                                      |
| qreg_sqrt+cqr[pos,add] · sdgain 0.2    | 183.658 |              183.846 |   0.864 |    0.827 |    0.804 |    0.960 |    0.875 |      136.250 |                0.855 |              3 |        0.000 | yes                                                                                      |
| qreg_sqrt+cqr[pos,width] · sdgain 0.2  | 183.680 |              183.868 |   0.864 |    0.827 |    0.804 |    0.960 |    0.875 |      136.310 |                0.848 |              4 |        0.000 | yes                                                                                      |
| qreg_sqrt+cqr[pool,width] · sdgain 0.2 | 183.681 |              183.869 |   0.863 |    0.815 |    0.804 |    0.960 |    0.875 |      136.130 |                0.846 |              4 |        0.000 | yes                                                                                      |
| qreg_sqrt α0.01 · sdgain 0.2           | 183.684 |              183.872 |   0.863 |    0.815 |    0.804 |    0.960 |    0.875 |      136.130 |                0.845 |              4 |        0.000 | yes                                                                                      |
| qreg_sqrt+cqr[pool,add] · sdgain 0.2   | 183.684 |              183.872 |   0.863 |    0.815 |    0.804 |    0.960 |    0.875 |      136.130 |                0.845 |              4 |        0.000 | yes                                                                                      |
| knn_norm k80 · sdgain 0.2              | 184.913 |              185.269 |   0.843 |    0.815 |    0.905 |    0.800 |    0.830 |      122.670 |                0.626 |              9 |        4.900 | yes                                                                                      |
| qreg_sqrt α0 · sdgain 0                | 185.190 |              185.269 |   0.828 |    0.802 |    0.797 |    0.860 |    0.844 |      131.070 |                0.949 |              4 |        0.000 | NO: RB 0.7973<0.800                                                                      |
| qreg_sqrt α0 · sdgain 0.1              | 185.604 |              185.715 |   0.850 |    0.815 |    0.797 |    0.900 |    0.875 |      134.430 |                0.908 |              4 |        0.000 | NO: RB 0.7973<0.800                                                                      |
| qreg_sqrt α0 · sdgain 0.2              | 185.787 |              185.926 |   0.855 |    0.815 |    0.797 |    0.910 |    0.884 |      137.260 |                0.917 |              4 |        0.000 | NO: RB 0.7973<0.800                                                                      |
| knn_norm k80 · sdgain 0.1              | 186.082 |              186.437 |   0.832 |    0.802 |    0.905 |    0.790 |    0.812 |      120.360 |                0.633 |              8 |        4.900 | NO: TE 0.79<0.800                                                                        |
| knn_norm k50 · sdgain 0.2              | 186.438 |              186.896 |   0.826 |    0.778 |    0.865 |    0.800 |    0.830 |      124.570 |                0.714 |              6 |        4.900 | NO: QB 0.7778<0.800                                                                      |
| qreg_perpos α0.01 · sdgain 0.2         | 187.237 |              187.411 |   0.826 |    0.716 |    0.797 |    0.830 |    0.884 |      128.400 |                0.890 |              6 |        4.900 | NO: QB 0.716<0.800; RB 0.7973<0.800                                                      |
| knn_norm k80 · sdgain 0                | 187.306 |              187.665 |   0.821 |    0.802 |    0.905 |    0.770 |    0.795 |      117.970 |                0.640 |              8 |        4.900 | NO: TE 0.77<0.800; WR 0.7946<0.800                                                       |
| knn_norm k50 · sdgain 0.1              | 187.456 |              187.921 |   0.810 |    0.765 |    0.865 |    0.790 |    0.799 |      122.210 |                0.689 |              6 |        4.900 | NO: QB 0.7654<0.800; TE 0.79<0.800; WR 0.7991<0.800                                      |
| qreg_perpos α0.01 · sdgain 0.1         | 187.469 |              187.632 |   0.825 |    0.716 |    0.797 |    0.820 |    0.884 |      126.000 |                0.890 |              6 |        4.900 | NO: QB 0.716<0.800; RB 0.7973<0.800                                                      |
| qreg_perpos α0.01 · sdgain 0           | 187.710 |              187.860 |   0.797 |    0.716 |    0.797 |    0.760 |    0.844 |      123.250 |                0.911 |              6 |        4.900 | NO: pooled 0.7975<0.80; QB 0.716<0.800; RB 0.7973<0.800; TE 0.76<0.800                   |
| knn_norm k30 · sdgain 0.2              | 187.963 |              188.258 |   0.835 |    0.802 |    0.865 |    0.820 |    0.835 |      122.330 |                0.741 |              7 |        4.900 | yes                                                                                      |
| knn_norm k30 · sdgain 0.1              | 188.548 |              188.834 |   0.814 |    0.790 |    0.865 |    0.770 |    0.808 |      119.850 |                0.752 |              6 |        4.900 | NO: QB 0.7901<0.800; TE 0.77<0.800                                                       |
| knn_norm k50 · sdgain 0                | 188.919 |              189.392 |   0.796 |    0.765 |    0.865 |    0.760 |    0.777 |      119.690 |                0.698 |              6 |        4.900 | NO: pooled 0.7957<0.80; QB 0.7654<0.800; TE 0.76<0.800; WR 0.7768<0.800                  |
| knn_norm k30 · sdgain 0                | 189.330 |              189.602 |   0.805 |    0.790 |    0.865 |    0.760 |    0.790 |      117.250 |                0.754 |              6 |        4.900 | NO: QB 0.7901<0.800; TE 0.76<0.800; WR 0.7902<0.800                                      |
| qreg_sqrt_perpos α0.01 · sdgain 0.2    | 190.053 |              190.237 |   0.830 |    0.704 |    0.811 |    0.830 |    0.888 |      132.220 |                0.873 |              6 |        4.900 | NO: QB 0.7037<0.800                                                                      |
| qreg_sqrt_perpos α0.01 · sdgain 0.1    | 190.145 |              190.309 |   0.825 |    0.704 |    0.811 |    0.820 |    0.879 |      129.780 |                0.897 |              6 |        4.900 | NO: QB 0.7037<0.800                                                                      |
| qreg_sqrt_perpos α0.01 · sdgain 0      | 190.228 |              190.375 |   0.808 |    0.691 |    0.811 |    0.800 |    0.853 |      127.120 |                0.919 |              6 |        4.900 | NO: QB 0.6914<0.800                                                                      |
| knn_norm k120 · sdgain 0.2             | 191.567 |              191.850 |   0.834 |    0.778 |    0.885 |    0.790 |    0.839 |      123.200 |                0.599 |             18 |        4.900 | NO: QB 0.7778<0.800; TE 0.79<0.800                                                       |
| qreg_perpos α0 · sdgain 0.2            | 191.878 |              192.152 |   0.814 |    0.704 |    0.750 |    0.860 |    0.875 |      128.640 |                0.888 |              6 |        4.900 | NO: QB 0.7037<0.800; RB 0.75<0.800                                                       |
| qreg_perpos α0 · sdgain 0.1            | 192.053 |              192.311 |   0.801 |    0.691 |    0.750 |    0.850 |    0.853 |      126.010 |                0.908 |              6 |        4.900 | NO: QB 0.6914<0.800; RB 0.75<0.800                                                       |
| qreg_perpos α0 · sdgain 0              | 192.187 |              192.427 |   0.768 |    0.691 |    0.750 |    0.800 |    0.795 |      122.880 |                0.940 |              6 |        4.900 | NO: pooled 0.7685<0.80; QB 0.6914<0.800; RB 0.75<0.800; WR 0.7946<0.800                  |
| knn_norm k120 · sdgain 0.1             | 192.933 |              193.222 |   0.826 |    0.778 |    0.885 |    0.780 |    0.826 |      120.970 |                0.599 |             15 |        4.900 | NO: QB 0.7778<0.800; TE 0.78<0.800                                                       |
| knn_norm k120 · sdgain 0               | 194.336 |              194.630 |   0.817 |    0.778 |    0.885 |    0.770 |    0.808 |      118.760 |                0.595 |             15 |        4.900 | NO: QB 0.7778<0.800; TE 0.77<0.800                                                       |
| knn_pos k30 · sdgain 0.2               | 194.399 |              194.774 |   0.806 |    0.753 |    0.797 |    0.810 |    0.830 |      118.980 |                0.494 |             13 |        4.900 | NO: QB 0.7531<0.800; RB 0.7973<0.800                                                     |
| knn_pos k30 · sdgain 0.1               | 195.344 |              195.721 |   0.799 |    0.753 |    0.797 |    0.790 |    0.821 |      116.380 |                0.490 |             13 |        4.900 | NO: pooled 0.7993<0.80; QB 0.7531<0.800; RB 0.7973<0.800; TE 0.79<0.800                  |
| knn_pos k30 · sdgain 0                 | 196.406 |              196.781 |   0.779 |    0.753 |    0.797 |    0.790 |    0.772 |      113.650 |                0.450 |             13 |        4.900 | NO: pooled 0.7794<0.80; QB 0.7531<0.800; RB 0.7973<0.800; TE 0.79<0.800; WR 0.7723<0.800 |
| qreg_sqrt_perpos α0 · sdgain 0.2       | 196.866 |              197.152 |   0.832 |    0.716 |    0.811 |    0.860 |    0.875 |      134.790 |                0.893 |              6 |        4.900 | NO: QB 0.716<0.800                                                                       |
| qreg_sqrt_perpos α0 · sdgain 0         | 196.952 |              197.170 |   0.803 |    0.704 |    0.811 |    0.820 |    0.826 |      129.180 |                0.895 |              6 |        4.900 | NO: QB 0.7037<0.800                                                                      |
| qreg_sqrt_perpos α0 · sdgain 0.1       | 196.957 |              197.206 |   0.825 |    0.704 |    0.811 |    0.860 |    0.862 |      132.150 |                0.879 |              6 |        4.900 | NO: QB 0.7037<0.800                                                                      |
| knn_pos k50 · sdgain 0.2               | 198.465 |              198.757 |   0.823 |    0.815 |    0.804 |    0.800 |    0.848 |      122.550 |                0.398 |             19 |        4.900 | yes                                                                                      |
| knn_pos k50 · sdgain 0.1               | 199.394 |              199.683 |   0.817 |    0.815 |    0.804 |    0.790 |    0.839 |      120.130 |                0.389 |             19 |        4.900 | NO: TE 0.79<0.800                                                                        |
| knn_pos k50 · sdgain 0                 | 200.278 |              200.565 |   0.808 |    0.815 |    0.804 |    0.790 |    0.817 |      117.610 |                0.342 |             19 |        4.900 | NO: TE 0.79<0.800                                                                        |
| class_tercile (NF1.4 INCUMBENT)        | 201.763 |              202.137 |   0.790 |    0.741 |    0.831 |    0.720 |    0.812 |      124.300 |                0.183 |             27 |      100.000 | n/a (null/incumbent)                                                                     |
| ratio_q · sdgain 0                     | 205.352 |              205.318 |   0.855 |    0.802 |    0.872 |    0.830 |    0.875 |      141.930 |                0.808 |              6 |        4.900 | yes                                                                                      |
| ratio_q · sdgain 0.1                   | 205.401 |              205.396 |   0.857 |    0.802 |    0.872 |    0.840 |    0.875 |      144.230 |                0.819 |              6 |        4.900 | yes                                                                                      |
| ratio_q · sdgain 0.2                   | 205.565 |              205.597 |   0.857 |    0.802 |    0.872 |    0.840 |    0.875 |      146.680 |                0.819 |              6 |        4.900 | yes                                                                                      |
| ratio_q_floor · sdgain 0               | 206.216 |              206.304 |   0.884 |    0.802 |    0.885 |    0.850 |    0.929 |      160.900 |                0.839 |              6 |        4.900 | yes                                                                                      |
| ratio_q_floor · sdgain 0.1             | 207.214 |              207.330 |   0.888 |    0.802 |    0.885 |    0.860 |    0.933 |      163.630 |                0.837 |              6 |        4.900 | yes                                                                                      |
| ratio_q_floor · sdgain 0.2             | 208.392 |              208.540 |   0.893 |    0.802 |    0.885 |    0.870 |    0.942 |      166.530 |                0.855 |              6 |        4.900 | yes                                                                                      |
| knn_pos k80 · sdgain 0.2               | 211.687 |              211.876 |   0.825 |    0.827 |    0.784 |    0.840 |    0.844 |      134.450 |                0.307 |             25 |        4.900 | NO: RB 0.7838<0.800                                                                      |
| knn_pos k80 · sdgain 0.1               | 212.608 |              212.788 |   0.817 |    0.827 |    0.784 |    0.830 |    0.830 |      132.190 |                0.297 |             36 |        4.900 | NO: RB 0.7838<0.800                                                                      |
| knn_pos k80 · sdgain 0                 | 213.653 |              213.830 |   0.812 |    0.827 |    0.784 |    0.830 |    0.817 |      129.830 |                0.282 |             25 |        4.900 | NO: RB 0.7838<0.800                                                                      |
| knn_pos k120 · sdgain 0.2              | 218.396 |              218.736 |   0.846 |    0.840 |    0.845 |    0.850 |    0.848 |      146.770 |                0.213 |             35 |        4.900 | yes                                                                                      |
| knn_pos k120 · sdgain 0.1              | 219.276 |              219.606 |   0.843 |    0.840 |    0.845 |    0.850 |    0.839 |      144.530 |                0.208 |             35 |        4.900 | yes                                                                                      |
| knn_pos k120 · sdgain 0                | 220.090 |              220.413 |   0.843 |    0.840 |    0.845 |    0.850 |    0.839 |      142.340 |                0.208 |             35 |        4.900 | yes                                                                                      |
| legacy_cv (pre-NF1.4 null)             | 230.134 |              230.031 |   0.680 |    0.444 |    0.757 |    0.600 |    0.750 |       91.580 |                0.854 |              4 |        0.000 | n/a (null/incumbent)                                                                     |

`eligible` applies the floors of §1. `fallback %` is the share of held-out rookies whose per-player fit was REFUSED and who therefore carried the CLASS-LEVEL band — a config with a high fallback rate at a position is the incumbent in disguise there, however well it covers. `distinct-band frac` = distinct (p10, p90) pairs ÷ rookies (1.0 = fully per-player; the incumbent's 3-buckets-per-position is ~0.18). `worst shared` is the number `audit_interval_quality()` fires on.

## 5. Deflation — CSCV / PBO over held-out draft-class splits

| search                                               |   configs |   PBO |   median logit |   os_gap_pct (Bailey degradation) |   os_gap p90 % |   contender spread % (top quartile) |   splits |
|:-----------------------------------------------------|----------:|------:|---------------:|----------------------------------:|---------------:|------------------------------------:|---------:|
| WHOLE field (every config scored)                    |        80 | 0.371 |          0.324 |                             3.748 |          8.614 |                               1.440 |       35 |
| ELIGIBLE set — the search the selection actually ran |        24 | 0.514 |         -0.080 |                             2.043 |          6.391 |                               0.110 |       35 |

Whole-field spread (best→worst IS80) = 180.811 → 230.134 (27.3%).

**⚠️ THIS FIELD BREAKS THE USUAL PBO HEURISTIC, AND THE FIX IS TO ADD A NUMBER RATHER THAN TO ARGUE WITH THE OLD ONE.** CLAUDE.md's rule is: a high PBO on a TIED field is the NULL; a high PBO with a WIDE spread is genuine overfitting; the spread is the discriminator. NF1.8's field violates that rule's premise — it contains BOTH ~15 near-clones within 0.3% of each other at the top AND known-bad nulls 27% away at the bottom, so the whole-field spread reads WIDE while the actual contest among contenders is a coin flip. Read together, those two numbers would condemn a selection that is merely tied. So two further statistics are reported:

- **`os_gap_pct` — Bailey's PERFORMANCE DEGRADATION.** How much worse the in-sample winner actually SCORES out-of-sample than the out-of-sample best. This is the decision-relevant question: not 'did my pick rank badly?' but 'did picking it COST anything?' A high PBO with a ~0% degradation is a tie **by definition** — the rank flips are between arms that score the same, which is what a rank statistic cannot distinguish from overfitting.
- **`contender_spread_pct` — the spread over the top QUARTILE only**, i.e. among arms that could plausibly be selected. That is the spread the heuristic actually means.
- ⭐ **`flips` — WHICH arms win the in-sample halves, and how often** (table below). The cheapest and most informative of the four: a PBO near 0.5 whose flip mass sits on two arms a fraction of a percent apart is a TIE BETWEEN THEM; the same PBO spread thinly over a dozen unrelated arms is a search that has learnt nothing. PBO compresses that distinction away, and it is exactly the distinction this field turns on.

### Which arms actually win the in-sample halves (ELIGIBLE set)

| config                                 |   IS-half wins |   share |   full-sample IS80 |   Δ vs best % |
|:---------------------------------------|---------------:|--------:|-------------------:|--------------:|
| qreg_sqrt+cqr[pos,add] · sdgain 0      |             12 |   0.343 |            183.539 |         0.000 |
| knn_norm k80 · sdgain 0.2              |             11 |   0.314 |            185.268 |         0.940 |
| qreg_sqrt+cqr[pos,add] · sdgain 0.2    |              4 |   0.114 |            183.846 |         0.170 |
| qreg_sqrt+cqr[pool,add] · sdgain 0.2   |              2 |   0.057 |            183.872 |         0.180 |
| qreg_sqrt+cqr[pos,width] · sdgain 0.2  |              2 |   0.057 |            183.868 |         0.180 |
| qreg_sqrt+cqr[pool,width] · sdgain 0.2 |              2 |   0.057 |            183.869 |         0.180 |
| knn_norm k30 · sdgain 0.2              |              1 |   0.029 |            188.258 |         2.570 |
| qreg_sqrt+cqr[pos,width] · sdgain 0    |              1 |   0.029 |            183.561 |         0.010 |

**Verdict on the deflation: A TWO-ARM TIE ACROSS FAMILIES — the NULL, not overfitting.** Over the ELIGIBLE set (the search the selection actually ran) PBO = 0.5143, which taken alone with the 27% whole-field spread would land in the 'genuine overfitting' quadrant and forbid shipping. The flip distribution shows what is really happening: **12 of 35 in-sample halves are won by `qreg_sqrt+cqr[pos,add] · sdgain 0` and 11 by `knn_norm k80 · sdgain 0.2` — two arms from DIFFERENT candidate families, 0.94% apart on the full sample.** The top-quartile spread is 0.11% and the median out-of-sample performance degradation is 2.043% (p90 6.391%). A rank statistic flipping between two arms that score within a percent of each other cannot separate them, and per CLAUDE.md a TIED field is the NULL: *which* of them wins is noise.

⇒ **What this story establishes is the per-position FLOOR, not the leaderboard's top row.** Both tied arms satisfy every per-position floor, so either is a defensible ship.

⚠️ **The tie is broken on the DEFECT METRIC, not on the primary one and NOT on coverage headroom.** `knn_norm k80 · sdgain 0.2` reverts 4.9% of held-out rookies to the CLASS-LEVEL band (distinct-band fraction 0.6257, worst shared band 9) against the shipped arm's 0.0% / 0.8933 / 3 — i.e. it is partly the very defect NF1.7 exists to remove, and is what `audit_interval_quality()` fires on. Breaking a primary-metric tie on the program's own defect metric is legitimate; breaking it on coverage headroom would not be, because `max_width` wins that (§2). Note the argmin already AGREES with this tiebreak, so nothing was re-picked — it is a confirmation, recorded because it would have mattered had the two been the other way round.

## 6. Selection

**SHIPPED: `qreg_sqrt+cqr[pos,add] · sdgain 0`** — IS80 183.407 · pooled coverage 0.8354 · mean width 130.75 · distinct-band fraction 0.8933 · worst shared band 3 · fallback 0.0%.

The per-position floor costs **+2.42 interval-score points (+1.3%)** against NF1.7's pooled-floor winner (`qreg α0.01 · sdgain 0`, IS80 180.989), and buys every position ≥ its floor: QB 0.7407 → 0.8148, RB 0.777 → 0.8041, TE 0.87 → 0.9, WR 0.8259 → 0.8348. Against the NF1.4 class-level incumbent it is still 9.1% better (201.763 → 183.407) with the distinct-band fraction 0.1826 → 0.8933. The rookie POINT projection is unchanged (max drift 0.0e+00).

### ⭐ What the per-position conformal layer actually bought (the FOIL comparison)

| arm                                             |    IS80 |   cov QB |   cov RB |   cov TE |   cov WR |   mean width |
|:------------------------------------------------|--------:|---------:|---------:|---------:|---------:|-------------:|
| base — no conformal layer                       | 183.451 |    0.778 |    0.804 |    0.900 |    0.835 |      130.620 |
| + conformal, POOLED calibration (the FOIL)      | 183.451 |    0.778 |    0.804 |    0.900 |    0.835 |      130.620 |
| + conformal, PER-POSITION calibration (SHIPPED) | 183.407 |    0.815 |    0.804 |    0.900 |    0.835 |      130.750 |

⭐ **The foil earns its place: the POOLED conformal calibration is a numerical NO-OP, so the gain is attributable to the PER-POSITION conditioning and not to 'conformal' as a word.** On the shipped base, pooled calibration moves the interval score 183.451 → 183.451 and QB coverage 0.7778 → 0.7778 — i.e. nowhere — while the per-position (Mondrian) calibration moves them to 183.407 and 0.8148. The reason is mechanical and worth recording: the pooled conformity quantile is ≈ 0 because the base band's OUT-OF-FOLD coverage over the training classes is already ≈ nominal in aggregate. Only when the conformity scores are read WITHIN a position does the QB-specific shortfall become visible, and only then can it be corrected.

⚠️ **And the honest limit of that:** the per-position adjustments are SMALL (on the served 2026 class the fitted inflation is **+0.82 PPR at QB and exactly 0.0 at RB/TE/WR** — the layer touches ONE position), because each position's in-fold out-of-fold coverage is also near nominal. In-fold recalibration cannot manufacture coverage that is missing only in the NEXT class — which is positive evidence that the QB gap is class-to-class variation rather than a fittable miscalibration, and a reason not to expect any recalibration mechanism to close it fully.

**The QB gain decomposes into two roughly equal halves**, and neither is the whole story: 0.7407 (NF1.7 `qreg`) → 0.7778 from moving to the √ scale, → 0.8148 from the Mondrian calibration. The √ scale is the larger structural change (the rookie outcome is heavy-right-tailed, so linearity is more plausible there); the conformal layer is the part that is TARGETED at the position that was short.

### The tie among ELIGIBLE arms — and why it is not re-picked on coverage headroom

| config                                 |    IS80 |   Δ IS80 vs shipped % |   pooled cov80 |   min per-position headroom |   mean width |
|:---------------------------------------|--------:|----------------------:|---------------:|----------------------------:|-------------:|
| qreg_sqrt+cqr[pos,add] · sdgain 0      | 183.407 |                 0.000 |          0.835 |                       0.004 |      130.750 |
| qreg_sqrt+cqr[pos,width] · sdgain 0    | 183.429 |                 0.010 |          0.835 |                       0.004 |      130.800 |
| qreg_sqrt+cqr[pos,add] · sdgain 0.1    | 183.550 |                 0.080 |          0.857 |                       0.004 |      133.690 |
| qreg_sqrt+cqr[pos,width] · sdgain 0.1  | 183.572 |                 0.090 |          0.857 |                       0.004 |      133.740 |
| qreg_sqrt+cqr[pool,width] · sdgain 0.1 | 183.580 |                 0.090 |          0.854 |                       0.002 |      133.570 |
| qreg_sqrt+cqr[pool,add] · sdgain 0.1   | 183.581 |                 0.090 |          0.854 |                       0.002 |      133.570 |
| qreg_sqrt α0.01 · sdgain 0.1           | 183.582 |                 0.100 |          0.854 |                       0.002 |      133.560 |
| qreg_sqrt+cqr[pos,add] · sdgain 0.2    | 183.658 |                 0.140 |          0.864 |                       0.004 |      136.250 |
| qreg_sqrt+cqr[pos,width] · sdgain 0.2  | 183.680 |                 0.150 |          0.864 |                       0.004 |      136.310 |
| qreg_sqrt+cqr[pool,width] · sdgain 0.2 | 183.681 |                 0.150 |          0.863 |                       0.004 |      136.130 |
| qreg_sqrt α0.01 · sdgain 0.2           | 183.684 |                 0.150 |          0.863 |                       0.004 |      136.130 |
| qreg_sqrt+cqr[pool,add] · sdgain 0.2   | 183.684 |                 0.150 |          0.863 |                       0.004 |      136.130 |
| knn_norm k80 · sdgain 0.2              | 184.913 |                 0.820 |          0.843 |                       0.000 |      122.670 |

The top **13** ELIGIBLE configs sit within 1% of each other on the primary metric. Per CLAUDE.md, when the leaders genuinely tie, *which* of them wins is noise — and §5's flip distribution says the same thing from the other direction.

⭐ **No coverage asymmetry to decline this time:** the shipped arm already carries the most headroom above the per-position floors in the tie (+0.004), so — unlike NF1.7, where the widened arms bought real headroom for free and had to be turned down — there is no temptation to resolve the tie on coverage. Recorded anyway, because the rule has to hold when it costs something: 'Prefer more headroom above the floor' is MONOTONE IN WIDENING — the `max_width` degenerate wins it outright (§2), and it satisfies every per-position floor while being useless. Re-picking a tie on a criterion a degenerate wins is the E2.1-r inversion facing the other way. The floor is a CONSTRAINT; the interval score SELECTS; the argmin breaks the tie because a rule must break it somehow.

(The `min per-position headroom` column is a MIN over positions, so it is bound by whichever position sits closest to its floor — RB here, not QB. That is the honest reading: RB is now the tightest position, and a future class that moves RB is the one to watch.)

### Per-position coverage and WIDTH — the incumbent, NF1.7, and NF1.8 side by side

| arm                                |   cov QB |   cov RB |   cov TE |   cov WR |   slack QB (rows) |   slack RB (rows) |   slack TE (rows) |   slack WR (rows) |   width QB |   width RB |   width TE |   width WR |
|:-----------------------------------|---------:|---------:|---------:|---------:|------------------:|------------------:|------------------:|------------------:|-----------:|-----------:|-----------:|-----------:|
| incumbent (NF1.4 class-level)      |    0.741 |    0.831 |    0.720 |    0.812 |                -5 |                 4 |                -8 |                 2 |    127.900 |    152.300 |     81.300 |    123.700 |
| NF1.7 (pooled floor)               |    0.741 |    0.777 |    0.870 |    0.826 |                -5 |                -4 |                 7 |                 5 |    161.600 |    119.500 |    106.900 |    129.900 |
| NF1.8 SHIPPED (per-position floor) |    0.815 |    0.804 |    0.900 |    0.835 |                 1 |                 0 |                10 |                 7 |    166.000 |    124.300 |    107.400 |    132.700 |

⭐ **The per-position floor is paid for in WIDTH, and mostly at QB — which is the correct answer, not a defect.** QB's mean band goes 161.6 → 166.0 PPR (+2.7%) while its coverage goes 0.7407 → 0.8148. A rookie QB whose modal outcome is 'never takes a snap' genuinely carries more outcome uncertainty than a rookie WR, and a band that says so is more honest than one that reads sharp and misses 26% of the time. Overall the shipped rookie band is 2.0× the average veteran band (130.75 vs 64.2 PPR) — a rookie has no NFL sample, so wider is the honest direction. Veteran coverage is not comparable (a veteran band is a normal approximation off realized game-to-game variance, not an empirical quantile), so only the WIDTH is compared.

## 7. Per-class detail (shipped config)

|   draft_class |   interval_score |
|--------------:|-----------------:|
|      2019.000 |          198.056 |
|      2020.000 |          182.260 |
|      2021.000 |          187.909 |
|      2022.000 |          149.605 |
|      2023.000 |          196.929 |
|      2024.000 |          196.462 |
|      2025.000 |          173.549 |

## 8. Honest limitations

- **The point projection is untouched, so a mis-placed rookie stays mis-placed.** NF1.4's finding was that the rookie point runs COLD and its model bake-off returned a NULL; neither NF1.7 nor NF1.8 re-attacks the level, and neither may be read as having improved it.
- **Per-position coverage is estimated on QB n=81, RB n=148, TE n=100, WR n=224** held-out rookie-seasons. The QB floor in particular is a hypothesis test with ~80 rows behind it (§3): passing it is necessary, not proof of calibration, and a future class can move it.
- 🚨 **THE FLOOR IS CLEARED BY A HANDFUL OF ROOKIE-SEASONS, AND THAT MUST NOT BE READ AS A COMFORTABLE PASS.** The margins in ROWS (see §6) are QB 1, RB 0, TE 10, WR 7 — i.e. RB clears its floor by 0 covered rookie-season(s), and QB's whole 'fix' is 6 more covered rookie-seasons out of 81. A coverage decimal makes that look like a calibration change; it is a small number of outcomes. The floor is a genuine pre-registered constraint and it is genuinely met, but nobody should treat 'QB now covers 0.815' as a stable property of the model.
- **A floor is not a guarantee out of sample.** The floor is met on held-out draft classes 2019–2025; the 2026 class is a genuine extrapolation and the served band carries `confidence = low` for exactly this reason.
- **The conformal arms calibrate IN-FOLD, so they cannot see a NEXT-CLASS gap.** Their fitted per-position adjustments are small precisely because the training folds' out-of-fold coverage is already ≈ nominal at every position — evidence that the QB gap is class-to-class variation rather than a fittable miscalibration, and a reason not to expect any recalibration mechanism to remove it.
- **A rookie's band still cannot see anything NFL-specific** — no camp reports, no depth chart, no preseason. Draft slot, the P1A translation and its parameter sd are the whole information set.
- **No edge claim.** An honest interval is a projection-quality property, not a market edge.

