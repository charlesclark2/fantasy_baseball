# Clustered Feature Importance — home_win (Epic E1.3)

- Recipe: `xgb_platt(challenger)` · metric **brier** (lower = better) · pooled baseline 0.1954
- Features: **209** in **178** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 149/178** covering **179/209** features → drop/consolidate candidates (≈86% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δbrier) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C27 | 1 | +0.03518 | [+0.03162, +0.03902] | ✅ signal | `home_bp_eb_xwoba` |
| 2 | C28 | 1 | +0.02648 | [+0.02278, +0.03017] | ✅ signal | `away_bp_eb_xwoba` |
| 3 | C29 | 1 | +0.00919 | [+0.00731, +0.01099] | ✅ signal | `home_bp_eb_uncertainty` |
| 4 | C30 | 1 | +0.00839 | [+0.00658, +0.01029] | ✅ signal | `away_bp_eb_uncertainty` |
| 5 | C174 | 1 | +0.00228 | [+0.00140, +0.00314] | ✅ signal | `away_team_sequential_bullpen_xwoba` |
| 6 | C31 | 1 | +0.00169 | [+0.00093, +0.00247] | ✅ signal | `home_bp_eb_coverage_pct` |
| 7 | C173 | 1 | +0.00106 | [+0.00042, +0.00172] | ✅ signal | `home_team_sequential_bullpen_xwoba` |
| 8 | C51 | 1 | +0.00033 | [+0.00004, +0.00063] | ✅ signal | `home_away_bp_xwoba_against_30d_pct_diff` |
| 9 | C37 | 1 | +0.00031 | [-0.00006, +0.00069] | 🟡 noise → drop | `away_starter_stuff_plus` |
| 10 | C32 | 1 | +0.00027 | [+0.00004, +0.00052] | ✅ signal | `away_bp_eb_coverage_pct` |
| 11 | C20 | 2 | +0.00020 | [+0.00003, +0.00037] | ✅ signal | `home_vs_lhp_xwoba_std, home_vs_lhp_woba_std` |
| 12 | C94 | 1 | +0.00017 | [+0.00002, +0.00032] | ✅ signal | `away_starter_k_pct_vs_lhb` |
| 13 | C5 | 3 | +0.00014 | [-0.00006, +0.00035] | 🟡 noise → drop | `home_starter_bb_pct_std, home_starter_bb_pct_14d, home_starter_bb_pct_30d` |
| 14 | C132 | 1 | +0.00014 | [-0.00002, +0.00030] | 🟡 noise → drop | `away_losses` |
| 15 | C105 | 1 | +0.00013 | [+0.00002, +0.00023] | ✅ signal | `home_avg_hard_hit_pct_std` |
| 16 | C60 | 1 | +0.00012 | [+0.00003, +0.00021] | ✅ signal | `away_lineup_vs_home_starter_k_pct_adj` |
| 17 | C57 | 1 | +0.00011 | [+0.00005, +0.00017] | ✅ signal | `home_starter_k_pct_30d` |
| 18 | C168 | 1 | +0.00011 | [-0.00002, +0.00024] | 🟡 noise → drop | `home_starter_barrel_pct_30d` |
| 19 | C125 | 1 | +0.00011 | [-0.00003, +0.00025] | 🟡 noise → drop | `away_team_oaa_prior_season` |
| 20 | C22 | 2 | +0.00011 | [-0.00004, +0.00026] | 🟡 noise → drop | `home_bp_whiff_rate_30d, home_bp_whiff_rate_14d` |
| 21 | C19 | 2 | +0.00011 | [-0.00008, +0.00030] | 🟡 noise → drop | `away_starter_batter_chase_rate_std, away_starter_batter_chase_rate_30d` |
| 22 | C46 | 1 | +0.00011 | [-0.00005, +0.00027] | 🟡 noise → drop | `home_away_starter_xwoba_against_std_pct_diff` |
| 23 | C26 | 2 | +0.00009 | [-0.00017, +0.00039] | 🟡 noise → drop | `ump_run_impact_zscore, ump_accuracy_zscore` |
| 24 | C120 | 1 | +0.00009 | [-0.00002, +0.00020] | 🟡 noise → drop | `right_center_ft` |
| 25 | C159 | 1 | +0.00009 | [-0.00014, +0.00033] | 🟡 noise → drop | `away_closer_used_prev_1d` |
| 26 | C23 | 2 | +0.00008 | [-0.00002, +0.00019] | 🟡 noise → drop | `away_starter_bb_pct_std, away_starter_bb_pct_30d` |
| 27 | C154 | 1 | +0.00008 | [-0.00001, +0.00018] | 🟡 noise → drop | `home_lineup_archetype_pa_coverage` |
| 28 | C127 | 1 | +0.00007 | [-0.00005, +0.00021] | 🟡 noise → drop | `away_off_k_pct_std` |
| 29 | C92 | 1 | +0.00007 | [-0.00009, +0.00025] | 🟡 noise → drop | `home_lineup_bat_speed_vs_starter_velo` |
| 30 | C21 | 2 | +0.00007 | [-0.00012, +0.00026] | 🟡 noise → drop | `home_bp_k_pct_30d, home_bp_k_pct_14d` |
| 31 | C83 | 1 | +0.00007 | [-0.00004, +0.00016] | 🟡 noise → drop | `away_starter_avg_ip_season` |
| 32 | C128 | 1 | +0.00007 | [-0.00008, +0.00022] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 33 | C144 | 1 | +0.00007 | [-0.00003, +0.00016] | 🟡 noise → drop | `home_starter_hard_hit_pct_std` |
| 34 | C119 | 1 | +0.00006 | [-0.00003, +0.00016] | 🟡 noise → drop | `away_starter_whiff_rate_vs_rhb` |
| 35 | C96 | 1 | +0.00006 | [-0.00030, +0.00041] | 🟡 noise → drop | `home_bp_xwoba_against_30d` |
| 36 | C54 | 1 | +0.00006 | [-0.00004, +0.00016] | 🟡 noise → drop | `away_pit_k_pct_7d` |
| 37 | C126 | 1 | +0.00006 | [-0.00008, +0.00020] | 🟡 noise → drop | `away_avg_whiff_rate_30d` |
| 38 | C138 | 1 | +0.00006 | [-0.00002, +0.00014] | 🟡 noise → drop | `away_bp_innings_pitched_14d` |
| 39 | C81 | 1 | +0.00006 | [-0.00011, +0.00021] | 🟡 noise → drop | `away_avg_hard_hit_pct_vs_lhp` |
| 40 | C10 | 2 | +0.00005 | [-0.00008, +0.00019] | 🟡 noise → drop | `away_pit_xwoba_against_14d, away_pit_xwoba_against_7d` |
| 41 | C12 | 2 | +0.00005 | [-0.00006, +0.00016] | 🟡 noise → drop | `away_avg_xwoba_std, away_avg_xwoba_30d` |
| 42 | C1 | 3 | +0.00005 | [-0.00025, +0.00036] | 🟡 noise → drop | `home_elo, home_pythagorean_win_exp, home_team_sequential_win_prob` |
| 43 | C124 | 1 | +0.00005 | [-0.00004, +0.00013] | 🟡 noise → drop | `home_starter_whiff_rate_vs_lhb` |
| 44 | C39 | 1 | +0.00005 | [-0.00005, +0.00014] | 🟡 noise → drop | `home_pit_woba_against_14d` |
| 45 | C71 | 1 | +0.00005 | [-0.00004, +0.00013] | 🟡 noise → drop | `away_bp_xwoba_against_30d` |
| 46 | C104 | 1 | +0.00005 | [-0.00002, +0.00011] | 🟡 noise → drop | `away_starter_avg_ip_last_3` |
| 47 | C85 | 1 | +0.00005 | [-0.00008, +0.00017] | 🟡 noise → drop | `home_avg_woba_vs_rhp` |
| 48 | C161 | 1 | +0.00005 | [-0.00003, +0.00013] | 🟡 noise → drop | `home_off_bb_pct_7d` |
| 49 | C113 | 1 | +0.00005 | [-0.00008, +0.00017] | 🟡 noise → drop | `home_starter_whiff_rate_vs_rhb` |
| 50 | C35 | 1 | +0.00005 | [-0.00003, +0.00012] | 🟡 noise → drop | `elevation_ft` |
| 51 | C97 | 1 | +0.00004 | [-0.00003, +0.00012] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 52 | C110 | 1 | +0.00004 | [-0.00007, +0.00015] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 53 | C82 | 1 | +0.00004 | [-0.00003, +0.00012] | 🟡 noise → drop | `away_vs_rhp_woba_30d` |
| 54 | C139 | 1 | +0.00004 | [-0.00007, +0.00016] | 🟡 noise → drop | `home_lineup_vs_away_starter_h2h_xwoba` |
| 55 | C98 | 1 | +0.00004 | [-0.00005, +0.00013] | 🟡 noise → drop | `home_catcher_defensive_runs` |
| 56 | C137 | 1 | +0.00004 | [-0.00005, +0.00014] | 🟡 noise → drop | `home_starter_bb_pct_vs_lhb` |
| 57 | C108 | 1 | +0.00004 | [-0.00008, +0.00016] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 58 | C157 | 1 | +0.00004 | [-0.00003, +0.00012] | 🟡 noise → drop | `home_starter_bb_pct_vs_rhb` |
| 59 | C131 | 1 | +0.00004 | [-0.00003, +0.00011] | 🟡 noise → drop | `away_pit_barrel_pct_30d` |
| 60 | C73 | 1 | +0.00003 | [-0.00004, +0.00011] | 🟡 noise → drop | `home_pit_k_pct_7d` |
| 61 | C160 | 1 | +0.00003 | [-0.00007, +0.00013] | 🟡 noise → drop | `home_lineup_vs_away_starter_bb_pct_adj` |
| 62 | C80 | 1 | +0.00003 | [-0.00005, +0.00012] | 🟡 noise → drop | `away_avg_xwoba_vs_lhp` |
| 63 | C115 | 1 | +0.00003 | [-0.00006, +0.00011] | 🟡 noise → drop | `away_pit_hard_hit_pct_30d` |
| 64 | C169 | 1 | +0.00003 | [-0.00007, +0.00013] | 🟡 noise → drop | `home_bp_innings_pitched_30d` |
| 65 | C147 | 1 | +0.00003 | [-0.00015, +0.00022] | 🟡 noise → drop | `away_starter_bb_pct_7d` |
| 66 | C75 | 1 | +0.00003 | [-0.00005, +0.00010] | 🟡 noise → drop | `away_lineup_archetype_avg_woba` |
| 67 | C18 | 2 | +0.00003 | [-0.00010, +0.00015] | 🟡 noise → drop | `away_pit_bb_pct_std, away_pit_bb_pct_30d` |
| 68 | C171 | 1 | +0.00002 | [-0.00007, +0.00012] | 🟡 noise → drop | `home_starter_appearances_30d` |
| 69 | C143 | 1 | +0.00002 | [-0.00004, +0.00009] | 🟡 noise → drop | `right_line_ft` |
| 70 | C77 | 1 | +0.00002 | [-0.00021, +0.00024] | 🟡 noise → drop | `away_starter_changeup_stuff_plus` |
| 71 | C84 | 1 | +0.00002 | [-0.00009, +0.00012] | 🟡 noise → drop | `home_starter_whiff_rate_14d` |
| 72 | C90 | 1 | +0.00002 | [-0.00007, +0.00011] | 🟡 noise → drop | `away_pit_bb_pct_7d` |
| 73 | C148 | 1 | +0.00002 | [-0.00007, +0.00010] | 🟡 noise → drop | `home_bp_hard_hit_pct_14d` |
| 74 | C107 | 1 | +0.00002 | [-0.00004, +0.00007] | 🟡 noise → drop | `center_ft` |
| 75 | C16 | 2 | +0.00001 | [-0.00012, +0.00015] | 🟡 noise → drop | `home_off_bb_pct_std, home_off_bb_pct_30d` |
| 76 | C130 | 1 | +0.00001 | [-0.00009, +0.00012] | 🟡 noise → drop | `away_lineup_vs_home_starter_h2h_xwoba` |
| 77 | C142 | 1 | +0.00001 | [-0.00007, +0.00009] | 🟡 noise → drop | `home_woba_with_risp_30d` |
| 78 | C153 | 1 | +0.00001 | [-0.00002, +0.00004] | 🟡 noise → drop | `home_lineup_archetype_slot_coverage` |
| 79 | C89 | 1 | +0.00001 | [-0.00006, +0.00009] | 🟡 noise → drop | `home_off_runs_per_game_30d` |
| 80 | C43 | 1 | +0.00001 | [-0.00006, +0.00007] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 81 | C152 | 1 | +0.00001 | [-0.00009, +0.00011] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 82 | C58 | 1 | +0.00001 | [-0.00007, +0.00009] | 🟡 noise → drop | `away_starter_k_pct_30d` |
| 83 | C8 | 2 | +0.00001 | [-0.00011, +0.00012] | 🟡 noise → drop | `home_pit_xwoba_against_std, home_pit_xwoba_against_30d` |
| 84 | C123 | 1 | +0.00001 | [-0.00015, +0.00016] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 85 | C163 | 1 | +0.00001 | [-0.00004, +0.00005] | 🟡 noise → drop | `away_closer_used_prev_2d` |
| 86 | C156 | 1 | +0.00001 | [-0.00003, +0.00004] | 🟡 noise → drop | `series_game_number` |
| 87 | C141 | 1 | +0.00000 | [-0.00007, +0.00008] | 🟡 noise → drop | `home_starter_xwoba_7d_minus_std` |
| 88 | C122 | 1 | +0.00000 | [-0.00005, +0.00006] | 🟡 noise → drop | `left_center_ft` |
| 89 | C106 | 1 | +0.00000 | [-0.00009, +0.00009] | 🟡 noise → drop | `home_off_runs_per_game_14d` |
| 90 | C162 | 1 | +0.00000 | [-0.00002, +0.00003] | 🟡 noise → drop | `home_win_rate_trailing_3yr` |
| 91 | C56 | 1 | +0.00000 | [-0.00013, +0.00013] | 🟡 noise → drop | `away_lineup_avg_xwoba_vs_cluster` |
| 92 | C9 | 2 | -0.00000 | [-0.00000, -0.00000] | ✅ signal | `away_starter_eb_xwoba_against, away_starter_eb_xwoba_against_sequential` |
| 93 | C13 | 2 | -0.00000 | [-0.00000, -0.00000] | ✅ signal | `home_starter_eb_xwoba_against, home_starter_eb_xwoba_against_sequential` |
| 94 | C40 | 1 | -0.00000 | [-0.00000, -0.00000] | ✅ signal | `away_avg_eb_woba` |
| 95 | C48 | 1 | -0.00000 | [-0.00000, -0.00000] | ✅ signal | `away_avg_eb_bb_pct` |
| 96 | C49 | 1 | -0.00000 | [-0.00000, -0.00000] | ✅ signal | `away_avg_eb_iso` |
| 97 | C50 | 1 | -0.00000 | [-0.00000, -0.00000] | ✅ signal | `home_starter_eb_k_pct` |
| 98 | C53 | 1 | -0.00000 | [-0.00000, -0.00000] | ✅ signal | `home_avg_eb_iso` |
| 99 | C118 | 1 | -0.00000 | [-0.00000, -0.00000] | ✅ signal | `home_starter_eb_xwoba_uncertainty` |
| 100 | C134 | 1 | -0.00000 | [-0.00000, -0.00000] | ✅ signal | `away_starter_eb_xwoba_uncertainty` |
| 101 | C175 | 1 | -0.00000 | [-0.00000, -0.00000] | ✅ signal | `home_avg_eb_woba_sequential` |
| 102 | C177 | 1 | -0.00000 | [-0.00000, -0.00000] | ✅ signal | `is_new_venue` |
| 103 | C68 | 1 | -0.00000 | [-0.00012, +0.00011] | 🟡 noise → drop | `away_starter_csw_pct_3start` |
| 104 | C14 | 2 | -0.00000 | [-0.00017, +0.00017] | 🟡 noise → drop | `home_avg_xwoba_std, home_avg_xwoba_30d` |
| 105 | C146 | 1 | -0.00000 | [-0.00003, +0.00002] | 🟡 noise → drop | `away_lineup_cluster_slot_coverage` |
| 106 | C103 | 1 | -0.00000 | [-0.00009, +0.00009] | 🟡 noise → drop | `home_off_hard_hit_pct_std` |
| 107 | C112 | 1 | -0.00000 | [-0.00009, +0.00008] | 🟡 noise → drop | `away_starter_xwoba_against_14d` |
| 108 | C93 | 1 | -0.00000 | [-0.00004, +0.00003] | 🟡 noise → drop | `home_n_no_label` |
| 109 | C36 | 1 | -0.00000 | [-0.00008, +0.00007] | 🟡 noise → drop | `away_games_back` |
| 110 | C95 | 1 | -0.00000 | [-0.00005, +0.00004] | 🟡 noise → drop | `home_n_patient_obp` |
| 111 | C158 | 1 | -0.00001 | [-0.00008, +0.00006] | 🟡 noise → drop | `home_lineup_k_pct_vs_starter_archetype` |
| 112 | C176 | 1 | -0.00001 | [-0.00002, +0.00001] | 🟡 noise → drop | `has_starter_platoon_data` |
| 113 | C67 | 1 | -0.00001 | [-0.00007, +0.00005] | 🟡 noise → drop | `home_starter_k_pct_vs_lhb` |
| 114 | C55 | 1 | -0.00001 | [-0.00007, +0.00006] | 🟡 noise → drop | `home_starter_trailing_fip_30g` |
| 115 | C135 | 1 | -0.00001 | [-0.00010, +0.00009] | 🟡 noise → drop | `home_off_hard_hit_pct_7d` |
| 116 | C136 | 1 | -0.00001 | [-0.00010, +0.00008] | 🟡 noise → drop | `home_avg_k_pct_std` |
| 117 | C72 | 1 | -0.00001 | [-0.00008, +0.00006] | 🟡 noise → drop | `home_starter_csw_pct_season` |
| 118 | C166 | 1 | -0.00001 | [-0.00018, +0.00016] | 🟡 noise → drop | `away_pit_xwoba_7d_minus_30d` |
| 119 | C66 | 1 | -0.00001 | [-0.00012, +0.00008] | 🟡 noise → drop | `away_avg_woba_std` |
| 120 | C47 | 1 | -0.00001 | [-0.00016, +0.00014] | 🟡 noise → drop | `away_starter_trailing_ra9_30g` |
| 121 | C38 | 1 | -0.00001 | [-0.00011, +0.00007] | 🟡 noise → drop | `home_games_back` |
| 122 | C99 | 1 | -0.00001 | [-0.00011, +0.00008] | 🟡 noise → drop | `away_avg_bb_pct_vs_lhp` |
| 123 | C167 | 1 | -0.00002 | [-0.00008, +0.00006] | 🟡 noise → drop | `home_lineup_avg_swing_length` |
| 124 | C69 | 1 | -0.00002 | [-0.00014, +0.00012] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 125 | C129 | 1 | -0.00002 | [-0.00008, +0.00004] | 🟡 noise → drop | `home_avg_bb_pct_30d` |
| 126 | C145 | 1 | -0.00002 | [-0.00014, +0.00011] | 🟡 noise → drop | `home_starter_fip_ra9_gap` |
| 127 | C102 | 1 | -0.00002 | [-0.00005, +0.00002] | 🟡 noise → drop | `away_n_power_pull` |
| 128 | C116 | 1 | -0.00002 | [-0.00011, +0.00006] | 🟡 noise → drop | `away_lineup_bat_speed_vs_starter_velo` |
| 129 | C78 | 1 | -0.00002 | [-0.00007, +0.00002] | 🟡 noise → drop | `away_n_no_label` |
| 130 | C11 | 2 | -0.00002 | [-0.00015, +0.00011] | 🟡 noise → drop | `home_lineup_avg_woba_vs_cluster, home_lineup_avg_xwoba_vs_cluster` |
| 131 | C133 | 1 | -0.00003 | [-0.00013, +0.00009] | 🟡 noise → drop | `away_avg_k_pct_vs_rhp` |
| 132 | C79 | 1 | -0.00003 | [-0.00012, +0.00008] | 🟡 noise → drop | `home_starter_avg_ip_season` |
| 133 | C86 | 1 | -0.00003 | [-0.00018, +0.00013] | 🟡 noise → drop | `away_lineup_iso_vs_starter_archetype` |
| 134 | C52 | 1 | -0.00003 | [-0.00013, +0.00006] | 🟡 noise → drop | `home_starter_trailing_ra9_30g` |
| 135 | C3 | 3 | -0.00003 | [-0.00026, +0.00019] | 🟡 noise → drop | `home_off_xwoba_std, home_off_xwoba_30d, home_team_sequential_woba` |
| 136 | C34 | 1 | -0.00003 | [-0.00012, +0.00004] | 🟡 noise → drop | `away_pit_k_pct_std` |
| 137 | C59 | 1 | -0.00003 | [-0.00011, +0.00005] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 138 | C87 | 1 | -0.00003 | [-0.00012, +0.00005] | 🟡 noise → drop | `away_starter_xwoba_vs_rhb` |
| 139 | C100 | 1 | -0.00004 | [-0.00011, +0.00004] | 🟡 noise → drop | `away_avg_hard_hit_pct_std` |
| 140 | C41 | 1 | -0.00004 | [-0.00012, +0.00006] | 🟡 noise → drop | `home_away_off_woba_30d_pct_diff` |
| 141 | C42 | 1 | -0.00004 | [-0.00015, +0.00007] | 🟡 noise → drop | `away_starter_proj_fip` |
| 142 | C150 | 1 | -0.00004 | [-0.00014, +0.00006] | 🟡 noise → drop | `home_starter_hard_hit_pct_14d` |
| 143 | C164 | 1 | -0.00004 | [-0.00015, +0.00007] | 🟡 noise → drop | `away_lineup_avg_attack_angle` |
| 144 | C62 | 1 | -0.00004 | [-0.00013, +0.00005] | 🟡 noise → drop | `home_avg_woba_std` |
| 145 | C4 | 3 | -0.00004 | [-0.00020, +0.00010] | 🟡 noise → drop | `home_starter_xwoba_against_14d, home_starter_xwoba_against_30d, home_starter_xwoba_against_std` |
| 146 | C109 | 1 | -0.00004 | [-0.00016, +0.00007] | 🟡 noise → drop | `away_woba_with_risp_30d` |
| 147 | C111 | 1 | -0.00005 | [-0.00016, +0.00006] | 🟡 noise → drop | `away_avg_k_pct_std` |
| 148 | C25 | 2 | -0.00005 | [-0.00018, +0.00007] | 🟡 noise → drop | `home_starter_barrel_pct_14d, home_starter_barrel_pct_7d` |
| 149 | C149 | 1 | -0.00006 | [-0.00011, -0.00000] | ✅ signal | `away_n_high_whiff` |
| 150 | C140 | 1 | -0.00006 | [-0.00012, +0.00001] | 🟡 noise → drop | `left_line_ft` |
| 151 | C165 | 1 | -0.00006 | [-0.00016, +0.00004] | 🟡 noise → drop | `away_lineup_archetype_pa_coverage` |
| 152 | C63 | 1 | -0.00006 | [-0.00016, +0.00004] | 🟡 noise → drop | `away_xwoba_with_runners_on_30d` |
| 153 | C121 | 1 | -0.00006 | [-0.00020, +0.00007] | 🟡 noise → drop | `away_off_bb_pct_7d` |
| 154 | C70 | 1 | -0.00006 | [-0.00015, +0.00003] | 🟡 noise → drop | `home_pit_hard_hit_pct_std` |
| 155 | C74 | 1 | -0.00007 | [-0.00018, +0.00005] | 🟡 noise → drop | `home_woba_against_with_risp_30d` |
| 156 | C76 | 1 | -0.00007 | [-0.00015, +0.00002] | 🟡 noise → drop | `away_avg_barrel_pct_std` |
| 157 | C2 | 3 | -0.00007 | [-0.00019, +0.00006] | 🟡 noise → drop | `away_off_xwoba_std, away_off_xwoba_30d, away_team_sequential_woba` |
| 158 | C172 | 1 | -0.00007 | [-0.00015, +0.00001] | 🟡 noise → drop | `away_consecutive_away_games` |
| 159 | C101 | 1 | -0.00007 | [-0.00017, +0.00003] | 🟡 noise → drop | `home_avg_barrel_pct_std` |
| 160 | C151 | 1 | -0.00007 | [-0.00017, +0.00004] | 🟡 noise → drop | `away_lineup_k_pct_vs_starter_archetype` |
| 161 | C91 | 1 | -0.00007 | [-0.00020, +0.00005] | 🟡 noise → drop | `away_bp_xwoba_against_14d` |
| 162 | C45 | 1 | -0.00008 | [-0.00020, +0.00004] | 🟡 noise → drop | `away_off_runs_per_game_std` |
| 163 | C155 | 1 | -0.00008 | [-0.00018, +0.00002] | 🟡 noise → drop | `home_avg_k_pct_vs_lhp` |
| 164 | C117 | 1 | -0.00008 | [-0.00020, +0.00003] | 🟡 noise → drop | `away_lineup_avg_swing_length` |
| 165 | C170 | 1 | -0.00008 | [-0.00017, -0.00000] | ✅ signal | `away_starter_hard_hit_pct_7d` |
| 166 | C0 | 3 | -0.00009 | [-0.00045, +0.00029] | 🟡 noise → drop | `away_elo, away_pythagorean_win_exp, away_team_sequential_win_prob` |
| 167 | C33 | 1 | -0.00009 | [-0.00023, +0.00005] | 🟡 noise → drop | `home_pit_woba_against_std` |
| 168 | C24 | 2 | -0.00010 | [-0.00025, +0.00004] | 🟡 noise → drop | `away_starter_hard_hit_pct_std, away_starter_hard_hit_pct_30d` |
| 169 | C44 | 1 | -0.00011 | [-0.00030, +0.00009] | 🟡 noise → drop | `home_away_starter_k_pct_std_pct_diff` |
| 170 | C88 | 1 | -0.00011 | [-0.00023, +0.00000] | 🟡 noise → drop | `away_vs_lhp_woba_30d` |
| 171 | C114 | 1 | -0.00012 | [-0.00022, -0.00001] | ✅ signal | `away_avg_hard_hit_pct_vs_rhp` |
| 172 | C17 | 2 | -0.00012 | [-0.00030, +0.00006] | 🟡 noise → drop | `away_bp_k_pct_30d, away_bp_k_pct_14d` |
| 173 | C7 | 2 | -0.00014 | [-0.00031, +0.00002] | 🟡 noise → drop | `away_pit_woba_against_std, away_pit_woba_against_30d` |
| 174 | C61 | 1 | -0.00015 | [-0.00035, +0.00004] | 🟡 noise → drop | `away_woba_against_with_risp_30d` |
| 175 | C64 | 1 | -0.00016 | [-0.00033, +0.00002] | 🟡 noise → drop | `away_vs_lhp_xwoba_std` |
| 176 | C15 | 2 | -0.00016 | [-0.00034, +0.00003] | 🟡 noise → drop | `away_starter_whiff_rate_std, away_starter_whiff_rate_14d` |
| 177 | C65 | 1 | -0.00018 | [-0.00030, -0.00006] | ✅ signal | `away_off_hard_hit_pct_std` |
| 178 | C6 | 2 | -0.00033 | [-0.00104, +0.00035] | 🟡 noise → drop | `elo_diff, pythagorean_win_exp_diff` |

## Payoff (E1.3 AC)
Dropping the 149 noise clusters (179 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_home_win.json`_