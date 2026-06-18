# Clustered Feature Importance — home_win (Epic E1.3)

- Recipe: `xgb_platt(challenger)` · metric **brier** (lower = better) · pooled baseline 0.2358
- Features: **209** in **174** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 158/174** covering **190/209** features → drop/consolidate candidates (≈91% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δbrier) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C30 | 1 | +0.00805 | [+0.00643, +0.00972] | ✅ signal | `home_bp_eb_coverage_pct` |
| 2 | C31 | 1 | +0.00368 | [+0.00261, +0.00480] | ✅ signal | `away_bp_eb_coverage_pct` |
| 3 | C9 | 2 | +0.00155 | [+0.00073, +0.00240] | ✅ signal | `elo_diff, pythagorean_win_exp_diff` |
| 4 | C17 | 2 | +0.00036 | [+0.00011, +0.00059] | ✅ signal | `home_avg_xwoba_std, home_avg_xwoba_30d` |
| 5 | C6 | 3 | +0.00032 | [-0.00002, +0.00066] | 🟡 noise → drop | `home_starter_bb_pct_std, home_starter_bb_pct_14d, home_starter_bb_pct_30d` |
| 6 | C169 | 1 | +0.00022 | [+0.00008, +0.00036] | ✅ signal | `home_starter_appearances_30d` |
| 7 | C2 | 3 | +0.00020 | [-0.00005, +0.00047] | 🟡 noise → drop | `home_elo, home_pythagorean_win_exp, home_team_sequential_win_prob` |
| 8 | C126 | 1 | +0.00020 | [+0.00003, +0.00037] | ✅ signal | `away_off_k_pct_std` |
| 9 | C14 | 2 | +0.00020 | [+0.00002, +0.00038] | ✅ signal | `home_lineup_avg_woba_vs_cluster, home_lineup_avg_xwoba_vs_cluster` |
| 10 | C7 | 2 | +0.00018 | [+0.00000, +0.00036] | ✅ signal | `home_bp_eb_xwoba, home_team_sequential_bullpen_xwoba` |
| 11 | C1 | 3 | +0.00017 | [-0.00006, +0.00038] | 🟡 noise → drop | `away_elo, away_pythagorean_win_exp, away_team_sequential_win_prob` |
| 12 | C20 | 2 | +0.00015 | [-0.00007, +0.00036] | 🟡 noise → drop | `away_bp_k_pct_30d, away_bp_k_pct_14d` |
| 13 | C76 | 1 | +0.00015 | [-0.00009, +0.00038] | 🟡 noise → drop | `away_starter_changeup_stuff_plus` |
| 14 | C110 | 1 | +0.00014 | [+0.00002, +0.00026] | ✅ signal | `away_avg_k_pct_std` |
| 15 | C43 | 1 | +0.00014 | [-0.00007, +0.00036] | 🟡 noise → drop | `home_away_starter_k_pct_std_pct_diff` |
| 16 | C19 | 2 | +0.00014 | [-0.00001, +0.00027] | 🟡 noise → drop | `home_off_bb_pct_std, home_off_bb_pct_30d` |
| 17 | C51 | 1 | +0.00013 | [-0.00002, +0.00028] | 🟡 noise → drop | `home_starter_trailing_ra9_30g` |
| 18 | C111 | 1 | +0.00012 | [-0.00004, +0.00029] | 🟡 noise → drop | `away_starter_xwoba_against_14d` |
| 19 | C143 | 1 | +0.00012 | [-0.00002, +0.00026] | 🟡 noise → drop | `home_starter_fip_ra9_gap` |
| 20 | C36 | 1 | +0.00012 | [-0.00025, +0.00050] | 🟡 noise → drop | `away_starter_stuff_plus` |
| 21 | C146 | 1 | +0.00011 | [+0.00002, +0.00020] | ✅ signal | `home_bp_hard_hit_pct_14d` |
| 22 | C72 | 1 | +0.00011 | [-0.00000, +0.00023] | 🟡 noise → drop | `home_pit_k_pct_7d` |
| 23 | C166 | 1 | +0.00010 | [-0.00001, +0.00022] | 🟡 noise → drop | `home_starter_barrel_pct_30d` |
| 24 | C136 | 1 | +0.00010 | [+0.00001, +0.00019] | ✅ signal | `away_bp_innings_pitched_14d` |
| 25 | C18 | 2 | +0.00010 | [-0.00010, +0.00030] | 🟡 noise → drop | `away_starter_whiff_rate_std, away_starter_whiff_rate_14d` |
| 26 | C118 | 1 | +0.00009 | [-0.00009, +0.00027] | 🟡 noise → drop | `away_starter_whiff_rate_vs_rhb` |
| 27 | C89 | 1 | +0.00009 | [-0.00004, +0.00022] | 🟡 noise → drop | `away_pit_bb_pct_7d` |
| 28 | C44 | 1 | +0.00008 | [-0.00001, +0.00018] | 🟡 noise → drop | `away_off_runs_per_game_std` |
| 29 | C32 | 1 | +0.00008 | [-0.00013, +0.00030] | 🟡 noise → drop | `home_pit_woba_against_std` |
| 30 | C137 | 1 | +0.00008 | [-0.00007, +0.00023] | 🟡 noise → drop | `home_lineup_vs_away_starter_h2h_xwoba` |
| 31 | C61 | 1 | +0.00008 | [-0.00006, +0.00021] | 🟡 noise → drop | `home_avg_woba_std` |
| 32 | C11 | 2 | +0.00008 | [-0.00002, +0.00017] | 🟡 noise → drop | `home_pit_xwoba_against_std, home_pit_xwoba_against_30d` |
| 33 | C99 | 1 | +0.00008 | [-0.00004, +0.00018] | 🟡 noise → drop | `away_avg_hard_hit_pct_std` |
| 34 | C103 | 1 | +0.00007 | [-0.00008, +0.00023] | 🟡 noise → drop | `away_starter_avg_ip_last_3` |
| 35 | C24 | 2 | +0.00007 | [-0.00007, +0.00022] | 🟡 noise → drop | `home_bp_k_pct_30d, home_bp_k_pct_14d` |
| 36 | C78 | 1 | +0.00007 | [-0.00004, +0.00019] | 🟡 noise → drop | `home_starter_avg_ip_season` |
| 37 | C104 | 1 | +0.00007 | [-0.00004, +0.00019] | 🟡 noise → drop | `home_avg_hard_hit_pct_std` |
| 38 | C122 | 1 | +0.00007 | [-0.00010, +0.00024] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 39 | C127 | 1 | +0.00007 | [-0.00007, +0.00021] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 40 | C66 | 1 | +0.00007 | [-0.00001, +0.00014] | 🟡 noise → drop | `home_starter_k_pct_vs_lhb` |
| 41 | C26 | 2 | +0.00006 | [-0.00009, +0.00021] | 🟡 noise → drop | `away_starter_bb_pct_std, away_starter_bb_pct_30d` |
| 42 | C134 | 1 | +0.00006 | [-0.00004, +0.00016] | 🟡 noise → drop | `home_avg_k_pct_std` |
| 43 | C125 | 1 | +0.00006 | [-0.00014, +0.00026] | 🟡 noise → drop | `away_avg_whiff_rate_30d` |
| 44 | C50 | 1 | +0.00006 | [-0.00014, +0.00027] | 🟡 noise → drop | `home_away_bp_xwoba_against_30d_pct_diff` |
| 45 | C54 | 1 | +0.00006 | [-0.00006, +0.00018] | 🟡 noise → drop | `home_starter_trailing_fip_30g` |
| 46 | C91 | 1 | +0.00006 | [-0.00005, +0.00016] | 🟡 noise → drop | `home_lineup_bat_speed_vs_starter_velo` |
| 47 | C119 | 1 | +0.00006 | [-0.00014, +0.00026] | 🟡 noise → drop | `right_center_ft` |
| 48 | C164 | 1 | +0.00006 | [-0.00002, +0.00013] | 🟡 noise → drop | `away_pit_xwoba_7d_minus_30d` |
| 49 | C109 | 1 | +0.00005 | [-0.00008, +0.00018] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 50 | C113 | 1 | +0.00005 | [-0.00008, +0.00018] | 🟡 noise → drop | `away_avg_hard_hit_pct_vs_rhp` |
| 51 | C149 | 1 | +0.00005 | [-0.00016, +0.00025] | 🟡 noise → drop | `away_lineup_k_pct_vs_starter_archetype` |
| 52 | C129 | 1 | +0.00004 | [-0.00014, +0.00023] | 🟡 noise → drop | `away_lineup_vs_home_starter_h2h_xwoba` |
| 53 | C5 | 3 | +0.00004 | [-0.00011, +0.00018] | 🟡 noise → drop | `home_starter_xwoba_against_14d, home_starter_xwoba_against_30d, home_starter_xwoba_against_std` |
| 54 | C74 | 1 | +0.00004 | [-0.00007, +0.00014] | 🟡 noise → drop | `away_lineup_archetype_avg_woba` |
| 55 | C45 | 1 | +0.00004 | [-0.00005, +0.00012] | 🟡 noise → drop | `home_away_starter_xwoba_against_std_pct_diff` |
| 56 | C115 | 1 | +0.00004 | [-0.00007, +0.00014] | 🟡 noise → drop | `away_lineup_bat_speed_vs_starter_velo` |
| 57 | C25 | 2 | +0.00003 | [-0.00009, +0.00016] | 🟡 noise → drop | `home_bp_whiff_rate_30d, home_bp_whiff_rate_14d` |
| 58 | C57 | 1 | +0.00003 | [-0.00007, +0.00013] | 🟡 noise → drop | `away_starter_k_pct_30d` |
| 59 | C80 | 1 | +0.00003 | [-0.00009, +0.00016] | 🟡 noise → drop | `away_avg_hard_hit_pct_vs_lhp` |
| 60 | C112 | 1 | +0.00003 | [-0.00008, +0.00014] | 🟡 noise → drop | `home_starter_whiff_rate_vs_rhb` |
| 61 | C82 | 1 | +0.00003 | [-0.00011, +0.00016] | 🟡 noise → drop | `away_starter_avg_ip_season` |
| 62 | C116 | 1 | +0.00003 | [-0.00004, +0.00010] | 🟡 noise → drop | `away_lineup_avg_swing_length` |
| 63 | C87 | 1 | +0.00003 | [-0.00012, +0.00017] | 🟡 noise → drop | `away_vs_lhp_woba_30d` |
| 64 | C55 | 1 | +0.00002 | [-0.00010, +0.00015] | 🟡 noise → drop | `away_lineup_avg_xwoba_vs_cluster` |
| 65 | C142 | 1 | +0.00002 | [-0.00006, +0.00011] | 🟡 noise → drop | `home_starter_hard_hit_pct_std` |
| 66 | C40 | 1 | +0.00002 | [-0.00005, +0.00010] | 🟡 noise → drop | `home_away_off_woba_30d_pct_diff` |
| 67 | C81 | 1 | +0.00002 | [-0.00005, +0.00010] | 🟡 noise → drop | `away_vs_rhp_woba_30d` |
| 68 | C161 | 1 | +0.00002 | [-0.00002, +0.00007] | 🟡 noise → drop | `away_closer_used_prev_2d` |
| 69 | C147 | 1 | +0.00002 | [-0.00001, +0.00005] | 🟡 noise → drop | `away_n_high_whiff` |
| 70 | C35 | 1 | +0.00002 | [-0.00007, +0.00010] | 🟡 noise → drop | `away_games_back` |
| 71 | C102 | 1 | +0.00002 | [-0.00006, +0.00010] | 🟡 noise → drop | `home_off_hard_hit_pct_std` |
| 72 | C144 | 1 | +0.00002 | [-0.00003, +0.00006] | 🟡 noise → drop | `away_lineup_cluster_slot_coverage` |
| 73 | C29 | 2 | +0.00001 | [-0.00030, +0.00035] | 🟡 noise → drop | `ump_run_impact_zscore, ump_accuracy_zscore` |
| 74 | C120 | 1 | +0.00001 | [-0.00011, +0.00014] | 🟡 noise → drop | `away_off_bb_pct_7d` |
| 75 | C77 | 1 | +0.00001 | [-0.00004, +0.00006] | 🟡 noise → drop | `away_n_no_label` |
| 76 | C170 | 1 | +0.00001 | [-0.00007, +0.00010] | 🟡 noise → drop | `away_consecutive_away_games` |
| 77 | C97 | 1 | +0.00001 | [-0.00011, +0.00014] | 🟡 noise → drop | `home_catcher_defensive_runs` |
| 78 | C124 | 1 | +0.00001 | [-0.00009, +0.00012] | 🟡 noise → drop | `away_team_oaa_prior_season` |
| 79 | C79 | 1 | +0.00001 | [-0.00012, +0.00014] | 🟡 noise → drop | `away_avg_xwoba_vs_lhp` |
| 80 | C106 | 1 | +0.00001 | [-0.00003, +0.00005] | 🟡 noise → drop | `center_ft` |
| 81 | C160 | 1 | +0.00001 | [-0.00001, +0.00003] | 🟡 noise → drop | `home_win_rate_trailing_3yr` |
| 82 | C114 | 1 | +0.00001 | [-0.00011, +0.00012] | 🟡 noise → drop | `away_pit_hard_hit_pct_30d` |
| 83 | C83 | 1 | +0.00001 | [-0.00013, +0.00016] | 🟡 noise → drop | `home_starter_whiff_rate_14d` |
| 84 | C38 | 1 | +0.00001 | [-0.00009, +0.00011] | 🟡 noise → drop | `home_pit_woba_against_14d` |
| 85 | C27 | 2 | +0.00001 | [-0.00017, +0.00019] | 🟡 noise → drop | `away_starter_hard_hit_pct_std, away_starter_hard_hit_pct_30d` |
| 86 | C153 | 1 | +0.00001 | [-0.00008, +0.00009] | 🟡 noise → drop | `home_avg_k_pct_vs_lhp` |
| 87 | C88 | 1 | +0.00001 | [-0.00007, +0.00008] | 🟡 noise → drop | `home_off_runs_per_game_30d` |
| 88 | C92 | 1 | +0.00000 | [-0.00003, +0.00004] | 🟡 noise → drop | `home_n_no_label` |
| 89 | C105 | 1 | +0.00000 | [-0.00006, +0.00007] | 🟡 noise → drop | `home_off_runs_per_game_14d` |
| 90 | C58 | 1 | +0.00000 | [-0.00007, +0.00007] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 91 | C67 | 1 | +0.00000 | [-0.00011, +0.00012] | 🟡 noise → drop | `away_starter_csw_pct_3start` |
| 92 | C101 | 1 | +0.00000 | [-0.00003, +0.00003] | 🟡 noise → drop | `away_n_power_pull` |
| 93 | C141 | 1 | +0.00000 | [-0.00005, +0.00005] | 🟡 noise → drop | `right_line_ft` |
| 94 | C12 | 2 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against, away_starter_eb_xwoba_against_sequential` |
| 95 | C16 | 2 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against, home_starter_eb_xwoba_against_sequential` |
| 96 | C39 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_woba` |
| 97 | C47 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_bb_pct` |
| 98 | C48 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_iso` |
| 99 | C49 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 100 | C52 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_iso` |
| 101 | C117 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_uncertainty` |
| 102 | C132 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_uncertainty` |
| 103 | C171 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_woba_sequential` |
| 104 | C173 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 105 | C158 | 1 | -0.00000 | [-0.00011, +0.00011] | 🟡 noise → drop | `home_lineup_vs_away_starter_bb_pct_adj` |
| 106 | C165 | 1 | -0.00000 | [-0.00007, +0.00008] | 🟡 noise → drop | `home_lineup_avg_swing_length` |
| 107 | C133 | 1 | -0.00000 | [-0.00013, +0.00013] | 🟡 noise → drop | `home_off_hard_hit_pct_7d` |
| 108 | C53 | 1 | -0.00000 | [-0.00011, +0.00011] | 🟡 noise → drop | `away_pit_k_pct_7d` |
| 109 | C157 | 1 | -0.00000 | [-0.00005, +0.00004] | 🟡 noise → drop | `away_closer_used_prev_1d` |
| 110 | C155 | 1 | -0.00000 | [-0.00009, +0.00009] | 🟡 noise → drop | `home_starter_bb_pct_vs_rhb` |
| 111 | C154 | 1 | -0.00000 | [-0.00005, +0.00004] | 🟡 noise → drop | `series_game_number` |
| 112 | C156 | 1 | -0.00001 | [-0.00011, +0.00010] | 🟡 noise → drop | `home_lineup_k_pct_vs_starter_archetype` |
| 113 | C65 | 1 | -0.00001 | [-0.00008, +0.00007] | 🟡 noise → drop | `away_avg_woba_std` |
| 114 | C168 | 1 | -0.00001 | [-0.00010, +0.00008] | 🟡 noise → drop | `away_starter_hard_hit_pct_7d` |
| 115 | C37 | 1 | -0.00001 | [-0.00011, +0.00010] | 🟡 noise → drop | `home_games_back` |
| 116 | C138 | 1 | -0.00001 | [-0.00005, +0.00003] | 🟡 noise → drop | `left_line_ft` |
| 117 | C172 | 1 | -0.00001 | [-0.00002, +0.00000] | 🟡 noise → drop | `has_starter_platoon_data` |
| 118 | C94 | 1 | -0.00001 | [-0.00005, +0.00003] | 🟡 noise → drop | `home_n_patient_obp` |
| 119 | C128 | 1 | -0.00001 | [-0.00011, +0.00009] | 🟡 noise → drop | `home_avg_bb_pct_30d` |
| 120 | C139 | 1 | -0.00001 | [-0.00012, +0.00011] | 🟡 noise → drop | `home_starter_xwoba_7d_minus_std` |
| 121 | C71 | 1 | -0.00001 | [-0.00013, +0.00011] | 🟡 noise → drop | `home_starter_csw_pct_season` |
| 122 | C63 | 1 | -0.00001 | [-0.00015, +0.00012] | 🟡 noise → drop | `away_vs_lhp_xwoba_std` |
| 123 | C60 | 1 | -0.00001 | [-0.00011, +0.00009] | 🟡 noise → drop | `away_woba_against_with_risp_30d` |
| 124 | C10 | 2 | -0.00001 | [-0.00023, +0.00021] | 🟡 noise → drop | `away_pit_woba_against_std, away_pit_woba_against_30d` |
| 125 | C107 | 1 | -0.00002 | [-0.00011, +0.00007] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 126 | C33 | 1 | -0.00002 | [-0.00010, +0.00007] | 🟡 noise → drop | `away_pit_k_pct_std` |
| 127 | C162 | 1 | -0.00002 | [-0.00013, +0.00009] | 🟡 noise → drop | `away_lineup_avg_attack_angle` |
| 128 | C151 | 1 | -0.00002 | [-0.00005, +0.00001] | 🟡 noise → drop | `home_lineup_archetype_slot_coverage` |
| 129 | C121 | 1 | -0.00002 | [-0.00007, +0.00003] | 🟡 noise → drop | `left_center_ft` |
| 130 | C130 | 1 | -0.00002 | [-0.00015, +0.00012] | 🟡 noise → drop | `away_pit_barrel_pct_30d` |
| 131 | C70 | 1 | -0.00002 | [-0.00012, +0.00008] | 🟡 noise → drop | `away_bp_xwoba_against_30d` |
| 132 | C152 | 1 | -0.00002 | [-0.00015, +0.00011] | 🟡 noise → drop | `home_lineup_archetype_pa_coverage` |
| 133 | C15 | 2 | -0.00002 | [-0.00015, +0.00010] | 🟡 noise → drop | `away_avg_xwoba_std, away_avg_xwoba_30d` |
| 134 | C159 | 1 | -0.00002 | [-0.00010, +0.00004] | 🟡 noise → drop | `home_off_bb_pct_7d` |
| 135 | C34 | 1 | -0.00002 | [-0.00008, +0.00003] | 🟡 noise → drop | `elevation_ft` |
| 136 | C84 | 1 | -0.00003 | [-0.00012, +0.00008] | 🟡 noise → drop | `home_avg_woba_vs_rhp` |
| 137 | C145 | 1 | -0.00003 | [-0.00015, +0.00010] | 🟡 noise → drop | `away_starter_bb_pct_7d` |
| 138 | C64 | 1 | -0.00003 | [-0.00009, +0.00004] | 🟡 noise → drop | `away_off_hard_hit_pct_std` |
| 139 | C62 | 1 | -0.00003 | [-0.00011, +0.00005] | 🟡 noise → drop | `away_xwoba_with_runners_on_30d` |
| 140 | C135 | 1 | -0.00003 | [-0.00013, +0.00008] | 🟡 noise → drop | `home_starter_bb_pct_vs_lhb` |
| 141 | C131 | 1 | -0.00003 | [-0.00016, +0.00010] | 🟡 noise → drop | `away_avg_k_pct_vs_rhp` |
| 142 | C28 | 2 | -0.00003 | [-0.00014, +0.00010] | 🟡 noise → drop | `home_starter_barrel_pct_14d, home_starter_barrel_pct_7d` |
| 143 | C59 | 1 | -0.00003 | [-0.00012, +0.00005] | 🟡 noise → drop | `away_lineup_vs_home_starter_k_pct_adj` |
| 144 | C22 | 2 | -0.00003 | [-0.00026, +0.00018] | 🟡 noise → drop | `away_starter_batter_chase_rate_std, away_starter_batter_chase_rate_30d` |
| 145 | C3 | 3 | -0.00003 | [-0.00015, +0.00009] | 🟡 noise → drop | `away_off_xwoba_std, away_off_xwoba_30d, away_team_sequential_woba` |
| 146 | C68 | 1 | -0.00003 | [-0.00018, +0.00010] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 147 | C98 | 1 | -0.00003 | [-0.00023, +0.00016] | 🟡 noise → drop | `away_avg_bb_pct_vs_lhp` |
| 148 | C42 | 1 | -0.00003 | [-0.00012, +0.00006] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 149 | C13 | 2 | -0.00003 | [-0.00014, +0.00007] | 🟡 noise → drop | `away_pit_xwoba_against_14d, away_pit_xwoba_against_7d` |
| 150 | C69 | 1 | -0.00003 | [-0.00020, +0.00013] | 🟡 noise → drop | `home_pit_hard_hit_pct_std` |
| 151 | C108 | 1 | -0.00004 | [-0.00015, +0.00006] | 🟡 noise → drop | `away_woba_with_risp_30d` |
| 152 | C167 | 1 | -0.00005 | [-0.00016, +0.00007] | 🟡 noise → drop | `home_bp_innings_pitched_30d` |
| 153 | C150 | 1 | -0.00005 | [-0.00017, +0.00006] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 154 | C75 | 1 | -0.00005 | [-0.00012, +0.00001] | 🟡 noise → drop | `away_avg_barrel_pct_std` |
| 155 | C8 | 2 | -0.00006 | [-0.00021, +0.00010] | 🟡 noise → drop | `away_bp_eb_xwoba, away_team_sequential_bullpen_xwoba` |
| 156 | C100 | 1 | -0.00006 | [-0.00017, +0.00006] | 🟡 noise → drop | `home_avg_barrel_pct_std` |
| 157 | C46 | 1 | -0.00006 | [-0.00028, +0.00014] | 🟡 noise → drop | `away_starter_trailing_ra9_30g` |
| 158 | C163 | 1 | -0.00006 | [-0.00013, +0.00001] | 🟡 noise → drop | `away_lineup_archetype_pa_coverage` |
| 159 | C56 | 1 | -0.00006 | [-0.00013, -0.00000] | ✅ signal | `home_starter_k_pct_30d` |
| 160 | C93 | 1 | -0.00007 | [-0.00026, +0.00012] | 🟡 noise → drop | `away_starter_k_pct_vs_lhb` |
| 161 | C148 | 1 | -0.00007 | [-0.00017, +0.00003] | 🟡 noise → drop | `home_starter_hard_hit_pct_14d` |
| 162 | C23 | 2 | -0.00007 | [-0.00021, +0.00007] | 🟡 noise → drop | `home_vs_lhp_xwoba_std, home_vs_lhp_woba_std` |
| 163 | C41 | 1 | -0.00007 | [-0.00021, +0.00007] | 🟡 noise → drop | `away_starter_proj_fip` |
| 164 | C123 | 1 | -0.00008 | [-0.00018, +0.00002] | 🟡 noise → drop | `home_starter_whiff_rate_vs_lhb` |
| 165 | C73 | 1 | -0.00008 | [-0.00021, +0.00004] | 🟡 noise → drop | `home_woba_against_with_risp_30d` |
| 166 | C96 | 1 | -0.00009 | [-0.00024, +0.00006] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 167 | C4 | 3 | -0.00009 | [-0.00020, +0.00003] | 🟡 noise → drop | `home_off_xwoba_std, home_off_xwoba_30d, home_team_sequential_woba` |
| 168 | C95 | 1 | -0.00009 | [-0.00023, +0.00006] | 🟡 noise → drop | `home_bp_xwoba_against_30d` |
| 169 | C140 | 1 | -0.00012 | [-0.00024, -0.00001] | ✅ signal | `home_woba_with_risp_30d` |
| 170 | C21 | 2 | -0.00012 | [-0.00024, -0.00000] | ✅ signal | `away_pit_bb_pct_std, away_pit_bb_pct_30d` |
| 171 | C86 | 1 | -0.00013 | [-0.00022, -0.00004] | ✅ signal | `away_starter_xwoba_vs_rhb` |
| 172 | C0 | 3 | -0.00013 | [-0.00031, +0.00004] | 🟡 noise → drop | `home_bp_eb_uncertainty, away_bp_eb_uncertainty, away_losses` |
| 173 | C90 | 1 | -0.00018 | [-0.00036, +0.00001] | 🟡 noise → drop | `away_bp_xwoba_against_14d` |
| 174 | C85 | 1 | -0.00023 | [-0.00043, -0.00001] | ✅ signal | `away_lineup_iso_vs_starter_archetype` |

## Payoff (E1.3 AC)
Dropping the 158 noise clusters (190 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_home_win_bullpen_v3.json`_