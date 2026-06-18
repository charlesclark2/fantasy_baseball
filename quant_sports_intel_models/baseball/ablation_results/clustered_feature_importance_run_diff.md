# Clustered Feature Importance — run_diff (Epic E1.3)

- Recipe: `ngboost-Normal(challenger)` · metric **mae** (lower = better) · pooled baseline 3.0620
- Features: **167** in **147** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 130/147** covering **150/167** features → drop/consolidate candidates (≈90% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δmae) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C21 | 1 | +0.21385 | [+0.18931, +0.23838] | ✅ signal | `home_bp_eb_xwoba` |
| 2 | C22 | 1 | +0.16712 | [+0.14237, +0.19072] | ✅ signal | `away_bp_eb_xwoba` |
| 3 | C25 | 1 | +0.06594 | [+0.04868, +0.08259] | ✅ signal | `home_bp_eb_coverage_pct` |
| 4 | C23 | 1 | +0.06491 | [+0.05122, +0.07786] | ✅ signal | `home_bp_eb_uncertainty` |
| 5 | C24 | 1 | +0.06180 | [+0.04711, +0.07665] | ✅ signal | `away_bp_eb_uncertainty` |
| 6 | C27 | 1 | +0.02714 | [+0.01542, +0.03887] | ✅ signal | `away_bp_eb_coverage_pct` |
| 7 | C1 | 2 | +0.01242 | [-0.00326, +0.02784] | 🟡 noise → drop | `elo_diff, pythagorean_win_exp_diff` |
| 8 | C142 | 1 | +0.01085 | [+0.00642, +0.01517] | ✅ signal | `away_team_sequential_bullpen_xwoba` |
| 9 | C141 | 1 | +0.00438 | [+0.00040, +0.00873] | ✅ signal | `home_team_sequential_bullpen_xwoba` |
| 10 | C116 | 1 | +0.00413 | [+0.00201, +0.00625] | ✅ signal | `home_avg_hard_hit_pct_vs_lhp` |
| 11 | C138 | 1 | +0.00356 | [+0.00082, +0.00637] | ✅ signal | `home_starter_appearances_30d` |
| 12 | C43 | 1 | +0.00229 | [-0.00029, +0.00483] | 🟡 noise → drop | `home_away_bp_xwoba_against_30d_pct_diff` |
| 13 | C79 | 1 | +0.00212 | [-0.00119, +0.00543] | 🟡 noise → drop | `home_avg_hard_hit_pct_std` |
| 14 | C10 | 2 | +0.00200 | [-0.00026, +0.00451] | 🟡 noise → drop | `away_avg_woba_std, away_avg_woba_30d` |
| 15 | C51 | 1 | +0.00188 | [+0.00075, +0.00314] | ✅ signal | `away_starter_xwoba_against_std` |
| 16 | C103 | 1 | +0.00166 | [-0.00002, +0.00320] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 17 | C134 | 1 | +0.00120 | [-0.00066, +0.00312] | 🟡 noise → drop | `away_lineup_archetype_pa_coverage` |
| 18 | C9 | 2 | +0.00120 | [+0.00037, +0.00211] | ✅ signal | `away_avg_bb_pct_std, away_avg_bb_pct_30d` |
| 19 | C31 | 1 | +0.00115 | [-0.00376, +0.00596] | 🟡 noise → drop | `away_starter_stuff_plus` |
| 20 | C65 | 1 | +0.00113 | [-0.00009, +0.00230] | 🟡 noise → drop | `away_starter_curveball_stuff_plus` |
| 21 | C107 | 1 | +0.00111 | [-0.00130, +0.00348] | 🟡 noise → drop | `away_lineup_vs_home_starter_h2h_xwoba` |
| 22 | C63 | 1 | +0.00095 | [-0.00098, +0.00294] | 🟡 noise → drop | `home_starter_avg_ip_season` |
| 23 | C75 | 1 | +0.00092 | [-0.00206, +0.00393] | 🟡 noise → drop | `home_bp_xwoba_against_30d` |
| 24 | C128 | 1 | +0.00086 | [-0.00008, +0.00186] | 🟡 noise → drop | `away_closer_used_prev_1d` |
| 25 | C123 | 1 | +0.00081 | [-0.00031, +0.00192] | 🟡 noise → drop | `home_lineup_archetype_pa_coverage` |
| 26 | C135 | 1 | +0.00078 | [-0.00047, +0.00202] | 🟡 noise → drop | `away_pit_xwoba_7d_minus_30d` |
| 27 | C80 | 1 | +0.00063 | [-0.00200, +0.00314] | 🟡 noise → drop | `away_vs_lhp_bb_pct_30d` |
| 28 | C71 | 1 | +0.00060 | [-0.00143, +0.00254] | 🟡 noise → drop | `away_pit_bb_pct_7d` |
| 29 | C50 | 1 | +0.00055 | [-0.00036, +0.00148] | 🟡 noise → drop | `home_starter_k_pct_30d` |
| 30 | C100 | 1 | +0.00043 | [-0.00089, +0.00190] | 🟡 noise → drop | `away_avg_whiff_rate_30d` |
| 31 | C125 | 1 | +0.00042 | [-0.00058, +0.00153] | 🟡 noise → drop | `home_starter_bb_pct_vs_rhb` |
| 32 | C82 | 1 | +0.00040 | [-0.00045, +0.00129] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 33 | C130 | 1 | +0.00038 | [-0.00079, +0.00154] | 🟡 noise → drop | `home_off_bb_pct_7d` |
| 34 | C19 | 2 | +0.00038 | [-0.00067, +0.00142] | 🟡 noise → drop | `home_starter_hard_hit_pct_30d, home_starter_hard_hit_pct_14d` |
| 35 | C55 | 1 | +0.00037 | [-0.00107, +0.00180] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 36 | C89 | 1 | +0.00037 | [-0.00011, +0.00092] | 🟡 noise → drop | `away_starter_batter_chase_rate_30d` |
| 37 | C74 | 1 | +0.00031 | [-0.00079, +0.00144] | 🟡 noise → drop | `away_starter_k_pct_vs_lhb` |
| 38 | C88 | 1 | +0.00030 | [-0.00177, +0.00246] | 🟡 noise → drop | `away_bp_bb_pct_14d` |
| 39 | C108 | 1 | +0.00030 | [-0.00074, +0.00140] | 🟡 noise → drop | `away_pit_barrel_pct_30d` |
| 40 | C133 | 1 | +0.00028 | [-0.00116, +0.00187] | 🟡 noise → drop | `home_pythagorean_residual_season` |
| 41 | C6 | 2 | +0.00028 | [-0.00045, +0.00107] | 🟡 noise → drop | `home_off_runs_per_game_std, home_off_runs_per_game_30d` |
| 42 | C73 | 1 | +0.00027 | [-0.00027, +0.00080] | 🟡 noise → drop | `home_starter_changeup_stuff_plus` |
| 43 | C60 | 1 | +0.00027 | [-0.00171, +0.00216] | 🟡 noise → drop | `home_avg_xwoba_30d` |
| 44 | C13 | 2 | +0.00026 | [-0.00055, +0.00110] | 🟡 noise → drop | `home_starter_xwoba_against_7d, home_starter_xwoba_7d_minus_std` |
| 45 | C57 | 1 | +0.00026 | [-0.00039, +0.00093] | 🟡 noise → drop | `home_starter_csw_pct_season` |
| 46 | C122 | 1 | +0.00025 | [-0.00012, +0.00076] | 🟡 noise → drop | `away_starter_hard_hit_pct_std` |
| 47 | C64 | 1 | +0.00025 | [-0.00027, +0.00083] | 🟡 noise → drop | `home_starter_avg_ip_last_3` |
| 48 | C53 | 1 | +0.00024 | [-0.00020, +0.00069] | 🟡 noise → drop | `away_lineup_vs_home_starter_k_pct_adj` |
| 49 | C68 | 1 | +0.00024 | [-0.00176, +0.00234] | 🟡 noise → drop | `home_avg_woba_vs_rhp` |
| 50 | C110 | 1 | +0.00024 | [-0.00013, +0.00061] | 🟡 noise → drop | `away_avg_k_pct_vs_rhp` |
| 51 | C124 | 1 | +0.00022 | [+0.00001, +0.00044] | ✅ signal | `series_game_number` |
| 52 | C81 | 1 | +0.00021 | [-0.00019, +0.00060] | 🟡 noise → drop | `home_avg_woba_30d` |
| 53 | C33 | 1 | +0.00020 | [-0.00001, +0.00043] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 54 | C127 | 1 | +0.00019 | [-0.00042, +0.00086] | 🟡 noise → drop | `home_starter_barrel_pct_std` |
| 55 | C37 | 1 | +0.00018 | [-0.00284, +0.00344] | 🟡 noise → drop | `away_lineup_avg_woba_vs_cluster` |
| 56 | C115 | 1 | +0.00018 | [-0.00196, +0.00237] | 🟡 noise → drop | `home_lineup_vs_away_starter_h2h_woba` |
| 57 | C20 | 2 | +0.00018 | [-0.00139, +0.00173] | 🟡 noise → drop | `ump_run_impact_zscore, ump_accuracy_zscore` |
| 58 | C69 | 1 | +0.00016 | [-0.00126, +0.00160] | 🟡 noise → drop | `away_lineup_iso_vs_starter_archetype` |
| 59 | C118 | 1 | +0.00016 | [-0.00029, +0.00063] | 🟡 noise → drop | `right_line_ft` |
| 60 | C35 | 1 | +0.00016 | [-0.00012, +0.00044] | 🟡 noise → drop | `away_off_runs_per_game_std` |
| 61 | C66 | 1 | +0.00015 | [-0.00085, +0.00114] | 🟡 noise → drop | `away_avg_woba_vs_rhp` |
| 62 | C15 | 2 | +0.00014 | [-0.00077, +0.00099] | 🟡 noise → drop | `home_off_xwoba_7d, home_off_xwoba_14d` |
| 63 | C114 | 1 | +0.00013 | [-0.00024, +0.00050] | 🟡 noise → drop | `home_starter_bb_pct_30d` |
| 64 | C44 | 1 | +0.00012 | [-0.00029, +0.00047] | 🟡 noise → drop | `home_starter_trailing_ra9_30g` |
| 65 | C95 | 1 | +0.00011 | [-0.00026, +0.00048] | 🟡 noise → drop | `home_vs_lhp_woba_std` |
| 66 | C5 | 2 | +0.00011 | [-0.00064, +0.00087] | 🟡 noise → drop | `away_pit_xwoba_against_14d, away_pit_xwoba_against_7d` |
| 67 | C78 | 1 | +0.00010 | [-0.00009, +0.00029] | 🟡 noise → drop | `home_off_hard_hit_pct_std` |
| 68 | C7 | 2 | +0.00008 | [-0.00048, +0.00062] | 🟡 noise → drop | `away_avg_xwoba_std, away_avg_xwoba_30d` |
| 69 | C38 | 1 | +0.00008 | [-0.00162, +0.00180] | 🟡 noise → drop | `away_starter_csw_pct_season` |
| 70 | C28 | 1 | +0.00006 | [-0.00072, +0.00076] | 🟡 noise → drop | `home_pit_woba_against_30d` |
| 71 | C91 | 1 | +0.00006 | [-0.00025, +0.00038] | 🟡 noise → drop | `away_starter_whiff_rate_vs_rhb` |
| 72 | C11 | 2 | +0.00006 | [-0.00123, +0.00131] | 🟡 noise → drop | `away_starter_whiff_rate_std, away_starter_whiff_rate_14d` |
| 73 | C18 | 2 | +0.00005 | [-0.00229, +0.00234] | 🟡 noise → drop | `home_bp_whiff_rate_30d, home_bp_whiff_rate_14d` |
| 74 | C86 | 1 | +0.00005 | [-0.00046, +0.00047] | 🟡 noise → drop | `home_starter_whiff_rate_vs_rhb` |
| 75 | C121 | 1 | +0.00002 | [-0.00052, +0.00054] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 76 | C109 | 1 | +0.00002 | [-0.00033, +0.00038] | 🟡 noise → drop | `home_vs_lhp_slugging_30d` |
| 77 | C87 | 1 | +0.00001 | [-0.00117, +0.00114] | 🟡 noise → drop | `home_starter_avg_fastball_velo` |
| 78 | C85 | 1 | +0.00001 | [-0.00004, +0.00006] | 🟡 noise → drop | `home_n_power_pull` |
| 79 | C126 | 1 | +0.00001 | [-0.00012, +0.00013] | 🟡 noise → drop | `home_lineup_k_pct_vs_starter_archetype` |
| 80 | C30 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_k_pct` |
| 81 | C39 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_bb_pct` |
| 82 | C40 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_woba` |
| 83 | C41 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_iso` |
| 84 | C42 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 85 | C46 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against` |
| 86 | C48 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_iso` |
| 87 | C58 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_bb_pct` |
| 88 | C90 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_uncertainty` |
| 89 | C112 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_bb_pct` |
| 90 | C119 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_high_leverage_used_prev_2d` |
| 91 | C143 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_woba_sequential` |
| 92 | C144 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against_sequential` |
| 93 | C145 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `has_starter_platoon_data` |
| 94 | C146 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 95 | C139 | 1 | -0.00000 | [-0.00001, +0.00001] | 🟡 noise → drop | `home_injured_player_count` |
| 96 | C47 | 1 | -0.00001 | [-0.00104, +0.00096] | 🟡 noise → drop | `left_ft` |
| 97 | C120 | 1 | -0.00001 | [-0.00009, +0.00006] | 🟡 noise → drop | `away_n_high_whiff` |
| 98 | C45 | 1 | -0.00001 | [-0.00021, +0.00018] | 🟡 noise → drop | `runs_per_game_at_park` |
| 99 | C136 | 1 | -0.00002 | [-0.00059, +0.00058] | 🟡 noise → drop | `home_starter_barrel_pct_7d` |
| 100 | C70 | 1 | -0.00003 | [-0.00062, +0.00057] | 🟡 noise → drop | `away_vs_lhp_woba_30d` |
| 101 | C106 | 1 | -0.00004 | [-0.00112, +0.00109] | 🟡 noise → drop | `home_pit_barrel_pct_30d` |
| 102 | C129 | 1 | -0.00004 | [-0.00137, +0.00107] | 🟡 noise → drop | `home_lineup_vs_away_starter_bb_pct_adj` |
| 103 | C72 | 1 | -0.00006 | [-0.00100, +0.00084] | 🟡 noise → drop | `home_lineup_bat_speed_vs_starter_velo` |
| 104 | C52 | 1 | -0.00007 | [-0.00024, +0.00008] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 105 | C140 | 1 | -0.00010 | [-0.00050, +0.00031] | 🟡 noise → drop | `away_team_sequential_woba` |
| 106 | C94 | 1 | -0.00010 | [-0.00122, +0.00098] | 🟡 noise → drop | `home_avg_chase_rate_30d` |
| 107 | C137 | 1 | -0.00010 | [-0.00032, +0.00011] | 🟡 noise → drop | `home_bp_innings_pitched_30d` |
| 108 | C29 | 1 | -0.00011 | [-0.00095, +0.00072] | 🟡 noise → drop | `away_games_back` |
| 109 | C98 | 1 | -0.00012 | [-0.00175, +0.00148] | 🟡 noise → drop | `away_team_oaa_prior_season` |
| 110 | C113 | 1 | -0.00013 | [-0.00032, +0.00004] | 🟡 noise → drop | `away_vs_lhp_k_pct_30d` |
| 111 | C92 | 1 | -0.00014 | [-0.00073, +0.00046] | 🟡 noise → drop | `home_avg_hard_hit_pct_vs_rhp` |
| 112 | C59 | 1 | -0.00014 | [-0.00140, +0.00111] | 🟡 noise → drop | `home_avg_xwoba_vs_lhp` |
| 113 | C61 | 1 | -0.00015 | [-0.00103, +0.00074] | 🟡 noise → drop | `away_starter_changeup_stuff_plus` |
| 114 | C56 | 1 | -0.00016 | [-0.00118, +0.00093] | 🟡 noise → drop | `home_pit_hard_hit_pct_std` |
| 115 | C104 | 1 | -0.00016 | [-0.00036, +0.00004] | 🟡 noise → drop | `home_starter_xwoba_vs_rhb` |
| 116 | C117 | 1 | -0.00017 | [-0.00070, +0.00033] | 🟡 noise → drop | `home_woba_with_risp_30d` |
| 117 | C77 | 1 | -0.00020 | [-0.00072, +0.00029] | 🟡 noise → drop | `away_avg_hard_hit_pct_std` |
| 118 | C76 | 1 | -0.00021 | [-0.00148, +0.00100] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 119 | C62 | 1 | -0.00021 | [-0.00105, +0.00069] | 🟡 noise → drop | `away_off_barrel_pct_30d` |
| 120 | C111 | 1 | -0.00022 | [-0.00074, +0.00029] | 🟡 noise → drop | `home_starter_xwoba_vs_lhb` |
| 121 | C96 | 1 | -0.00023 | [-0.00374, +0.00312] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 122 | C83 | 1 | -0.00025 | [-0.00080, +0.00033] | 🟡 noise → drop | `home_off_barrel_pct_30d` |
| 123 | C102 | 1 | -0.00026 | [-0.00077, +0.00014] | 🟡 noise → drop | `home_starter_batter_chase_rate_7d` |
| 124 | C54 | 1 | -0.00029 | [-0.00078, +0.00019] | 🟡 noise → drop | `away_lineup_xwoba_vs_starter_archetype` |
| 125 | C97 | 1 | -0.00032 | [-0.00122, +0.00063] | 🟡 noise → drop | `home_vs_rhp_slugging_30d` |
| 126 | C132 | 1 | -0.00033 | [-0.00065, -0.00005] | ✅ signal | `away_injured_player_count` |
| 127 | C32 | 1 | -0.00040 | [-0.00217, +0.00139] | 🟡 noise → drop | `home_away_off_woba_30d_pct_diff` |
| 128 | C49 | 1 | -0.00041 | [-0.00124, +0.00044] | 🟡 noise → drop | `home_starter_trailing_fip_30g` |
| 129 | C101 | 1 | -0.00043 | [-0.00232, +0.00133] | 🟡 noise → drop | `away_off_k_pct_std` |
| 130 | C131 | 1 | -0.00048 | [-0.00126, +0.00034] | 🟡 noise → drop | `home_away_injury_adj_avg_woba_30d_pct_diff` |
| 131 | C8 | 2 | -0.00057 | [-0.00142, +0.00025] | 🟡 noise → drop | `away_vs_lhp_xwoba_std, away_vs_lhp_xwoba_30d` |
| 132 | C36 | 1 | -0.00066 | [-0.00325, +0.00191] | 🟡 noise → drop | `home_away_starter_xwoba_against_std_pct_diff` |
| 133 | C84 | 1 | -0.00066 | [-0.00202, +0.00062] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 134 | C12 | 2 | -0.00075 | [-0.00282, +0.00139] | 🟡 noise → drop | `home_off_bb_pct_std, home_off_bb_pct_30d` |
| 135 | C16 | 2 | -0.00082 | [-0.00192, +0.00030] | 🟡 noise → drop | `home_bp_k_pct_30d, home_bp_k_pct_14d` |
| 136 | C67 | 1 | -0.00084 | [-0.00214, +0.00044] | 🟡 noise → drop | `home_pit_bb_pct_std` |
| 137 | C99 | 1 | -0.00094 | [-0.00281, +0.00082] | 🟡 noise → drop | `away_bullpen_pitches_prev_7d` |
| 138 | C14 | 2 | -0.00095 | [-0.00234, +0.00014] | 🟡 noise → drop | `home_off_xwoba_30d, home_team_sequential_woba` |
| 139 | C93 | 1 | -0.00095 | [-0.00193, -0.00010] | ✅ signal | `away_starter_avg_fastball_velo` |
| 140 | C3 | 2 | -0.00107 | [-0.00348, +0.00140] | 🟡 noise → drop | `away_pit_woba_against_14d, away_pit_woba_against_7d` |
| 141 | C17 | 2 | -0.00108 | [-0.00323, +0.00106] | 🟡 noise → drop | `home_off_runs_per_game_14d, home_off_runs_per_game_7d` |
| 142 | C105 | 1 | -0.00110 | [-0.00407, +0.00160] | 🟡 noise → drop | `away_starter_bb_pct_std` |
| 143 | C4 | 2 | -0.00115 | [-0.00276, +0.00040] | 🟡 noise → drop | `home_pit_xwoba_against_30d, home_pit_xwoba_against_14d` |
| 144 | C26 | 1 | -0.00152 | [-0.00318, +0.00004] | 🟡 noise → drop | `away_pit_woba_against_std` |
| 145 | C0 | 3 | -0.00252 | [-0.01108, +0.00601] | 🟡 noise → drop | `home_elo, home_pythagorean_win_exp, home_team_sequential_win_prob` |
| 146 | C34 | 1 | -0.00339 | [-0.00632, -0.00045] | ✅ signal | `home_away_starter_k_pct_std_pct_diff` |
| 147 | C2 | 2 | -0.00602 | [-0.01155, -0.00079] | ✅ signal | `away_elo, away_team_sequential_win_prob` |

## Payoff (E1.3 AC)
Dropping the 130 noise clusters (150 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_run_diff.json`_