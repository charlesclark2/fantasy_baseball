# Clustered Feature Importance — home_win (Epic E1.3)

- Recipe: `glm_elasticnet(scorer)` · metric **brier** (lower = better) · pooled baseline 0.2433
- Features: **154** in **123** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 96/123** covering **120/154** features → drop/consolidate candidates (≈78% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δbrier) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C26 | 1 | +0.00272 | [+0.00188, +0.00361] | ✅ signal | `away_bp_eb_coverage_pct` |
| 2 | C9 | 2 | +0.00207 | [+0.00142, +0.00276] | ✅ signal | `elo_diff, pythagorean_win_exp_diff` |
| 3 | C27 | 1 | +0.00081 | [+0.00044, +0.00117] | ✅ signal | `home_pit_woba_against_std` |
| 4 | C42 | 1 | +0.00076 | [+0.00026, +0.00126] | ✅ signal | `home_away_bp_xwoba_against_30d_pct_diff` |
| 5 | C92 | 1 | +0.00069 | [+0.00034, +0.00103] | ✅ signal | `away_off_k_pct_std` |
| 6 | C7 | 2 | +0.00066 | [+0.00029, +0.00105] | ✅ signal | `home_bp_eb_xwoba, home_team_sequential_bullpen_xwoba` |
| 7 | C88 | 1 | +0.00057 | [+0.00023, +0.00090] | ✅ signal | `left_center_ft` |
| 8 | C2 | 3 | +0.00052 | [+0.00020, +0.00082] | ✅ signal | `home_elo, home_pythagorean_win_exp, home_team_sequential_win_prob` |
| 9 | C6 | 3 | +0.00037 | [+0.00009, +0.00064] | ✅ signal | `home_starter_bb_pct_std, home_starter_bb_pct_14d, home_starter_bb_pct_30d` |
| 10 | C10 | 2 | +0.00031 | [+0.00007, +0.00055] | ✅ signal | `away_pit_woba_against_std, away_pit_woba_against_30d` |
| 11 | C51 | 1 | +0.00027 | [+0.00009, +0.00044] | ✅ signal | `away_vs_lhp_xwoba_std` |
| 12 | C38 | 1 | +0.00024 | [+0.00010, +0.00038] | ✅ signal | `away_off_runs_per_game_std` |
| 13 | C37 | 1 | +0.00024 | [+0.00001, +0.00047] | ✅ signal | `home_away_starter_k_pct_std_pct_diff` |
| 14 | C34 | 1 | +0.00024 | [+0.00004, +0.00045] | ✅ signal | `home_away_off_woba_30d_pct_diff` |
| 15 | C75 | 1 | +0.00024 | [+0.00001, +0.00047] | ✅ signal | `away_starter_avg_ip_last_3` |
| 16 | C69 | 1 | +0.00023 | [+0.00002, +0.00046] | ✅ signal | `away_pit_bb_pct_7d` |
| 17 | C76 | 1 | +0.00022 | [+0.00001, +0.00042] | ✅ signal | `home_off_runs_per_game_14d` |
| 18 | C48 | 1 | +0.00019 | [-0.00013, +0.00050] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 19 | C87 | 1 | +0.00019 | [-0.00005, +0.00043] | 🟡 noise → drop | `away_off_bb_pct_7d` |
| 20 | C62 | 1 | +0.00018 | [+0.00005, +0.00031] | ✅ signal | `home_starter_avg_ip_season` |
| 21 | C45 | 1 | +0.00017 | [+0.00005, +0.00031] | ✅ signal | `home_starter_trailing_fip_30g` |
| 22 | C32 | 1 | +0.00017 | [+0.00007, +0.00027] | ✅ signal | `home_games_back` |
| 23 | C107 | 1 | +0.00016 | [-0.00008, +0.00041] | 🟡 noise → drop | `home_starter_hard_hit_pct_14d` |
| 24 | C59 | 1 | +0.00016 | [+0.00006, +0.00025] | ✅ signal | `home_pit_k_pct_7d` |
| 25 | C50 | 1 | +0.00015 | [+0.00005, +0.00027] | ✅ signal | `away_xwoba_with_runners_on_30d` |
| 26 | C86 | 1 | +0.00014 | [-0.00024, +0.00054] | 🟡 noise → drop | `right_center_ft` |
| 27 | C31 | 1 | +0.00014 | [-0.00005, +0.00032] | 🟡 noise → drop | `away_starter_stuff_plus` |
| 28 | C36 | 1 | +0.00013 | [+0.00004, +0.00022] | ✅ signal | `home_pit_k_pct_std` |
| 29 | C52 | 1 | +0.00012 | [-0.00013, +0.00038] | 🟡 noise → drop | `away_off_hard_hit_pct_std` |
| 30 | C16 | 2 | +0.00012 | [-0.00008, +0.00032] | 🟡 noise → drop | `home_off_bb_pct_std, home_off_bb_pct_30d` |
| 31 | C15 | 2 | +0.00011 | [-0.00007, +0.00029] | 🟡 noise → drop | `away_starter_whiff_rate_std, away_starter_whiff_rate_14d` |
| 32 | C44 | 1 | +0.00010 | [+0.00000, +0.00021] | ✅ signal | `away_pit_k_pct_7d` |
| 33 | C4 | 3 | +0.00010 | [-0.00004, +0.00024] | 🟡 noise → drop | `home_off_xwoba_std, home_off_xwoba_30d, home_team_sequential_woba` |
| 34 | C116 | 1 | +0.00009 | [-0.00010, +0.00029] | 🟡 noise → drop | `home_starter_barrel_pct_30d` |
| 35 | C40 | 1 | +0.00008 | [-0.00007, +0.00023] | 🟡 noise → drop | `away_starter_trailing_ra9_30g` |
| 36 | C68 | 1 | +0.00007 | [-0.00028, +0.00043] | 🟡 noise → drop | `home_off_runs_per_game_30d` |
| 37 | C43 | 1 | +0.00007 | [-0.00000, +0.00015] | 🟡 noise → drop | `home_starter_trailing_ra9_30g` |
| 38 | C47 | 1 | +0.00007 | [-0.00009, +0.00022] | 🟡 noise → drop | `away_starter_k_pct_30d` |
| 39 | C23 | 2 | +0.00006 | [-0.00005, +0.00016] | 🟡 noise → drop | `away_starter_bb_pct_std, away_starter_bb_pct_30d` |
| 40 | C103 | 1 | +0.00006 | [-0.00007, +0.00018] | 🟡 noise → drop | `home_starter_hard_hit_pct_std` |
| 41 | C55 | 1 | +0.00006 | [-0.00001, +0.00013] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 42 | C108 | 1 | +0.00006 | [-0.00017, +0.00027] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 43 | C105 | 1 | +0.00005 | [-0.00006, +0.00016] | 🟡 noise → drop | `away_starter_bb_pct_7d` |
| 44 | C89 | 1 | +0.00005 | [-0.00013, +0.00023] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 45 | C102 | 1 | +0.00004 | [-0.00021, +0.00029] | 🟡 noise → drop | `right_line_ft` |
| 46 | C93 | 1 | +0.00004 | [-0.00010, +0.00018] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 47 | C97 | 1 | +0.00004 | [-0.00001, +0.00008] | 🟡 noise → drop | `home_starter_bb_pct_vs_lhb` |
| 48 | C67 | 1 | +0.00003 | [-0.00007, +0.00014] | 🟡 noise → drop | `away_vs_lhp_woba_30d` |
| 49 | C94 | 1 | +0.00003 | [-0.00001, +0.00008] | 🟡 noise → drop | `away_pit_barrel_pct_30d` |
| 50 | C115 | 1 | +0.00003 | [-0.00004, +0.00010] | 🟡 noise → drop | `away_pit_xwoba_7d_minus_30d` |
| 51 | C121 | 1 | +0.00003 | [-0.00008, +0.00015] | 🟡 noise → drop | `has_starter_platoon_data` |
| 52 | C28 | 1 | +0.00003 | [-0.00008, +0.00014] | 🟡 noise → drop | `away_pit_k_pct_std` |
| 53 | C90 | 1 | +0.00003 | [-0.00002, +0.00007] | 🟡 noise → drop | `home_starter_whiff_rate_vs_lhb` |
| 54 | C82 | 1 | +0.00003 | [-0.00005, +0.00010] | 🟡 noise → drop | `home_starter_whiff_rate_vs_rhb` |
| 55 | C118 | 1 | +0.00002 | [-0.00005, +0.00010] | 🟡 noise → drop | `away_starter_hard_hit_pct_7d` |
| 56 | C39 | 1 | +0.00002 | [-0.00029, +0.00032] | 🟡 noise → drop | `home_away_starter_xwoba_against_std_pct_diff` |
| 57 | C22 | 2 | +0.00002 | [-0.00000, +0.00004] | 🟡 noise → drop | `home_bp_whiff_rate_30d, home_bp_whiff_rate_14d` |
| 58 | C61 | 1 | +0.00001 | [-0.00007, +0.00010] | 🟡 noise → drop | `away_starter_changeup_stuff_plus` |
| 59 | C58 | 1 | +0.00001 | [-0.00001, +0.00004] | 🟡 noise → drop | `home_starter_csw_pct_season` |
| 60 | C106 | 1 | +0.00001 | [-0.00019, +0.00022] | 🟡 noise → drop | `home_bp_hard_hit_pct_14d` |
| 61 | C30 | 1 | +0.00001 | [-0.00001, +0.00003] | 🟡 noise → drop | `away_games_back` |
| 62 | C19 | 2 | +0.00001 | [-0.00016, +0.00017] | 🟡 noise → drop | `away_starter_batter_chase_rate_std, away_starter_batter_chase_rate_30d` |
| 63 | C35 | 1 | +0.00001 | [-0.00004, +0.00006] | 🟡 noise → drop | `away_starter_proj_fip` |
| 64 | C49 | 1 | +0.00001 | [-0.00011, +0.00012] | 🟡 noise → drop | `away_woba_against_with_risp_30d` |
| 65 | C63 | 1 | +0.00001 | [-0.00004, +0.00005] | 🟡 noise → drop | `away_vs_rhp_woba_30d` |
| 66 | C70 | 1 | +0.00000 | [-0.00002, +0.00003] | 🟡 noise → drop | `away_bp_xwoba_against_14d` |
| 67 | C65 | 1 | +0.00000 | [-0.00001, +0.00002] | 🟡 noise → drop | `home_starter_whiff_rate_14d` |
| 68 | C83 | 1 | +0.00000 | [-0.00007, +0.00008] | 🟡 noise → drop | `away_pit_hard_hit_pct_30d` |
| 69 | C98 | 1 | +0.00000 | [-0.00004, +0.00004] | 🟡 noise → drop | `away_bp_innings_pitched_14d` |
| 70 | C12 | 2 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against, away_starter_eb_xwoba_against_sequential` |
| 71 | C14 | 2 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against, home_starter_eb_xwoba_against_sequential` |
| 72 | C41 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 73 | C84 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_uncertainty` |
| 74 | C95 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_uncertainty` |
| 75 | C122 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 76 | C114 | 1 | -0.00000 | [-0.00001, +0.00001] | 🟡 noise → drop | `away_closer_used_prev_2d` |
| 77 | C104 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_fip_ra9_gap` |
| 78 | C109 | 1 | -0.00000 | [-0.00003, +0.00002] | 🟡 noise → drop | `series_game_number` |
| 79 | C17 | 2 | -0.00000 | [-0.00008, +0.00007] | 🟡 noise → drop | `away_bp_k_pct_30d, away_bp_k_pct_14d` |
| 80 | C91 | 1 | -0.00000 | [-0.00010, +0.00009] | 🟡 noise → drop | `away_team_oaa_prior_season` |
| 81 | C111 | 1 | -0.00000 | [-0.00005, +0.00004] | 🟡 noise → drop | `away_closer_used_prev_1d` |
| 82 | C24 | 2 | -0.00001 | [-0.00026, +0.00025] | 🟡 noise → drop | `away_starter_hard_hit_pct_std, away_starter_hard_hit_pct_30d` |
| 83 | C74 | 1 | -0.00001 | [-0.00002, +0.00001] | 🟡 noise → drop | `home_off_hard_hit_pct_std` |
| 84 | C46 | 1 | -0.00001 | [-0.00005, +0.00004] | 🟡 noise → drop | `home_starter_k_pct_30d` |
| 85 | C112 | 1 | -0.00001 | [-0.00004, +0.00003] | 🟡 noise → drop | `home_off_bb_pct_7d` |
| 86 | C66 | 1 | -0.00001 | [-0.00005, +0.00003] | 🟡 noise → drop | `away_starter_xwoba_vs_rhb` |
| 87 | C110 | 1 | -0.00001 | [-0.00003, +0.00002] | 🟡 noise → drop | `home_starter_bb_pct_vs_rhb` |
| 88 | C25 | 2 | -0.00001 | [-0.00013, +0.00013] | 🟡 noise → drop | `home_starter_barrel_pct_14d, home_starter_barrel_pct_7d` |
| 89 | C80 | 1 | -0.00001 | [-0.00013, +0.00011] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 90 | C100 | 1 | -0.00002 | [-0.00007, +0.00002] | 🟡 noise → drop | `home_starter_xwoba_7d_minus_std` |
| 91 | C0 | 3 | -0.00003 | [-0.00016, +0.00010] | 🟡 noise → drop | `home_bp_eb_uncertainty, away_bp_eb_uncertainty, away_losses` |
| 92 | C5 | 3 | -0.00003 | [-0.00012, +0.00006] | 🟡 noise → drop | `home_starter_xwoba_against_14d, home_starter_xwoba_against_30d, home_starter_xwoba_against_std` |
| 93 | C78 | 1 | -0.00003 | [-0.00007, +0.00002] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 94 | C99 | 1 | -0.00003 | [-0.00012, +0.00006] | 🟡 noise → drop | `left_line_ft` |
| 95 | C120 | 1 | -0.00003 | [-0.00014, +0.00009] | 🟡 noise → drop | `away_consecutive_away_games` |
| 96 | C71 | 1 | -0.00003 | [-0.00021, +0.00013] | 🟡 noise → drop | `away_starter_k_pct_vs_lhb` |
| 97 | C64 | 1 | -0.00004 | [-0.00008, +0.00000] | 🟡 noise → drop | `away_starter_avg_ip_season` |
| 98 | C57 | 1 | -0.00004 | [-0.00019, +0.00012] | 🟡 noise → drop | `away_bp_xwoba_against_30d` |
| 99 | C20 | 2 | -0.00004 | [-0.00009, +0.00002] | 🟡 noise → drop | `home_vs_lhp_xwoba_std, home_vs_lhp_woba_std` |
| 100 | C60 | 1 | -0.00005 | [-0.00009, +0.00000] | 🟡 noise → drop | `home_woba_against_with_risp_30d` |
| 101 | C8 | 2 | -0.00005 | [-0.00025, +0.00017] | 🟡 noise → drop | `away_bp_eb_xwoba, away_team_sequential_bullpen_xwoba` |
| 102 | C113 | 1 | -0.00005 | [-0.00017, +0.00007] | 🟡 noise → drop | `home_win_rate_trailing_3yr` |
| 103 | C77 | 1 | -0.00005 | [-0.00012, +0.00002] | 🟡 noise → drop | `center_ft` |
| 104 | C13 | 2 | -0.00005 | [-0.00020, +0.00009] | 🟡 noise → drop | `away_pit_xwoba_against_14d, away_pit_xwoba_against_7d` |
| 105 | C85 | 1 | -0.00006 | [-0.00012, +0.00000] | 🟡 noise → drop | `away_starter_whiff_rate_vs_rhb` |
| 106 | C119 | 1 | -0.00006 | [-0.00014, +0.00002] | 🟡 noise → drop | `home_starter_appearances_30d` |
| 107 | C11 | 2 | -0.00007 | [-0.00019, +0.00005] | 🟡 noise → drop | `home_pit_xwoba_against_std, home_pit_xwoba_against_30d` |
| 108 | C54 | 1 | -0.00008 | [-0.00024, +0.00008] | 🟡 noise → drop | `away_starter_csw_pct_3start` |
| 109 | C96 | 1 | -0.00008 | [-0.00016, -0.00000] | ✅ signal | `home_off_hard_hit_pct_7d` |
| 110 | C81 | 1 | -0.00008 | [-0.00030, +0.00011] | 🟡 noise → drop | `away_starter_xwoba_against_14d` |
| 111 | C56 | 1 | -0.00008 | [-0.00024, +0.00009] | 🟡 noise → drop | `home_pit_hard_hit_pct_std` |
| 112 | C21 | 2 | -0.00009 | [-0.00018, +0.00001] | 🟡 noise → drop | `home_bp_k_pct_30d, home_bp_k_pct_14d` |
| 113 | C3 | 3 | -0.00009 | [-0.00037, +0.00021] | 🟡 noise → drop | `away_off_xwoba_std, away_off_xwoba_30d, away_team_sequential_woba` |
| 114 | C53 | 1 | -0.00010 | [-0.00024, +0.00004] | 🟡 noise → drop | `home_starter_k_pct_vs_lhb` |
| 115 | C101 | 1 | -0.00011 | [-0.00025, +0.00002] | 🟡 noise → drop | `home_woba_with_risp_30d` |
| 116 | C117 | 1 | -0.00012 | [-0.00031, +0.00008] | 🟡 noise → drop | `home_bp_innings_pitched_30d` |
| 117 | C18 | 2 | -0.00012 | [-0.00034, +0.00012] | 🟡 noise → drop | `away_pit_bb_pct_std, away_pit_bb_pct_30d` |
| 118 | C72 | 1 | -0.00013 | [-0.00043, +0.00016] | 🟡 noise → drop | `home_bp_xwoba_against_30d` |
| 119 | C33 | 1 | -0.00014 | [-0.00033, +0.00006] | 🟡 noise → drop | `home_pit_woba_against_14d` |
| 120 | C79 | 1 | -0.00021 | [-0.00041, -0.00001] | ✅ signal | `away_woba_with_risp_30d` |
| 121 | C29 | 1 | -0.00022 | [-0.00062, +0.00022] | 🟡 noise → drop | `elevation_ft` |
| 122 | C73 | 1 | -0.00030 | [-0.00058, +0.00000] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 123 | C1 | 3 | -0.00032 | [-0.00058, -0.00008] | ✅ signal | `away_elo, away_pythagorean_win_exp, away_team_sequential_win_prob` |

## Payoff (E1.3 AC)
Dropping the 96 noise clusters (120 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_home_win_bullpen_v3_stuffplus_deleaked_scorer_glm_elasticnet_pre_lineup_home_win.json`_