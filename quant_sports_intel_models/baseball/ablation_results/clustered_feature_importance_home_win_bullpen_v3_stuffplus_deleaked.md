# Clustered Feature Importance — home_win (Epic E1.3)

- Recipe: `xgb_platt(challenger)` · metric **brier** (lower = better) · pooled baseline 0.2364
- Features: **209** in **174** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 158/174** covering **192/209** features → drop/consolidate candidates (≈92% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δbrier) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C30 | 1 | +0.00777 | [+0.00618, +0.00946] | ✅ signal | `home_bp_eb_coverage_pct` |
| 2 | C31 | 1 | +0.00351 | [+0.00248, +0.00457] | ✅ signal | `away_bp_eb_coverage_pct` |
| 3 | C9 | 2 | +0.00147 | [+0.00067, +0.00230] | ✅ signal | `elo_diff, pythagorean_win_exp_diff` |
| 4 | C17 | 2 | +0.00043 | [+0.00014, +0.00070] | ✅ signal | `home_avg_xwoba_std, home_avg_xwoba_30d` |
| 5 | C7 | 2 | +0.00027 | [+0.00008, +0.00045] | ✅ signal | `home_bp_eb_xwoba, home_team_sequential_bullpen_xwoba` |
| 6 | C1 | 3 | +0.00022 | [-0.00001, +0.00046] | 🟡 noise → drop | `away_elo, away_pythagorean_win_exp, away_team_sequential_win_prob` |
| 7 | C51 | 1 | +0.00021 | [+0.00007, +0.00036] | ✅ signal | `home_starter_trailing_ra9_30g` |
| 8 | C43 | 1 | +0.00019 | [-0.00006, +0.00045] | 🟡 noise → drop | `home_away_starter_k_pct_std_pct_diff` |
| 9 | C126 | 1 | +0.00017 | [+0.00000, +0.00032] | ✅ signal | `away_off_k_pct_std` |
| 10 | C6 | 3 | +0.00015 | [-0.00019, +0.00048] | 🟡 noise → drop | `home_starter_bb_pct_std, home_starter_bb_pct_14d, home_starter_bb_pct_30d` |
| 11 | C137 | 1 | +0.00014 | [-0.00001, +0.00029] | 🟡 noise → drop | `home_lineup_vs_away_starter_h2h_xwoba` |
| 12 | C169 | 1 | +0.00013 | [+0.00001, +0.00027] | ✅ signal | `home_starter_appearances_30d` |
| 13 | C122 | 1 | +0.00013 | [-0.00004, +0.00031] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 14 | C110 | 1 | +0.00012 | [-0.00001, +0.00026] | 🟡 noise → drop | `away_avg_k_pct_std` |
| 15 | C54 | 1 | +0.00012 | [-0.00000, +0.00024] | 🟡 noise → drop | `home_starter_trailing_fip_30g` |
| 16 | C146 | 1 | +0.00011 | [+0.00002, +0.00020] | ✅ signal | `home_bp_hard_hit_pct_14d` |
| 17 | C111 | 1 | +0.00011 | [-0.00004, +0.00027] | 🟡 noise → drop | `away_starter_xwoba_against_14d` |
| 18 | C14 | 2 | +0.00010 | [-0.00007, +0.00028] | 🟡 noise → drop | `home_lineup_avg_woba_vs_cluster, home_lineup_avg_xwoba_vs_cluster` |
| 19 | C20 | 2 | +0.00010 | [-0.00011, +0.00031] | 🟡 noise → drop | `away_bp_k_pct_30d, away_bp_k_pct_14d` |
| 20 | C2 | 3 | +0.00010 | [-0.00014, +0.00033] | 🟡 noise → drop | `home_elo, home_pythagorean_win_exp, home_team_sequential_win_prob` |
| 21 | C28 | 2 | +0.00009 | [-0.00002, +0.00021] | 🟡 noise → drop | `home_starter_barrel_pct_14d, home_starter_barrel_pct_7d` |
| 22 | C129 | 1 | +0.00009 | [-0.00009, +0.00026] | 🟡 noise → drop | `away_lineup_vs_home_starter_h2h_xwoba` |
| 23 | C18 | 2 | +0.00009 | [-0.00011, +0.00029] | 🟡 noise → drop | `away_starter_whiff_rate_std, away_starter_whiff_rate_14d` |
| 24 | C103 | 1 | +0.00009 | [-0.00008, +0.00027] | 🟡 noise → drop | `away_starter_avg_ip_last_3` |
| 25 | C152 | 1 | +0.00009 | [-0.00005, +0.00021] | 🟡 noise → drop | `home_lineup_archetype_pa_coverage` |
| 26 | C99 | 1 | +0.00008 | [-0.00003, +0.00019] | 🟡 noise → drop | `away_avg_hard_hit_pct_std` |
| 27 | C44 | 1 | +0.00008 | [-0.00001, +0.00017] | 🟡 noise → drop | `away_off_runs_per_game_std` |
| 28 | C166 | 1 | +0.00007 | [-0.00004, +0.00019] | 🟡 noise → drop | `home_starter_barrel_pct_30d` |
| 29 | C37 | 1 | +0.00007 | [-0.00005, +0.00020] | 🟡 noise → drop | `home_games_back` |
| 30 | C19 | 2 | +0.00007 | [-0.00005, +0.00020] | 🟡 noise → drop | `home_off_bb_pct_std, home_off_bb_pct_30d` |
| 31 | C71 | 1 | +0.00007 | [-0.00005, +0.00019] | 🟡 noise → drop | `home_starter_csw_pct_season` |
| 32 | C136 | 1 | +0.00007 | [-0.00003, +0.00016] | 🟡 noise → drop | `away_bp_innings_pitched_14d` |
| 33 | C139 | 1 | +0.00006 | [-0.00004, +0.00017] | 🟡 noise → drop | `home_starter_xwoba_7d_minus_std` |
| 34 | C97 | 1 | +0.00006 | [-0.00006, +0.00019] | 🟡 noise → drop | `home_catcher_defensive_runs` |
| 35 | C134 | 1 | +0.00006 | [-0.00004, +0.00016] | 🟡 noise → drop | `home_avg_k_pct_std` |
| 36 | C72 | 1 | +0.00005 | [-0.00006, +0.00017] | 🟡 noise → drop | `home_pit_k_pct_7d` |
| 37 | C32 | 1 | +0.00005 | [-0.00016, +0.00028] | 🟡 noise → drop | `home_pit_woba_against_std` |
| 38 | C149 | 1 | +0.00005 | [-0.00016, +0.00026] | 🟡 noise → drop | `away_lineup_k_pct_vs_starter_archetype` |
| 39 | C158 | 1 | +0.00005 | [-0.00006, +0.00016] | 🟡 noise → drop | `home_lineup_vs_away_starter_bb_pct_adj` |
| 40 | C118 | 1 | +0.00005 | [-0.00011, +0.00020] | 🟡 noise → drop | `away_starter_whiff_rate_vs_rhb` |
| 41 | C35 | 1 | +0.00005 | [-0.00004, +0.00012] | 🟡 noise → drop | `away_games_back` |
| 42 | C100 | 1 | +0.00005 | [-0.00007, +0.00016] | 🟡 noise → drop | `home_avg_barrel_pct_std` |
| 43 | C8 | 2 | +0.00005 | [-0.00010, +0.00020] | 🟡 noise → drop | `away_bp_eb_xwoba, away_team_sequential_bullpen_xwoba` |
| 44 | C5 | 3 | +0.00004 | [-0.00010, +0.00018] | 🟡 noise → drop | `home_starter_xwoba_against_14d, home_starter_xwoba_against_30d, home_starter_xwoba_against_std` |
| 45 | C74 | 1 | +0.00004 | [-0.00005, +0.00013] | 🟡 noise → drop | `away_lineup_archetype_avg_woba` |
| 46 | C133 | 1 | +0.00004 | [-0.00007, +0.00015] | 🟡 noise → drop | `home_off_hard_hit_pct_7d` |
| 47 | C98 | 1 | +0.00004 | [-0.00013, +0.00022] | 🟡 noise → drop | `away_avg_bb_pct_vs_lhp` |
| 48 | C120 | 1 | +0.00004 | [-0.00010, +0.00018] | 🟡 noise → drop | `away_off_bb_pct_7d` |
| 49 | C55 | 1 | +0.00004 | [-0.00008, +0.00016] | 🟡 noise → drop | `away_lineup_avg_xwoba_vs_cluster` |
| 50 | C61 | 1 | +0.00003 | [-0.00008, +0.00015] | 🟡 noise → drop | `home_avg_woba_std` |
| 51 | C168 | 1 | +0.00003 | [-0.00007, +0.00013] | 🟡 noise → drop | `away_starter_hard_hit_pct_7d` |
| 52 | C91 | 1 | +0.00003 | [-0.00008, +0.00015] | 🟡 noise → drop | `home_lineup_bat_speed_vs_starter_velo` |
| 53 | C142 | 1 | +0.00003 | [-0.00005, +0.00011] | 🟡 noise → drop | `home_starter_hard_hit_pct_std` |
| 54 | C125 | 1 | +0.00003 | [-0.00018, +0.00024] | 🟡 noise → drop | `away_avg_whiff_rate_30d` |
| 55 | C112 | 1 | +0.00003 | [-0.00007, +0.00013] | 🟡 noise → drop | `home_starter_whiff_rate_vs_rhb` |
| 56 | C155 | 1 | +0.00003 | [-0.00006, +0.00011] | 🟡 noise → drop | `home_starter_bb_pct_vs_rhb` |
| 57 | C40 | 1 | +0.00003 | [-0.00004, +0.00009] | 🟡 noise → drop | `home_away_off_woba_30d_pct_diff` |
| 58 | C161 | 1 | +0.00003 | [-0.00002, +0.00007] | 🟡 noise → drop | `away_closer_used_prev_2d` |
| 59 | C107 | 1 | +0.00002 | [-0.00006, +0.00011] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 60 | C115 | 1 | +0.00002 | [-0.00007, +0.00012] | 🟡 noise → drop | `away_lineup_bat_speed_vs_starter_velo` |
| 61 | C109 | 1 | +0.00002 | [-0.00010, +0.00015] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 62 | C77 | 1 | +0.00002 | [-0.00002, +0.00007] | 🟡 noise → drop | `away_n_no_label` |
| 63 | C157 | 1 | +0.00002 | [-0.00003, +0.00007] | 🟡 noise → drop | `away_closer_used_prev_1d` |
| 64 | C105 | 1 | +0.00002 | [-0.00005, +0.00009] | 🟡 noise → drop | `home_off_runs_per_game_14d` |
| 65 | C26 | 2 | +0.00002 | [-0.00014, +0.00017] | 🟡 noise → drop | `away_starter_bb_pct_std, away_starter_bb_pct_30d` |
| 66 | C84 | 1 | +0.00002 | [-0.00008, +0.00013] | 🟡 noise → drop | `home_avg_woba_vs_rhp` |
| 67 | C89 | 1 | +0.00002 | [-0.00007, +0.00011] | 🟡 noise → drop | `away_pit_bb_pct_7d` |
| 68 | C143 | 1 | +0.00002 | [-0.00012, +0.00016] | 🟡 noise → drop | `home_starter_fip_ra9_gap` |
| 69 | C119 | 1 | +0.00002 | [-0.00018, +0.00020] | 🟡 noise → drop | `right_center_ft` |
| 70 | C92 | 1 | +0.00002 | [-0.00003, +0.00006] | 🟡 noise → drop | `home_n_no_label` |
| 71 | C82 | 1 | +0.00001 | [-0.00011, +0.00014] | 🟡 noise → drop | `away_starter_avg_ip_season` |
| 72 | C79 | 1 | +0.00001 | [-0.00011, +0.00013] | 🟡 noise → drop | `away_avg_xwoba_vs_lhp` |
| 73 | C66 | 1 | +0.00001 | [-0.00005, +0.00008] | 🟡 noise → drop | `home_starter_k_pct_vs_lhb` |
| 74 | C151 | 1 | +0.00001 | [-0.00002, +0.00005] | 🟡 noise → drop | `home_lineup_archetype_slot_coverage` |
| 75 | C78 | 1 | +0.00001 | [-0.00012, +0.00013] | 🟡 noise → drop | `home_starter_avg_ip_season` |
| 76 | C104 | 1 | +0.00001 | [-0.00010, +0.00012] | 🟡 noise → drop | `home_avg_hard_hit_pct_std` |
| 77 | C38 | 1 | +0.00001 | [-0.00010, +0.00011] | 🟡 noise → drop | `home_pit_woba_against_14d` |
| 78 | C57 | 1 | +0.00001 | [-0.00010, +0.00012] | 🟡 noise → drop | `away_starter_k_pct_30d` |
| 79 | C160 | 1 | +0.00001 | [-0.00001, +0.00003] | 🟡 noise → drop | `home_win_rate_trailing_3yr` |
| 80 | C106 | 1 | +0.00001 | [-0.00003, +0.00004] | 🟡 noise → drop | `center_ft` |
| 81 | C144 | 1 | +0.00001 | [-0.00004, +0.00005] | 🟡 noise → drop | `away_lineup_cluster_slot_coverage` |
| 82 | C22 | 2 | +0.00000 | [-0.00023, +0.00022] | 🟡 noise → drop | `away_starter_batter_chase_rate_std, away_starter_batter_chase_rate_30d` |
| 83 | C65 | 1 | +0.00000 | [-0.00007, +0.00008] | 🟡 noise → drop | `away_avg_woba_std` |
| 84 | C10 | 2 | +0.00000 | [-0.00022, +0.00022] | 🟡 noise → drop | `away_pit_woba_against_std, away_pit_woba_against_30d` |
| 85 | C58 | 1 | +0.00000 | [-0.00007, +0.00008] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 86 | C11 | 2 | +0.00000 | [-0.00009, +0.00009] | 🟡 noise → drop | `home_pit_xwoba_against_std, home_pit_xwoba_against_30d` |
| 87 | C130 | 1 | +0.00000 | [-0.00013, +0.00014] | 🟡 noise → drop | `away_pit_barrel_pct_30d` |
| 88 | C113 | 1 | +0.00000 | [-0.00012, +0.00012] | 🟡 noise → drop | `away_avg_hard_hit_pct_vs_rhp` |
| 89 | C167 | 1 | +0.00000 | [-0.00011, +0.00011] | 🟡 noise → drop | `home_bp_innings_pitched_30d` |
| 90 | C127 | 1 | +0.00000 | [-0.00014, +0.00014] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 91 | C76 | 1 | +0.00000 | [-0.00012, +0.00012] | 🟡 noise → drop | `away_starter_changeup_stuff_plus` |
| 92 | C12 | 2 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against, away_starter_eb_xwoba_against_sequential` |
| 93 | C16 | 2 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against, home_starter_eb_xwoba_against_sequential` |
| 94 | C39 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_woba` |
| 95 | C47 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_bb_pct` |
| 96 | C48 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_iso` |
| 97 | C49 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 98 | C52 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_iso` |
| 99 | C117 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_uncertainty` |
| 100 | C132 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_uncertainty` |
| 101 | C171 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_woba_sequential` |
| 102 | C173 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 103 | C83 | 1 | -0.00000 | [-0.00014, +0.00014] | 🟡 noise → drop | `home_starter_whiff_rate_14d` |
| 104 | C164 | 1 | -0.00000 | [-0.00008, +0.00007] | 🟡 noise → drop | `away_pit_xwoba_7d_minus_30d` |
| 105 | C154 | 1 | -0.00000 | [-0.00004, +0.00004] | 🟡 noise → drop | `series_game_number` |
| 106 | C172 | 1 | -0.00000 | [-0.00001, +0.00001] | 🟡 noise → drop | `has_starter_platoon_data` |
| 107 | C156 | 1 | -0.00000 | [-0.00010, +0.00009] | 🟡 noise → drop | `home_lineup_k_pct_vs_starter_archetype` |
| 108 | C148 | 1 | -0.00000 | [-0.00011, +0.00010] | 🟡 noise → drop | `home_starter_hard_hit_pct_14d` |
| 109 | C93 | 1 | -0.00000 | [-0.00016, +0.00015] | 🟡 noise → drop | `away_starter_k_pct_vs_lhb` |
| 110 | C116 | 1 | -0.00000 | [-0.00009, +0.00008] | 🟡 noise → drop | `away_lineup_avg_swing_length` |
| 111 | C147 | 1 | -0.00000 | [-0.00004, +0.00003] | 🟡 noise → drop | `away_n_high_whiff` |
| 112 | C135 | 1 | -0.00000 | [-0.00010, +0.00009] | 🟡 noise → drop | `home_starter_bb_pct_vs_lhb` |
| 113 | C138 | 1 | -0.00000 | [-0.00005, +0.00004] | 🟡 noise → drop | `left_line_ft` |
| 114 | C67 | 1 | -0.00000 | [-0.00013, +0.00012] | 🟡 noise → drop | `away_starter_csw_pct_3start` |
| 115 | C94 | 1 | -0.00001 | [-0.00004, +0.00002] | 🟡 noise → drop | `home_n_patient_obp` |
| 116 | C159 | 1 | -0.00001 | [-0.00008, +0.00007] | 🟡 noise → drop | `home_off_bb_pct_7d` |
| 117 | C25 | 2 | -0.00001 | [-0.00013, +0.00012] | 🟡 noise → drop | `home_bp_whiff_rate_30d, home_bp_whiff_rate_14d` |
| 118 | C145 | 1 | -0.00001 | [-0.00014, +0.00012] | 🟡 noise → drop | `away_starter_bb_pct_7d` |
| 119 | C141 | 1 | -0.00001 | [-0.00006, +0.00004] | 🟡 noise → drop | `right_line_ft` |
| 120 | C124 | 1 | -0.00001 | [-0.00011, +0.00008] | 🟡 noise → drop | `away_team_oaa_prior_season` |
| 121 | C101 | 1 | -0.00001 | [-0.00004, +0.00001] | 🟡 noise → drop | `away_n_power_pull` |
| 122 | C50 | 1 | -0.00001 | [-0.00023, +0.00019] | 🟡 noise → drop | `home_away_bp_xwoba_against_30d_pct_diff` |
| 123 | C59 | 1 | -0.00001 | [-0.00011, +0.00008] | 🟡 noise → drop | `away_lineup_vs_home_starter_k_pct_adj` |
| 124 | C165 | 1 | -0.00001 | [-0.00009, +0.00006] | 🟡 noise → drop | `home_lineup_avg_swing_length` |
| 125 | C121 | 1 | -0.00002 | [-0.00006, +0.00003] | 🟡 noise → drop | `left_center_ft` |
| 126 | C68 | 1 | -0.00002 | [-0.00016, +0.00013] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 127 | C81 | 1 | -0.00002 | [-0.00009, +0.00006] | 🟡 noise → drop | `away_vs_rhp_woba_30d` |
| 128 | C53 | 1 | -0.00002 | [-0.00013, +0.00009] | 🟡 noise → drop | `away_pit_k_pct_7d` |
| 129 | C62 | 1 | -0.00002 | [-0.00009, +0.00006] | 🟡 noise → drop | `away_xwoba_with_runners_on_30d` |
| 130 | C102 | 1 | -0.00002 | [-0.00009, +0.00004] | 🟡 noise → drop | `home_off_hard_hit_pct_std` |
| 131 | C163 | 1 | -0.00002 | [-0.00009, +0.00004] | 🟡 noise → drop | `away_lineup_archetype_pa_coverage` |
| 132 | C13 | 2 | -0.00002 | [-0.00014, +0.00010] | 🟡 noise → drop | `away_pit_xwoba_against_14d, away_pit_xwoba_against_7d` |
| 133 | C73 | 1 | -0.00002 | [-0.00017, +0.00012] | 🟡 noise → drop | `home_woba_against_with_risp_30d` |
| 134 | C128 | 1 | -0.00002 | [-0.00012, +0.00008] | 🟡 noise → drop | `home_avg_bb_pct_30d` |
| 135 | C88 | 1 | -0.00002 | [-0.00010, +0.00005] | 🟡 noise → drop | `home_off_runs_per_game_30d` |
| 136 | C33 | 1 | -0.00003 | [-0.00011, +0.00005] | 🟡 noise → drop | `away_pit_k_pct_std` |
| 137 | C170 | 1 | -0.00003 | [-0.00011, +0.00005] | 🟡 noise → drop | `away_consecutive_away_games` |
| 138 | C24 | 2 | -0.00003 | [-0.00016, +0.00010] | 🟡 noise → drop | `home_bp_k_pct_30d, home_bp_k_pct_14d` |
| 139 | C80 | 1 | -0.00003 | [-0.00017, +0.00011] | 🟡 noise → drop | `away_avg_hard_hit_pct_vs_lhp` |
| 140 | C108 | 1 | -0.00003 | [-0.00012, +0.00007] | 🟡 noise → drop | `away_woba_with_risp_30d` |
| 141 | C114 | 1 | -0.00003 | [-0.00012, +0.00006] | 🟡 noise → drop | `away_pit_hard_hit_pct_30d` |
| 142 | C45 | 1 | -0.00003 | [-0.00012, +0.00004] | 🟡 noise → drop | `home_away_starter_xwoba_against_std_pct_diff` |
| 143 | C131 | 1 | -0.00004 | [-0.00017, +0.00010] | 🟡 noise → drop | `away_avg_k_pct_vs_rhp` |
| 144 | C0 | 3 | -0.00004 | [-0.00022, +0.00014] | 🟡 noise → drop | `home_bp_eb_uncertainty, away_bp_eb_uncertainty, away_losses` |
| 145 | C64 | 1 | -0.00004 | [-0.00010, +0.00003] | 🟡 noise → drop | `away_off_hard_hit_pct_std` |
| 146 | C41 | 1 | -0.00004 | [-0.00017, +0.00010] | 🟡 noise → drop | `away_starter_proj_fip` |
| 147 | C70 | 1 | -0.00004 | [-0.00013, +0.00006] | 🟡 noise → drop | `away_bp_xwoba_against_30d` |
| 148 | C4 | 3 | -0.00004 | [-0.00015, +0.00007] | 🟡 noise → drop | `home_off_xwoba_std, home_off_xwoba_30d, home_team_sequential_woba` |
| 149 | C150 | 1 | -0.00004 | [-0.00015, +0.00007] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 150 | C42 | 1 | -0.00004 | [-0.00014, +0.00005] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 151 | C21 | 2 | -0.00005 | [-0.00015, +0.00005] | 🟡 noise → drop | `away_pit_bb_pct_std, away_pit_bb_pct_30d` |
| 152 | C15 | 2 | -0.00005 | [-0.00017, +0.00007] | 🟡 noise → drop | `away_avg_xwoba_std, away_avg_xwoba_30d` |
| 153 | C27 | 2 | -0.00006 | [-0.00022, +0.00011] | 🟡 noise → drop | `away_starter_hard_hit_pct_std, away_starter_hard_hit_pct_30d` |
| 154 | C60 | 1 | -0.00006 | [-0.00016, +0.00005] | 🟡 noise → drop | `away_woba_against_with_risp_30d` |
| 155 | C34 | 1 | -0.00006 | [-0.00012, -0.00000] | ✅ signal | `elevation_ft` |
| 156 | C46 | 1 | -0.00006 | [-0.00028, +0.00014] | 🟡 noise → drop | `away_starter_trailing_ra9_30g` |
| 157 | C63 | 1 | -0.00006 | [-0.00020, +0.00007] | 🟡 noise → drop | `away_vs_lhp_xwoba_std` |
| 158 | C87 | 1 | -0.00006 | [-0.00021, +0.00007] | 🟡 noise → drop | `away_vs_lhp_woba_30d` |
| 159 | C56 | 1 | -0.00007 | [-0.00013, -0.00001] | ✅ signal | `home_starter_k_pct_30d` |
| 160 | C153 | 1 | -0.00007 | [-0.00017, +0.00003] | 🟡 noise → drop | `home_avg_k_pct_vs_lhp` |
| 161 | C23 | 2 | -0.00007 | [-0.00021, +0.00006] | 🟡 noise → drop | `home_vs_lhp_xwoba_std, home_vs_lhp_woba_std` |
| 162 | C69 | 1 | -0.00008 | [-0.00024, +0.00009] | 🟡 noise → drop | `home_pit_hard_hit_pct_std` |
| 163 | C95 | 1 | -0.00008 | [-0.00024, +0.00008] | 🟡 noise → drop | `home_bp_xwoba_against_30d` |
| 164 | C86 | 1 | -0.00008 | [-0.00018, +0.00001] | 🟡 noise → drop | `away_starter_xwoba_vs_rhb` |
| 165 | C3 | 3 | -0.00009 | [-0.00022, +0.00004] | 🟡 noise → drop | `away_off_xwoba_std, away_off_xwoba_30d, away_team_sequential_woba` |
| 166 | C75 | 1 | -0.00009 | [-0.00015, -0.00003] | ✅ signal | `away_avg_barrel_pct_std` |
| 167 | C36 | 1 | -0.00010 | [-0.00032, +0.00012] | 🟡 noise → drop | `away_starter_stuff_plus` |
| 168 | C162 | 1 | -0.00011 | [-0.00022, -0.00001] | ✅ signal | `away_lineup_avg_attack_angle` |
| 169 | C96 | 1 | -0.00012 | [-0.00028, +0.00002] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 170 | C29 | 2 | -0.00013 | [-0.00045, +0.00021] | 🟡 noise → drop | `ump_run_impact_zscore, ump_accuracy_zscore` |
| 171 | C140 | 1 | -0.00013 | [-0.00026, -0.00000] | ✅ signal | `home_woba_with_risp_30d` |
| 172 | C123 | 1 | -0.00016 | [-0.00026, -0.00005] | ✅ signal | `home_starter_whiff_rate_vs_lhb` |
| 173 | C85 | 1 | -0.00019 | [-0.00040, +0.00002] | 🟡 noise → drop | `away_lineup_iso_vs_starter_archetype` |
| 174 | C90 | 1 | -0.00020 | [-0.00038, -0.00001] | ✅ signal | `away_bp_xwoba_against_14d` |

## Payoff (E1.3 AC)
Dropping the 158 noise clusters (192 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_home_win_bullpen_v3_stuffplus_deleaked.json`_