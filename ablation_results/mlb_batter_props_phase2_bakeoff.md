# MLB Batter Props — Phase 2 §0.5 pricing bake-off (hits / HR / TB)

*Generated 2026-08-15T01:42:23.598044+00:00*  ·  `best_alpha = 0` — no edge/ROI/win-rate claim; market-blind (book prices are never features); deploy-held, research-only.

Pre-registration: `quant_sports_intel_models/baseball/edge_program/MLB_batter_props_phase2_preregistration.md` — executed as registered (6 half-season folds = a HARD data ceiling; regular-season only).


## batter_hits — **NULL**

**Null state: `GENUINE_ABSENCE`** — `batter_hits:crps`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.

Gates: {'beats_foil': False, 'pbo_lt_0.2': True, 'dsr_ge_0.95': False, 'fold_consistency': False, 'bh_fdr': False}

Leader **glm_poisson** vs foil `glm_poisson` — mean OOS CRPS 0.44513 vs 0.44513; fold wins 0/6 (required 5); p(one-sided) 1.0; PBO 0.0; DSR UNDEFINED (binds: None; with-degenerates-in-V UNDEFINED)

DSR note: the leader's per-fold skill series is degenerate (fewer than 3 folds, or identically zero because the leader IS the incumbent) — DSR is UNDEFINED here, not failed

| arm | mean CRPS | mean MAE | PIT max-dec dev |
|---|---|---|---|
| glm_poisson (foil) | 0.44513 | 0.64208 | 0.0139 |
| glm_nb | 0.44513 | 0.64208 | 0.0136 |
| hurdle_nb | 0.46984 | 0.64171 | 0.0726 |
| lgbm_nb | 0.44995 | 0.65529 | 0.01 |
| pa_structural | 0.44961 | 0.66268 | 0.007 |
| degenerate_zero (degenerate anchor) | 0.86333 | 0.86333 | — |
| degenerate_marginal (degenerate anchor) | 0.45729 | 0.66489 | — |

Anchors: degenerate_zero loses CRPS = True; degenerate_marginal loses CRPS = True; **MAE inversion observed = False** (the NF-D11 read — measured, not predicted); oracle beats matched-n = True

Paired mechanism deltas (NF-D10; + = mechanism helped, per fold): {'dispersion (glm_nb − glm_poisson)': [-0.0, -0.0, -0.0, -0.0, -0.0, -0.0], 'zero_mechanism (hurdle_nb − glm_nb)': [-0.02289, -0.02511, -0.02553, -0.02364, -0.02664, -0.0244]}

Per-fold CRPS:

| fold | glm_poisson | glm_nb | hurdle_nb | lgbm_nb | pa_structural | degenerate_zero | degenerate_marginal |
|---|---|---|---|---|---|---|---|
| 2023H2 (n=9925) | 0.44844 | 0.44844 | 0.47133 | 0.46206 | 0.45171 | 0.87234 | 0.45993 |
| 2024H1 (n=13699) | 0.43661 | 0.43661 | 0.46172 | 0.44363 | 0.44211 | 0.84882 | 0.45035 |
| 2024H2 (n=20678) | 0.44285 | 0.44285 | 0.46839 | 0.44716 | 0.44931 | 0.86058 | 0.45767 |
| 2025H1 (n=20253) | 0.4518 | 0.4518 | 0.47543 | 0.45391 | 0.45599 | 0.87444 | 0.46343 |
| 2025H2 (n=20243) | 0.44632 | 0.44632 | 0.47295 | 0.44778 | 0.45042 | 0.86919 | 0.45786 |
| 2026H1 (n=20778) | 0.44479 | 0.44479 | 0.46919 | 0.44516 | 0.44809 | 0.85461 | 0.45451 |

