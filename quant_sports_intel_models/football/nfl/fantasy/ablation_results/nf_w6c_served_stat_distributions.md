# NF-W6c — the NF-W6b per-stat distributions wired onto the served raw line

**Generated:** 2026-08-15T18:17:26+00:00 · **serve:** 2025 wk 18 (gw 174) · **served rows:** 821 across 7 cells · **train rows:** 84036

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held**. This story WIRES already-certified results: NF-W6b's six SHIP cells plus NF-W6b-C's RB rushing_tds successor are fitted fresh on full train through the identical pinned code path and emitted in the served 199-level representation. ⛔ No bake-off, no selection, no gate, no re-reading of a settled verdict. The distributions are honest predictive UNCERTAINTY (a quantile bank and its P(0)); they make no edge, ROI or win-rate claim. The points hurdle champion (total fantasy points) is UNTOUCHED — these sit beside it on the raw line.

## Served cells (cell → the certifying record's winning form → the pinned constructing function)

| cell | form | constructing function | serve rows | P(0) served | q10 | q50 | q90 |
|---|---|---|---|---|---|---|---|
| QB\|passing_tds | knn_quantile | `SD.arm_knn_quantile` | 89 | 0.6992 | 0.0 | 0.399 | 1.171 |
| QB\|passing_yards | lgbm_quantile_tail | `SD.arm_lgbm_quantile_tail` | 89 | 0.3295 | 14.423 | 66.857 | 145.778 |
| QB\|rushing_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` | 89 | 0.6602 | 0.047 | 4.098 | 16.618 |
| RB\|rushing_tds | knn_quantile | `SD.arm_knn_quantile` | 126 | 0.8591 | 0.0 | 0.0 | 0.486 |
| RB\|rushing_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` | 126 | 0.4218 | 2.039 | 19.06 | 49.921 |
| TE\|receiving_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` | 115 | 0.5219 | 0.487 | 9.41 | 33.659 |
| WR\|receiving_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` | 187 | 0.4418 | 0.727 | 16.093 | 50.238 |

## Serving smoke — fresh full-train fit vs the certifying records (⛔ NEVER a gate)

A single week against records that each pool 8 half-season folds (NF-W6b for six cells, NF-W6b-C for RB|rushing_tds): these differ by sampling alone. What this table is FOR is the structural break — a dead zero atom, a collapsed band, a cell served by the wrong form — which is what a wiring defect looks like.

| cell | n | CRPS fresh | CRPS record | cov80 fresh | cov80 record | P(0) fresh | P(0) record | realized P(0) |
|---|---|---|---|---|---|---|---|---|
| QB\|passing_tds | 89 | 0.3041 | 0.29747 | 0.9551 | 0.9484 | 0.6992 | 0.6842 | 0.764 |
| QB\|passing_yards | 89 | 37.8863 | 30.69922 | 0.764 | 0.7938 | 0.3295 | 0.3099 | 0.5506 |
| QB\|rushing_yards | 89 | 5.2637 | 4.6049 | 0.7978 | 0.8268 | 0.6602 | 0.6321 | 0.5955 |
| RB\|rushing_tds | 126 | 0.1181 | 0.13023 | 0.9444 | 0.9537 | 0.8591 | 0.8719 | 0.9048 |
| RB\|rushing_yards | 126 | 13.7019 | 10.78942 | 0.8254 | 0.8328 | 0.4218 | 0.4254 | 0.3571 |
| TE\|receiving_yards | 115 | 7.3094 | 7.45552 | 0.887 | 0.8874 | 0.5219 | 0.5051 | 0.4696 |
| WR\|receiving_yards | 187 | 11.7885 | 12.16074 | 0.861 | 0.8578 | 0.4418 | 0.4119 | 0.4439 |

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
    "WR|receiving_yards": "lgbm_hurdle_tail",
    "RB|rushing_tds": "knn_quantile"
  },
  "withheld_null_cells": [
    "RB|receiving_yards"
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
- withheld NULL cell (⛔ not served): ['RB|receiving_yards'] — RB receiving_yards is PM Decision B (calendar-bound re-test on the same harness once the 2026 folds exist). RB rushing_tds (PM Decision C) is no longer withheld: NF-W6b-C's fresh atom-aware family (a separate §0.5 record) shipped it, and NF-W6c-wire moved it into the served set under NF-G0 governance.
- CLOSED cells (⛔ re-opening needs a different mechanism): ['QB|rushing_tds', 'RB|receiving_tds', 'WR|receiving_tds', 'TE|receiving_tds'].
- built artifact: `quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_w6c_served_stat_distributions.parquet` — 821 rows, 723722 bytes, sha256 `c2ca084b9999edac342eb352cff98dc8735245f4206a4d2f22624de0af08cda5` (gitignored; this manifest is what the registry pins).

## Deploy hold — why nothing publishes

- NF-C6 Phase 2 — no weekly serving path exists (the deployed fantasy surface is the SEASON raw line `projections.json`; there is no weekly endpoint to attach a player-week distribution to)
- NF-G0 promotion review — the ten gates plus a PM decision; NF-W6b promoted nothing and this story stages, it does not promote
- the downstream arbitrary-league re-scoring consumer is a FOLLOW-ON story — the moment a scorer reads these distributions the three-implementations parity tax (fantasy_engine / the browser TS scorer / the Lambda scorer) triggers under the merge-gate parity test

_Runtime: 172.4s · fit 170.0s · served_version `nfl_fantasy_w6c_v1`_