# NCAAF-P2.1-S1 — `pace` under a lower-variance gate design (fresh §0.5 registration)

_Decided 2026-08-15 · 8 configs · 8 purged folds · 8,325 games · declared real-arm field 3 · primary `pace`_

**Pre-registration:** [`ncaaf_p2_1_s1_preregistration.md`](./ncaaf_p2_1_s1_preregistration.md) — written and committed BEFORE the first S1 score. The ONE design change vs P2.1: the DSR return series is per-FOLD (declared forward, binding); PBO stays on P2.1's per-BUCKET series. Same folds, learner, form, seed, draws; NO new feature.

## Verdict

**SHIP**

| gate | value | bar | |
|---|---|---|---|
| anchors valid | True | all six checks | ✅ |
| reproduction of P2.1 (`reference` + `pace` per-fold CRPS) | max abs dev 0.0 | < 0.0001 | ✅ |
| primary arm-level gates (eligible · not tie · ΔCRPS>0 · BH-FDR · fold clause) | True | all | ✅ |
| PBO (per-BUCKET series, eligible real set + reference) | 0.03 | < 0.2 | ✅ |
| **DSR (per-FOLD series, declared field, degenerate-excluded — BINDING)** | **0.9981** | ≥ 0.95 | ✅ |
| BH-FDR cutoff | 0.05 | α = 0.05 | — |
| fold-consistency (calibrated) | 6 of 8 wins | false-fire ≤ 0.20 | — |

## Anchors — the two-sided proof the metric is not inverted

| anchor | reading | expectation | holds |
|---|---|---|---|
| `oracle_peek` (ORACLE FLOOR) | CRPS 1.4042 vs best real 18.4387 | nothing may beat it | ✅ |
| `permute` | CRPS 21.7975, calib80 0.677/0.782, coverage floor FAILED | must LOSE | ✅ |
| `zero_width` | CRPS 23.1887, calib80 0.195/0.185, coverage floor FAILED | must LOSE + FAIL the floor | ✅ |
| `max_width` | CRPS 27.4594, calib80 1.000/0.999, coverage floor satisfied | must SATISFY the floor + LOSE | ✅ |

## The field — both series, side by side (the audit the story asks for)

ΔCRPS > 0 = arm beats the reference. `SR/fold` is the DECLARED DSR series (8 obs); `SR/bucket` is P2.1's gate series (32 obs) — same folds, same effect, the gap is the SERIES DEFINITION.

| arm | ΔCRPS | fold wins | p (1-sided) | BH | eligible | tie | SR per FOLD | SR per BUCKET | state |
|---|---|---|---|---|---|---|---|---|---|
| `pace_axis` | +0.0803 | 8/8 | 0.0005 | ✅ | ✅ | — | 1.914 | 0.678 | FIELD_MEMBER_CLEARED_NOT_PROMOTABLE |
| `pace_total_axis` | +0.0789 | 8/8 | 0.0008 | ✅ | ✅ | — | 1.780 | 0.678 | FIELD_MEMBER_CLEARED_NOT_PROMOTABLE |
| `pace` ⭐ | +0.0620 | 8/8 | 0.0020 | ✅ | ✅ | — | 1.492 | 0.532 | **PROMOTED** |

`pace` per-fold ΔCRPS by eval season: 2018 +0.0664, 2019 +0.0324, 2020 +0.1063, 2021 +0.0330, 2022 +0.0624, 2023 +0.0036, 2024 +0.0668, 2025 +0.1364.

## DSR — the declared series binds; the others are disclosure

| figure | DSR | SR | SR0 | N trials | n obs | status |
|---|---|---|---|---|---|---|
| `per_fold_declared_field_degenerate_excluded` | 0.9981 | 1.4915 | 0.3151 | 8 | 8 | ⭐ **BINDING** |
| `per_fold_whole_field` | 0.0 | 1.4915 | 29.2723 | 8 | 8 | reported |
| `per_fold_lineage_inclusive` | 0.995 | 1.4915 | 0.4477 | 30 | 8 | reported |
| `per_bucket_p21_series_REPORTED_ONLY` | 0.9809 | 0.5316 | 0.1235 | 8 | 32 | P2.1's series — reported only |

`V` (cross-trial per-fold Sharpe dispersion): degenerate-excluded 0.0466 · whole field 402.5259 · per-bucket degenerate-excluded 0.0072.

## Which lever did the work? — the 2×2 (series × field), post-verdict DISCLOSURE, never a gate

S1 changed TWO things vs P2.1's DSR: the return SERIES (bucket→fold) and the FIELD (16 heterogeneous arms → 3 pace representations, which sets `V` and `N`). The binding cell was fixed before the run; the other three are computed from the P2.1 record so the verdict's dependence on each lever is auditable. The (bucket, P2.1 field) cell reproduces P2.1's recorded 0.0409.

P2.1 field: 16 real arms, N = 22, V per-fold = 0.6824, V per-bucket = 0.2025.

| series ＼ field | P2.1 field (16 heterogeneous arms) | S1 field (3 pace representations) |
|---|---|---|
| per-BUCKET (P2.1's series) | DSR **0.0409** (SR 0.5316, SR0 0.8742, N 22, V 0.2025) ← P2.1 record | DSR **0.9809** (SR 0.5316, SR0 0.1235, N 8, V 0.0072) |
| per-FOLD (S1's series) | DSR **0.3903** (SR 1.4915, SR0 1.6045, N 22, V 0.6824) | DSR **0.9981** (SR 1.4915, SR0 0.3151, N 8, V 0.0466) ⭐ BINDING |

## Attribution reads (declared; reported, never gated)

- **levels_add_beyond_composites (pace vs pace_axis)** — `{"crps_a": 18.45702, "crps_b": 18.43867, "a_minus_b_gain": -0.01835, "a_beats_b": false, "tie": false}`
- **margin_axis_content (pace_axis vs pace_total_axis)** — `{"crps_a": 18.43867, "crps_b": 18.44006, "a_minus_b_gain": 0.00139, "a_beats_b": true, "tie": false}`

## Null classification

Each non-promoted arm is classified with `cv_power.classify_null(n_arms=3, declared_field_size=3, degenerates_excluded_from_v=True)` on the DECLARED per-fold series; the MACHINE flag `field_remedy_admissible` is read, not the prose (MH2.7).

| arm | primary | arm-gates | state | field remedy admissible | re-test trigger |
|---|---|---|---|---|---|
| `pace_axis` | — | ✅ | FIELD_MEMBER_CLEARED_NOT_PROMOTABLE | None | — |
| `pace_total_axis` | — | ✅ | FIELD_MEMBER_CLEARED_NOT_PROMOTABLE | None | — |
| `pace` | ⭐ | ✅ | **PROMOTED** | — | — |

## Honest framing

`best_alpha = 0`. A calibration ship is **product value** (honest 3-market probabilities), never an edge claim; the edge bar (model-side ATS/OU > 0.5238 AND > placebo) is unchanged and unclaimed.

- reference vs-close: `{"ats_hit_rate": 0.5009, "ats_n": 4113, "ats_placebo": 0.4899, "ou_hit_rate": 0.5081, "ou_n": 4135, "n_with_close": 4187, "breakeven": 0.5238, "clears_edge_bar": false}`
- `pace` vs-close: `{"ats_hit_rate": 0.5057, "ats_n": 4113, "ats_placebo": 0.4899, "ou_hit_rate": 0.5141, "ou_n": 4135, "n_with_close": 4187, "breakeven": 0.5238, "clears_edge_bar": false}`
