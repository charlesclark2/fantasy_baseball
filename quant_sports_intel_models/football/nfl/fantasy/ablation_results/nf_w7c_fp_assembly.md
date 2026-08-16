# NF-W7c — arbitrary-league fantasy-point assembly (SHIP)

Generated 2026-08-16T08:16:23.418683+00:00 · gate league **full_ppr** · 8 folds · target `league_fantasy_points` · metric `crps_q199`

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing and publishes nothing.

## Verdict

- ship positions: **['TE']**
- null positions: {'QB': 'GENUINE_ABSENCE', 'RB': 'GENUINE_ABSENCE', 'WR': 'POWER_LIMITED'}
- unavailable: none

## Per position

| pos | winner | best foil | Δ CRPS vs foil | CI95 | folds | cov80 | cov80 indep | PIT dev | PBO | DSR | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| QB | `joint_double` | `foil_direct_points` | -0.0025 | [-0.0183, 0.0133] | 3/8 | 0.8131 | 0.7812 | 0.0888 | 0.1429 | 0.0023 | NULL |
| RB | `joint_factor` | `foil_direct_points` | -0.0589 | [-0.0777, -0.0402] | 0/8 | 0.8849 | 0.7848 | 0.0254 | 0.0 | 0.0 | NULL |
| WR | `joint_rank` | `foil_direct_points` | +0.0173 | [0.0055, 0.029] | 7/8 | 0.8633 | 0.7383 | 0.0173 | 0.0 | 0.7242 | NULL |
| TE | `joint_rank` | `foil_direct_points` | +0.0257 | [0.0161, 0.0354] | 8/8 | 0.8859 | 0.7966 | 0.0201 | 0.0 | 0.9822 | SHIP |

⚠️ **A null above is about the FOIL named beside it, not about dependence.** The best foil at every position is `foil_direct_points` — a learner pointed straight at league points — so a `beats_foil` failure says *assembling from per-stat parts did not beat modelling the total directly*, NOT that cross-stat correlation is inert. The next table answers the dependence question, and it passes at every position.


## Did correlation earn its place?

| pos | Δ CRPS vs the matched INDEPENDENT foil | independence under-disperses | knob moves coverage | winner beats indep on coverage |
|---|---|---|---|---|
| QB | +0.0739 | True | True | True |
| RB | +0.0733 | True | True | True |
| WR | +0.1051 | True | True | True |
| TE | +0.0565 | True | True | True |

## Gate clauses

- **QB** — FAILING: beats_foil, fold_consistency, dsr_ok, fdr_ok, pit_flat_ok
  - null state `GENUINE_ABSENCE` — `nf_w7c_fp_assembly|QB`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.
  - re-test trigger: NONE
- **RB** — FAILING: beats_foil, fold_consistency, dsr_ok, fdr_ok
  - null state `GENUINE_ABSENCE` — `nf_w7c_fp_assembly|RB`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.
  - re-test trigger: NONE
- **WR** — FAILING: dsr_ok
  - null state `POWER_LIMITED` — `nf_w7c_fp_assembly|WR`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it — DSR alone needs 33 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.
  - re-test trigger: +25 folds for the DSR gate — field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)
- **TE** — all clauses green

## Anchors (all SCORED, never reasoned about)

- **QB** degenerates {'nihilist_zero': 6.5404, 'zero_width': 7.8446, 'max_width': 10.4448, 'assembled_comonotone': 2.6954} vs winner 2.5859
  - oracle floor `joint_rank`: **RESPECTED** (arm 2.5893, own-form oracle 2.5883, matched-n 2.5878, peek gain vs arm 0.000948, inversion p 0.9766)
  - oracle floor `joint_factor`: **RESPECTED** (arm 2.5905, own-form oracle 2.5895, matched-n 2.5894, peek gain vs arm 0.000944, inversion p 0.9543)
  - oracle floor `joint_pit`: **RESPECTED** (arm 2.6225, own-form oracle 2.6187, matched-n 2.6214, peek gain vs arm 0.003784, inversion p 0.8932)
  - oracle floor `joint_double`: **INACTIVE** (arm 2.5859, own-form oracle 2.5868, matched-n 2.5863, peek gain vs arm -0.000948, inversion p 0.0769)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 0.861802 — proves the detector can see an oracle that acts
- **RB** degenerates {'nihilist_zero': 5.5948, 'zero_width': 5.8589, 'max_width': 7.1397, 'assembled_comonotone': 2.6442} vs winner 2.5282
  - oracle floor `joint_rank`: **RESPECTED** (arm 2.529, own-form oracle 2.5289, matched-n 2.5287, peek gain vs arm 0.000102, inversion p 0.6349)
  - oracle floor `joint_factor`: **RESPECTED** (arm 2.5282, own-form oracle 2.528, matched-n 2.5282, peek gain vs arm 0.000192, inversion p 0.8918)
  - oracle floor `joint_pit`: **RESPECTED** (arm 2.5577, own-form oracle 2.5576, matched-n 2.5577, peek gain vs arm 0.000104, inversion p 0.5224)
  - oracle floor `joint_double`: **RESPECTED** (arm 2.559, own-form oracle 2.5582, matched-n 2.5592, peek gain vs arm 0.000866, inversion p 0.6835)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 0.975938 — proves the detector can see an oracle that acts
