# NF-W8-0b — the tail-completed cross-position ranking point (TAIL_COMPLETED_GAP_PERSISTS)

Generated 2026-08-20T01:42:29.748774+00:00 · gate league **full_ppr** · 8 folds · target `league_fantasy_points`

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing and publishes nothing.

## Verdict

- state: **TAIL_COMPLETED_GAP_PERSISTS**
- **`cross_rankable`: False** (the deterministic reading — the tail-completed point closes the gap with NO recalibration layer)
- `cross_rankable_with_layer`: False (the weaker, predecessor-inherited reading)
- the cross-position level gap SURVIVES the tail completion and no registered arm is admissible — the hybrid is NOT cross-rankable; the input ships as `identity` on the tail-completed point with the residual per-position gap DISCLOSED (`level_gap_disclosure`)
- predecessor-state mapping: `LEVEL_GAP_DETECTED_UNREPAIRED` · shipped arm `identity`

## The transform (deterministic — no fitting)

- form: `exponential_mean_excess_symmetric` · anchors {'inner_hi': 0.975, 'outer_hi': 0.995, 'inner_lo': 0.025, 'outer_lo': 0.005}
- covered mass 0.995 + 0.0025 per side restored

| pos | grid-mean bias (PPR) | tail-completed bias (PPR) | mean completion Δ (PPR) |
|---|---|---|---|
| QB | -0.4695 | -0.4237 | 0.0462 |
| RB | -0.2532 | -0.2206 | 0.0331 |
| WR | -0.111 | -0.0591 | 0.0498 |
| TE | -0.1509 | -0.1127 | 0.0383 |

## Reproduction pins (the consumed generators, by identity)

| pos | generator | reproduces | folds | max gap |
|---|---|---|---|---|
| QB | `qb_zm_floor` | True | 8 | 0.0 |
| RB | `rb_direct` | True | 8 | 0.0 |
| WR | `wr_mixall` | True | 8 | 0.0 |
| TE | `te_single_copula` | True | 8 | 0.0 |

## Family A — the pairwise level-gap tests ON THE TAIL-COMPLETED POINT

- gap_detected: **True** (BH q=0.1, 6 evaluable pairs, max pairwise MDE 0.3288 PPR at 80% power)

| pair | gap (PPR) | se | p (2-sided) | BH rejected | MDE |
|---|---|---|---|---|---|
| QB|RB | -0.2032 | 0.1174 | 0.126985 | False | 0.3288 |
| QB|WR | -0.3621 | 0.0727 | 0.001595 | True | 0.2036 |
| QB|TE | -0.3106 | 0.0679 | 0.002567 | True | 0.1903 |
| RB|WR | -0.1589 | 0.0908 | 0.123504 | False | 0.2543 |
| RB|TE | -0.1074 | 0.0619 | 0.126097 | False | 0.1733 |
| WR|TE | 0.0515 | 0.066 | 0.461092 | False | 0.185 |

⭐ **The bound.** A pair's movement vs the grid-mean read is EXACTLY the difference of its two positions' ROW-POOLED completion deltas (QB +0.0458 · RB +0.0326 · WR +0.0519 · TE +0.0382), so the whole mechanism is bounded by their SPREAD: **0.019303 PPR**. ⚠️ The convention is load-bearing — the per-fold means in `tail_completion_by_position` are a MEAN OF FOLD MEANS and imply a different (wrong) bound (NF1.8).

## §6 swap clause under the registered MATERIALITY FLOOR

