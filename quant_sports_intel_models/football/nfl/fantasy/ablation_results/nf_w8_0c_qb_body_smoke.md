# NF-W8-0c — the QB BODY-level comparison (UNDEFINED)

Generated 2026-08-20T05:15:53.215870+00:00 · gate league **full_ppr** · 2 folds · target `league_fantasy_points` · position **QB**

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing, publishes nothing and writes NO optimizer input.

## Verdict

- state: **UNDEFINED**
- **`cross_rankable`: False**
- a reproduction pin failed, a position was skipped, or fewer than 4 evaluable folds — the harness DID NOT RUN and this is never read as any verdict (NF1.7 (a))
- family-B winner: `None` · family-C state: `None`

## Reproduction pins (prereg §7)

| pin | reproduces | detail |
|---|---|---|
| `qb_zm_floor` @ QB | False | 2 folds, max gap 0.012522071564870174 |
| `rb_direct` @ RB | True | 2 folds, max gap 0.0 |
| `wr_mixall` @ WR | False | 2 folds, max gap 0.006519650162477575 |
| `te_single_copula` @ TE | False | 2 folds, max gap 0.0029736568582232614 |
| QB `zm_floor` CRPS+PIT vs NF-W7f | False | 2 folds, crps 0.012522071564870174, pit 0.004279600570613412 |
| per-position identity bias vs NF-W8-0b | False | max gap 0.015758869119072233 by position {'QB': 0.009824730843515317, 'RB': 0.0, 'WR': 0.015758869119072233, 'TE': 0.009998586409554575} |
| this story's assembly ≡ the certified path | True | crps gap 0.0, point gap 0.0 |

## Family A — the decomposition (a MEASUREMENT; no gate)

- QB level bias (row-pooled): **-0.4033 PPR** = READ -0.0160 + MODEL -0.3873
- the model channel splits: availability 0.005359287369573053 · conditional level -0.3926283876978951
- ⭐ the identity is ASSERTED against the artifact, not restated: `identity_holds` **True**, max residual 6.66e-16 (tolerance 1e-08)
- material channels (≥ 0.05 PPR): ['conditional_channel_ppr']

| leg | w | contribution (PPR) | availability part | conditional part | material |
|---|---|---|---|---|---|
| passing_yards | +0.04 | -0.2832 | 0.002900303421283813 | -0.2861215913811945 | True |
| passing_interceptions | -2 | -0.0339 | -0.00041569392681424787 | -0.03352502521798653 | False |
| passing_tds | +4 | -0.0293 | 0.001823590231472068 | -0.031143318122628626 | False |
| fumbles_lost | -2 | -0.0232 | -0.0001658417088361689 | -0.02307030989466238 | False |
| rushing_yards | +0.1 | +0.0177 | 0.0007327430860819715 | 0.016979609535254864 | False |
| rushing_tds | +6 | -0.0102 | 0.0004780531684835829 | -0.010652980282186152 | False |
| receiving_tds | +6 | -0.0087 | 0.0 | -0.008746355685131196 | False |
| receptions | +1 | -0.0072 | 3.2791789610771716e-06 | -0.007189868100243877 | False |
| receiving_yards | +0.1 | -0.0064 | 1.5368698928657734e-06 | -0.0063583976808266295 | False |
| two_pt | +2 | -0.0028 | 1.3170490480873351e-06 | -0.0028001508682900704 | False |

### Where along the quantile function the `zm_floor`-vs-`direct_points` gap lives

- grid-mean gap (row-pooled): **-0.4384 PPR** (NF-W8-0b recorded -0.3505 on the same construction pair)

| level band | contribution (PPR) | share of the gap |
|---|---|---|
| 0.005–0.095 | -0.0074 | 1.7% |
| 0.100–0.195 | -0.0125 | 2.8% |
| 0.200–0.295 | -0.0355 | 8.1% |
| 0.300–0.395 | -0.0440 | 10.0% |
| 0.400–0.495 | -0.0453 | 10.3% |
| 0.500–0.595 | -0.0444 | 10.1% |
| 0.600–0.695 | -0.0569 | 13.0% |
| 0.700–0.795 | -0.0744 | 17.0% |
| 0.800–0.895 | -0.1091 | 24.9% |
| 0.900–0.995 | -0.0089 | 2.0% |

⛔ The TAIL lever is not re-read here: NF-W8-0b bounded it DETERMINISTICALLY at 0.0193 PPR — ~19× short of the artifact.

## Family B — the declared repair field

- evaluable folds: 1 · declared field size 4 · winner `None` · PBO None · DSR None
- winner clauses: {}
- PIT bar **0.05** (INHERITED, un-relaxed — a FLOOR, never a target)

