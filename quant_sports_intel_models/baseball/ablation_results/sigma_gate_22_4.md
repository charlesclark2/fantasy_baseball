# Story 22.4 — σ-gate backtest: uncertainty-aware selection & sizing

**Date:** 2026-06-16  ·  **Surface:** 3927 games, model_version IN ['v0', 'v1', 'v2', 'v3', 'v4', 'prod']  ·  **Period:** 2026-03-26 – 2026-06-12

**Calibration prerequisite (9.8):** total_runs cov80 0.808 ✓, run_diff cov80 0.776 ✓, home_win ECE 0.040 ✓ (A2.9 identity). All cleared.

**Preliminary thresholds (pre-backtest):** abstain<0.25, low<0.75, medium<1.5, high≥1.5

## TOTALS

**Ungated baseline (threshold=0):** n=3144, hit_rate=0.5232, flat_roi=0.047, avg_|edge|=0.0866

| threshold | n | pct_kept | hit_rate | flat_roi | σ-kelly_roi | avg_|edge| |
|-----------|---|----------|----------|----------|-------------|------------|
| 0.00 | 3144 | 100.0% | 0.5232 | +0.0470 | -0.0310 | 0.0866 |
| 0.10 | 1302 | 41.4% | 0.5046 | +0.0120 | -0.0519 | 0.1566 |
| 0.15 | 841 | 26.7% | 0.5065 | +0.0166 | -0.0561 | 0.1927 |
| 0.20 | 634 | 20.2% | 0.4874 | -0.0212 | -0.0754 | 0.2166 |
| 0.25 | 508 | 16.2% | 0.4882 | -0.0203 | -0.0755 | 0.2342 |
| 0.30 | 445 | 14.2% | 0.4876 | -0.0230 | -0.0766 | 0.2442 |
| 0.40 | 369 | 11.7% | 0.4770 | -0.0439 | -0.0900 | 0.2592 |
| 0.50 | 313 | 10.0% | 0.4824 | -0.0348 | -0.0855 | 0.2620 |
| 0.75 | 176 | 5.6% | 0.4716 | -0.0555 | -0.1099 | 0.1940 |
| 1.00 | 157 | 5.0% | 0.4713 | -0.0549 | -0.1128 | 0.1988 |
| 1.50 | 138 | 4.4% | 0.4783 | -0.0410 | -0.1077 | 0.1988 |
| 2.00 | 124 | 3.9% | 0.4677 | -0.0616 | -0.1304 | 0.2021 |

**Bootstrap verdict at threshold=0.25:** DOES NOT LIFT hit-rate: Δ=-0.0350, p(gated≥ungated)=0.07, 95% CI [-0.0833,+0.0122] — ✗ not significant

**Dropped bets sample at threshold=0.25** (top-20 by |edge|, no silent truncation):

| game_pk | date | model | edge | ets | ci_width | correct |
|---------|------|-------|------|-----|----------|---------|
| 824434 | 2026-05-26 | v2 | +0.1867 | 0.248 | 0.751 | 1 |
| 823372 | 2026-06-10 | v4 | +0.1857 | 0.238 | 0.781 | 1 |
| 823290 | 2026-06-09 | v4 | +0.1855 | 0.245 | 0.756 | 1 |
| 822897 | 2026-05-27 | v2 | +0.1854 | 0.247 | 0.751 | 0 |
| 824517 | 2026-05-14 | prod | +0.1825 | 0.243 | 0.750 | 1 |
| 823218 | 2026-06-08 | prod | +0.1821 | 0.244 | 0.746 | 0 |
| 823953 | 2026-05-11 | v0 | +0.1820 | 0.239 | 0.760 | 1 |
| 822808 | 2026-06-06 | prod | +0.1801 | 0.240 | 0.750 | 1 |
| 823781 | 2026-06-01 | v2 | +0.1780 | 0.236 | 0.754 | 1 |
| 823621 | 2026-05-31 | prod | +0.1765 | 0.235 | 0.750 | 1 |
| 824675 | 2026-06-02 | prod | +0.1759 | 0.231 | 0.760 | 0 |
| 823713 | 2026-05-01 | v2 | +0.1756 | 0.236 | 0.743 | 1 |
| 822731 | 2026-05-30 | v2 | +0.1752 | 0.235 | 0.744 | 1 |
| 822731 | 2026-05-30 | v2 | +0.1749 | 0.232 | 0.753 | 1 |
| 823622 | 2026-05-30 | v2 | +0.1739 | 0.229 | 0.760 | 0 |
| 824533 | 2026-04-12 | v2 | +0.1730 | 0.228 | 0.758 | 1 |
| 823290 | 2026-06-09 | v4 | +0.1729 | 0.226 | 0.764 | 1 |
| 824193 | 2026-05-16 | v2 | +0.1721 | 0.228 | 0.756 | 0 |
| 822904 | 2026-05-08 | v2 | +0.1715 | 0.227 | 0.756 | 0 |
| 822730 | 2026-06-01 | v2 | +0.1712 | 0.227 | 0.755 | 1 |

## H2H

**Ungated baseline (threshold=0):** n=1972, hit_rate=0.4878, flat_roi=-0.0577, avg_|edge|=0.0444

