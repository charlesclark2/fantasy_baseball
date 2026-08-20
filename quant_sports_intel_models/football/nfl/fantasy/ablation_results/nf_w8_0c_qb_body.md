# NF-W8-0c — the QB BODY-level comparison (QB_BODY_GAP_PERSISTS)

Generated 2026-08-20T06:14:17.789604+00:00 · gate league **full_ppr** · 8 folds · target `league_fantasy_points` · position **QB**

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing, publishes nothing and writes NO optimizer input.

## Verdict

- state: **QB_BODY_GAP_PERSISTS**
- **`cross_rankable`: False**
- the QB body gap survives every registered arm — the hybrid architecture stands as-is; the input keeps NF-W8-0b's disclosed per-position gap and raw-point cross-position surfaces and superflex stay BLOCKED
- family-B winner: `cond_shift` · family-C state: `ARCHITECTURE_DISAGREEMENT_UNRESOLVED`

## Reproduction pins (prereg §7)

| pin | reproduces | detail |
|---|---|---|
| `qb_zm_floor` @ QB | True | 8 folds, max gap 0.0 |
| `rb_direct` @ RB | True | 8 folds, max gap 0.0 |
| `wr_mixall` @ WR | True | 8 folds, max gap 0.0 |
| `te_single_copula` @ TE | True | 8 folds, max gap 0.0 |
| QB `zm_floor` CRPS+PIT vs NF-W7f | True | 8 folds, crps 0.0, pit 0.0 |
| per-position identity bias vs NF-W8-0b | True | max gap 0.0 by position {'QB': 0.0, 'RB': 0.0, 'WR': 0.0, 'TE': 0.0} |
| this story's assembly ≡ the certified path | True | crps gap 0.0, point gap 0.0 |

## Family A — the decomposition (a MEASUREMENT; no gate)

- QB level bias (row-pooled): **-0.4237 PPR** = READ +0.0039 + MODEL -0.4276
- the model channel splits: availability -0.018222245476456712 · conditional level -0.4094087283459252
- ⭐ the identity is ASSERTED against the artifact, not restated: `identity_holds` **True**, max residual 1.17e-15 (tolerance 1e-08)
- material channels (≥ 0.05 PPR): ['conditional_channel_ppr']

| leg | w | contribution (PPR) | availability part | conditional part | material |
|---|---|---|---|---|---|
| passing_yards | +0.04 | -0.3975 | -0.009702785872887662 | -0.3878303476041046 | True |
| passing_tds | +4 | +0.0274 | -0.0069536529896616715 | 0.03439540321755602 | False |
| rushing_yards | +0.1 | -0.0205 | -0.002352964783698115 | -0.01818146645427384 | False |
| rushing_tds | +6 | -0.0143 | -0.001316306291231612 | -0.012968561530099319 | False |
| receiving_tds | +6 | -0.0088 | 0.0 | -0.008751139471285323 | False |
| receptions | +1 | -0.0057 | -2.450340219924836e-05 | -0.005636708995248335 | False |
| fumbles_lost | -2 | -0.0051 | 0.0005034323468108601 | -0.005640715847266641 | False |
| receiving_yards | +0.1 | -0.0049 | -5.717623667356252e-06 | -0.004860562951389286 | False |
| passing_interceptions | -2 | +0.0037 | 0.001789633756865258 | 0.0019212140097709814 | False |
| two_pt | +2 | -0.0020 | -0.0001593806167871675 | -0.001855842719584758 | False |

### Where along the quantile function the `zm_floor`-vs-`direct_points` gap lives

- grid-mean gap (row-pooled): **-0.3512 PPR** (NF-W8-0b recorded -0.3505 on the same construction pair)

| level band | contribution (PPR) | share of the gap |
|---|---|---|
| 0.005–0.095 | -0.0158 | 4.5% |
| 0.100–0.195 | -0.0096 | 2.7% |
| 0.200–0.295 | -0.0278 | 7.9% |
| 0.300–0.395 | -0.0345 | 9.8% |
| 0.400–0.495 | -0.0384 | 10.9% |
| 0.500–0.595 | -0.0398 | 11.3% |
| 0.600–0.695 | -0.0500 | 14.2% |
| 0.700–0.795 | -0.0640 | 18.2% |
| 0.800–0.895 | -0.0982 | 28.0% |
| 0.900–0.995 | +0.0270 | -7.7% |

⛔ The TAIL lever is not re-read here: NF-W8-0b bounded it DETERMINISTICALLY at 0.0193 PPR — ~19× short of the artifact.

## Family B — the declared repair field

- evaluable folds: 7 · declared field size 4 · winner `cond_shift` · PBO 0.0 · DSR 0.1654
- winner clauses: {'pit_preserved': True, 'no_crps_harm': True, 'reduces_bias': True, 'beats_permuted': True, 'degenerates_lose': True, 'banks_move_deliberately': True, 'pbo_ok': True, 'dsr_ok': False}
- PIT bar **0.05** (INHERITED, un-relaxed — a FLOOR, never a target)

