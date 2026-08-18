# NF-W7i — the RB DIRECT-POINTS improvement ceiling (NO)

Generated 2026-08-18T06:30:20.430923+00:00 · position **RB** · league **full_ppr** · 8 folds · target `league_fantasy_points` · metric `crps_q199` · cross-fit K=3

⚖️ `best_alpha = 0` · **DEPLOY-HELD** · a MEASUREMENT, not a bake-off — nothing is selected and nothing is promoted.

## Verdict

**`NO`** — ceiling 0.14% on `direct_augmented` is not statistically demonstrable (CI-excludes-zero False, fold clause True, BH binding False) — NO regardless of magnitude

> Licensed for a bake-off: **False** · licensed iff answer ∈ ('YES','MARGINAL') ∧ stat_ok — the NF-W6d LICENSE_BANDS convention, declared before the run

> ⛔ RB ONLY, DIRECT-POINTS form only, at the NF-W1 fold axis. This record certifies nothing about QB/WR/TE and licenses no assembly successor (NF-W7h measured assembly as LOSING at RB by 0.0263 CRPS).

| quantity | value |
|---|---|
| honest incumbent (`direct_points`, full-train) | 2.46924 |
| best ACTIVE form | `direct_augmented` |
| **ceiling** | **0.136%** |
| **ceiling CI95 (band units)** | **[-0.166, 0.438]** — the band comparison is a direct read, not an arithmetic exercise |
| paired Δ (CI95) | 0.00335 [-0.0041, 0.01081] |
| folds won | 6/8 (clause requires 6) |
| BH cutoff (q=0.1, family=5) | None |
| bands | <2.0% NO · 2.0–5.0% MARGINAL · ≥5.0% YES |

## Per-form ceilings (NF-D16 (g‴): one ceiling per FORM, never one for the field)

> ⭐ ACTIVITY IS READ BEFORE MAGNITUDE. A peek that does not BEAT its own matched-n control could not ACT — its ceiling is UNINFORMATIVE, never a NO (NF-W6d / NF-D20).

| form | oracle | matched-n | activity | ceiling | folds | p |
|---|---|---|---|---|---|---|
| `direct_blockonly` | 2.6495 | 2.68746 | ACTIVE | -7.3% | 0/8 | 1.0 |
| `direct_augmented` | 2.46589 | 2.47039 | ACTIVE | 0.136% | 6/8 | 0.1613 |
| `direct_upweighted` | 2.49721 | 2.47643 | INACTIVE | -1.132% | 1/8 | 0.9928 |
| `recal_block` | 2.73434 | 2.80374 | ACTIVE | -10.736% | 0/8 | 1.0 |
| `climatology_block` | 3.74865 | 3.75433 | ACTIVE | -51.814% | 0/8 | 1.0 |

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

`MEASURED_IMMATERIAL` · field-remedy admissible: `None`

> ⚠️ **HAND-CORRECTED from `POWER_LIMITED`** (retained verbatim under `classify_null_raw`, NF-D20). the 95% interval on the ceiling is [-0.166%, 0.438%] and its UPPER bound sits 4.57× BELOW the 2.0% materiality band — the evidence RULES OUT a material ceiling rather than failing to detect one. This is a MEASUREMENT, not a power shortfall: more folds tighten the interval around a point estimate 14.7× too small to reach the band.

> **Remedy:** a DIFFERENT MECHANISM, never more data and never a smaller field — a bake-off confined to this form cannot pay, which is exactly the question the oracle gate was run to answer before funding one

> ⛔ NO season/fold re-test trigger is published for RB — pre-registered scope guard. A ceiling below the band is a MEASUREMENT of the form's headroom, not a power shortfall, and more seasons cannot move it.

## Mean CRPS by label

| label | crps_q199 |
|---|---|
| `oracle__direct_augmented` | 2.46589 |
| `direct_points` | 2.46924 |
| `matched_n__direct_augmented` | 2.47039 |
| `matched_n__direct_upweighted` | 2.47643 |
| `oracle__direct_upweighted` | 2.49721 |
| `oracle__direct_blockonly` | 2.6495 |
| `matched_n__direct_blockonly` | 2.68746 |
| `oracle__recal_block` | 2.73434 |
| `matched_n__recal_block` | 2.80374 |
| `oracle__climatology_block` | 3.74865 |
| `matched_n__climatology_block` | 3.75433 |
| `permuted_direct` | 3.801 |
| `nihilist_zero` | 5.59484 |
| `zero_width` | 5.8589 |
| `max_width` | 7.13968 |
