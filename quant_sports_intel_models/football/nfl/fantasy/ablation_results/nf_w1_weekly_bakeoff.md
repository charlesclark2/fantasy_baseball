# NF-W1 — the lean weekly per-game distributional fantasy projection (§0.5 bake-off)

**Generated:** 2026-08-07T04:08:59+00:00 · **folds:** 8 half-season blocks over weeks (2022H1…2025H2) · **modeled rows:** 84553 (byes excluded by pre-registration) · **label:** `v1.nflverse.stats_player_week` / `ppr`

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects — it is inverted at QB/TE on this frame (conditional median 0.0, NF-W0 §2.3).

**PIT gate (NF-W0a `assert_point_in_time` — first real caller):** 175 weeks / 84553 records checked; 0 rows in 0 weeks dropped fail-closed (the un-provable-window class).

## Per-position verdicts

### QB — **SHIP**

| arm             |   mean_crps |
|:----------------|------------:|
| lgbm_hurdle     |      2.5882 |
| lgbm_quantile   |      2.6249 |
| knn_quantile    |      2.7335 |
| enet_residual   |      3.3011 |
| foil_flat       |      3.7585 |
| foil_matchup    |      3.7820 |
| oracle_marginal |      4.6935 |
| pos_marginal    |      4.6990 |
| permuted_within |      4.7693 |
| zero_width      |      5.1437 |
| max_width       |      5.2306 |
| nihilist_zero   |      6.5404 |

- winner `lgbm_hurdle` vs best foil `foil_flat`: mean lift +1.1703 CRPS, fold wins 8/8 (clause requires 6) · PBO 0.0 · DSR 1.0 · p 0.0 · FDR pass True
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'permuted_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'oracle_marginal_beaten_by_winner': True} · coverage(80) {'winner_coverage_80': 0.8173, 'n_rows': 5485, 'binomial_se': 0.0054, 'blocking_shortfall': False}
- MAE (report-only): {'lgbm_hurdle': 3.4045, 'foil_flat': 4.7258, 'nihilist_zero': 6.5404}

### RB — **SHIP**

| arm             |   mean_crps |
|:----------------|------------:|
| lgbm_hurdle     |      2.5046 |
| lgbm_quantile   |      2.5079 |
| knn_quantile    |      2.6049 |
| enet_residual   |      2.8986 |
| foil_flat       |      3.0697 |
| foil_matchup    |      3.0974 |
| oracle_marginal |      3.8228 |
| pos_marginal    |      3.8262 |
| permuted_within |      3.8653 |
| zero_width      |      4.2348 |
| max_width       |      4.5690 |
| nihilist_zero   |      5.6032 |

- winner `lgbm_hurdle` vs best foil `foil_flat`: mean lift +0.5651 CRPS, fold wins 8/8 (clause requires 6) · PBO 0.0 · DSR 0.9956 · p 0.0 · FDR pass True
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'permuted_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'oracle_marginal_beaten_by_winner': True} · coverage(80) {'winner_coverage_80': 0.8494, 'n_rows': 8591, 'binomial_se': 0.0043, 'blocking_shortfall': False}
- MAE (report-only): {'lgbm_hurdle': 3.3786, 'foil_flat': 3.8803, 'nihilist_zero': 5.6032}

### WR — **SHIP**

| arm             |   mean_crps |
|:----------------|------------:|
| lgbm_hurdle     |      2.6726 |
| lgbm_quantile   |      2.6731 |
| knn_quantile    |      2.7287 |
| enet_residual   |      3.0398 |
| foil_flat       |      3.1460 |
| foil_matchup    |      3.1806 |
| oracle_marginal |      3.7409 |
| pos_marginal    |      3.7490 |
| permuted_within |      3.7634 |
| zero_width      |      4.4549 |
| max_width       |      4.8549 |
| nihilist_zero   |      5.5464 |

- winner `lgbm_hurdle` vs best foil `foil_flat`: mean lift +0.4734 CRPS, fold wins 8/8 (clause requires 6) · PBO 0.0 · DSR 1.0 · p 0.0 · FDR pass True
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'permuted_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'oracle_marginal_beaten_by_winner': True} · coverage(80) {'winner_coverage_80': 0.8523, 'n_rows': 12827, 'binomial_se': 0.0035, 'blocking_shortfall': False}
- MAE (report-only): {'lgbm_hurdle': 3.6103, 'foil_flat': 4.0268, 'nihilist_zero': 5.5464}

### TE — **SHIP**

| arm             |   mean_crps |
|:----------------|------------:|
| lgbm_hurdle     |      1.8197 |
| lgbm_quantile   |      1.8299 |
| knn_quantile    |      1.8655 |
| enet_residual   |      2.1430 |
| foil_flat       |      2.1958 |
| foil_matchup    |      2.2299 |
| oracle_marginal |      2.5539 |
| pos_marginal    |      2.5567 |
| permuted_within |      2.5878 |
| zero_width      |      3.0176 |
| max_width       |      3.2927 |
| nihilist_zero   |      3.4918 |

