# NF-W6d — the served per-stat distribution substrate (52 cells)

**Generated:** 2026-08-16T01:29:39+00:00 · smoke: False · rows 6721 · serve gw 174 (2025 wk 18)

> ⚖️ Edge-independent projection product — `best_alpha = 0`, deploy-held, NF-G0 challenger. Every cell is a calibrated RANGE; `source` says whether it is a bake-off winner (nf_w6b / nf_w6b_c / nf_w6d_b_ship) or a Phase-C calibrated default (nf_w6d_c_default). No edge / ROI / win-rate claim.

cells by source: {'nf_w6b': 6, 'nf_w6b_c': 1, 'nf_w6d_c_default': 36, 'nf_w6d_b_ship': 9}; calibration warnings: none

| cell | form | source | n | fresh CRPS | cov80 | pred P(0) | real P(0) |
|---|---|---|---|---|---|---|---|
| QB|attempts | climatology | nf_w6d_c_default | 89 | 7.5423 | 0.9438 | 0.5528 | 0.5393 |
| QB|carries | count_negbin | nf_w6d_c_default | 89 | 0.9495 | 0.8989 | 0.4999 | 0.5618 |
| QB|fumbles_lost | count_negbin | nf_w6d_c_default | 89 | 0.0886 | 0.9551 | 0.9462 | 0.9101 |
| QB|passing_interceptions | knn_quantile | nf_w6d_b_ship | 89 | 0.1622 | 0.9326 | 0.8023 | 0.7978 |
| QB|passing_tds | knn_quantile | nf_w6b | 89 | 0.3041 | 0.9551 | 0.6992 | 0.764 |
| QB|passing_yards | lgbm_quantile_tail | nf_w6b | 89 | 37.8863 | 0.764 | 0.3295 | 0.5506 |
| QB|receiving_tds | climatology | nf_w6d_c_default | 89 | 0.0 | 1.0 | 1.0 | 1.0 |
| QB|receiving_yards | climatology | nf_w6d_c_default | 89 | 0.393 | 0.9775 | 0.995 | 0.9775 |
| QB|receptions | climatology | nf_w6d_c_default | 89 | 0.0336 | 0.9888 | 0.995 | 0.9888 |
| QB|rushing_tds | count_negbin | nf_w6d_b_ship | 89 | 0.0567 | 0.9551 | 0.9542 | 0.9438 |
| QB|rushing_yards | lgbm_hurdle_tail | nf_w6b | 89 | 5.2637 | 0.7978 | 0.6602 | 0.5955 |
| QB|targets | climatology | nf_w6d_c_default | 89 | 0.0336 | 0.9888 | 0.9899 | 0.9888 |
| QB|two_pt | count_negbin | nf_w6d_c_default | 89 | 0.0334 | 0.9663 | 0.9709 | 0.9663 |
| RB|attempts | climatology | nf_w6d_c_default | 126 | 0.0 | 1.0 | 1.0 | 1.0 |
| RB|carries | lgbm_hurdle_tail | nf_w6d_b_ship | 126 | 2.8134 | 0.8016 | 0.408 | 0.3492 |
| RB|fumbles_lost | count_negbin | nf_w6d_c_default | 126 | 0.0232 | 0.9762 | 0.9715 | 0.9762 |
| RB|passing_interceptions | climatology | nf_w6d_c_default | 126 | 0.0 | 1.0 | 1.0 | 1.0 |
| RB|passing_tds | climatology | nf_w6d_c_default | 126 | 0.0 | 1.0 | 1.0 | 1.0 |
| RB|passing_yards | climatology | nf_w6d_c_default | 126 | 0.0 | 1.0 | 1.0 | 1.0 |
| RB|receiving_tds | count_negbin | nf_w6d_c_default | 126 | 0.0488 | 0.9683 | 0.9641 | 0.9444 |
| RB|receiving_yards | climatology | nf_w6d_c_default | 126 | 5.6739 | 0.9286 | 0.5628 | 0.4921 |
| RB|receptions | lgbm_hurdle_tail | nf_w6d_b_ship | 126 | 0.6182 | 0.873 | 0.5685 | 0.4762 |
| RB|rushing_tds | knn_quantile | nf_w6b_c | 126 | 0.1181 | 0.9444 | 0.8591 | 0.9048 |
| RB|rushing_yards | lgbm_hurdle_tail | nf_w6b | 126 | 13.7019 | 0.8254 | 0.4218 | 0.3571 |
| RB|targets | count_negbin | nf_w6d_c_default | 126 | 0.7298 | 0.9286 | 0.4519 | 0.4603 |
| RB|two_pt | count_negbin | nf_w6d_c_default | 126 | 0.0158 | 0.9841 | 0.9937 | 0.9841 |
| TE|attempts | climatology | nf_w6d_c_default | 115 | 0.0 | 1.0 | 1.0 | 1.0 |
| TE|carries | climatology | nf_w6d_c_default | 115 | 0.0346 | 0.9826 | 0.9899 | 0.9826 |
| TE|fumbles_lost | count_negbin | nf_w6d_c_default | 115 | 0.0172 | 0.9826 | 0.994 | 0.9826 |
| TE|passing_interceptions | climatology | nf_w6d_c_default | 115 | 0.0 | 1.0 | 1.0 | 1.0 |
| TE|passing_tds | climatology | nf_w6d_c_default | 115 | 0.0 | 1.0 | 1.0 | 1.0 |
| TE|passing_yards | climatology | nf_w6d_c_default | 115 | 0.0 | 1.0 | 1.0 | 1.0 |
| TE|receiving_tds | count_negbin | nf_w6d_c_default | 115 | 0.0994 | 0.9565 | 0.9011 | 0.8957 |
| TE|receiving_yards | lgbm_hurdle_tail | nf_w6b | 115 | 7.3094 | 0.887 | 0.5219 | 0.4696 |
| TE|receptions | lgbm_hurdle_tail | nf_w6d_b_ship | 115 | 0.6195 | 0.9217 | 0.5018 | 0.4609 |
| TE|rushing_tds | climatology | nf_w6d_c_default | 115 | 0.0087 | 0.9913 | 1.0 | 0.9913 |
| TE|rushing_yards | climatology | nf_w6d_c_default | 115 | 0.0346 | 0.9826 | 0.9899 | 0.9826 |
| TE|targets | lgbm_hurdle_tail | nf_w6d_b_ship | 115 | 0.8775 | 0.8522 | 0.4301 | 0.4174 |
| TE|two_pt | count_negbin | nf_w6d_c_default | 115 | 0.0088 | 0.9913 | 0.9949 | 0.9913 |
| WR|attempts | climatology | nf_w6d_c_default | 187 | 0.0053 | 0.9947 | 0.995 | 0.9947 |
| WR|carries | climatology | nf_w6d_c_default | 187 | 0.1051 | 0.9144 | 0.9095 | 0.9144 |
| WR|fumbles_lost | count_negbin | nf_w6d_c_default | 187 | 0.0003 | 1.0 | 0.9902 | 1.0 |
| WR|passing_interceptions | climatology | nf_w6d_c_default | 187 | 0.0 | 1.0 | 1.0 | 1.0 |
| WR|passing_tds | climatology | nf_w6d_c_default | 187 | 0.0 | 1.0 | 1.0 | 1.0 |
| WR|passing_yards | climatology | nf_w6d_c_default | 187 | 0.0 | 1.0 | 1.0 | 1.0 |
| WR|receiving_tds | knn_quantile | nf_w6d_b_ship | 187 | 0.089 | 0.9626 | 0.8725 | 0.9144 |
| WR|receiving_yards | lgbm_hurdle_tail | nf_w6b | 187 | 11.7885 | 0.861 | 0.4418 | 0.4439 |
| WR|receptions | lgbm_hurdle_tail | nf_w6d_b_ship | 187 | 0.8666 | 0.861 | 0.4331 | 0.4439 |
| WR|rushing_tds | climatology | nf_w6d_c_default | 187 | 0.0 | 1.0 | 1.0 | 1.0 |
| WR|rushing_yards | climatology | nf_w6d_c_default | 187 | 0.6541 | 0.9144 | 0.9246 | 0.9144 |
| WR|targets | lgbm_hurdle_tail | nf_w6d_b_ship | 187 | 1.3378 | 0.8396 | 0.3594 | 0.369 |
| WR|two_pt | count_negbin | nf_w6d_c_default | 187 | 0.0163 | 0.984 | 0.9918 | 0.984 |

built artifact: `quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_w6d_served_stat_distributions.parquet` sha256 a2739df4d4ed73d67be66c91865ef96455dbd52fec146a0a4a74ab374fb96391 (6721 rows)

promote blockers: NF-C6 Phase 2 — no weekly serving path exists (the deployed fantasy surface is the SEASON raw line `projections.json`; there is no weekly endpoint to attach a player-week distribution to); NF-G0 promotion review — the ten gates plus a PM decision; NF-W6b promoted nothing and this story stages, it does not promote; the downstream arbitrary-league re-scoring consumer is a FOLLOW-ON story — the moment a scorer reads these distributions the three-implementations parity tax (fantasy_engine / the browser TS scorer / the Lambda scorer) triggers under the merge-gate parity test; NF-W6d Phase-C DEFAULT cells are calibrated ranges, not bake-off winners — the assembly consumer must read `source`/`calibration_warning` and never present a default as a conditional projection