| arm | pooled bias (PPR) | \|bias\| | CRPS | PIT (mean) | folds clearing the bar | acts |
|---|---|---|---|---|---|---|
| `identity` | -0.2740 | 0.2740 | 2.6214723114360132 | 0.03409415121255349 | 1/1 | yes |
| `cond_shift` | +0.2547 | 0.2547 | 2.630201966364579 | 0.045506419400855924 | 1/1 | yes |
| `cond_scale` | +0.0563 | 0.0563 | 2.622887912043547 | 0.03409415121255349 | 1/1 | yes |
| `avail_relevel` | -0.2774 | 0.2774 | 2.622016136402862 | 0.03266761768901569 | 1/1 | yes |
| `leg_scale` | -0.0231 | 0.0231 | 2.6182060021668923 | 0.03409415121255349 | 1/1 | yes |
| `oracle_cond_shift` | +0.0001 | 0.0001 | 2.6216521467873664 | 0.038373751783166904 | 1/1 | — |
| `oracle_cond_scale` | -0.0890 | 0.0890 | 2.6200256222386704 | 0.03409415121255349 | 1/1 | — |
| `oracle_avail_relevel` | -0.2754 | 0.2754 | 2.621880511150838 | 0.035520684736091296 | 1/1 | — |
| `oracle_leg_scale` | +0.0083 | 0.0083 | 2.6198602306434227 | 0.03409415121255349 | 1/1 | — |
| `over_cond_shift` | +0.7832 | 0.7832 | 2.673290223819906 | 0.06119828815977174 | 0/1 | — |
| `permuted_leg_scale` | +0.7259 | 0.7259 | 2.6769144548790833 | 0.03980028530670471 | 1/1 | — |
| `climatology_bank` | +0.8190 | 0.8190 | 4.453261461587537 | 0.03152639087018545 | 1/1 | — |
| `nihilist_zero` | -6.0816 | 6.0816 | 6.1409415121255355 | 0.3878744650499286 | 0/1 | — |
| `direct_points` | +0.1974 | 0.1974 | 2.612798153102158 | 0.11398002853067046 | 0/1 | — |

### The per-form oracle ceilings (one per FORM — NF-D16 (g‴))

| arm | its own form's ceiling (PPR) | captured fraction |
|---|---|---|
| `cond_shift` | +0.2739 | 7.0% |
| `cond_scale` | +0.1850 | 117.7% |
| `avail_relevel` | -0.0014 | 237.5% |
| `leg_scale` | +0.2658 | 94.4% |

- magnitude anchor `over_cond_shift` (registered to **LOSE**): |bias| 0.7832213656319456 vs best real 0.023061535699267905 ⇒ lost_as_registered **True**
  - ⛔ if this anchor WINS it is left FAILING and DECOMPOSED, never re-labelled: that is a refuted MAGNITUDE hypothesis (the fit UNDER-corrects), obtainable only because the anchor was SCORED (NF-D20 / NF-D14 (g′))

## Family C — the architecture comparison (`direct_points` for QB)

- UNEVALUABLE on this run (fewer than 2 evaluable folds) — never read as a result (NF1.7 (a))

## Family A′ — the cross-position contrasts under each candidate QB point

- under `identity`: gap_detected **False** · QB|WR -0.5345 (BH False) · QB|TE -0.2197 (BH False)
- under `direct_points`: gap_detected **False** · QB|WR -0.1035 (BH False) · QB|TE 0.2113 (BH False)

- gap closed under the winner: **None** · under `direct_points`: **True**

## Null classification

- None

⚠️⚠️ ANY TRIGGER ABOVE DESCRIBES FAMILY B ONLY — the FITTED repair contest. Family A is a DETERMINISTIC decomposition (an exact identity; no fold count changes it in kind) and family A′'s bar is INHERITED. Reading a fold trigger onto either would be the NF-D18 misleading-trigger class.

## Promote blockers

- NF-W8-0 is DEPLOY-HELD: the cross-position input is an NF-G0 challenger consumed by nothing until governance promotes it
- every QB row carries the §1 Option-B caveat: calibrated + best-on-record, consumed under a registered-forward PM decision — NOT certification-equivalent to WR/TE/RB, and the ship bar was never relaxed (E2.1-r)
- NF-W7c's promote blockers are INHERITED in full: an assembled row whose source is not `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices (`calibration_warning`), and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap
- K/DST are OUT OF SCOPE — the input is declared 4-position; the NF-W7 K/DST weekly models join in a successor's registration, never by silent extension
- the layer corrects LEVEL (and uniform affine scale) only; a rank-dependent generator artifact is a successor's fresh registration
- the tail completion is a DETERMINISTIC read of the certified bank — it re-certifies NO position: NF-W7f's QB Option-B caveat, NF-W7c's calibrated-default disclosure and every per-position certification scope are inherited UNCHANGED
- `cross_rankable: true` licenses the RAW-POINT cross-position surfaces and a superflex board at the stated MDE only; it is not a claim about a rank-dependent (within-position non-uniform) generator artifact, which stays out of scope for a successor's registration
- NF-W8-0c writes NO optimizer input — NF-W8-0b's shipped input stands untouched; regenerating it under a repaired QB generator is a SUCCESSOR's step, never a side effect of this run
- `leg_scale` and `cond_scale` re-level a CERTIFIED per-stat marginal (NF-W6d): their per-leg marginal drift is measured and disclosed, and an admissible win under either form trades a per-stat certification scope for an assembled level
- family C is a CONSUMPTION comparison, never a re-certification: `direct_points` at QB is not a certified QB distribution and this story does not make it one
- the four arms correct a LEVEL (and a uniform per-leg scale); a rank-dependent or covariate-dependent generator artifact stays out of scope for a successor's registration