- **WR** degenerates {'nihilist_zero': 5.5287, 'zero_width': 5.7988, 'max_width': 6.9358, 'assembled_comonotone': 2.6387} vs winner 2.6062
  - oracle floor `joint_rank`: **RESPECTED** (arm 2.6062, own-form oracle 2.6061, matched-n 2.6063, peek gain vs arm 0.000139, inversion p 0.7936)
  - oracle floor `joint_factor`: **RESPECTED** (arm 2.6064, own-form oracle 2.6065, matched-n 2.6066, peek gain vs arm -0.000106, inversion p 0.3245)
  - oracle floor `joint_pit`: **RESPECTED** (arm 2.6325, own-form oracle 2.6287, matched-n 2.6318, peek gain vs arm 0.003796, inversion p 0.9997)
  - oracle floor `joint_double`: **RESPECTED** (arm 2.6164, own-form oracle 2.615, matched-n 2.6158, peek gain vs arm 0.00145, inversion p 0.8519)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 1.040853 — proves the detector can see an oracle that acts
- **TE** degenerates {'nihilist_zero': 3.491, 'zero_width': 4.0078, 'max_width': 4.9148, 'assembled_comonotone': 1.811} vs winner 1.7824
  - oracle floor `joint_rank`: **RESPECTED** (arm 1.7824, own-form oracle 1.7824, matched-n 1.7824, peek gain vs arm 7.4e-05, inversion p 0.672)
  - oracle floor `joint_factor`: **RESPECTED** (arm 1.7826, own-form oracle 1.7961, matched-n 1.7991, peek gain vs arm -0.013487, inversion p 0.0862)
  - oracle floor `joint_pit`: **RESPECTED** (arm 1.798, own-form oracle 1.7936, matched-n 1.7969, peek gain vs arm 0.004465, inversion p 1.0)
  - oracle floor `joint_double`: **RESPECTED** (arm 1.7925, own-form oracle 1.7906, matched-n 1.7902, peek gain vs arm 0.001885, inversion p 0.9145)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 0.687705 — proves the detector can see an oracle that acts

## What the assembled row is actually made of

| pos | source | priced legs from a bake-off winner | on a calibrated DEFAULT |
|---|---|---|---|
| QB | `partial_default` | 5 of 10 (passing_yards, passing_tds, passing_interceptions, rushing_yards, rushing_tds) | 5 |
| RB | `partial_default` | 3 of 10 (rushing_yards, rushing_tds, receptions) | 7 |
| WR | `partial_default` | 3 of 10 (receptions, receiving_yards, receiving_tds) | 7 |
| TE | `partial_default` | 2 of 10 (receptions, receiving_yards) | 8 |
- **QB** — 5 of 10 priced stats use a NF-W6d calibrated DEFAULT (fumbles_lost, receiving_tds, receiving_yards, receptions, two_pt) — a calibrated range, not a conditional projection
  - legs no preset prices (never scored, never shown): attempts, carries, targets
- **RB** — 7 of 10 priced stats use a NF-W6d calibrated DEFAULT (fumbles_lost, passing_interceptions, passing_tds, passing_yards, receiving_tds, receiving_yards, two_pt) — a calibrated range, not a conditional projection
  - legs no preset prices (never scored, never shown): attempts, carries, targets
- **WR** — 7 of 10 priced stats use a NF-W6d calibrated DEFAULT (fumbles_lost, passing_interceptions, passing_tds, passing_yards, rushing_tds, rushing_yards, two_pt) — a calibrated range, not a conditional projection
  - legs no preset prices (never scored, never shown): attempts, carries, targets
- **TE** — 8 of 10 priced stats use a NF-W6d calibrated DEFAULT (fumbles_lost, passing_interceptions, passing_tds, passing_yards, receiving_tds, rushing_tds, rushing_yards, two_pt) — a calibrated range, not a conditional projection
  - legs no preset prices (never scored, never shown): attempts, carries, targets

## Promote blockers

- NF-W7c is DEPLOY-HELD: the assembled fantasy-point distribution is an NF-G0 challenger and is served by nothing until governance promotes it
- an assembled row whose `source` is not `bakeoff_all_priced_legs` carries at least one NF-W6d calibrated DEFAULT among the stats this league prices — the consumer must surface `calibration_warning` and must never present it as a conditional projection
- a league pricing a term in SKILL_UNMODELED_KEYS has a REAL coverage gap: the assembled total omits it, and `unpriced_scored_terms` must be shown, never silently scored as 0
- the dependence structure is certified PER POSITION on the NF-W7c fold axis — a position or a league whose priced legs fall outside that certification is not covered by this record
