# NF-W7d — QB availability mixture for the assembled FP distribution (NULL)

Generated 2026-08-17T04:20:21.821691+00:00 · gate position **QB** · gate league **full_ppr** · 8 folds · target `league_fantasy_points` · ranked on `crps_q199` · gated on `randomized_pit_max_decile_dev`

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing and publishes nothing.

## Verdict

- ship positions: **none**
- null positions: {'QB': 'GENUINE_ABSENCE'}
- report-only (diagnostic, never shippable from this record): ['RB', 'WR', 'TE']
- scored but unusable: none
- not run in this invocation: none

⭐ **Selection key.** arms are RANKED on crps_q199; PIT flatness is a hard GATE clause on the selected arm and never a ranking key, because NF-W7c measured the over-correlated degenerate posting the best PIT in the QB field while posting the worst CRPS — a criterion a degenerate wins is fatal (NF1.8). The bar (0.05) and the statistic are NF-W7c's, unchanged.

## Per position

| pos | gated | winner | best contest foil | Δ CRPS vs foil | CI95 | folds | **PIT dev** | bar | cov80 | PBO | DSR | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| QB | **YES** | `mix_learned` | `single_copula` | -0.0031 | [-0.0066, 0.0005] | 1/8 | **0.0595** | 0.05 | 0.835 | 0.0 | 0.0017 | NULL |
| RB | report-only | `mix_learned` | `single_copula` | +0.0117 | [0.0101, 0.0132] | 8/8 | **0.0242** | 0.05 | 0.8742 | 0.0 | 0.9999 | — |
| WR | report-only | `mix_learned` | `single_copula` | +0.0016 | [0.0008, 0.0024] | 8/8 | **0.0152** | 0.05 | 0.8618 | 0.0 | 1.0 | — |
| TE | report-only | `mix_learned` | `single_copula` | +0.0021 | [0.0014, 0.0028] | 8/8 | **0.0167** | 0.05 | 0.8825 | 0.0 | 0.9967 | — |

## ⭐ The gate statistic — randomized-PIT decile flatness

⚠️ **Read the baseline like-for-like.** NF-W7c's QB record reports 0.0888, but that is its SELECTED winner `joint_double`; the construction this story actually contests is its pre-registered PRIMARY `joint_rank`, which NF-W7c §11.1 measured at 0.065 and which appears below as `single_copula` (reproduced here to 1e-9). Comparing a mixture arm against 0.0888 would overstate the gain by attributing another arm's miscalibration to it. The whole field is shown because the bar is a **CONSTRAINT, not a ranking key**: the over-correlated degenerate `assembled_comonotone` posts a strong PIT precisely *because* perfect dependence is a crude availability factor, and it loses CRPS by a mile. A criterion a degenerate wins would be fatal (NF1.8); a constraint it satisfies is fine.

| pos | winner PIT (per-fold mean, BINDS) | pooled over rows | perfect-calibration median at this n | P(this rough \| calibrated) | worst decile |
|---|---|---|---|---|---|
| QB | 0.0595 | 0.0568 (n=5485) | 0.0212 (n=685) | 0.00025 | 1 |
| RB | 0.0242 | 0.0154 (n=8591) | 0.0165 (n=1073) | 0.07573 | 4 |
| WR | 0.0152 | 0.0101 (n=12827) | 0.0135 (n=1603) | 0.33842 | 0 |
| TE | 0.0167 | 0.0059 (n=7649) | 0.0174 (n=956) | 0.56736 | 0 |

