# NF-W7c — arbitrary-league fantasy-point assembly (NULL)

Generated 2026-08-16T06:12:48.845227+00:00 · gate league **full_ppr** · 1 folds · target `league_fantasy_points` · metric `crps_q199`

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing and publishes nothing.

## Verdict

- ship positions: **none**
- null positions: none
- unavailable: ['QB', 'RB', 'TE', 'WR']

## Per position

| pos | winner | best foil | Δ CRPS vs foil | CI95 | folds | cov80 | cov80 indep | PIT dev | PBO | DSR | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|

## Did correlation earn its place?

| pos | Δ CRPS vs the matched INDEPENDENT foil | independence under-disperses | knob moves coverage | winner beats indep on coverage |
|---|---|---|---|---|

## Gate clauses


## Anchors (all SCORED, never reasoned about)


## Promote blockers

- NF-W7c is DEPLOY-HELD: the assembled fantasy-point distribution is an NF-G0 challenger and is served by nothing until governance promotes it
- an assembled row whose `source` is not `bakeoff_all_priced_legs` carries at least one NF-W6d calibrated DEFAULT among the stats this league prices — the consumer must surface `calibration_warning` and must never present it as a conditional projection
- a league pricing a term in SKILL_UNMODELED_KEYS has a REAL coverage gap: the assembled total omits it, and `unpriced_scored_terms` must be shown, never silently scored as 0
- the dependence structure is certified PER POSITION on the NF-W7c fold axis — a position or a league whose priced legs fall outside that certification is not covered by this record