- floor: **0.197 PPR** (`median_pairwise_mde_ppr` over 6 pairs) · sensitivity band {'min': 0.1733, 'median': 0.197, 'max': 0.3288}
- state: **PASS**
  - QB: {'activity': {'active': True, 'pooled_shift': -0.3576, 'se': 0.0227, 'threshold': 0.0454, 'n_folds': 7, 'precise': True, 'material': True, 'materiality_floor_ppr': 0.197}, 'mean_abs_before': 0.3576, 'mean_abs_after': 0.0763, 'p_one_sided': 3.404377463267494e-07, 'passes': True}
  - RB: {'activity': {'active': False, 'pooled_shift': -0.0566, 'se': 0.0187, 'threshold': 0.0374, 'n_folds': 7, 'precise': True, 'material': False, 'materiality_floor_ppr': 0.197}}
  - WR: {'activity': {'active': False, 'pooled_shift': -0.0263, 'se': 0.0106, 'threshold': 0.0212, 'n_folds': 7, 'precise': True, 'material': False, 'materiality_floor_ppr': 0.197}}
  - TE: {'activity': {'active': False, 'pooled_shift': 0.1059, 'se': 0.0128, 'threshold': 0.0257, 'n_folds': 7, 'precise': True, 'material': False, 'materiality_floor_ppr': 0.197}}

## Family B — the recalibration contest (reported; the gate is family A)

- evaluable folds: 7 · winner: `level_affine` · PBO 0.0857 · DSR 0.9193
- winner clauses: {'reduces_gap': False, 'beats_permuted': True, 'no_rmse_harm': True, 'degenerates_lose': True, 'pbo_ok': True, 'dsr_ok': False, 'swap_clause': True, 'banks_untouched': True}

| arm | pooled cross-position bias range (PPR) |
|---|---|
| `identity` | 0.4901 |
| `level_add` | 0.4051 |
| `level_affine` | 0.3906 |
| `zero_point` | 2.9892 |
| `position_mean_point` | 0.511 |
| `level_add_permuted` | 0.5538 |
| `level_add_oracle` | 0.0 |

## Null classification

- {'state': 'POWER_LIMITED', 'reason': '`cross_position_bias_range`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it — DSR alone needs 9 folds against 7 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.', 'retest_trigger': '+2 folds for the DSR gate — field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)', 'failing_statistical_checks': ['reduces_gap', 'dsr_ok'], 'field_remedy_admissible': None}

⚠️⚠️ **THE TRIGGER ABOVE DESCRIBES FAMILY B ONLY (the FITTED recalibration contest) AND IS NOT FAMILY A'S STATUS.** Family A — this story's gate — asks whether the DETERMINISTIC point closes the gap, and its answer is ARITHMETICALLY BOUNDED, not underpowered: the completion delta is a deterministic function of each certified bank and no fold count can widen its cross-position spread. Reading a fold trigger onto family A would be the NF-D18 misleading-trigger class.

## The input

- dir: `/Users/charlesclark/Documents/machine_learning/baseball_betting/nf-w8-0b/quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_w8_0b_input` · shipped arm `identity` · banks_untouched True (max quantile drift 0.0)
- schema: ['season', 'week', 'gw', 'gsis_id', 'position', 'generator', 'point_raw', 'point_recal', 'recal_arm', 'point_vs_bank_offset', 'p10', 'p50', 'p90', 'replacement_points', 'vor', 'overall_rank', 'positional_rank', 'level_gap_disclosure', 'qb_option_b', 'calibration_warning']

## Promote blockers

- NF-W8-0 is DEPLOY-HELD: the cross-position input is an NF-G0 challenger consumed by nothing until governance promotes it
- every QB row carries the §1 Option-B caveat: calibrated + best-on-record, consumed under a registered-forward PM decision — NOT certification-equivalent to WR/TE/RB, and the ship bar was never relaxed (E2.1-r)
- NF-W7c's promote blockers are INHERITED in full: an assembled row whose source is not `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices (`calibration_warning`), and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap
- K/DST are OUT OF SCOPE — the input is declared 4-position; the NF-W7 K/DST weekly models join in a successor's registration, never by silent extension
- the layer corrects LEVEL (and uniform affine scale) only; a rank-dependent generator artifact is a successor's fresh registration
- the tail completion is a DETERMINISTIC read of the certified bank — it re-certifies NO position: NF-W7f's QB Option-B caveat, NF-W7c's calibrated-default disclosure and every per-position certification scope are inherited UNCHANGED
- `cross_rankable: true` licenses the RAW-POINT cross-position surfaces and a superflex board at the stated MDE only; it is not a claim about a rank-dependent (within-position non-uniform) generator artifact, which stays out of scope for a successor's registration
