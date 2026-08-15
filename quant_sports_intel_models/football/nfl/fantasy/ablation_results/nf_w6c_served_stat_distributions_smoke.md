# NF-W6c — the NF-W6b per-stat distributions wired onto the served raw line

**Generated:** 2026-08-15T02:55:45+00:00 · **serve:** 2025 wk 18 (gw 174) · **served rows:** 695 across 6 cells · **train rows:** 17256 · ⚠️ **SMOKE**

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held**. This story WIRES an already-certified result: NF-W6b's six SHIP cells are fitted fresh on full train through the identical pinned code path and emitted in the served 199-level representation. ⛔ No bake-off, no selection, no gate, no re-reading of a settled verdict. The distributions are honest predictive UNCERTAINTY (a quantile bank and its P(0)); they make no edge, ROI or win-rate claim. The points hurdle champion (total fantasy points) is UNTOUCHED — these sit beside it on the raw line.

## Served cells (cell → the NF-W6b winning form → the pinned constructing function)

| cell | form | constructing function | serve rows | P(0) served | q10 | q50 | q90 |
|---|---|---|---|---|---|---|---|
| QB\|passing_tds | knn_quantile | `SD.arm_knn_quantile` | 89 | 0.7109 | 0.0 | 0.416 | 1.135 |
| QB\|passing_yards | lgbm_quantile_tail | `SD.arm_lgbm_quantile_tail` | 89 | 0.3492 | 14.745 | 65.977 | 158.578 |
| QB\|rushing_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` | 89 | 0.6262 | 0.325 | 4.877 | 17.112 |
| RB\|rushing_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` | 126 | 0.4152 | 3.819 | 20.644 | 46.295 |
| TE\|receiving_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` | 115 | 0.4931 | 1.036 | 10.896 | 32.891 |
| WR\|receiving_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` | 187 | 0.4437 | 1.75 | 16.675 | 46.069 |

## Serving smoke — fresh full-train fit vs the NF-W6b record (⛔ NEVER a gate)

A single week against a record that pools 8 half-season folds: these differ by sampling alone. What this table is FOR is the structural break — a dead zero atom, a collapsed band, a cell served by the wrong form — which is what a wiring defect looks like.

| cell | n | CRPS fresh | CRPS record | cov80 fresh | cov80 record | P(0) fresh | P(0) record | realized P(0) |
|---|---|---|---|---|---|---|---|---|
| QB\|passing_tds | 89 | 0.3049 | 0.29747 | 0.9551 | 0.9484 | 0.7109 | 0.6842 | 0.764 |
| QB\|passing_yards | 89 | 38.1152 | 30.69922 | 0.7978 | 0.7938 | 0.3492 | 0.3099 | 0.5506 |
| QB\|rushing_yards | 89 | 5.3854 | 4.6049 | 0.7865 | 0.8268 | 0.6262 | 0.6321 | 0.5955 |
| RB\|rushing_yards | 126 | 14.2914 | 10.78942 | 0.7937 | 0.8328 | 0.4152 | 0.4254 | 0.3571 |
| TE\|receiving_yards | 115 | 7.7273 | 7.45552 | 0.8696 | 0.8874 | 0.4931 | 0.5051 | 0.4696 |
| WR\|receiving_yards | 187 | 11.6023 | 12.16074 | 0.8342 | 0.8578 | 0.4437 | 0.4119 | 0.4439 |

## The served representation (the consumer contract)

```json
{
  "story": "NF-W6c",
  "served_version": "nfl_fantasy_w6c_v1",
  "levels": 199,
  "level_grid": "MC.EVAL_LEVELS (0.005\u20260.995, step 0.005)",
  "level_min": 0.005,
  "level_max": 0.995,
  "monotone": true,
  "zero_atom": "P(0) = the share of grid levels at or below 1e-09 (column `p_zero`)",
  "index_q10": 19,
  "index_q50": 99,
  "index_q90": 179,
  "central_80_interval": "quantiles[index_q10] \u2026 quantiles[index_q90]",
  "cells": {
    "QB|passing_tds": "knn_quantile",
    "QB|passing_yards": "lgbm_quantile_tail",
    "QB|rushing_yards": "lgbm_hurdle_tail",
    "RB|rushing_yards": "lgbm_hurdle_tail",
    "TE|receiving_yards": "lgbm_hurdle_tail",
    "WR|receiving_yards": "lgbm_hurdle_tail"
  },
  "withheld_null_cells": [
    "RB|receiving_yards",
    "RB|rushing_tds"
  ],
  "closed_cells": [
    "QB|rushing_tds",
    "RB|receiving_tds",
    "WR|receiving_tds",
    "TE|receiving_tds"
  ],
  "uncertainty_framing": "honest predictive uncertainty for one player-week stat \u2014 a quantile bank and its P(0). Not a market comparison and not an edge/ROI claim of any kind."
}
```

## Provenance

- matrix: the NF-W6 certified build (`build_matrix_w6`, cache key `57c4cf96bb3c3570`) — the NF-W0a PIT gate ran on load: 175 weeks / 84553 records, 0 rows dropped.
- serving train ⊇ validated fold train, PROVED at this boundary: 84036 serving-train rows vs 83011 in NF-W6b's purged fold train (+1025; purge = 2 weeks). Serving with MORE data than was certified is the safe direction; the containment is measured, not asserted.
- features: the champion set, 29 columns (⛔ no new features — the NF-W6b prereg constraint carries to serving).
- withheld NULL cells (⛔ not served): ['RB|receiving_yards', 'RB|rushing_tds'] — RB receiving_yards is PM Decision B (calendar-bound re-test), RB rushing_tds is PM Decision C (deferred NF-W6b-C, a FRESH atom-aware family).
- CLOSED cells (⛔ re-opening needs a different mechanism): ['QB|rushing_tds', 'RB|receiving_tds', 'WR|receiving_tds', 'TE|receiving_tds'].
- built artifact: `quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_w6c_served_stat_distributions_smoke.parquet` — 695 rows, 730038 bytes, sha256 `11dfc90ad25ed150edf9baf5673ddb739f1a772b5aa919060975780e8f6fdfb0` (gitignored; this manifest is what the registry pins).

## Deploy hold — why nothing publishes

- NF-C6 Phase 2 — no weekly serving path exists (the deployed fantasy surface is the SEASON raw line `projections.json`; there is no weekly endpoint to attach a player-week distribution to)
- NF-G0 promotion review — the ten gates plus a PM decision; NF-W6b promoted nothing and this story stages, it does not promote
- the downstream arbitrary-league re-scoring consumer is a FOLLOW-ON story — the moment a scorer reads these distributions the three-implementations parity tax (fantasy_engine / the browser TS scorer / the Lambda scorer) triggers under the merge-gate parity test

_Runtime: 163.1s · fit 160.1s · served_version `nfl_fantasy_w6c_v1`_