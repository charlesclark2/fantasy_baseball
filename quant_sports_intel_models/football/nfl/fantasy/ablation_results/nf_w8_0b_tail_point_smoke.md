# NF-W8-0b — the tail-completed cross-position ranking point (UNDEFINED)

Generated 2026-08-20T00:27:26.620110+00:00 · gate league **full_ppr** · 1 folds · target `league_fantasy_points`

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing and publishes nothing.

## Verdict

- state: **UNDEFINED**
- **`cross_rankable`: False** (the deterministic reading — the tail-completed point closes the gap with NO recalibration layer)
- `cross_rankable_with_layer`: False (the weaker, predecessor-inherited reading)
- a reproduction pin failed, a position was skipped, or family A could not evaluate on the tail-completed point — the harness did not run; never read as any verdict (NF1.7 (a))
- predecessor-state mapping: `UNDEFINED` · shipped arm `identity`

## The transform (deterministic — no fitting)

- form: `exponential_mean_excess_symmetric` · anchors {'inner_hi': 0.975, 'outer_hi': 0.995, 'inner_lo': 0.025, 'outer_lo': 0.005}
- covered mass 0.995 + 0.0025 per side restored

| pos | grid-mean bias (PPR) | tail-completed bias (PPR) | mean completion Δ (PPR) |
|---|---|---|---|
| QB | -0.3144 | -0.2740301435086643 | 0.0403 |
| RB | -0.3858 | -0.35239151373413274 | 0.0334 |
| WR | 0.1483 | 0.19352541439809853 | 0.0453 |
| TE | -0.1373 | -0.10368324554992474 | 0.0336 |

## Reproduction pins (the consumed generators, by identity)

| pos | generator | reproduces | folds | max gap |
|---|---|---|---|---|
| QB | `qb_zm_floor` | False | 1 | 0.012522071564870174 |
| RB | `rb_direct` | True | 1 | 0.0 |
| WR | `wr_mixall` | False | 1 | 0.006519650162477575 |
| TE | `te_single_copula` | False | 1 | 0.0029736568582232614 |

## Family A — the pairwise level-gap tests ON THE TAIL-COMPLETED POINT

- gap_detected: **None** (BH q=0.1, 0 evaluable pairs, max pairwise MDE None PPR at 80% power)

| pair | gap (PPR) | se | p (2-sided) | BH rejected | MDE |
|---|---|---|---|---|---|
| QB|RB | None | None | None | False | None |
| QB|WR | None | None | None | False | None |
| QB|TE | None | None | None | False | None |
| RB|WR | None | None | None | False | None |
| RB|TE | None | None | None | False | None |
| WR|TE | None | None | None | False | None |

## §6 swap clause under the registered MATERIALITY FLOOR

- floor: **inf PPR** (`median_pairwise_mde_ppr` over 0 pairs) · sensitivity band None
- state: **None**

## Family B — the recalibration contest (reported; the gate is family A)

- evaluable folds: 0 · winner: `None` · PBO None · DSR None
- winner clauses: {'banks_untouched': True}

| arm | pooled cross-position bias range (PPR) |
|---|---|
| `identity` | None |
| `level_add` | None |
| `level_affine` | None |
| `zero_point` | None |
| `position_mean_point` | None |
| `level_add_permuted` | None |
| `level_add_oracle` | None |

## Null classification

- None

## The input

- dir: `/Users/charlesclark/Documents/machine_learning/baseball_betting/nf-w8-0b/quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_w8_0b_input_smoke` · shipped arm `identity` · banks_untouched True (max quantile drift 0.0)
- schema: ['season', 'week', 'gw', 'gsis_id', 'position', 'generator', 'point_raw', 'point_recal', 'recal_arm', 'point_vs_bank_offset', 'p10', 'p50', 'p90', 'replacement_points', 'vor', 'overall_rank', 'positional_rank', 'level_gap_disclosure', 'qb_option_b', 'calibration_warning']

## Promote blockers

- NF-W8-0 is DEPLOY-HELD: the cross-position input is an NF-G0 challenger consumed by nothing until governance promotes it
- every QB row carries the §1 Option-B caveat: calibrated + best-on-record, consumed under a registered-forward PM decision — NOT certification-equivalent to WR/TE/RB, and the ship bar was never relaxed (E2.1-r)
- NF-W7c's promote blockers are INHERITED in full: an assembled row whose source is not `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices (`calibration_warning`), and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap
- K/DST are OUT OF SCOPE — the input is declared 4-position; the NF-W7 K/DST weekly models join in a successor's registration, never by silent extension
- the layer corrects LEVEL (and uniform affine scale) only; a rank-dependent generator artifact is a successor's fresh registration
- the tail completion is a DETERMINISTIC read of the certified bank — it re-certifies NO position: NF-W7f's QB Option-B caveat, NF-W7c's calibrated-default disclosure and every per-position certification scope are inherited UNCHANGED
- `cross_rankable: true` licenses the RAW-POINT cross-position surfaces and a superflex board at the stated MDE only; it is not a claim about a rank-dependent (within-position non-uniform) generator artifact, which stays out of scope for a successor's registration
