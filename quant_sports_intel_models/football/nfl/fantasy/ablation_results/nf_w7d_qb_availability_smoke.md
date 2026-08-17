# NF-W7d — QB availability mixture for the assembled FP distribution (NULL)

Generated 2026-08-17T01:46:58.603289+00:00 · gate position **QB** · gate league **full_ppr** · 1 folds · target `league_fantasy_points` · ranked on `crps_q199` · gated on `randomized_pit_max_decile_dev`

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing and publishes nothing.

## Verdict

- ship positions: **none**
- null positions: none
- report-only (diagnostic, never shippable from this record): none
- scored but unusable: ['QB']
- not run in this invocation: ['RB', 'TE', 'WR']

⭐ **Selection key.** arms are RANKED on crps_q199; PIT flatness is a hard GATE clause on the selected arm and never a ranking key, because NF-W7c measured the over-correlated degenerate posting the best PIT in the QB field while posting the worst CRPS — a criterion a degenerate wins is fatal (NF1.8). The bar (0.05) and the statistic are NF-W7c's, unchanged.

## Per position

| pos | gated | winner | best contest foil | Δ CRPS vs foil | CI95 | folds | **PIT dev** | bar | cov80 | PBO | DSR | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## ⭐ The gate statistic — randomized-PIT decile flatness

NF-W7c refused QB on this clause alone (0.0888 against 0.05). The whole field is shown because the bar is a **CONSTRAINT, not a ranking key**: the over-correlated degenerate `assembled_comonotone` posts a strong PIT precisely *because* perfect dependence is a crude availability factor, and it loses CRPS by a mile. A criterion a degenerate wins would be fatal (NF1.8); a constraint it satisfies is fine.

| pos | winner PIT (per-fold mean, BINDS) | pooled over rows | perfect-calibration median at this n | P(this rough \| calibrated) | worst decile |
|---|---|---|---|---|---|

| pos | `mix_learned` | `mix_clim` | `mix_const` | `single_copula` | `mix_off` | `assembled_indep` | `foil_direct_points` | `assembled_comonotone` |
|---|---|---|---|---|---|---|---|---|

## Attribution — which half of the mixture earned it?

`mixture − mix_off` isolates the **split** (the Bernoulli × conditional-rescale structure) holding the conditional Σ fixed; `mix_off − single_copula` isolates the **Σ-estimation population** (active rows only vs all rows). A bundled Δ against the incumbent alone could not tell them apart (NF-D15 (g′)).

| pos | Δ vs `mix_off` (the SPLIT) | Δ vs `single_copula` (TOTAL) | `mix_off` − `single_copula` (the Σ POPULATION) | Δ vs indep | Δ vs direct points (report-only) |
|---|---|---|---|---|---|

⚠️ **The last column never gates.** NF-W7c §11.4: `classify_null` names the FOIL, not the hypothesis. `foil_direct_points` answers *does assembling from per-stat parts beat modelling the total directly* — an ARCHITECTURE question §11.3 cards as its own successor, and not the question this story asks.


## Could the mechanism act? (⭐ measured before it is credited)

| pos | mean installed atom | observed all-zero rate | clamp binding share | max marginal drift | tolerance | active? | marginals preserved? |
|---|---|---|---|---|---|---|---|

A mixture whose clamp binds everywhere IS its own matched foil — an arm compared against itself, passing on nothing (NF1.9 / NF-D20). The atom is measured, not assumed.


## ⭐ The incumbent-reproduction identity proof

`single_copula` is NF-W7c's pre-registered primary construction. Reproducing its RECORDED per-fold scores to float precision is what proves the marginals, folds, draws and scoring did not drift — without it, a drifted harness would still produce a perfectly plausible contest. It is checkable only because the draw seed was deliberately INHERITED rather than refreshed.

| pos | folds compared | max abs gap | tolerance | reproduces |
|---|---|---|---|---|

## Dependence clauses (inherited from NF-W7c)

| pos | independence under-disperses | knob moves coverage | winner beats indep on coverage |
|---|---|---|---|

## Gate clauses


## Anchors (all SCORED, never reasoned about)


## The mechanism, re-measured per fold

NF-W7c §11.1 found the availability RATIO (ρ̄ all rows ÷ ρ̄ played-only) orders the PIT failure across positions while the zero-atom SIZE does not. Recorded here per fold so the mechanism is auditable rather than inherited.

| pos | all-zero rate (test) | ρ̄ ratio by fold |
|---|---|---|

## Relation to NF-W4 (which nulled an availability mixture ×4)

- NF-W4 **Layer A** modelled the roster PLAYED label and **SHIPPED** it — availability is modelable, a certified result this story CONSUMES.
- NF-W4 **Layer B** injected projected availability as a **FEATURE** into the point/quantile champion and returned GENUINE_ABSENCE ×3 + POWER_LIMITED. That is the null: a learner already given lagged usage cannot be told anything new by an availability COLUMN.
- NF-W7d consumes availability as a **component of the predictive's draw law** and is gated on a statistic NF-W4 never scored — the assembled total's joint-zero atom and its randomized-PIT flatness. A feature cannot put an atom in a distribution.
- ⛔ A null here does NOT re-decide NF-W4; a ship here does NOT re-open its Layer B.


## What the assembled row is actually made of (inherited from NF-W7c)

| pos | source | priced legs from a bake-off winner | on a calibrated DEFAULT |
|---|---|---|---|
| QB | `partial_default` | 5 of 10 | 5 |
- **QB** — 5 of 10 priced stats use a NF-W6d calibrated DEFAULT (fumbles_lost, receiving_tds, receiving_yards, receptions, two_pt) — a calibrated range, not a conditional projection

## Promote blockers

- NF-W7d is DEPLOY-HELD: the availability-mixture assembly is an NF-G0 challenger and is served by nothing until governance promotes it
- QB is the ONLY gated position — RB/WR/TE are scored REPORT-ONLY and a win there is a hypothesis for a successor to register, never a ship from this record (E2.1-r)
- NF-W7c's promote blockers are INHERITED in full: an assembled row whose `source` is not `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices, and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap
- a ship here does NOT re-open NF-W4's Layer B: this story consumes availability as a component of the predictive's draw law, never as a feature injected into a point/quantile learner
- the mixture is certified on the NF-W7c fold axis under the declared gate league — a league or a position outside that certification is not covered by this record

RB/WR/TE are DIAGNOSTIC on this record. A report-only position that would have passed every clause is a hypothesis for a successor to register FORWARD — re-classifying a result into shippability after seeing it is the E2.1-r inversion.