De-vigged market benchmark (graded, never fit against; leader's P(over) vs consensus; level-adj = NF-D15 matched level-only foil):

| fold | two-sided coverage | n bench | Brier market | Brier lvl-adj | Brier model | bias mkt | bias model |
|---|---|---|---|---|---|---|---|
| 2023H2 | 98.1% | 9472 | 0.24439 | 0.24435 | 0.23511 | -0.0485 | -0.0307 |
| 2024H1 | 95.6% | 13050 | 0.23982 | 0.24069 | 0.22726 | 0.0016 | -0.0264 |
| 2024H2 | 95.8% | 19707 | 0.23843 | 0.23857 | 0.23147 | -0.0047 | -0.0182 |
| 2025H1 | 98.4% | 19705 | 0.23711 | 0.2374 | 0.23462 | 0.0078 | -0.025 |
| 2025H2 | 99.4% | 19888 | 0.23704 | 0.23729 | 0.23165 | 0.0178 | -0.0167 |
| 2026H1 | 98.9% | 20193 | 0.23904 | 0.23905 | 0.2349 | 0.0137 | -0.0228 |

Pooled (row-weighted): {'brier_market': 0.23876, 'brier_market_level_adj': 0.239, 'brier_model': 0.23259}  ·  model beats market in 6/6 folds

Coverage-80 FLOOR per fold (never a target — E2.1-r): [0.9599, 0.9621, 0.9595, 0.9537, 0.9605, 0.9585] (leader)

## batter_home_runs — **NULL**

**Null state: `GENUINE_ABSENCE`** — `batter_home_runs:crps`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.

Gates: {'beats_foil': False, 'pbo_lt_0.2': True, 'dsr_ge_0.95': False, 'fold_consistency': False, 'bh_fdr': False}

Leader **glm_nb** vs foil `glm_poisson` — mean OOS CRPS 0.10895 vs 0.10895; fold wins 4/6 (required 5); p(one-sided) 1.0; PBO 0.0; DSR 0.0000 (binds: degenerate_excluded_whole_field; with-degenerates-in-V 0.0000)

| arm | mean CRPS | mean MAE | PIT max-dec dev |
|---|---|---|---|
| glm_poisson (foil) | 0.10895 | 0.12464 | 0.001 |
| glm_nb | 0.10895 | 0.12464 | 0.0016 |
| hurdle_nb | 0.11165 | 0.12459 | 0.018 |
| lgbm_nb | 0.11057 | 0.12457 | 0.012 |
| pa_structural | 0.10912 | 0.12466 | 0.0031 |
| degenerate_zero (degenerate anchor) | 0.12457 | 0.12457 | — |
| degenerate_marginal (degenerate anchor) | 0.11089 | 0.12457 | — |

Anchors: degenerate_zero loses CRPS = True; degenerate_marginal loses CRPS = True; **MAE inversion observed = True** (the NF-D11 read — measured, not predicted); oracle beats matched-n = True

Paired mechanism deltas (NF-D10; + = mechanism helped, per fold): {'dispersion (glm_nb − glm_poisson)': [0.0, -0.0, 0.0, 0.0, 0.0, -0.0], 'zero_mechanism (hurdle_nb − glm_nb)': [-0.00373, -0.00251, -0.00275, -0.00243, -0.00288, -0.00194]}

Per-fold CRPS:

| fold | glm_poisson | glm_nb | hurdle_nb | lgbm_nb | pa_structural | degenerate_zero | degenerate_marginal |
|---|---|---|---|---|---|---|---|
| 2023H2 (n=9818) | 0.11748 | 0.11748 | 0.12121 | 0.12295 | 0.11752 | 0.13557 | 0.11927 |
| 2024H1 (n=13694) | 0.10363 | 0.10363 | 0.10614 | 0.10586 | 0.10388 | 0.11801 | 0.10553 |
| 2024H2 (n=21139) | 0.10807 | 0.10807 | 0.11082 | 0.1091 | 0.10835 | 0.12366 | 0.11036 |
| 2025H1 (n=20340) | 0.10364 | 0.10364 | 0.10607 | 0.10393 | 0.10392 | 0.11711 | 0.10525 |
| 2025H2 (n=20220) | 0.1138 | 0.1138 | 0.11668 | 0.11448 | 0.11391 | 0.13101 | 0.11605 |
| 2026H1 (n=20595) | 0.10706 | 0.10706 | 0.109 | 0.10713 | 0.10714 | 0.12207 | 0.1089 |

De-vigged market benchmark (graded, never fit against; leader's P(over) vs consensus; level-adj = NF-D15 matched level-only foil):

| fold | two-sided coverage | n bench | Brier market | Brier lvl-adj | Brier model | bias mkt | bias model |
|---|---|---|---|---|---|---|---|
| 2023H2 | 95.4% | 9347 | 0.11119 | 0.111 | 0.11174 | 0.014 | 0.0049 |
| 2024H1 | 92.5% | 11722 | 0.09227 | 0.09155 | 0.09064 | 0.0321 | -0.0018 |
| 2024H2 | 90.2% | 14820 | 0.07381 | 0.0729 | 0.0712 | 0.0323 | 0.0018 |
| 2025H1 | 93.2% | 17104 | 0.09267 | 0.09183 | 0.09168 | 0.0292 | 0.0062 |
| 2025H2 | 94.2% | 18864 | 0.10581 | 0.10558 | 0.10565 | 0.0176 | 0.0008 |
| 2026H1 | 15.6% | 3080 | 0.12598 | 0.12623 | 0.12755 | 0.007 | -0.0303 |

⚠️ HR benchmark figures are PER-FOLD ONLY by registration (§9.1): the two-sided share collapses 60.9→8.7% by season (books moved to one-way anytime-HR; 2026H1 is Pinnacle-dominated = a DIFFERENT estimand). A pooled HR figure would average incomparable regimes and is forbidden.

Coverage-80 FLOOR per fold (never a target — E2.1-r): [0.9694, 0.962, 0.9669, 0.9655, 0.966, 0.9518] (leader)

## batter_total_bases — **SHIP_CANDIDATE (research-only, deploy-held)**

Gates: {'beats_foil': True, 'pbo_lt_0.2': True, 'dsr_ge_0.95': True, 'fold_consistency': True, 'bh_fdr': True}

Leader **glm_nb** vs foil `glm_poisson` — mean OOS CRPS 0.86311 vs 0.90255; fold wins 6/6 (required 5); p(one-sided) 0.0; PBO 0.0; DSR 0.9993 (binds: degenerate_excluded_whole_field; with-degenerates-in-V 0.0000)

| arm | mean CRPS | mean MAE | PIT max-dec dev |
|---|---|---|---|
| glm_poisson (foil) | 0.90255 | 1.24692 | 0.0703 |
| glm_nb | 0.86311 | 1.21018 | 0.011 |
| hurdle_nb | 0.87843 | 1.2386 | 0.0359 |
| lgbm_nb | 0.88633 | 1.23132 | 0.0366 |
| pa_structural | 0.86907 | 1.23347 | 0.0077 |
| degenerate_zero (degenerate anchor) | 1.43031 | 1.43031 | — |
| degenerate_marginal (degenerate anchor) | 0.88338 | 1.23516 | — |

Anchors: degenerate_zero loses CRPS = True; degenerate_marginal loses CRPS = True; **MAE inversion observed = False** (the NF-D11 read — measured, not predicted); oracle beats matched-n = True

Paired mechanism deltas (NF-D10; + = mechanism helped, per fold): {'dispersion (glm_nb − glm_poisson)': [0.04273, 0.03611, 0.04071, 0.03844, 0.04278, 0.03589], 'zero_mechanism (hurdle_nb − glm_nb)': [-0.01349, -0.01444, -0.01741, -0.01792, -0.0163, -0.01239]}

Per-fold CRPS:

| fold | glm_poisson | glm_nb | hurdle_nb | lgbm_nb | pa_structural | degenerate_zero | degenerate_marginal |
|---|---|---|---|---|---|---|---|
| 2023H2 (n=10044) | 0.92661 | 0.88388 | 0.89737 | 0.9444 | 0.88936 | 1.46784 | 0.90609 |
| 2024H1 (n=13693) | 0.87945 | 0.84334 | 0.85778 | 0.87803 | 0.85021 | 1.40269 | 0.86473 |
| 2024H2 (n=21121) | 0.89772 | 0.857 | 0.87441 | 0.8797 | 0.86533 | 1.41722 | 0.88214 |
| 2025H1 (n=20321) | 0.89358 | 0.85514 | 0.87306 | 0.86569 | 0.86268 | 1.41858 | 0.87474 |
| 2025H2 (n=20244) | 0.92381 | 0.88103 | 0.89733 | 0.88726 | 0.8852 | 1.46053 | 0.89852 |
| 2026H1 (n=20651) | 0.89414 | 0.85825 | 0.87064 | 0.86291 | 0.86165 | 1.41499 | 0.87409 |

De-vigged market benchmark (graded, never fit against; leader's P(over) vs consensus; level-adj = NF-D15 matched level-only foil):

| fold | two-sided coverage | n bench | Brier market | Brier lvl-adj | Brier model | bias mkt | bias model |
|---|---|---|---|---|---|---|---|
| 2023H2 | 98.7% | 9562 | 0.24399 | 0.24401 | 0.23775 | 0.0075 | 0.0077 |
| 2024H1 | 95.7% | 12782 | 0.2416 | 0.24147 | 0.23852 | 0.0128 | 0.0056 |
| 2024H2 | 94.0% | 19699 | 0.24232 | 0.2422 | 0.23974 | 0.011 | 0.0159 |
| 2025H1 | 98.3% | 19712 | 0.24313 | 0.24293 | 0.24138 | 0.0149 | 0.0088 |
| 2025H2 | 99.3% | 19546 | 0.24311 | 0.24266 | 0.23969 | 0.0258 | 0.0132 |
| 2026H1 | 99.4% | 19580 | 0.24359 | 0.24318 | 0.24123 | 0.0214 | -0.0024 |

Pooled (row-weighted): {'brier_market': 0.24294, 'brier_market_level_adj': 0.2427, 'brier_model': 0.24}  ·  model beats market in 6/6 folds

Coverage-80 FLOOR per fold (never a target — E2.1-r): [0.9152, 0.9164, 0.9206, 0.9226, 0.9183, 0.9123] (leader)

## Cross-market multiplicity (NF-D15 g″)

BH-FDR (q=0.05, 3 hypotheses): {'batter_total_bases': True, 'batter_hits': False, 'batter_home_runs': False}  ·  one-sided p per market: {'batter_hits': 1.0, 'batter_home_runs': 1.0, 'batter_total_bases': 0.0}

---
*Folds are the registered 2023H2..2026H1 blocks — a HARD ceiling (the 2023-05-03 archive floor was verified on the correct endpoint; no spend widens the window). Regular-season only; postseason application is extrapolation. Population is market-selected (books quote better hitters).*
