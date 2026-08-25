# Interval-band re-validation — the standing annual check on both per-position coverage floors

**Generated:** 2026-08-25T03:21:53.728777+00:00 · **verdict: ✅ ALL FLOORS MET**

⚠️ **A per-position coverage floor is invisible at serving time** — coverage needs realized outcomes, so no board build, export guard or API check can see it break. That is how the veteran band went five stories at 0.55 coverage of its nominal 0.80. This check is the owner of both floors; a breach is a **RE-SELECTION TRIGGER** (re-run that population's bake-off), never a reason to move the floor.

## The floor in force — a DESIGN table, computable before any band is scored (NF-D22)

Every floor below is a function of the group's held-out row count and a **pre-registered false-reject target** (0.05 — NF1.8's own Tier-2 level), and of nothing else. No observed coverage reaches the derivation: `power_floor(n, nominal, target)` has no coverage argument and a guard asserts its signature never gains one. That is what makes it a floor rather than a number reverse-engineered from something that failed (E2.1-r).

The rule it replaces was a hard point estimate at nominal, whose false-reject rate against a **perfectly calibrated** band is ≈ 0.5 at every sample size this program has — so a breach carried almost no information while its refusals still read as evidence. Both columns are kept below so the change is auditable per run.

| population   | group   |    n |   floor (NF-D22) |   covered rows required |   …at the nominal floor |   relaxation (rows) |   P(reject | truly nominal) |   …under the previous rule |   detectable shortfall | thin?   |
|:-------------|:--------|-----:|-----------------:|------------------------:|------------------------:|--------------------:|----------------------------:|---------------------------:|-----------------------:|:--------|
| rookies      | QB      |   81 |            0.728 |                      59 |                      65 |                   6 |                       0.044 |                      0.456 |                  0.678 | True    |
| rookies      | RB      |  148 |            0.743 |                     110 |                     119 |                   9 |                       0.037 |                      0.500 |                  0.708 | True    |
| rookies      | TE      |  100 |            0.730 |                      73 |                      80 |                   7 |                       0.034 |                      0.441 |                  0.685 | True    |
| rookies      | WR      |  224 |            0.754 |                     169 |                     180 |                  11 |                       0.040 |                      0.513 |                  0.727 | True    |
| veterans     | QB      | 1116 |            0.780 |                     871 |                     893 |                  22 |                       0.049 |                      0.488 |                  0.769 | True    |
| veterans     | RB      | 2018 |            0.785 |                    1585 |                    1615 |                  30 |                       0.049 |                      0.500 |                  0.777 | True    |
| veterans     | TE      | 1801 |            0.785 |                    1413 |                    1441 |                  28 |                       0.049 |                      0.491 |                  0.776 | True    |
| veterans     | WR      | 3164 |            0.788 |                    2494 |                    2532 |                  38 |                       0.048 |                      0.503 |                  0.781 | True    |
| kdst         | DST     |  320 |            0.762 |                     244 |                     256 |                  12 |                       0.043 |                      0.467 |                  0.740 | True    |
| kdst         | K       |  475 |            0.768 |                     365 |                     380 |                  15 |                       0.040 |                      0.473 |                  0.750 | True    |

⚠️ **`detectable shortfall` is the floor's RESOLUTION and is reported with every verdict.** It is the largest true coverage the floor rejects with ≥80% probability. A floor that cannot resolve a defect has not cleared the band, it has failed to look — so a ✅ here means "not shown to be broken at this n", never "shown to be right" (NF1.7 (a)).

⚠️ **Multiplicity is REPORTED AND NOT CORRECTED FOR, deliberately.** Every floor must hold, so the rate at which the whole check falsely fires compounds across groups:

| population   |   floors |   family false-reject (NF-D22) |   …under the previous rule |
|:-------------|---------:|-------------------------------:|---------------------------:|
| rookies      |        4 |                          0.146 |                      0.926 |
| veterans     |        4 |                          0.181 |                      0.935 |
| kdst         |        2 |                          0.081 |                      0.719 |

A Bonferroni split would bound the family figure — by making **every individual floor looser**, which is precisely the adjustment a reader should distrust from a story whose downstream consequence is a previously-refused publish clearing. The per-group pre-registered target binds; this is the caveat beside it, not a lever (NF1.8: report both conventions, let the pre-registered one bind).

### The substantive backstop — MEASURED, not asserted

The objection to a self-attenuating per-group floor is that a band could rest near every thin group's own low floor. It cannot: the POOLED check runs the identical rule over a several-times-larger `n`, so its floor sits closer to nominal than any single group's.

| population   |   pooled_n |   pooled_floor |   loosest_group_floor |   tightest_group_floor | verdict        |
|:-------------|-----------:|---------------:|----------------------:|-----------------------:|:---------------|
| rookies      |        553 |          0.772 |                 0.754 |                  0.728 | BACKSTOP_HOLDS |
| veterans     |       8398 |          0.793 |                 0.788 |                  0.780 | BACKSTOP_HOLDS |

## Pooled per-position coverage — the BINDING check