| pos | `mix_learned` | `mix_clim` | `mix_const` | `single_copula` | `mix_off` | `assembled_indep` | `foil_direct_points` | `assembled_comonotone` |
|---|---|---|---|---|---|---|---|---|
| QB | 0.0595 | 0.0596 | 0.0594 | 0.0646 | 0.0731 | 0.0814 | 0.0959 | 0.0563 |
| RB | 0.0242 | 0.0253 | 0.0257 | 0.0257 | 0.03 | 0.0862 | 0.1222 | 0.0363 |
| WR | 0.0152 | 0.0177 | 0.017 | 0.0173 | 0.0234 | 0.1023 | 0.1459 | 0.0238 |
| TE | 0.0167 | 0.018 | 0.0185 | 0.0201 | 0.016 | 0.0731 | 0.1591 | 0.0248 |

## Attribution — which half of the mixture earned it?

`mixture − mix_off` isolates the **split** (the Bernoulli × conditional-rescale structure) holding the conditional Σ fixed; `mix_off − single_copula` isolates the **Σ-estimation population** (active rows only vs all rows). A bundled Δ against the incumbent alone could not tell them apart (NF-D15 (g′)).

| pos | Δ vs `mix_off` (the SPLIT) | Δ vs `single_copula` (TOTAL) | `mix_off` − `single_copula` (the Σ POPULATION) | Δ vs indep | Δ vs direct points (report-only) |
|---|---|---|---|---|---|
| QB | +0.0149 | -0.0031 | -0.0180 | +0.0674 | -0.0089 |
| RB | +0.0161 | +0.0117 | -0.0044 | +0.0841 | -0.0481 |
| WR | +0.0058 | +0.0016 | -0.0042 | +0.1067 | +0.0189 |
| TE | +0.0036 | +0.0021 | -0.0015 | +0.0586 | +0.0278 |

⚠️ **The last column never gates.** NF-W7c §11.4: `classify_null` names the FOIL, not the hypothesis. `foil_direct_points` answers *does assembling from per-stat parts beat modelling the total directly* — an ARCHITECTURE question §11.3 cards as its own successor, and not the question this story asks.


## Could the mechanism act? (⭐ measured before it is credited)

| pos | mean installed atom | observed all-zero rate | clamp binding share | max marginal drift | tolerance | active? | marginals preserved? |
|---|---|---|---|---|---|---|---|
| QB | 0.2671 | 0.5162 | 0.917 | 0.00495 | 0.01 | True | True |
| RB | 0.2646 | 0.3359 | 0.4184 | 0.00334 | 0.01 | True | True |
| WR | 0.2947 | 0.3285 | 0.3786 | 0.00367 | 0.01 | True | True |
| TE | 0.3856 | 0.4283 | 0.4629 | 0.00509 | 0.01 | True | True |

A mixture whose clamp binds everywhere IS its own matched foil — an arm compared against itself, passing on nothing (NF1.9 / NF-D20). The atom is measured, not assumed.


## ⭐ The incumbent-reproduction identity proof

`single_copula` is NF-W7c's pre-registered primary construction. Reproducing its RECORDED per-fold scores to float precision is what proves the marginals, folds, draws and scoring did not drift — without it, a drifted harness would still produce a perfectly plausible contest. It is checkable only because the draw seed was deliberately INHERITED rather than refreshed.

| pos | folds compared | max abs gap | tolerance | reproduces |
|---|---|---|---|---|
| QB | 8 | 0.0 | 1e-09 | True |
| RB | 8 | 0.0 | 1e-09 | True |
| WR | 8 | 0.0 | 1e-09 | True |
| TE | 8 | 0.0 | 1e-09 | True |

## Dependence clauses (inherited from NF-W7c)

| pos | independence under-disperses | knob moves coverage | winner beats indep on coverage |
|---|---|---|---|
| QB | True | True | True |
| RB | True | True | True |
| WR | True | True | True |
| TE | True | True | True |

## Gate clauses

- **QB** — FAILING: beats_foil, fold_consistency, dsr_ok, fdr_ok, pit_flat_ok
  - null state `GENUINE_ABSENCE` — `nf_w7d_qb_availability|QB`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.
  - re-test trigger: NONE
  - field remedy admissible: None

## Anchors (all SCORED, never reasoned about)