- winner `lgbm_hurdle` vs best foil `foil_flat`: mean lift +0.3762 CRPS, fold wins 8/8 (clause requires 6) · PBO 0.0 · DSR 0.9888 · p 0.0 · FDR pass True
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'permuted_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'oracle_marginal_beaten_by_winner': True} · coverage(80) {'winner_coverage_80': 0.8827, 'n_rows': 7649, 'binomial_se': 0.0046, 'blocking_shortfall': False}
- MAE (report-only): {'lgbm_hurdle': 2.4429, 'foil_flat': 2.7461, 'nihilist_zero': 3.4918}

## Gate detail

```json
{
  "QB": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_beaten": true,
      "coverage_floor_ok": true
    },
    "ship": true
  },
  "RB": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_beaten": true,
      "coverage_floor_ok": true
    },
    "ship": true
  },
  "WR": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_beaten": true,
      "coverage_floor_ok": true
    },
    "ship": true
  },
  "TE": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_beaten": true,
      "coverage_floor_ok": true
    },
    "ship": true
  }
}
```

## Null-state classification (failing positions)

```json
{}
```

## With-bye sensitivity (analytic)

A bye row's honest projection is the identity point-mass at 0 (CRPS 0 for every arm that emits it, including the nihilist). Including byes therefore multiplies every arm's mean CRPS by the same factor n/(n+n_bye) and CANNOT reorder arms — which is why the scoring population excludes them.

## Reading the result (hand-written; the JSON is the machine record)

**The verdict is SHIP at all four positions, and the win is attributable.** The champion is
`lgbm_hurdle` — a two-part mixture (P(zero) classifier × conditional-on-nonzero GBM quantile bank)
— beating the honest weekly null (`foil_flat`, EB-shrunk season÷games) by **+1.17 CRPS/week at QB
(31%), +0.57 at RB (18%), +0.47 at WR (15%), +0.38 at TE (17%)**, 8/8 folds everywhere, PBO 0.0,
DSR 0.989–1.0, p≈0, all four positions surviving BH-FDR together.

Five honest notes:

1. **RB/WR winner is a TIE between two real arms, not a fragile pick** (the NF1.8 flip reading):
   `lgbm_hurdle` vs `lgbm_quantile` sit 0.13% / 0.02% apart with flip mass 69/31 and 53/47. The
   ship pick is `lgbm_hurdle` uniformly — it wins QB/TE outright (flip share 1.0 both) and ties
   the GBM-quantile arm elsewhere; one champion class across the board beats four per-position
   champions on serving complexity, and nothing turns on the choice.
2. **The matchup tilt is STILL a null on top of season÷games** — `foil_matchup` loses to
   `foil_flat` at all four positions, reproducing the 2026-07-27 `run_nf1.py` weekly-bakeoff null
   under CRPS + deflation. The weekly lift does NOT come from DVP; it comes from conditioning on
   recent usage/snaps/availability history. (The DVP index is still IN the champion's feature set;
   the GBM is free to use or ignore it.)
3. **The marginal "oracle" being beaten is legitimate, not an inversion**: `oracle_marginal` is
   the peeking ceiling of MARGINAL information only (it knows the test block's per-position
   distribution, not the conditional), and it lands within noise of train climatology
   (`pos_marginal`) at every position — conditioning is the whole game here (NF1.9 (f) capacity
   note). The degenerates (`nihilist_zero`, `zero_width`, `max_width`) and the permutation all
   lose everywhere, as pre-registered.
4. **Coverage runs ABOVE the 0.80 floor (0.817–0.883)** — the intervals are mildly conservative.
   The floor-not-target discipline means this is recorded, not tuned away post-hoc; sharpening
   (a Mondrian/conformal layer, the NF1.8 winner's shape) is NF-W2-scope follow-up work.
5. **What SHIP means operationally: nothing auto-deploys.** This story delivers the validated
   champion SPEC + machinery (assembly with the PIT gate, the arm, the component head, ROS
   aggregation). Wiring a weekly build/serving surface is NF-C6 Phase 2 / NF-W2+ scope, and any
   registry staging goes through the NF-G0 governance CLI as an operator step.

**Follow-ups carded from this result:** weekly K/DST (parked, per the story's slicing) · the
conformal sharpening pass · NGS/pfr_advanced/injury_report families (allowed, deferred here —
each enters as a pre-registered matched pair against this champion, the NF-D10 discipline) ·
the NF-W2..W8 component system must BEAT this model as its direct foil on held-out weeks.
