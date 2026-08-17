# NF-W7e — the availability split over the ALL-ROWS Σ (SHIP)

Generated 2026-08-17T19:35:12.971776+00:00 · gate positions **QB, RB, WR, TE** · gate league **full_ppr** · 8 folds · target `league_fantasy_points` · ranked on `crps_q199` · gated on `randomized_pit_max_decile_dev`

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing and publishes nothing.

## Verdict

- ship positions: **['WR']**
- null positions: {'QB': 'CONSTRAINT_REFUSED', 'RB': 'GENUINE_ABSENCE', 'TE': 'GENUINE_ABSENCE'}
- ⭐ atom-cap confirmation (QB): **QB_BLOCKED_AT_THE_MARGINAL_LAYER** — the installed atom is Σ-invariant (identity holds) and no all-rows arm clears the PIT bar — with split on/off × Σ_all/Σ_played all measured, the QB ceiling is set by the MARGINAL layer; no joint-layer story clears it; the QB roadmap moves to the 52-cell substrate
- scored but unusable: none
- not run in this invocation: none

⭐ **Selection key.** arms are RANKED on crps_q199; PIT flatness is a hard GATE clause on the selected arm and never a ranking key, because NF-W7c measured the over-correlated degenerate posting the best PIT in the QB field while posting the worst CRPS — a criterion a degenerate wins is fatal (NF1.8). The bar (0.05) and the statistic are NF-W7c's, unchanged.

## Per position

| pos | winner | best contest foil | Δ CRPS vs foil | CI95 | folds | **PIT dev** | bar | cov80 | PBO | DSR | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| QB | `mixall_learned` | `single_copula` | +0.0064 | [0.0055, 0.0073] | 8/8 | **0.0648** | 0.05 | 0.8314 | 0.0 | 0.9999 | NULL |
| RB | `mixall_learned` | `mix_played` | -0.0039 | [-0.0065, -0.0013] | 1/8 | **0.0263** | 0.05 | 0.8901 | 0.0 | 0.0076 | NULL |
| WR | `mixall_learned` | `mix_played` | +0.0018 | [0.0006, 0.003] | 7/8 | **0.0145** | 0.05 | 0.8668 | 0.0 | 0.9852 | SHIP |
| TE | `mixall_learned` | `mix_played` | -0.0005 | [-0.0015, 0.0005] | 4/8 | **0.0165** | 0.05 | 0.8869 | 0.0 | 0.0036 | NULL |

## ⭐ The 2×2 — split {on, off} × Σ {all rows, active rows}, per position

NF-W7d measured two of these cells and could not measure the third. Every cell is scored here on common random numbers against the reproduced incumbent. `single_copula` is the incumbent AND the matched foil (the mixture over Σ_all at π ≡ 1 is byte-identical to it); `mix_played` is NF-W7d's registered primary; `mix_off` completes the square.

| pos | **split over Σ_all** (THE CLAIM: `single_copula` − winner) | Σ population WITH the split (`mix_played` − winner) | split over Σ_played (`mix_off` − `mix_played`, NF-W7d) | Σ population WITHOUT the split (`single_copula` − `mix_off`, NF-W7d) | Δ vs indep | Δ vs direct points (report-only) |
|---|---|---|---|---|---|---|
| QB | **+0.0064** | +0.0095 | +0.0149 | -0.0180 | +0.0769 | +0.0005 |
| RB | **+0.0078** | -0.0039 | +0.0161 | -0.0044 | +0.0802 | -0.0520 |
| WR | **+0.0034** | +0.0018 | +0.0058 | -0.0042 | +0.1085 | +0.0207 |
| TE | **+0.0016** | -0.0005 | +0.0036 | -0.0015 | +0.0581 | +0.0273 |