- **QB** degenerates {'nihilist_zero': 6.5404, 'zero_width': 7.8446, 'max_width': 10.4448, 'assembled_comonotone': 2.6954} vs winner 2.5924
  - π permutation (the availability SIGNAL): `pi_permuted` 2.597, winner beats it True
  - oracle floor `mix_learned`: **RESPECTED** (arm 2.5924, own-form oracle 2.5874, matched-n 2.5915, peek gain vs arm 0.00498, inversion p 0.9982)
  - oracle floor `mix_clim`: **RESPECTED** (arm 2.5926, own-form oracle 2.59, matched-n 2.5909, peek gain vs arm 0.002655, inversion p 0.9713)
  - oracle floor `mix_const`: **RESPECTED** (arm 2.5925, own-form oracle 2.5899, matched-n 2.5908, peek gain vs arm 0.002564, inversion p 0.969)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 0.861802 — proves the detector can see an oracle that acts
- **RB** degenerates {'nihilist_zero': 5.5948, 'zero_width': 5.8589, 'max_width': 7.1397, 'assembled_comonotone': 2.6442} vs winner 2.5173
  - π permutation (the availability SIGNAL): `pi_permuted` 2.5237, winner beats it True
  - oracle floor `mix_learned`: **RESPECTED** (arm 2.5173, own-form oracle 2.5008, matched-n 2.52, peek gain vs arm 0.016545, inversion p 1.0)
  - oracle floor `mix_clim`: **RESPECTED** (arm 2.5204, own-form oracle 2.5204, matched-n 2.5203, peek gain vs arm 6.6e-05, inversion p 0.6469)
  - oracle floor `mix_const`: **INACTIVE** (arm 2.5214, own-form oracle 2.5215, matched-n 2.5213, peek gain vs arm -7.7e-05, inversion p 0.349)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 0.975938 — proves the detector can see an oracle that acts
- **WR** degenerates {'nihilist_zero': 5.5287, 'zero_width': 5.7988, 'max_width': 6.9358, 'assembled_comonotone': 2.6387} vs winner 2.6046
  - π permutation (the availability SIGNAL): `pi_permuted` 2.6067, winner beats it True
  - oracle floor `mix_learned`: **RESPECTED** (arm 2.6046, own-form oracle 2.5929, matched-n 2.6064, peek gain vs arm 0.011684, inversion p 1.0)
  - oracle floor `mix_clim`: **RESPECTED** (arm 2.6057, own-form oracle 2.6051, matched-n 2.6058, peek gain vs arm 0.000633, inversion p 0.9961)
  - oracle floor `mix_const`: **RESPECTED** (arm 2.6056, own-form oracle 2.605, matched-n 2.6057, peek gain vs arm 0.000593, inversion p 0.9873)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 1.040853 — proves the detector can see an oracle that acts
- **TE** degenerates {'nihilist_zero': 3.491, 'zero_width': 4.0078, 'max_width': 4.9148, 'assembled_comonotone': 1.811} vs winner 1.7803
  - π permutation (the availability SIGNAL): `pi_permuted` 1.7809, winner beats it True
  - oracle floor `mix_learned`: **RESPECTED** (arm 1.7803, own-form oracle 1.7722, matched-n 1.7812, peek gain vs arm 0.008077, inversion p 1.0)
  - oracle floor `mix_clim`: **RESPECTED** (arm 1.7815, own-form oracle 1.7814, matched-n 1.7815, peek gain vs arm 0.000118, inversion p 0.7098)
  - oracle floor `mix_const`: **RESPECTED** (arm 1.7808, own-form oracle 1.7806, matched-n 1.7808, peek gain vs arm 0.00016, inversion p 0.8007)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 0.687705 — proves the detector can see an oracle that acts

## The mechanism, re-measured per fold

