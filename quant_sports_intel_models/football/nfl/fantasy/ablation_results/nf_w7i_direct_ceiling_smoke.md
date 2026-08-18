# NF-W7i — the RB DIRECT-POINTS improvement ceiling (NO)

Generated 2026-08-18T04:40:39.075534+00:00 · position **RB** · league **full_ppr** · 1 folds · target `league_fantasy_points` · metric `crps_q199` · cross-fit K=3

⚖️ `best_alpha = 0` · **DEPLOY-HELD** · a MEASUREMENT, not a bake-off — nothing is selected and nothing is promoted.

## Verdict

**`NO`** — ceiling 0.45% on `direct_augmented` is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding None) — NO regardless of magnitude

> Licensed for a bake-off: **False** · licensed iff answer ∈ ('YES','MARGINAL') ∧ stat_ok — the NF-W6d LICENSE_BANDS convention, declared before the run

> ⛔ RB ONLY, DIRECT-POINTS form only, at the NF-W1 fold axis. This record certifies nothing about QB/WR/TE and licenses no assembly successor (NF-W7h measured assembly as LOSING at RB by 0.0263 CRPS).

| quantity | value |
|---|---|
| honest incumbent (`direct_points`, full-train) | 2.43465 |
| best ACTIVE form | `direct_augmented` |
| **ceiling** | **0.453%** |
| paired Δ (CI95) | 0.01102 [None, None] |
| folds won | 1/1 (clause requires None) |
| BH cutoff (q=0.1, family=0) | None |
| bands | <2.0% NO · 2.0–5.0% MARGINAL · ≥5.0% YES |

## Per-form ceilings (NF-D16 (g‴): one ceiling per FORM, never one for the field)

> ⭐ ACTIVITY IS READ BEFORE MAGNITUDE. A peek that does not BEAT its own matched-n control could not ACT — its ceiling is UNINFORMATIVE, never a NO (NF-W6d / NF-D20).

| form | oracle | matched-n | activity | ceiling | folds | p |
|---|---|---|---|---|---|---|
| `direct_blockonly` | 2.64001 | 2.54832 | INACTIVE | -8.435% | 0/1 | None |
| `direct_augmented` | 2.42363 | 2.42941 | ACTIVE | 0.453% | 1/1 | None |
| `direct_upweighted` | 2.43362 | 2.42982 | INACTIVE | 0.042% | 1/1 | None |
| `recal_block` | 2.74058 | 2.81391 | ACTIVE | -12.566% | 0/1 | None |
| `climatology_block` | 3.83659 | 3.84001 | ACTIVE | -57.583% | 0/1 | None |

## Anchors (measured every run, never reasoned about — NF-D14)

| anchor | loses to the incumbent? |
|---|---|
| `nihilist_loses` | True |
| `zero_width_loses` | True |
| `max_width_loses` | True |
| `permutation_loses` | True |

> MAX over the per-form cross-fit peeks vs the honest full-train incumbent. Every bias here favours a BUILD — selection over forms is upward-biased on the oracle side, the peek sees the future, and the headline block weight is the smoke sweep's most generous (ceiling-maximising) value — so a NO is CONSERVATIVE (the NF-W5/NF-W6 rule, declared before the run).

> UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field (the NF-W5/NF-W6 ceiling rule). DSR does not arise: no arm is selected and nothing is promoted.

## Null state

`UNDEFINED` · field-remedy admissible: `None`

> ⛔ NO season/fold re-test trigger is published for RB — pre-registered scope guard. A ceiling below the band is a MEASUREMENT of the form's headroom, not a power shortfall, and more seasons cannot move it.

## Mean CRPS by label

| label | crps_q199 |
|---|---|
| `oracle__direct_augmented` | 2.42363 |
| `matched_n__direct_augmented` | 2.42941 |
| `matched_n__direct_upweighted` | 2.42982 |
| `oracle__direct_upweighted` | 2.43362 |
| `direct_points` | 2.43465 |
| `matched_n__direct_blockonly` | 2.54832 |
| `oracle__direct_blockonly` | 2.64001 |
| `oracle__recal_block` | 2.74058 |
| `matched_n__recal_block` | 2.81391 |
| `oracle__climatology_block` | 3.83659 |
| `matched_n__climatology_block` | 3.84001 |
| `permuted_direct` | 3.88866 |
| `nihilist_zero` | 5.72218 |
| `zero_width` | 5.92115 |
| `max_width` | 7.20128 |

## Positive control (NF-W6 §6 / MH2.1 (d))

Block points scaled ×1.3. Gating clause: absolute peek advantage grows ≥ 2.0× AND the ceiling WIDENS → **SEES the shift** (absolute advantage ×3.907, ceiling widened True).

> ⛔ The ORIGINAL pre-registered clause (relative ceiling moves ≥ 2.0 pct points) **FAILS** at 0.821 — retained and decomposed, never re-labelled (NF-D20). Diagnosis: the incumbent CRPS goes 2.43465 → 3.38045 (×1.3885), i.e. the shift inflates the DENOMINATOR of the relative ceiling, so that ratio understates sensitivity by construction.

| form | base ceiling | shifted ceiling | abs Δ base | abs Δ shifted |
|---|---|---|---|---|
| `direct_blockonly` | -8.435% | -1.526% | -0.20535 | -0.05157 |
| `direct_augmented` | 0.453% | 1.274% | 0.01102 | 0.04306 |
| `direct_upweighted` | 0.042% | 1.723% | 0.00103 | 0.05825 |
| `recal_block` | -12.566% | -5.975% | -0.30593 | -0.20197 |
| `climatology_block` | -57.583% | -47.542% | -1.40193 | -1.60712 |