| threshold | n | pct_kept | hit_rate | flat_roi | σ-kelly_roi | avg_|edge| |
|-----------|---|----------|----------|----------|-------------|------------|
| 0.00 | 1972 | 100.0% | 0.4878 | -0.0577 | -0.1666 | 0.0444 |
| 0.10 | 1657 | 84.0% | 0.4828 | -0.0651 | -0.1683 | 0.0518 |
| 0.15 | 1502 | 76.2% | 0.4760 | -0.0734 | -0.1725 | 0.0557 |
| 0.20 | 1350 | 68.5% | 0.4637 | -0.0936 | -0.1830 | 0.0598 |
| 0.25 | 1219 | 61.8% | 0.4569 | -0.1028 | -0.1883 | 0.0633 |
| 0.30 | 1061 | 53.8% | 0.4590 | -0.0931 | -0.1887 | 0.0682 |
| 0.40 | 834 | 42.3% | 0.4412 | -0.1204 | -0.2110 | 0.0764 |
| 0.50 | 666 | 33.8% | 0.4294 | -0.1417 | -0.2300 | 0.0842 |
| 0.75 | 380 | 19.3% | 0.3842 | -0.2210 | -0.3089 | 0.1012 |
| 1.00 | 206 | 10.4% | 0.3350 | -0.2771 | -0.3883 | 0.1217 |
| 1.50 | 57 | 2.9% | 0.2105 | -0.5302 | -0.6212 | 0.1596 |
| 2.00 | 18 | 0.9% | 0.0556 | -0.9238 | -0.8727 | 0.1725 |

**Bootstrap verdict at threshold=0.25:** DOES NOT LIFT hit-rate: Δ=-0.0309, p(gated≥ungated)=0.05, 95% CI [-0.0663,+0.0064] — ✗ not significant

**Dropped bets sample at threshold=0.25** (top-20 by |edge|, no silent truncation):

| game_pk | date | model | edge | ets | ci_width | correct |
|---------|------|-------|------|-----|----------|---------|
| 823890 | 2026-03-30 | v1 | +0.0873 | 0.244 | 0.358 | 0 |
| 823890 | 2026-03-30 | v0 | +0.0866 | 0.243 | 0.356 | 0 |
| 822969 | 2026-06-09 | v4 | +0.0520 | 0.158 | 0.330 | 1 |
| 824999 | 2026-06-09 | prod | +0.0470 | 0.216 | 0.218 | 1 |
| 823052 | 2026-06-02 | prod | +0.0439 | 0.212 | 0.207 | 0 |
| 823454 | 2026-06-06 | prod | +0.0437 | 0.213 | 0.205 | 0 |
| 822891 | 2026-06-06 | prod | +0.0392 | 0.202 | 0.194 | 0 |
| 823807 | 2026-03-31 | v0 | +0.0374 | 0.188 | 0.199 | 1 |
| 823807 | 2026-03-31 | v1 | +0.0363 | 0.185 | 0.196 | 1 |
| 823862 | 2026-05-23 | v1 | +0.0359 | 0.236 | 0.152 | 1 |
| 824511 | 2026-06-02 | prod | +0.0346 | 0.225 | 0.154 | 1 |
| 823226 | 2026-05-06 | v1 | +0.0346 | 0.208 | 0.167 | 0 |
| 823567 | 2026-04-07 | v0 | +0.0319 | 0.138 | 0.231 | 1 |
| 823567 | 2026-04-07 | v1 | +0.0318 | 0.138 | 0.230 | 1 |
| 823377 | 2026-05-29 | v2 | +0.0314 | 0.243 | 0.130 | 1 |
| 823862 | 2026-05-23 | v2 | +0.0314 | 0.207 | 0.152 | 1 |
| 823051 | 2026-06-03 | prod | +0.0311 | 0.167 | 0.186 | 1 |
| 823377 | 2026-05-29 | v2 | +0.0309 | 0.239 | 0.129 | 1 |
| 824520 | 2026-05-10 | prod | +0.0299 | 0.250 | 0.120 | 1 |
| 823957 | 2026-05-08 | v1 | +0.0292 | 0.151 | 0.193 | 1 |

## σ-Kelly sizing verdict

σ-scaled Kelly (`base_kelly / (1 + 3.0 * ci_width)`) is uniformly worse than flat Kelly at every threshold for both
targets. The penalty amplifies losses: wide-CI bets (which σ-Kelly down-stakes) include many winning bets, so the
net effect is reducing stakes on winners while keeping stakes roughly flat on losers.

## Honest verdict — REJECT σ-gating for both targets

**σ-selection:** REJECT. No threshold in [0.10, 2.00] beats the ungated baseline on hit-rate or ROI. The bootstrap
confirms: p(gated ≥ ungated) = 0.07 (totals) and 0.05 (H2H) — gating is more likely to *hurt* than help.

**σ-Kelly sizing:** REJECT. Uniformly worse than flat across all thresholds and both targets.

**Root cause:** `edge_to_sigma = |edge| / ci_width` is *inversely* correlated with correctness. The NegBin scale
parameter grows with prediction magnitude, so high-edge totals predictions carry wide CIs. The gate drops the
model's highest-edge (and often best) bets. CI width measures prediction spread, not model reliability — the
posterior is correctly calibrated in coverage (9.8 ✓), but that does not make CI width a useful discriminator
for which individual bets will win.

**Gate config:** `uncertainty_below_threshold.enabled` stays `false`. Do not set a threshold.

**Future work:** If uncertainty-aware selection is retried, the discriminating signal should be
*relative* CI width (normalized by a baseline for that line range) or a direct posterior-overlap test
(does the model's 80% PI cover the market line?), not the raw CI width.