NF-W7c §11.1 found the availability RATIO (ρ̄ all rows ÷ ρ̄ played-only) orders the PIT failure across positions while the zero-atom SIZE does not. Recorded here per fold so the mechanism is auditable rather than inherited.

| pos | all-zero rate (test) | ρ̄ ratio by fold |
|---|---|---|
| QB | 0.5162 | [1.812, 1.833, 1.848, 1.837, 1.806, 1.795, 1.806, 1.804] |
| RB | 0.3359 | [1.322, 1.325, 1.319, 1.317, 1.314, 1.316, 1.316, 1.315] |
| WR | 0.3285 | [1.238, 1.238, 1.241, 1.232, 1.232, 1.238, 1.24, 1.237] |
| TE | 0.4283 | [1.166, 1.171, 1.13, 1.128, 1.13, 1.131, 1.133, 1.136] |

## Relation to NF-W4 (which nulled an availability mixture ×4)

- NF-W4 **Layer A** modelled the roster PLAYED label and **SHIPPED** it — availability is modelable, a certified result this story CONSUMES.
- NF-W4 **Layer B** injected projected availability as a **FEATURE** into the point/quantile champion and returned GENUINE_ABSENCE ×3 + POWER_LIMITED. That is the null: a learner already given lagged usage cannot be told anything new by an availability COLUMN.
- NF-W7d consumes availability as a **component of the predictive's draw law** and is gated on a statistic NF-W4 never scored — the assembled total's joint-zero atom and its randomized-PIT flatness. A feature cannot put an atom in a distribution.
- ⛔ A null here does NOT re-decide NF-W4; a ship here does NOT re-open its Layer B.


## What the assembled row is actually made of (inherited from NF-W7c)

| pos | source | priced legs from a bake-off winner | on a calibrated DEFAULT |
|---|---|---|---|
| QB | `partial_default` | 5 of 10 | 5 |
| RB | `partial_default` | 3 of 10 | 7 |
| WR | `partial_default` | 3 of 10 | 7 |
| TE | `partial_default` | 2 of 10 | 8 |
- **QB** — 5 of 10 priced stats use a NF-W6d calibrated DEFAULT (fumbles_lost, receiving_tds, receiving_yards, receptions, two_pt) — a calibrated range, not a conditional projection
- **RB** — 7 of 10 priced stats use a NF-W6d calibrated DEFAULT (fumbles_lost, passing_interceptions, passing_tds, passing_yards, receiving_tds, receiving_yards, two_pt) — a calibrated range, not a conditional projection
- **WR** — 7 of 10 priced stats use a NF-W6d calibrated DEFAULT (fumbles_lost, passing_interceptions, passing_tds, passing_yards, rushing_tds, rushing_yards, two_pt) — a calibrated range, not a conditional projection
- **TE** — 8 of 10 priced stats use a NF-W6d calibrated DEFAULT (fumbles_lost, passing_interceptions, passing_tds, passing_yards, receiving_tds, rushing_tds, rushing_yards, two_pt) — a calibrated range, not a conditional projection

## Promote blockers

- NF-W7d is DEPLOY-HELD: the availability-mixture assembly is an NF-G0 challenger and is served by nothing until governance promotes it
- QB is the ONLY gated position — RB/WR/TE are scored REPORT-ONLY and a win there is a hypothesis for a successor to register, never a ship from this record (E2.1-r)
- NF-W7c's promote blockers are INHERITED in full: an assembled row whose `source` is not `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices, and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap
- a ship here does NOT re-open NF-W4's Layer B: this story consumes availability as a component of the predictive's draw law, never as a feature injected into a point/quantile learner
- the mixture is certified on the NF-W7c fold axis under the declared gate league — a league or a position outside that certification is not covered by this record

RB/WR/TE are DIAGNOSTIC on this record. A report-only position that would have passed every clause is a hypothesis for a successor to register FORWARD — re-classifying a result into shippability after seeing it is the E2.1-r inversion.