⚠️ **The last column never gates** (NF-W7c §11.4 — an ARCHITECTURE question, not this story's).


## ⭐ The atom-cap confirmation

**State: `QB_BLOCKED_AT_THE_MARGINAL_LAYER`** — the installed atom is Σ-invariant (identity holds) and no all-rows arm clears the PIT bar — with split on/off × Σ_all/Σ_played all measured, the QB ceiling is set by the MARGINAL layer; no joint-layer story clears it; the QB roadmap moves to the 52-cell substrate

| identity holds | installed atom (Σ_all) | installed atom (Σ_played) | atom CAP (what the marginals admit) | realized all-zero rate | shortfall (realized − cap) | PIT (`mix_played`, NF-W7d) | best PIT here | moved by Σ_all | bar |
|---|---|---|---|---|---|---|---|---|---|
| True | 0.267125 | 0.267125 | 0.2687 | 0.5162 | 0.2475 | 0.0595 | 0.064 (`mixall_clim`) | 0.0053 | 0.05 |

Total zero mass the ASSEMBLED predictive actually carries at QB, per construction (vs a realized all-zero rate of 0.5162): `mixall_learned` 0.3019, `mixall_clim` 0.3021, `mixall_const` 0.302, `mix_played` 0.2963, `single_copula` 0.2842, `mix_off` 0.2553, `assembled_indep` 0.2348, `assembled_comonotone` 0.2643


## The gate statistic — randomized-PIT decile flatness (gates, never ranks)

| pos | winner PIT (per-fold mean, BINDS) | pooled over rows | perfect-calibration median at this n | P(this rough \| calibrated) | worst decile |
|---|---|---|---|---|---|
| QB | 0.0648 | 0.0621 (n=5485) | 0.0212 (n=685) | 0.00025 | 0 |
| RB | 0.0263 | 0.0191 (n=8591) | 0.0165 (n=1073) | 0.04024 | 9 |
| WR | 0.0145 | 0.007 (n=12827) | 0.0135 (n=1603) | 0.42464 | 1 |
| TE | 0.0165 | 0.0095 (n=7649) | 0.0174 (n=956) | 0.56736 | 0 |

| pos | `mixall_learned` | `mixall_clim` | `mixall_const` | `single_copula` | `mix_played` | `mix_off` | `assembled_indep` | `foil_direct_points` | `assembled_comonotone` | `pi_permuted` |
|---|---|---|---|---|---|---|---|---|---|---|
| QB | 0.0648 | 0.064 | 0.0642 | 0.0646 | 0.0595 | 0.0731 | 0.0814 | 0.0959 | 0.0563 | 0.0639 |
| RB | 0.0263 | 0.0246 | 0.0259 | 0.0257 | 0.0242 | 0.03 | 0.0862 | 0.1222 | 0.0363 | 0.0255 |
| WR | 0.0145 | 0.0141 | 0.0141 | 0.0173 | 0.0152 | 0.0234 | 0.1023 | 0.1459 | 0.0238 | 0.0151 |
| TE | 0.0165 | 0.0185 | 0.018 | 0.0201 | 0.0167 | 0.016 | 0.0731 | 0.1591 | 0.0248 | 0.0188 |

| pos | winner decile vector (low → high) |
|---|---|
| QB | [0.162, 0.139, 0.117, 0.1065, 0.1021, 0.082, 0.0664, 0.0688, 0.0663, 0.09] |
| RB | [0.0906, 0.0933, 0.1007, 0.1112, 0.1164, 0.1129, 0.0974, 0.1032, 0.0935, 0.0808] |
| WR | [0.1068, 0.093, 0.1006, 0.0983, 0.1035, 0.097, 0.1026, 0.1003, 0.0974, 0.1005] |
| TE | [0.0905, 0.0935, 0.1032, 0.099, 0.1039, 0.0994, 0.1026, 0.1061, 0.1017, 0.1002] |

## Could the mechanism act? (measured before it is credited)

| pos | mean installed atom | observed all-zero rate | clamp binding share | max marginal drift | tolerance | active? | marginals preserved? |
|---|---|---|---|---|---|---|---|
| QB | 0.2671 | 0.5162 | 0.917 | 0.00393 | 0.01 | True | True |
| RB | 0.2646 | 0.3359 | 0.4184 | 0.00329 | 0.01 | True | True |
| WR | 0.2947 | 0.3285 | 0.3786 | 0.00273 | 0.01 | True | True |
| TE | 0.3856 | 0.4283 | 0.4629 | 0.00471 | 0.01 | True | True |

## ⭐ The reproduction identity proofs

`single_copula` must reproduce NF-W7c's recorded `joint_rank`; `mix_off` and `mix_played` must reproduce NF-W7d's `mix_off` and `mix_learned` — per fold, to 1e-9. Every comparison here is against those foils; a drifted harness would still produce a plausible contest.

| pos | vs NF-W7c (`single_copula`) folds / max gap / ok | vs NF-W7d (`mix_off`) | vs NF-W7d (`mix_played`) |
|---|---|---|---|
| QB | 8 / 0.0 / True | 8 / 0.0 / True | 8 / 0.0 / True |
| RB | 8 / 0.0 / True | 8 / 0.0 / True | 8 / 0.0 / True |
| WR | 8 / 0.0 / True | 8 / 0.0 / True | 8 / 0.0 / True |
| TE | 8 / 0.0 / True | 8 / 0.0 / True | 8 / 0.0 / True |

## Dependence clauses (inherited from NF-W7c)

| pos | independence under-disperses | knob moves coverage | winner beats indep on coverage |
|---|---|---|---|
| QB | True | True | True |
| RB | True | True | True |
| WR | True | True | True |
| TE | True | True | True |

## Gate clauses

- **QB** — FAILING: pit_flat_ok
  - null state `CONSTRAINT_REFUSED` — every other gate is GREEN and the ship is refused by the pre-registered PIT flatness bar alone: 0.0648 against 0.05. A max-decile deviation against a FIXED bar is a deterministic constraint, not a sampling shortfall — more folds shrink nothing that would move it. The mechanism: the availability split over the ALL-ROWS Σ moves the assembled predictive in the modelled direction but does not carry it across the pre-registered bar — the split prices the atom the row's own marginals ADMIT, and the residual is the atom they do not: the marginal-admissible floor caps the installed atom below the realized all-zero rate, and no joint-layer construction can install mass its marginals forbid.
  - re-test trigger: NONE — a constraint refusal is not rescuable by data (NF-D18): more folds shrink the SE and make the refusal MORE certain. The remedy is a DIFFERENT LAYER under a FRESH registration — the MARGINAL layer (a NF-W6d cell whose own zero mass is smaller than the realized all-zero rate; the 52-cell substrate) — or a PM decision; ⛔ never a post-hoc bar change (E2.1-r).
  - field remedy admissible: None
- **RB** — FAILING: beats_foil, fold_consistency, dsr_ok, fdr_ok
  - null state `GENUINE_ABSENCE` — `nf_w7e_split_allrows|RB`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.
  - re-test trigger: NONE
  - field remedy admissible: None
- **WR** — all clauses green
- **TE** — FAILING: beats_foil, fold_consistency, dsr_ok, fdr_ok
  - null state `GENUINE_ABSENCE` — `nf_w7e_split_allrows|TE`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.
  - re-test trigger: NONE
  - field remedy admissible: None

## Anchors (all SCORED, never reasoned about)

- **QB** degenerates {'nihilist_zero': 6.5404, 'zero_width': 7.8446, 'max_width': 10.4448, 'assembled_comonotone': 2.6954} vs winner 2.5829
  - π permutation (the availability SIGNAL): `pi_permuted` 2.585, winner beats it True
  - oracle floor `mixall_learned`: **RESPECTED** (arm 2.5829, own-form oracle 2.5806, matched-n 2.5824, peek gain vs arm 0.002303, inversion p 0.9999)
  - oracle floor `mixall_clim`: **RESPECTED** (arm 2.5832, own-form oracle 2.5825, matched-n 2.5821, peek gain vs arm 0.000698, inversion p 0.9714)
  - oracle floor `mixall_const`: **RESPECTED** (arm 2.583, own-form oracle 2.5824, matched-n 2.582, peek gain vs arm 0.000663, inversion p 0.9644)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 0.861802
- **RB** degenerates {'nihilist_zero': 5.5948, 'zero_width': 5.8589, 'max_width': 7.1397, 'assembled_comonotone': 2.6442} vs winner 2.5212
  - π permutation (the availability SIGNAL): `pi_permuted` 2.5254, winner beats it True
  - oracle floor `mixall_learned`: **RESPECTED** (arm 2.5212, own-form oracle 2.5066, matched-n 2.5222, peek gain vs arm 0.014616, inversion p 1.0)
  - oracle floor `mixall_clim`: **RESPECTED** (arm 2.524, own-form oracle 2.5239, matched-n 2.5238, peek gain vs arm 0.000155, inversion p 0.6517)
  - oracle floor `mixall_const`: **RESPECTED** (arm 2.5249, own-form oracle 2.5248, matched-n 2.5248, peek gain vs arm 5.4e-05, inversion p 0.557)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 0.975938
- **WR** degenerates {'nihilist_zero': 5.5287, 'zero_width': 5.7988, 'max_width': 6.9358, 'assembled_comonotone': 2.6387} vs winner 2.6028
  - π permutation (the availability SIGNAL): `pi_permuted` 2.6042, winner beats it True
  - oracle floor `mixall_learned`: **RESPECTED** (arm 2.6028, own-form oracle 2.5927, matched-n 2.604, peek gain vs arm 0.010037, inversion p 1.0)
  - oracle floor `mixall_clim`: **RESPECTED** (arm 2.6036, own-form oracle 2.6035, matched-n 2.6038, peek gain vs arm 5.9e-05, inversion p 0.6376)
  - oracle floor `mixall_const`: **RESPECTED** (arm 2.6035, own-form oracle 2.6034, matched-n 2.6037, peek gain vs arm 0.000104, inversion p 0.7451)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 1.040853
- **TE** degenerates {'nihilist_zero': 3.491, 'zero_width': 4.0078, 'max_width': 4.9148, 'assembled_comonotone': 1.811} vs winner 1.7808
  - π permutation (the availability SIGNAL): `pi_permuted` 1.7812, winner beats it True
  - oracle floor `mixall_learned`: **RESPECTED** (arm 1.7808, own-form oracle 1.7744, matched-n 1.7812, peek gain vs arm 0.006394, inversion p 1.0)
  - oracle floor `mixall_clim`: **RESPECTED** (arm 1.7817, own-form oracle 1.7816, matched-n 1.7815, peek gain vs arm 0.000121, inversion p 0.7714)
  - oracle floor `mixall_const`: **RESPECTED** (arm 1.7813, own-form oracle 1.7811, matched-n 1.7811, peek gain vs arm 0.000132, inversion p 0.76)
  - ⭐ activity POSITIVE CONTROL `foil_direct_points`: **RESPECTED**, peek gain 0.687705

## The mechanism, re-measured per fold

| pos | all-zero rate (test) | ρ̄ ratio by fold (all rows ÷ active rows) |
|---|---|---|
| QB | 0.5162 | [1.812, 1.833, 1.848, 1.837, 1.806, 1.795, 1.806, 1.804] |
| RB | 0.3359 | [1.322, 1.325, 1.319, 1.317, 1.314, 1.316, 1.316, 1.315] |
| WR | 0.3285 | [1.238, 1.238, 1.241, 1.232, 1.232, 1.238, 1.24, 1.237] |
| TE | 0.4283 | [1.166, 1.171, 1.13, 1.128, 1.13, 1.131, 1.133, 1.136] |

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

- NF-W7e is DEPLOY-HELD: the all-rows-Σ availability-mixture assembly is an NF-G0 challenger and is served by nothing until governance promotes it
- a position ships from this record ONLY through its own registered gate (all four gate; the BH family carries four members) — a position that failed is a null, and NF-W7d's report-only wins are NOT carried forward as evidence (E2.1-r)
- NF-W7c's promote blockers are INHERITED in full: an assembled row whose `source` is not `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices, and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap
- a ship here does NOT re-open NF-W4's Layer B: availability enters as a component of the predictive's draw law, never as a feature injected into a point/quantile learner
- the mixture is certified on the NF-W7c fold axis under the declared gate league — a league or a position outside that certification is not covered by this record
