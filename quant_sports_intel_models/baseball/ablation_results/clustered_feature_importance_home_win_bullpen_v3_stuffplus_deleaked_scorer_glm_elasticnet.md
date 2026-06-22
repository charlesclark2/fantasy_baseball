# Clustered Feature Importance — home_win (Epic E1.3)

- Recipe: `glm_elasticnet(scorer)` · metric **brier** (lower = better) · pooled baseline 0.2403
- Features: **209** in **174** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 143/174** covering **169/209** features → drop/consolidate candidates (≈81% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δbrier) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C30 | 1 | +0.00499 | [+0.00382, +0.00621] | ✅ signal | `home_bp_eb_coverage_pct` |
| 2 | C31 | 1 | +0.00282 | [+0.00178, +0.00387] | ✅ signal | `away_bp_eb_coverage_pct` |
| 3 | C9 | 2 | +0.00219 | [+0.00150, +0.00291] | ✅ signal | `elo_diff, pythagorean_win_exp_diff` |
| 4 | C32 | 1 | +0.00100 | [+0.00058, +0.00142] | ✅ signal | `home_pit_woba_against_std` |
| 5 | C50 | 1 | +0.00080 | [+0.00028, +0.00134] | ✅ signal | `home_away_bp_xwoba_against_30d_pct_diff` |
| 6 | C110 | 1 | +0.00074 | [+0.00035, +0.00114] | ✅ signal | `away_avg_k_pct_std` |
| 7 | C2 | 3 | +0.00066 | [+0.00033, +0.00099] | ✅ signal | `home_elo, home_pythagorean_win_exp, home_team_sequential_win_prob` |
| 8 | C7 | 2 | +0.00061 | [+0.00024, +0.00098] | ✅ signal | `home_bp_eb_xwoba, home_team_sequential_bullpen_xwoba` |
| 9 | C121 | 1 | +0.00048 | [+0.00017, +0.00080] | ✅ signal | `left_center_ft` |
| 10 | C15 | 2 | +0.00048 | [-0.00018, +0.00112] | 🟡 noise → drop | `away_avg_xwoba_std, away_avg_xwoba_30d` |
| 11 | C103 | 1 | +0.00041 | [+0.00013, +0.00070] | ✅ signal | `away_starter_avg_ip_last_3` |
| 12 | C89 | 1 | +0.00033 | [+0.00008, +0.00058] | ✅ signal | `away_pit_bb_pct_7d` |
| 13 | C6 | 3 | +0.00032 | [+0.00004, +0.00062] | ✅ signal | `home_starter_bb_pct_std, home_starter_bb_pct_14d, home_starter_bb_pct_30d` |
| 14 | C126 | 1 | +0.00032 | [+0.00012, +0.00051] | ✅ signal | `away_off_k_pct_std` |
| 15 | C137 | 1 | +0.00030 | [+0.00005, +0.00053] | ✅ signal | `home_lineup_vs_away_starter_h2h_xwoba` |
| 16 | C61 | 1 | +0.00029 | [+0.00004, +0.00054] | ✅ signal | `home_avg_woba_std` |
| 17 | C65 | 1 | +0.00029 | [+0.00012, +0.00046] | ✅ signal | `away_avg_woba_std` |
| 18 | C125 | 1 | +0.00027 | [+0.00005, +0.00049] | ✅ signal | `away_avg_whiff_rate_30d` |
| 19 | C43 | 1 | +0.00026 | [+0.00007, +0.00047] | ✅ signal | `home_away_starter_k_pct_std_pct_diff` |
| 20 | C17 | 2 | +0.00024 | [+0.00006, +0.00041] | ✅ signal | `home_avg_xwoba_std, home_avg_xwoba_30d` |
| 21 | C75 | 1 | +0.00021 | [-0.00011, +0.00053] | 🟡 noise → drop | `away_avg_barrel_pct_std` |
| 22 | C101 | 1 | +0.00020 | [-0.00006, +0.00048] | 🟡 noise → drop | `away_n_power_pull` |
| 23 | C62 | 1 | +0.00019 | [+0.00002, +0.00037] | ✅ signal | `away_xwoba_with_runners_on_30d` |
| 24 | C40 | 1 | +0.00019 | [+0.00006, +0.00032] | ✅ signal | `home_away_off_woba_30d_pct_diff` |
| 25 | C59 | 1 | +0.00017 | [+0.00005, +0.00029] | ✅ signal | `away_lineup_vs_home_starter_k_pct_adj` |
| 26 | C148 | 1 | +0.00017 | [-0.00005, +0.00039] | 🟡 noise → drop | `home_starter_hard_hit_pct_14d` |
| 27 | C19 | 2 | +0.00015 | [-0.00003, +0.00033] | 🟡 noise → drop | `home_off_bb_pct_std, home_off_bb_pct_30d` |
| 28 | C95 | 1 | +0.00014 | [-0.00018, +0.00046] | 🟡 noise → drop | `home_bp_xwoba_against_30d` |
| 29 | C72 | 1 | +0.00014 | [+0.00005, +0.00023] | ✅ signal | `home_pit_k_pct_7d` |
| 30 | C105 | 1 | +0.00013 | [-0.00002, +0.00029] | 🟡 noise → drop | `home_off_runs_per_game_14d` |
| 31 | C166 | 1 | +0.00013 | [-0.00011, +0.00037] | 🟡 noise → drop | `home_starter_barrel_pct_30d` |
| 32 | C58 | 1 | +0.00013 | [-0.00017, +0.00043] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 33 | C78 | 1 | +0.00012 | [+0.00001, +0.00022] | ✅ signal | `home_starter_avg_ip_season` |
| 34 | C14 | 2 | +0.00011 | [-0.00010, +0.00032] | 🟡 noise → drop | `home_lineup_avg_woba_vs_cluster, home_lineup_avg_xwoba_vs_cluster` |
| 35 | C114 | 1 | +0.00011 | [-0.00005, +0.00026] | 🟡 noise → drop | `away_pit_hard_hit_pct_30d` |
| 36 | C53 | 1 | +0.00010 | [-0.00004, +0.00025] | 🟡 noise → drop | `away_pit_k_pct_7d` |
| 37 | C149 | 1 | +0.00010 | [-0.00028, +0.00049] | 🟡 noise → drop | `away_lineup_k_pct_vs_starter_archetype` |
| 38 | C63 | 1 | +0.00010 | [-0.00003, +0.00023] | 🟡 noise → drop | `away_vs_lhp_xwoba_std` |
| 39 | C122 | 1 | +0.00010 | [-0.00013, +0.00032] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 40 | C10 | 2 | +0.00010 | [-0.00005, +0.00025] | 🟡 noise → drop | `away_pit_woba_against_std, away_pit_woba_against_30d` |
| 41 | C150 | 1 | +0.00010 | [-0.00012, +0.00032] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 42 | C27 | 2 | +0.00010 | [-0.00014, +0.00035] | 🟡 noise → drop | `away_starter_hard_hit_pct_std, away_starter_hard_hit_pct_30d` |
| 43 | C18 | 2 | +0.00010 | [-0.00008, +0.00026] | 🟡 noise → drop | `away_starter_whiff_rate_std, away_starter_whiff_rate_14d` |
| 44 | C37 | 1 | +0.00009 | [+0.00002, +0.00016] | ✅ signal | `home_games_back` |
| 45 | C144 | 1 | +0.00009 | [-0.00004, +0.00022] | 🟡 noise → drop | `away_lineup_cluster_slot_coverage` |
| 46 | C152 | 1 | +0.00008 | [-0.00004, +0.00020] | 🟡 noise → drop | `home_lineup_archetype_pa_coverage` |
| 47 | C97 | 1 | +0.00008 | [-0.00004, +0.00020] | 🟡 noise → drop | `home_catcher_defensive_runs` |
| 48 | C87 | 1 | +0.00008 | [-0.00006, +0.00022] | 🟡 noise → drop | `away_vs_lhp_woba_30d` |
| 49 | C141 | 1 | +0.00008 | [-0.00017, +0.00032] | 🟡 noise → drop | `right_line_ft` |
| 50 | C77 | 1 | +0.00008 | [-0.00016, +0.00030] | 🟡 noise → drop | `away_n_no_label` |
| 51 | C127 | 1 | +0.00008 | [-0.00004, +0.00020] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 52 | C54 | 1 | +0.00007 | [+0.00001, +0.00014] | ✅ signal | `home_starter_trailing_fip_30g` |
| 53 | C0 | 3 | +0.00007 | [-0.00015, +0.00032] | 🟡 noise → drop | `home_bp_eb_uncertainty, away_bp_eb_uncertainty, away_losses` |
| 54 | C45 | 1 | +0.00007 | [-0.00021, +0.00035] | 🟡 noise → drop | `home_away_starter_xwoba_against_std_pct_diff` |
| 55 | C112 | 1 | +0.00007 | [-0.00000, +0.00014] | 🟡 noise → drop | `home_starter_whiff_rate_vs_rhb` |
| 56 | C46 | 1 | +0.00006 | [-0.00011, +0.00024] | 🟡 noise → drop | `away_starter_trailing_ra9_30g` |
| 57 | C68 | 1 | +0.00006 | [-0.00003, +0.00016] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 58 | C29 | 2 | +0.00006 | [-0.00013, +0.00025] | 🟡 noise → drop | `ump_run_impact_zscore, ump_accuracy_zscore` |
| 59 | C93 | 1 | +0.00006 | [-0.00013, +0.00025] | 🟡 noise → drop | `away_starter_k_pct_vs_lhb` |
| 60 | C84 | 1 | +0.00006 | [-0.00000, +0.00012] | 🟡 noise → drop | `home_avg_woba_vs_rhp` |
| 61 | C131 | 1 | +0.00006 | [-0.00012, +0.00023] | 🟡 noise → drop | `away_avg_k_pct_vs_rhp` |
| 62 | C57 | 1 | +0.00005 | [-0.00010, +0.00021] | 🟡 noise → drop | `away_starter_k_pct_30d` |
| 63 | C26 | 2 | +0.00005 | [-0.00007, +0.00017] | 🟡 noise → drop | `away_starter_bb_pct_std, away_starter_bb_pct_30d` |
| 64 | C104 | 1 | +0.00004 | [-0.00001, +0.00010] | 🟡 noise → drop | `home_avg_hard_hit_pct_std` |
| 65 | C145 | 1 | +0.00004 | [-0.00008, +0.00016] | 🟡 noise → drop | `away_starter_bb_pct_7d` |
| 66 | C22 | 2 | +0.00004 | [-0.00010, +0.00019] | 🟡 noise → drop | `away_starter_batter_chase_rate_std, away_starter_batter_chase_rate_30d` |
| 67 | C81 | 1 | +0.00004 | [-0.00001, +0.00009] | 🟡 noise → drop | `away_vs_rhp_woba_30d` |
| 68 | C129 | 1 | +0.00004 | [-0.00008, +0.00016] | 🟡 noise → drop | `away_lineup_vs_home_starter_h2h_xwoba` |
| 69 | C51 | 1 | +0.00004 | [-0.00005, +0.00012] | 🟡 noise → drop | `home_starter_trailing_ra9_30g` |
| 70 | C79 | 1 | +0.00004 | [-0.00004, +0.00011] | 🟡 noise → drop | `away_avg_xwoba_vs_lhp` |
| 71 | C28 | 2 | +0.00003 | [-0.00011, +0.00018] | 🟡 noise → drop | `home_starter_barrel_pct_14d, home_starter_barrel_pct_7d` |
| 72 | C64 | 1 | +0.00003 | [-0.00014, +0.00020] | 🟡 noise → drop | `away_off_hard_hit_pct_std` |
| 73 | C151 | 1 | +0.00003 | [-0.00003, +0.00010] | 🟡 noise → drop | `home_lineup_archetype_slot_coverage` |
| 74 | C158 | 1 | +0.00003 | [-0.00005, +0.00011] | 🟡 noise → drop | `home_lineup_vs_away_starter_bb_pct_adj` |
| 75 | C168 | 1 | +0.00003 | [-0.00005, +0.00010] | 🟡 noise → drop | `away_starter_hard_hit_pct_7d` |
| 76 | C71 | 1 | +0.00003 | [-0.00001, +0.00006] | 🟡 noise → drop | `home_starter_csw_pct_season` |
| 77 | C142 | 1 | +0.00002 | [-0.00012, +0.00016] | 🟡 noise → drop | `home_starter_hard_hit_pct_std` |
| 78 | C11 | 2 | +0.00002 | [-0.00005, +0.00010] | 🟡 noise → drop | `home_pit_xwoba_against_std, home_pit_xwoba_against_30d` |
| 79 | C138 | 1 | +0.00002 | [-0.00009, +0.00014] | 🟡 noise → drop | `left_line_ft` |
| 80 | C20 | 2 | +0.00002 | [-0.00004, +0.00008] | 🟡 noise → drop | `away_bp_k_pct_30d, away_bp_k_pct_14d` |
| 81 | C164 | 1 | +0.00002 | [-0.00011, +0.00015] | 🟡 noise → drop | `away_pit_xwoba_7d_minus_30d` |
| 82 | C135 | 1 | +0.00002 | [-0.00002, +0.00006] | 🟡 noise → drop | `home_starter_bb_pct_vs_lhb` |
| 83 | C100 | 1 | +0.00002 | [-0.00006, +0.00010] | 🟡 noise → drop | `home_avg_barrel_pct_std` |
| 84 | C70 | 1 | +0.00002 | [-0.00005, +0.00008] | 🟡 noise → drop | `away_bp_xwoba_against_30d` |
| 85 | C44 | 1 | +0.00002 | [-0.00000, +0.00004] | 🟡 noise → drop | `away_off_runs_per_game_std` |
| 86 | C116 | 1 | +0.00001 | [-0.00028, +0.00032] | 🟡 noise → drop | `away_lineup_avg_swing_length` |
| 87 | C146 | 1 | +0.00001 | [-0.00017, +0.00019] | 🟡 noise → drop | `home_bp_hard_hit_pct_14d` |
| 88 | C35 | 1 | +0.00001 | [-0.00002, +0.00004] | 🟡 noise → drop | `away_games_back` |
| 89 | C134 | 1 | +0.00001 | [-0.00000, +0.00002] | 🟡 noise → drop | `home_avg_k_pct_std` |
| 90 | C33 | 1 | +0.00001 | [-0.00011, +0.00012] | 🟡 noise → drop | `away_pit_k_pct_std` |
| 91 | C36 | 1 | +0.00001 | [-0.00017, +0.00018] | 🟡 noise → drop | `away_starter_stuff_plus` |
| 92 | C124 | 1 | +0.00001 | [-0.00007, +0.00008] | 🟡 noise → drop | `away_team_oaa_prior_season` |
| 93 | C113 | 1 | +0.00000 | [-0.00000, +0.00001] | 🟡 noise → drop | `away_avg_hard_hit_pct_vs_rhp` |
| 94 | C161 | 1 | +0.00000 | [-0.00001, +0.00002] | 🟡 noise → drop | `away_closer_used_prev_2d` |
| 95 | C91 | 1 | +0.00000 | [-0.00001, +0.00002] | 🟡 noise → drop | `home_lineup_bat_speed_vs_starter_velo` |
| 96 | C123 | 1 | +0.00000 | [-0.00005, +0.00005] | 🟡 noise → drop | `home_starter_whiff_rate_vs_lhb` |
| 97 | C143 | 1 | +0.00000 | [-0.00000, +0.00001] | 🟡 noise → drop | `home_starter_fip_ra9_gap` |
| 98 | C86 | 1 | +0.00000 | [-0.00001, +0.00002] | 🟡 noise → drop | `away_starter_xwoba_vs_rhb` |
| 99 | C136 | 1 | +0.00000 | [-0.00007, +0.00007] | 🟡 noise → drop | `away_bp_innings_pitched_14d` |
| 100 | C85 | 1 | +0.00000 | [-0.00041, +0.00042] | 🟡 noise → drop | `away_lineup_iso_vs_starter_archetype` |
| 101 | C12 | 2 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against, away_starter_eb_xwoba_against_sequential` |
| 102 | C16 | 2 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against, home_starter_eb_xwoba_against_sequential` |
| 103 | C39 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_woba` |
| 104 | C47 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_bb_pct` |
| 105 | C48 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_iso` |
| 106 | C49 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 107 | C52 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_iso` |
| 108 | C117 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_uncertainty` |
| 109 | C132 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_uncertainty` |
| 110 | C171 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_woba_sequential` |
| 111 | C173 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 112 | C92 | 1 | -0.00000 | [-0.00010, +0.00010] | 🟡 noise → drop | `home_n_no_label` |
| 113 | C90 | 1 | -0.00000 | [-0.00002, +0.00002] | 🟡 noise → drop | `away_bp_xwoba_against_14d` |
| 114 | C163 | 1 | -0.00000 | [-0.00005, +0.00005] | 🟡 noise → drop | `away_lineup_archetype_pa_coverage` |
| 115 | C83 | 1 | -0.00000 | [-0.00001, +0.00001] | 🟡 noise → drop | `home_starter_whiff_rate_14d` |
| 116 | C160 | 1 | -0.00000 | [-0.00014, +0.00012] | 🟡 noise → drop | `home_win_rate_trailing_3yr` |
| 117 | C133 | 1 | -0.00000 | [-0.00006, +0.00006] | 🟡 noise → drop | `home_off_hard_hit_pct_7d` |
| 118 | C102 | 1 | -0.00001 | [-0.00009, +0.00007] | 🟡 noise → drop | `home_off_hard_hit_pct_std` |
| 119 | C60 | 1 | -0.00001 | [-0.00007, +0.00006] | 🟡 noise → drop | `away_woba_against_with_risp_30d` |
| 120 | C154 | 1 | -0.00001 | [-0.00006, +0.00005] | 🟡 noise → drop | `series_game_number` |
| 121 | C94 | 1 | -0.00001 | [-0.00003, +0.00001] | 🟡 noise → drop | `home_n_patient_obp` |
| 122 | C170 | 1 | -0.00001 | [-0.00011, +0.00011] | 🟡 noise → drop | `away_consecutive_away_games` |
| 123 | C128 | 1 | -0.00001 | [-0.00006, +0.00005] | 🟡 noise → drop | `home_avg_bb_pct_30d` |
| 124 | C157 | 1 | -0.00001 | [-0.00008, +0.00006] | 🟡 noise → drop | `away_closer_used_prev_1d` |
| 125 | C99 | 1 | -0.00001 | [-0.00005, +0.00003] | 🟡 noise → drop | `away_avg_hard_hit_pct_std` |
| 126 | C130 | 1 | -0.00001 | [-0.00003, +0.00001] | 🟡 noise → drop | `away_pit_barrel_pct_30d` |
| 127 | C147 | 1 | -0.00002 | [-0.00007, +0.00004] | 🟡 noise → drop | `away_n_high_whiff` |
| 128 | C41 | 1 | -0.00002 | [-0.00010, +0.00006] | 🟡 noise → drop | `away_starter_proj_fip` |
| 129 | C74 | 1 | -0.00002 | [-0.00012, +0.00009] | 🟡 noise → drop | `away_lineup_archetype_avg_woba` |
| 130 | C155 | 1 | -0.00002 | [-0.00004, +0.00000] | 🟡 noise → drop | `home_starter_bb_pct_vs_rhb` |
| 131 | C153 | 1 | -0.00002 | [-0.00007, +0.00002] | 🟡 noise → drop | `home_avg_k_pct_vs_lhp` |
| 132 | C172 | 1 | -0.00002 | [-0.00010, +0.00006] | 🟡 noise → drop | `has_starter_platoon_data` |
| 133 | C67 | 1 | -0.00002 | [-0.00021, +0.00015] | 🟡 noise → drop | `away_starter_csw_pct_3start` |
| 134 | C118 | 1 | -0.00002 | [-0.00005, +0.00001] | 🟡 noise → drop | `away_starter_whiff_rate_vs_rhb` |
| 135 | C69 | 1 | -0.00002 | [-0.00017, +0.00011] | 🟡 noise → drop | `home_pit_hard_hit_pct_std` |
| 136 | C5 | 3 | -0.00002 | [-0.00013, +0.00009] | 🟡 noise → drop | `home_starter_xwoba_against_14d, home_starter_xwoba_against_30d, home_starter_xwoba_against_std` |
| 137 | C55 | 1 | -0.00003 | [-0.00013, +0.00007] | 🟡 noise → drop | `away_lineup_avg_xwoba_vs_cluster` |
| 138 | C159 | 1 | -0.00003 | [-0.00008, +0.00002] | 🟡 noise → drop | `home_off_bb_pct_7d` |
| 139 | C139 | 1 | -0.00003 | [-0.00008, +0.00003] | 🟡 noise → drop | `home_starter_xwoba_7d_minus_std` |
| 140 | C106 | 1 | -0.00003 | [-0.00007, +0.00001] | 🟡 noise → drop | `center_ft` |
| 141 | C109 | 1 | -0.00003 | [-0.00013, +0.00007] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 142 | C56 | 1 | -0.00003 | [-0.00008, +0.00002] | 🟡 noise → drop | `home_starter_k_pct_30d` |
| 143 | C25 | 2 | -0.00003 | [-0.00010, +0.00003] | 🟡 noise → drop | `home_bp_whiff_rate_30d, home_bp_whiff_rate_14d` |
| 144 | C42 | 1 | -0.00003 | [-0.00010, +0.00004] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 145 | C169 | 1 | -0.00004 | [-0.00012, +0.00004] | 🟡 noise → drop | `home_starter_appearances_30d` |
| 146 | C119 | 1 | -0.00004 | [-0.00042, +0.00036] | 🟡 noise → drop | `right_center_ft` |
| 147 | C13 | 2 | -0.00004 | [-0.00021, +0.00013] | 🟡 noise → drop | `away_pit_xwoba_against_14d, away_pit_xwoba_against_7d` |
| 148 | C107 | 1 | -0.00004 | [-0.00009, +0.00001] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 149 | C76 | 1 | -0.00004 | [-0.00015, +0.00006] | 🟡 noise → drop | `away_starter_changeup_stuff_plus` |
| 150 | C82 | 1 | -0.00005 | [-0.00014, +0.00004] | 🟡 noise → drop | `away_starter_avg_ip_season` |
| 151 | C4 | 3 | -0.00005 | [-0.00018, +0.00007] | 🟡 noise → drop | `home_off_xwoba_std, home_off_xwoba_30d, home_team_sequential_woba` |
| 152 | C156 | 1 | -0.00005 | [-0.00010, -0.00000] | ✅ signal | `home_lineup_k_pct_vs_starter_archetype` |
| 153 | C8 | 2 | -0.00005 | [-0.00028, +0.00020] | 🟡 noise → drop | `away_bp_eb_xwoba, away_team_sequential_bullpen_xwoba` |
| 154 | C115 | 1 | -0.00005 | [-0.00019, +0.00009] | 🟡 noise → drop | `away_lineup_bat_speed_vs_starter_velo` |
| 155 | C80 | 1 | -0.00006 | [-0.00018, +0.00008] | 🟡 noise → drop | `away_avg_hard_hit_pct_vs_lhp` |
| 156 | C165 | 1 | -0.00006 | [-0.00020, +0.00008] | 🟡 noise → drop | `home_lineup_avg_swing_length` |
| 157 | C98 | 1 | -0.00006 | [-0.00033, +0.00021] | 🟡 noise → drop | `away_avg_bb_pct_vs_lhp` |
| 158 | C34 | 1 | -0.00006 | [-0.00046, +0.00033] | 🟡 noise → drop | `elevation_ft` |
| 159 | C120 | 1 | -0.00007 | [-0.00027, +0.00014] | 🟡 noise → drop | `away_off_bb_pct_7d` |
| 160 | C111 | 1 | -0.00007 | [-0.00024, +0.00010] | 🟡 noise → drop | `away_starter_xwoba_against_14d` |
| 161 | C73 | 1 | -0.00007 | [-0.00016, +0.00001] | 🟡 noise → drop | `home_woba_against_with_risp_30d` |
| 162 | C3 | 3 | -0.00007 | [-0.00029, +0.00017] | 🟡 noise → drop | `away_off_xwoba_std, away_off_xwoba_30d, away_team_sequential_woba` |
| 163 | C24 | 2 | -0.00008 | [-0.00018, +0.00002] | 🟡 noise → drop | `home_bp_k_pct_30d, home_bp_k_pct_14d` |
| 164 | C23 | 2 | -0.00008 | [-0.00014, -0.00003] | ✅ signal | `home_vs_lhp_xwoba_std, home_vs_lhp_woba_std` |
| 165 | C88 | 1 | -0.00010 | [-0.00043, +0.00022] | 🟡 noise → drop | `home_off_runs_per_game_30d` |
| 166 | C167 | 1 | -0.00010 | [-0.00032, +0.00011] | 🟡 noise → drop | `home_bp_innings_pitched_30d` |
| 167 | C66 | 1 | -0.00011 | [-0.00029, +0.00006] | 🟡 noise → drop | `home_starter_k_pct_vs_lhb` |
| 168 | C140 | 1 | -0.00012 | [-0.00024, +0.00001] | 🟡 noise → drop | `home_woba_with_risp_30d` |
| 169 | C38 | 1 | -0.00019 | [-0.00041, +0.00003] | 🟡 noise → drop | `home_pit_woba_against_14d` |
| 170 | C108 | 1 | -0.00022 | [-0.00039, -0.00004] | ✅ signal | `away_woba_with_risp_30d` |
| 171 | C96 | 1 | -0.00024 | [-0.00058, +0.00011] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 172 | C162 | 1 | -0.00024 | [-0.00066, +0.00017] | 🟡 noise → drop | `away_lineup_avg_attack_angle` |
| 173 | C1 | 3 | -0.00024 | [-0.00046, -0.00004] | ✅ signal | `away_elo, away_pythagorean_win_exp, away_team_sequential_win_prob` |
| 174 | C21 | 2 | -0.00027 | [-0.00050, -0.00006] | ✅ signal | `away_pit_bb_pct_std, away_pit_bb_pct_30d` |

## Payoff (E1.3 AC)
Dropping the 143 noise clusters (169 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_home_win_bullpen_v3_stuffplus_deleaked_scorer_glm_elasticnet.json`_