| population   | position   |   n (held-out) |   coverage | floor (power-derived)                              |   slack (rows) |   floor at nominal (previous rule) |   slack at nominal (rows) |   P(reject | truly nominal) |   …under the previous rule |   detectable shortfall | verdict   |
|:-------------|:-----------|---------------:|-----------:|:---------------------------------------------------|---------------:|-----------------------------------:|--------------------------:|----------------------------:|---------------------------:|-----------------------:|:----------|
| rookies      | QB         |             81 |      0.802 | 0.7284                                             |          6.000 |                              0.800 |                     0.000 |                       0.044 |                      0.456 |                  0.678 | ✅ met    |
| rookies      | RB         |            148 |      0.790 | 0.7432                                             |          7.000 |                              0.800 |                    -2.000 |                       0.037 |                      0.500 |                  0.708 | ✅ met    |
| rookies      | TE         |            100 |      0.900 | 0.73                                               |         17.000 |                              0.800 |                    10.000 |                       0.034 |                      0.441 |                  0.685 | ✅ met    |
| rookies      | WR         |            224 |      0.835 | 0.7545                                             |         18.000 |                              0.800 |                     7.000 |                       0.040 |                      0.513 |                  0.727 | ✅ met    |
| veterans     | FB         |            299 |      0.860 | unconstrained (n below the pre-registered minimum) |        nan     |                            nan     |                   nan     |                     nan     |                    nan     |                nan     | —         |
| veterans     | QB         |           1116 |      0.858 | 0.7805                                             |         86.000 |                              0.800 |                    64.000 |                       0.049 |                      0.488 |                  0.769 | ✅ met    |
| veterans     | RB         |           2018 |      0.886 | 0.7854                                             |        204.000 |                              0.800 |                   174.000 |                       0.049 |                      0.500 |                  0.777 | ✅ met    |
| veterans     | TE         |           1801 |      0.888 | 0.7846                                             |        187.000 |                              0.800 |                   159.000 |                       0.049 |                      0.491 |                  0.776 | ✅ met    |
| veterans     | WR         |           3164 |      0.907 | 0.7882                                             |        375.000 |                              0.800 |                   337.000 |                       0.048 |                      0.503 |                  0.781 | ✅ met    |
| kdst         | DST        |            320 |      0.897 | 0.7625                                             |         43.000 |                              0.800 |                    31.000 |                       0.043 |                      0.467 |                  0.740 | ✅ met    |
| kdst         | K          |            475 |      0.830 | 0.7684                                             |         29.000 |                              0.800 |                    14.000 |                       0.040 |                      0.473 |                  0.750 | ✅ met    |

## Newest cohort — a LEADING INDICATOR, never a gate

One draft class (~80 rookie-seasons) or one target season (~600 veteran-seasons, ~55 per thin position) is far too small to gate a per-position floor: a perfectly-calibrated band fails a hard point-estimate floor at nominal about half the time (NF1.8 §3). A newest cohort that misses badly is a reason to LOOK, because it will move the pooled number next year.

| population   |   cohort |   n |   pooled coverage |   cov QB |   cov RB |   cov TE |   cov WR |   cov FB |   cov DST |   cov K |
|:-------------|---------:|----:|------------------:|---------:|---------:|---------:|---------:|---------:|----------:|--------:|
| rookies      |     2025 |  85 |             0.812 |    0.786 |    0.720 |    0.875 |    0.867 |  nan     |   nan     | nan     |
| veterans     |     2025 | 701 |             0.903 |    0.913 |    0.883 |    0.927 |    0.904 |    0.769 |   nan     | nan     |
| kdst         |     2025 |  76 |             0.868 |  nan     |  nan     |  nan     |  nan     |  nan     |     0.938 |   0.818 |

## What to do on a breach

1. **Do NOT adjust the floor.** A floor that moves until something clears it is not a floor (E2.1-r; NF1.8 §1). ⭐ That prohibition BINDS HARDER after NF-D22, not less: the false-reject target is not a tuning knob, it is NF1.8's own pre-registered level, and a breach under a calibrated rule is now genuine evidence rather than a coin toss. The one honest response is to re-select (or, for K/DST, to widen).
2. Re-run the bake-off for the breaching population — it re-selects under the same pre-registered floor, anchors and deflation:

```
# rookies (NF1.8):
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_rookie_perposition_ablation
# veterans (NF1.9):
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_veteran_interval_ablation --rebuild-panel
```

   ⭐ **EXCEPT for the NF1.6 K/DST population, whose response is different by design.** That band is *reported, not selected* — a deliberately BASE band with no candidate field behind it — so there is no bake-off to re-run. Widen it honestly instead and re-report:

```
# K/DST (NF1.6) — widen, do not re-select:
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_kdst_projection \
  --rebuild-panel --widen 1.15    # or raise kdst_projection.BAND_CLUSTER_Z
```

   Widening is monotone by construction (it inflates the half-widths around 1.0, so it can only ever widen, never sharpen one side — the NF1.7 (d) widen-only invariant).

3. ⚠️ **Rookie RB is the position to watch** — NF1.8 shipped it with **0 rows** of slack above its floor, so it is the one a new class breaks first.

