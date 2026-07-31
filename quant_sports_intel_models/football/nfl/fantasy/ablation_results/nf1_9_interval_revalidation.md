# Interval-band re-validation — the standing annual check on both per-position coverage floors

**Generated:** 2026-07-31T20:52:35.074991+00:00 · **verdict: ✅ ALL FLOORS MET**

⚠️ **A per-position coverage floor is invisible at serving time** — coverage needs realized outcomes, so no board build, export guard or API check can see it break. That is how the veteran band went five stories at 0.55 coverage of its nominal 0.80. This check is the owner of both floors; a breach is a **RE-SELECTION TRIGGER** (re-run that population's bake-off), never a reason to move the floor.

## Pooled per-position coverage — the BINDING check

| population   | position   |   n (held-out) |   coverage | floor                                              |   slack (rows) | verdict   |
|:-------------|:-----------|---------------:|-----------:|:---------------------------------------------------|---------------:|:----------|
| rookies      | QB         |             81 |      0.815 | 0.8                                                |          1.000 | ✅ met    |
| rookies      | RB         |            148 |      0.804 | 0.8                                                |          0.000 | ✅ met    |
| rookies      | TE         |            100 |      0.900 | 0.8                                                |         10.000 | ✅ met    |
| rookies      | WR         |            224 |      0.835 | 0.8                                                |          7.000 | ✅ met    |
| veterans     | FB         |            299 |      0.860 | unconstrained (n below the pre-registered minimum) |        nan     | —         |
| veterans     | QB         |           1116 |      0.858 | 0.8                                                |         64.000 | ✅ met    |
| veterans     | RB         |           2018 |      0.886 | 0.8                                                |        174.000 | ✅ met    |
| veterans     | TE         |           1801 |      0.888 | 0.8                                                |        159.000 | ✅ met    |
| veterans     | WR         |           3164 |      0.907 | 0.8                                                |        337.000 | ✅ met    |
| kdst         | DST        |            320 |      0.897 | 0.8                                                |         31.000 | ✅ met    |
| kdst         | K          |            475 |      0.830 | 0.8                                                |         14.000 | ✅ met    |

## Newest cohort — a LEADING INDICATOR, never a gate

One draft class (~80 rookie-seasons) or one target season (~600 veteran-seasons, ~55 per thin position) is far too small to gate a per-position floor: a perfectly-calibrated band fails a hard point-estimate floor at nominal about half the time (NF1.8 §3). A newest cohort that misses badly is a reason to LOOK, because it will move the pooled number next year.

| population   |   cohort |   n |   pooled coverage |   cov QB |   cov RB |   cov TE |   cov WR |   cov FB |   cov DST |   cov K |
|:-------------|---------:|----:|------------------:|---------:|---------:|---------:|---------:|---------:|----------:|--------:|
| rookies      |     2025 |  85 |             0.824 |    0.786 |    0.760 |    0.875 |    0.867 |  nan     |   nan     | nan     |
| veterans     |     2025 | 701 |             0.903 |    0.913 |    0.883 |    0.927 |    0.904 |    0.769 |   nan     | nan     |
| kdst         |     2025 |  76 |             0.868 |  nan     |  nan     |  nan     |  nan     |  nan     |     0.938 |   0.818 |

## What to do on a breach

1. **Do NOT adjust the floor.** A floor that moves until something clears it is not a floor (E2.1-r; NF1.8 §1).
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