| arm | pooled bias (PPR) | \|bias\| | CRPS | PIT (mean) | folds clearing the bar | acts |
|---|---|---|---|---|---|---|
| `identity` | -0.4571 | 0.4571 | 2.5851999535916717 | 0.029686710216253444 | 7/7 | yes |
| `cond_shift` | -0.1059 | 0.1059 | 2.580444573551587 | 0.027338030192488223 | 7/7 | yes |
| `cond_scale` | -0.2248 | 0.2248 | 2.579210963370596 | 0.0264974618773479 | 7/7 | yes |
| `avail_relevel` | -0.4583 | 0.4583 | 2.585285488353325 | 0.029311896685549198 | 7/7 | yes |
| `leg_scale` | -0.0193 | 0.0193 | 2.580034747541634 | 0.025456305917062664 | 7/7 | yes |
| `oracle_cond_shift` | +0.0003 | 0.0003 | 2.578185580462088 | 0.025665062734142912 | 7/7 | — |
| `oracle_cond_scale` | -0.1280 | 0.1280 | 2.5754501616304415 | 0.023547193834083657 | 7/7 | — |
| `oracle_avail_relevel` | -0.4589 | 0.4589 | 2.585493049017621 | 0.028254672648303482 | 7/7 | — |
| `oracle_leg_scale` | -0.0391 | 0.0391 | 2.5774987822477953 | 0.02458861839625006 | 7/7 | — |
| `over_cond_shift` | +0.2450 | 0.2450 | 2.5919362591627255 | 0.02874309051963186 | 6/7 | — |
| `permuted_leg_scale` | -0.1548 | 0.1548 | 2.5832902150240287 | 0.026718513703306596 | 7/7 | — |
| `climatology_bank` | -0.0051 | 0.0051 | 4.605731991851429 | 0.02370763873366759 | 7/7 | — |
| `nihilist_zero` | -6.4847 | 6.4847 | 6.530064411582937 | 0.4026685908798314 | 0/7 | — |
| `direct_points` | -0.0990 | 0.0990 | 2.6011151564004806 | 0.09910789210066648 | 0/7 | — |

### The per-form oracle ceilings (one per FORM — NF-D16 (g‴))

| arm | its own form's ceiling (PPR) | captured fraction |
|---|---|---|
| `cond_shift` | +0.4568 | 76.9% |
| `cond_scale` | +0.3291 | 70.6% |
| `avail_relevel` | -0.0018 | 68.4% |
| `leg_scale` | +0.4180 | 104.7% |

- magnitude anchor `over_cond_shift` (registered to **LOSE**): |bias| 0.24501428126760733 vs best real 0.01927904521840736 ⇒ lost_as_registered **True**
  - ⛔ if this anchor WINS it is left FAILING and DECOMPOSED, never re-labelled: that is a refuted MAGNITUDE hypothesis (the fit UNDER-corrects), obtainable only because the anchor was SCORED (NF-D20 / NF-D14 (g′))

## Family C — the architecture comparison (`direct_points` for QB)

- state: **ARCHITECTURE_DISAGREEMENT_UNRESOLVED**
- each construction wins at least one axis (or neither wins any) — a GENUINE disagreement NEITHER SIDE CAN CLAIM: the trade is disclosed, not resolved by preference, and the consumption call is a PM decision
- PIT folds clearing the 0.05 bar: {'assembly': 7, 'direct_points': 0, 'of': 7}
- assembly wins {'pit': True, 'crps': False, 'bias': False} · `direct_points` wins {'pit': False, 'crps': False, 'bias': True}
- mean CRPS delta (direct − assembly) +0.0159 · mean |bias| delta (assembly − direct) +0.2389

## Family A′ — the cross-position contrasts under each candidate QB point

- under `identity`: gap_detected **True** · QB|WR -0.3621 (BH True) · QB|TE -0.3106 (BH True)
- under `direct_points`: gap_detected **False** · QB|WR -0.0251 (BH False) · QB|TE 0.0264 (BH False)
- under `cond_shift`: gap_detected **False** · QB|WR -0.0546 (BH False) · QB|TE -0.0032 (BH False)

- gap closed under the winner: **True** · under `direct_points`: **True**

## Null classification

- {'state': 'DSR_UNREACHABLE', 'reason': "`qb_abs_level_bias`: the winner's per-fold Sharpe 1.064 sits at or BELOW the 4-arm field's deflated benchmark SR0 1.665, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, PRE-REGISTERED field, not more seasons — and ⛔ only if such a field was pre-registered; this is NOT a licence to re-cut a field you have already scored (MH2.7). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.", 'retest_trigger': 'field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)', 'failing_statistical_checks': ['dsr_ok'], 'field_remedy_admissible': None, 'field_shrink_flag': {'proposed_field_size': None, 'declared_family_size': 4, 'status': 'SUSPECT — NOT ADVICE', 'note': "the instrument suggests a smaller field, but this story's family of 4 arms was PRE-REGISTERED as the minimum §0.5 field (≥3 classes + a direct-learned foil). ⛔ Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one."}}

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
