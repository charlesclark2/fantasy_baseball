# NF-W8-0 — the cross-position comparability layer (LEVEL_GAP_DETECTED_UNREPAIRED)

Generated 2026-08-19T22:54:26.143702+00:00 · gate league **full_ppr** · 8 folds · target `league_fantasy_points`

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing and publishes nothing.

## §1 The QB consumption decision (Option B, registered forward)

- decision: **OPTION_B_RECALIBRATED**
- rationale: dsr_ok is a SHIPPING gate, not a CONSUMPTION bar for a projection consumer: the fantasy vertical gates consumption on calibration + the product metric, not betting-posture deflation. NF-W7f's `zm_floor` is the only QB construction on record clearing the PIT bar (0.0281, 8/8 folds vs the incumbent's 0/8) AND the best-scoring (+0.0184 CRPS vs the matched foil, p=0.0121, PBO 0.0; +0.0189 vs direct-points); its dsr_ok refusal deflated a search whose flip mass was 100% on the winner, and every remedy is measured closed (NF-W7j DSR_UNREACHABLE — field size is no lever; NF-W7k MC_LEVER_EXHAUSTED — a 325x draw-noise shortfall). Every alternative consumption is strictly worse on BOTH axes.
- ⚠️ caveat: WEAKER FOOTING, carried by every consumer of QB rows: QB is the only position not through the full certification gate WR (DSR 0.9852) and TE (0.9822) cleared and RB was registered against. The un-certified residual is deflation-adjusted ARM SELECTION within the zm family — not calibration (a per-fold measurement) and not the sign of the improvement. QB rows are 'calibrated + best-on-record, consumed under Option B; not certification-equivalent'.
- 🚩 second reader: OPEN — unsigned until a governance second reader signs the prereg §1

## Verdict

- state: **LEVEL_GAP_DETECTED_UNREPAIRED**
- the level gap is real and no registered arm is admissible (winner=level_affine, failing=['reduces_gap', 'swap_clause', 'dsr_ok'], unevaluable=[]) — the hybrid is NOT cross-rankable as-is; the input ships as `identity` with the per-position gap DISCLOSED (`level_gap_disclosure`) and flagged not-cross-rankable
- shipped arm: `identity`

## Reproduction pins (the consumed generators, by identity)

| pos | generator | reproduces | folds | max gap |
|---|---|---|---|---|
| QB | `qb_zm_floor` | True | 8 | 0.0 |
| RB | `rb_direct` | True | 8 | 0.0 |
| WR | `wr_mixall` | True | 8 | 0.0 |
| TE | `te_single_copula` | True | 8 | 0.0 |

## Family A — the pairwise level-gap tests

- gap_detected: **True** (BH q=0.1, 6 evaluable pairs, max pairwise MDE 0.3277 PPR at 80% power)

| pair | gap (PPR) | se | p (2-sided) | BH rejected | MDE |
|---|---|---|---|---|---|
| QB|RB | -0.2163 | 0.117 | 0.106867 | False | 0.3277 |
| QB|WR | -0.3585 | 0.0721 | 0.001613 | True | 0.202 |
| QB|TE | -0.3186 | 0.0674 | 0.002145 | True | 0.1889 |
| RB|WR | -0.1422 | 0.0906 | 0.16038 | False | 0.2538 |
| RB|TE | -0.1023 | 0.0618 | 0.141943 | False | 0.1732 |
| WR|TE | 0.0399 | 0.0656 | 0.562177 | False | 0.1839 |

## Identity bias by position (pooled Σerr/Σn)

| pos | bias (PPR) | n rows | calibration slope (last fold) |
|---|---|---|---|
| QB | -0.4699 | 5485 | 0.965 |
| RB | -0.2537 | 8591 | 1.1197 |
| WR | -0.1089 | 12827 | 0.9907 |
| TE | -0.151 | 7649 | 1.0746 |

## Family B — the recalibration contest

- evaluable folds: 7 (2022H2, 2023H1, 2023H2, 2024H1, 2024H2, 2025H1, 2025H2)
- winner: `level_affine` · p(reduces gap) 0.051196924504800734 · PBO 0.0857 · DSR 0.9138
- affine eligibility: {'eligible': True, 'violations': []}
- winner clauses: {'reduces_gap': False, 'beats_permuted': True, 'no_rmse_harm': True, 'degenerates_lose': True, 'pbo_ok': True, 'dsr_ok': False, 'swap_clause': False, 'banks_untouched': True}

