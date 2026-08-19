# NF-W8-0 — the cross-position comparability layer (UNDEFINED)

Generated 2026-08-19T07:03:31.279385+00:00 · gate league **full_ppr** · 1 folds · target `league_fantasy_points`

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing and publishes nothing.

## §1 The QB consumption decision (Option B, registered forward)

- decision: **OPTION_B_RECALIBRATED**
- rationale: dsr_ok is a SHIPPING gate, not a CONSUMPTION bar for a projection consumer: the fantasy vertical gates consumption on calibration + the product metric, not betting-posture deflation. NF-W7f's `zm_floor` is the only QB construction on record clearing the PIT bar (0.0281, 8/8 folds vs the incumbent's 0/8) AND the best-scoring (+0.0184 CRPS vs the matched foil, p=0.0121, PBO 0.0; +0.0189 vs direct-points); its dsr_ok refusal deflated a search whose flip mass was 100% on the winner, and every remedy is measured closed (NF-W7j DSR_UNREACHABLE — field size is no lever; NF-W7k MC_LEVER_EXHAUSTED — a 325x draw-noise shortfall). Every alternative consumption is strictly worse on BOTH axes.
- ⚠️ caveat: WEAKER FOOTING, carried by every consumer of QB rows: QB is the only position not through the full certification gate WR (DSR 0.9852) and TE (0.9822) cleared and RB was registered against. The un-certified residual is deflation-adjusted ARM SELECTION within the zm family — not calibration (a per-fold measurement) and not the sign of the improvement. QB rows are 'calibrated + best-on-record, consumed under Option B; not certification-equivalent'.
- 🚩 second reader: OPEN — unsigned until a governance second reader signs the prereg §1

## Verdict

- state: **UNDEFINED**
- a reproduction pin failed, a position was skipped, or family A could not evaluate — the harness did not run; never read as any verdict (NF1.7 (a))
- shipped arm: `identity`

## Reproduction pins (the consumed generators, by identity)

| pos | generator | reproduces | folds | max gap |
|---|---|---|---|---|
| QB | `qb_zm_floor` | False | 1 | 0.012521760128856751 |
| RB | `rb_direct` | False | 1 | 4.1524652205637835e-07 |
| WR | `wr_mixall` | False | 1 | 0.006520035730808171 |
| TE | `te_single_copula` | False | 1 | 0.0029736470725385544 |

## Family A — the pairwise level-gap tests

- gap_detected: **None** (BH q=0.1, 0 evaluable pairs, max pairwise MDE None PPR at 80% power)

| pair | gap (PPR) | se | p (2-sided) | BH rejected | MDE |
|---|---|---|---|---|---|
| QB|RB | None | None | None | False | None |
| QB|WR | None | None | None | False | None |
| QB|TE | None | None | None | False | None |
| RB|WR | None | None | None | False | None |
| RB|TE | None | None | None | False | None |
| WR|TE | None | None | None | False | None |

## Identity bias by position (pooled Σerr/Σn)

| pos | bias (PPR) | n rows | calibration slope (last fold) |
|---|---|---|---|
| QB | -0.3144 | 701 | 0.9598 |
| RB | -0.3858 | 1082 | 1.1197 |
| WR | 0.1483 | 1622 | 0.987 |
| TE | -0.1373 | 975 | 1.0731 |

## Family B — the recalibration contest

- evaluable folds: 0 ()
- winner: `None` · p(reduces gap) None · PBO None · DSR None
- affine eligibility: {'eligible': True, 'violations': []}
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

## §6 Generator-swap verification


## The input

- dir: `/Users/charlesclark/Documents/machine_learning/baseball_betting/nf-w80/quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_w8_0_input_smoke` · shipped arm `identity` · banks_untouched True
- schema: ['season', 'week', 'gw', 'gsis_id', 'position', 'generator', 'point_raw', 'point_recal', 'recal_arm', 'point_vs_bank_offset', 'p10', 'p50', 'p90', 'replacement_points', 'vor', 'overall_rank', 'positional_rank', 'level_gap_disclosure', 'qb_option_b', 'calibration_warning']

## Promote blockers

- NF-W8-0 is DEPLOY-HELD: the cross-position input is an NF-G0 challenger consumed by nothing until governance promotes it
- every QB row carries the §1 Option-B caveat: calibrated + best-on-record, consumed under a registered-forward PM decision — NOT certification-equivalent to WR/TE/RB, and the ship bar was never relaxed (E2.1-r)
- NF-W7c's promote blockers are INHERITED in full: an assembled row whose source is not `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices (`calibration_warning`), and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap
- K/DST are OUT OF SCOPE — the input is declared 4-position; the NF-W7 K/DST weekly models join in a successor's registration, never by silent extension
- the layer corrects LEVEL (and uniform affine scale) only; a rank-dependent generator artifact is a successor's fresh registration
