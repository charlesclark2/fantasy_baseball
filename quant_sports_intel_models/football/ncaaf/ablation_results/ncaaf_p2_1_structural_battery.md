# NCAAF-P2.1 — game-model structural refinement: the pre-registered hypothesis battery

_Decided 2026-08-15 · 22 configs · 8 purged folds · 8,325 games · declared real-arm field 16_

**Pre-registration:** [`ncaaf_p2_1_preregistration.md`](./ncaaf_p2_1_preregistration.md) — written and committed BEFORE the first score.

## Verdict

**REFERENCE_STANDS**

No pre-registered structural hypothesis survived the full deflation. The shipped P1.4 reference (`ridge / strength_only / strength_posterior`) carries.

| gate | value | bar | |
|---|---|---|---|
| anchors valid | True | all five must behave | ✅ |
| PBO (eligible real set) | 0.023 | < 0.2 | ✅ |
| DSR (degenerate-excluded — **binding**) | 0.0409 | ≥ 0.95 | ❌ |
| DSR (whole field, reported) | 0.0 | — | — |
| BH-FDR cutoff | 0.003125 | α = 0.05 | — |
| fold-consistency (calibrated) | 6 of 8 wins | false-fire ≤ 0.20 | — |

## Anchors — the two-sided proof the metric is not inverted

| anchor | reading | expectation | holds |
|---|---|---|---|
| `oracle_peek` (ORACLE FLOOR) | CRPS 1.4042 vs best real 18.4570 | nothing may beat it | ✅ |
| `permute` | CRPS 21.7975, calib80 0.677/0.782, coverage floor FAILED | must LOSE | ✅ |
| `zero_width` | CRPS 23.1887, calib80 0.195/0.185, coverage floor FAILED | must LOSE + FAIL the floor | ✅ |
| `max_width` | CRPS 27.4594, calib80 1.000/0.999, coverage floor satisfied | must SATISFY the floor + LOSE | ✅ |

## Per-hypothesis result

ΔCRPS > 0 means the arm BEATS the reference (CRPS is lower-is-better; the column is `reference − arm`). `elig` is the pre-registered calibration CONSTRAINT; `tie` is the nested-form guard (every arm nests the reference, so a sub-`1e-3` "lead" is a TIE, refused as a win).

| arm | ΔCRPS | fold wins | p (1-sided) | BH | eligible | tie | null state |
|---|---|---|---|---|---|---|---|
| `pace` | +0.0620 | 8/8 | 0.0020 | ✅ | ✅ | — | DSR_UNREACHABLE |
| `matchup_unit` | +0.0539 | 5/8 | 0.0691 | — | ✅ | — | DSR_UNREACHABLE |
| `recency` | +0.0092 | 6/8 | 0.0366 | — | ✅ | — | DSR_UNREACHABLE |
| `preseason_weight` | +0.0015 | 3/8 | 0.4702 | — | ✅ | — | DSR_UNREACHABLE |
| `hfa_venue` | -0.0000 | 5/8 | 0.4692 | — | ✅ | ≈ | GENUINE_ABSENCE |
| `lookahead_letdown` | -0.0004 | 5/8 | 0.4942 | — | ❌ | ≈ | CONSTRAINT_REFUSED |
| `matchup_interaction` | -0.0007 | 4/8 | 0.4939 | — | ✅ | ≈ | GENUINE_ABSENCE |
| `qb_regime` | -0.0054 | 3/8 | 0.5322 | — | ✅ | — | GENUINE_ABSENCE |
| `turnover_luck` | -0.0063 | 2/8 | 0.9099 | — | ✅ | — | GENUINE_ABSENCE |
| `bowl` | -0.0087 | 2/8 | 0.8415 | — | ✅ | — | GENUINE_ABSENCE |
| `garbage_clean` | -0.0089 | 3/8 | 0.7309 | — | ✅ | — | GENUINE_ABSENCE |
| `rivalry` | -0.0091 | 3/8 | 0.8431 | — | ✅ | — | GENUINE_ABSENCE |
| `rest` | -0.0123 | 2/8 | 0.9450 | — | ✅ | — | GENUINE_ABSENCE |
| `special_teams` | -0.0477 | 0/8 | 0.9957 | — | ✅ | — | GENUINE_ABSENCE |
| `hfa_full` | -0.1420 | 0/8 | 0.9988 | — | ✅ | — | GENUINE_ABSENCE |
| `hfa_team_eb` | -0.1452 | 0/8 | 0.9989 | — | ✅ | — | GENUINE_ABSENCE |

## Mechanism attribution (matched foils)

- **hfa_team_eb_vs_global** — {"eb_crps": 18.66424, "global_foil_crps": 18.51688, "delta": -0.14736, "per_team_content_earns_it": false}
  <br>if the EB per-team arm does not beat the identical construction with shrinkage→∞, the effect is a GLOBAL LEVEL (H1a's territory), not per-team content — the mechanism claim is refuted, not assumed (NF-D15 g′).

## Null classification

Each non-survivor is classified with `cv_power.classify_null(declared_field_size=16, degenerates_excluded_from_v=True)`. The report reads the MACHINE flag `field_remedy_admissible`, not the prose (MH2.7). A `CONSTRAINT_REFUSED` gets **no** re-test trigger — no sampling error accumulates against a hard constraint (NF-D18).

⭐ An arm marked **arm-gates ✅** cleared every ARM-level gate (eligible · not a tie · BH-FDR · fold-consistency) and was still not promoted because a RUN-level gate (PBO / DSR) failed. Its state is the line that says whether that shortfall is REACHABLE.

| arm | arm-gates | state | field remedy admissible | re-test trigger |
|---|---|---|---|---|
| `hfa_venue` | — | GENUINE_ABSENCE | None | — |
| `hfa_team_eb` | — | GENUINE_ABSENCE | None | — |
| `hfa_full` | — | GENUINE_ABSENCE | None | — |
| `matchup_interaction` | — | GENUINE_ABSENCE | None | — |
| `matchup_unit` | — | DSR_UNREACHABLE | None | field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric) |
| `rest` | — | GENUINE_ABSENCE | None | — |
| `lookahead_letdown` | — | CONSTRAINT_REFUSED | None | — |
| `rivalry` | — | GENUINE_ABSENCE | None | — |
| `bowl` | — | GENUINE_ABSENCE | None | — |
| `qb_regime` | — | GENUINE_ABSENCE | None | — |
| `recency` | — | DSR_UNREACHABLE | None | field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric) |
| `pace` | ✅ | DSR_UNREACHABLE | None | field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric) |
| `turnover_luck` | — | GENUINE_ABSENCE | None | — |
| `garbage_clean` | — | GENUINE_ABSENCE | None | — |
| `special_teams` | — | GENUINE_ABSENCE | None | — |
| `preseason_weight` | — | DSR_UNREACHABLE | None | field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric) |

## Honest framing

`best_alpha = 0`. A calibration result is **product value** (honest 3-market probabilities), never an edge claim. An edge claim additionally requires the deflated vs-close leg (model-side ATS/OU > 0.5238 breakeven AND > placebo); the reference's own vs-close reading is recorded below.

- reference vs-close: `{"ats_hit_rate": 0.4996, "ats_n": 4115, "ats_placebo": 0.4897, "ou_hit_rate": 0.507, "ou_n": 4134, "n_with_close": 4187, "breakeven": 0.5238, "clears_edge_bar": false}`