| arm | pooled cross-position bias range (PPR) |
|---|---|
| `identity` | 0.4888 |
| `level_add` | 0.403 |
| `level_affine` | 0.3884 |
| `zero_point` | 2.9892 |
| `position_mean_point` | 0.511 |
| `level_add_permuted` | 0.5665 |
| `level_add_oracle` | 0.0 |

## §6 Generator-swap verification

- state: **FAIL** (3 active positions, arm `level_affine`)
  - QB: {'activity': {'active': True, 'pooled_shift': -0.3707, 'se': 0.0217, 'threshold': 0.0434, 'n_folds': 7}, 'mean_abs_before': 0.3707, 'mean_abs_after': 0.0738, 'p_one_sided': 2.2157511503362315e-07, 'passes': True}
  - RB: {'activity': {'active': False, 'pooled_shift': -0.0354, 'se': 0.0183, 'threshold': 0.0366, 'n_folds': 7}}
  - WR: {'activity': {'active': True, 'pooled_shift': -0.0368, 'se': 0.0106, 'threshold': 0.0212, 'n_folds': 7}, 'mean_abs_before': 0.0368, 'mean_abs_after': 0.0332, 'p_one_sided': 0.42310167475402816, 'passes': False}
  - TE: {'activity': {'active': True, 'pooled_shift': 0.0946, 'se': 0.0126, 'threshold': 0.0252, 'n_folds': 7}, 'mean_abs_before': 0.0946, 'mean_abs_after': 0.0448, 'p_one_sided': 0.06011228106145872, 'passes': False}
- board decomposition QB (fold 2025H2): level shift -0.4704 PPR · total move {'own_mean_abs_rank_move': 15.321, 'other_mean_abs_rank_move': 1.536} · ordering-only {'own_mean_abs_rank_move': 15.321, 'other_mean_abs_rank_move': 1.536}
- board decomposition RB (fold 2025H2): level shift -0.0826 PPR · total move {'own_mean_abs_rank_move': 27.244, 'other_mean_abs_rank_move': 7.915} · ordering-only {'own_mean_abs_rank_move': 25.923, 'other_mean_abs_rank_move': 7.633}
- board decomposition WR (fold 2025H2): level shift -0.041 PPR · total move {'own_mean_abs_rank_move': 12.776, 'other_mean_abs_rank_move': 3.264} · ordering-only {'own_mean_abs_rank_move': 12.77, 'other_mean_abs_rank_move': 3.292}
- board decomposition TE (fold 2025H2): level shift 0.0443 PPR · total move {'own_mean_abs_rank_move': 12.112, 'other_mean_abs_rank_move': 1.94} · ordering-only {'own_mean_abs_rank_move': 12.112, 'other_mean_abs_rank_move': 1.94}

## Null classification

- {'state': 'CONSTRAINT_REFUSED', 'binding_half': 'anchor', 'failing_anchor_checks': ['swap_clause'], 'failing_statistical_checks': ['reduces_gap', 'dsr_ok'], 'retest_trigger': None, 'reason': 'the refusal rests on anchor/constraint clauses — more data makes the refusal MORE certain, never less (NF-D18); no data trigger is published', 'instrument_verdict': {'state': 'POWER_LIMITED', 'reason': '`cross_position_bias_range`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it — DSR alone needs 9 folds against 7 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.', 'retest_trigger': '+2 folds for the DSR gate — field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)'}}

## The input

- dir: `/Users/charlesclark/Documents/machine_learning/baseball_betting/nf-w80/quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_w8_0_input` · shipped arm `identity` · banks_untouched True
- schema: ['season', 'week', 'gw', 'gsis_id', 'position', 'generator', 'point_raw', 'point_recal', 'recal_arm', 'point_vs_bank_offset', 'p10', 'p50', 'p90', 'replacement_points', 'vor', 'overall_rank', 'positional_rank', 'level_gap_disclosure', 'qb_option_b', 'calibration_warning']

## Promote blockers

- NF-W8-0 is DEPLOY-HELD: the cross-position input is an NF-G0 challenger consumed by nothing until governance promotes it
- every QB row carries the §1 Option-B caveat: calibrated + best-on-record, consumed under a registered-forward PM decision — NOT certification-equivalent to WR/TE/RB, and the ship bar was never relaxed (E2.1-r)
- NF-W7c's promote blockers are INHERITED in full: an assembled row whose source is not `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices (`calibration_warning`), and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap
- K/DST are OUT OF SCOPE — the input is declared 4-position; the NF-W7 K/DST weekly models join in a successor's registration, never by silent extension
- the layer corrects LEVEL (and uniform affine scale) only; a rank-dependent generator artifact is a successor's fresh registration
