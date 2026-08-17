# NF-W7e — the availability split over the ALL-ROWS Σ (NULL)

Generated 2026-08-17T17:45:20.044354+00:00 · gate positions **QB, RB, WR, TE** · gate league **full_ppr** · 1 folds · target `league_fantasy_points` · ranked on `crps_q199` · gated on `randomized_pit_max_decile_dev`

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing and publishes nothing.

## Verdict

- ship positions: **none**
- null positions: none
- ⭐ atom-cap confirmation (QB): **UNDEFINED** — the confirmation could not run — never read as a verdict (NF1.7 (a))
- scored but unusable: ['QB']
- not run in this invocation: ['RB', 'TE', 'WR']

⭐ **Selection key.** arms are RANKED on crps_q199; PIT flatness is a hard GATE clause on the selected arm and never a ranking key, because NF-W7c measured the over-correlated degenerate posting the best PIT in the QB field while posting the worst CRPS — a criterion a degenerate wins is fatal (NF1.8). The bar (0.05) and the statistic are NF-W7c's, unchanged.

## Per position

| pos | winner | best contest foil | Δ CRPS vs foil | CI95 | folds | **PIT dev** | bar | cov80 | PBO | DSR | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|

## ⭐ The 2×2 — split {on, off} × Σ {all rows, active rows}, per position

NF-W7d measured two of these cells and could not measure the third. Every cell is scored here on common random numbers against the reproduced incumbent. `single_copula` is the incumbent AND the matched foil (the mixture over Σ_all at π ≡ 1 is byte-identical to it); `mix_played` is NF-W7d's registered primary; `mix_off` completes the square.

| pos | **split over Σ_all** (THE CLAIM: `single_copula` − winner) | Σ population WITH the split (`mix_played` − winner) | split over Σ_played (`mix_off` − `mix_played`, NF-W7d) | Σ population WITHOUT the split (`single_copula` − `mix_off`, NF-W7d) | Δ vs indep | Δ vs direct points (report-only) |
|---|---|---|---|---|---|---|

⚠️ **The last column never gates** (NF-W7c §11.4 — an ARCHITECTURE question, not this story's).


## ⭐ The atom-cap confirmation

**State: `UNDEFINED`** — the confirmation could not run — never read as a verdict (NF1.7 (a))

| identity holds | installed atom (Σ_all) | installed atom (Σ_played) | atom CAP (what the marginals admit) | realized all-zero rate | shortfall (realized − cap) | PIT (`mix_played`, NF-W7d) | best PIT here | moved by Σ_all | bar |
|---|---|---|---|---|---|---|---|---|---|
| False | nan | nan | nan | nan | nan | None | None (`None`) | None | 0.05 |

Total zero mass the ASSEMBLED predictive actually carries at QB, per construction (vs a realized all-zero rate of nan): 


## The gate statistic — randomized-PIT decile flatness (gates, never ranks)

| pos | winner PIT (per-fold mean, BINDS) | pooled over rows | perfect-calibration median at this n | P(this rough \| calibrated) | worst decile |
|---|---|---|---|---|---|

| pos | `mixall_learned` | `mixall_clim` | `mixall_const` | `single_copula` | `mix_played` | `mix_off` | `assembled_indep` | `foil_direct_points` | `assembled_comonotone` | `pi_permuted` |
|---|---|---|---|---|---|---|---|---|---|---|

| pos | winner decile vector (low → high) |
|---|---|

## Could the mechanism act? (measured before it is credited)

| pos | mean installed atom | observed all-zero rate | clamp binding share | max marginal drift | tolerance | active? | marginals preserved? |
|---|---|---|---|---|---|---|---|

## ⭐ The reproduction identity proofs

`single_copula` must reproduce NF-W7c's recorded `joint_rank`; `mix_off` and `mix_played` must reproduce NF-W7d's `mix_off` and `mix_learned` — per fold, to 1e-9. Every comparison here is against those foils; a drifted harness would still produce a plausible contest.

| pos | vs NF-W7c (`single_copula`) folds / max gap / ok | vs NF-W7d (`mix_off`) | vs NF-W7d (`mix_played`) |
|---|---|---|---|

## Dependence clauses (inherited from NF-W7c)

| pos | independence under-disperses | knob moves coverage | winner beats indep on coverage |
|---|---|---|---|

## Gate clauses


## Anchors (all SCORED, never reasoned about)


## The mechanism, re-measured per fold

| pos | all-zero rate (test) | ρ̄ ratio by fold (all rows ÷ active rows) |
|---|---|---|

## What the assembled row is actually made of (inherited from NF-W7c)

| pos | source | priced legs from a bake-off winner | on a calibrated DEFAULT |
|---|---|---|---|
| QB | `partial_default` | 5 of 10 | 5 |
- **QB** — 5 of 10 priced stats use a NF-W6d calibrated DEFAULT (fumbles_lost, receiving_tds, receiving_yards, receptions, two_pt) — a calibrated range, not a conditional projection

## Promote blockers

- NF-W7e is DEPLOY-HELD: the all-rows-Σ availability-mixture assembly is an NF-G0 challenger and is served by nothing until governance promotes it
- a position ships from this record ONLY through its own registered gate (all four gate; the BH family carries four members) — a position that failed is a null, and NF-W7d's report-only wins are NOT carried forward as evidence (E2.1-r)
- NF-W7c's promote blockers are INHERITED in full: an assembled row whose `source` is not `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices, and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap
- a ship here does NOT re-open NF-W4's Layer B: availability enters as a component of the predictive's draw law, never as a feature injected into a point/quantile learner
- the mixture is certified on the NF-W7c fold axis under the declared gate league — a league or a position outside that certification is not covered by this record
