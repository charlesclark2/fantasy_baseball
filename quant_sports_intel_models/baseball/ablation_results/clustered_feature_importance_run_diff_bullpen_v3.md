# Clustered Feature Importance — run_diff (Epic E1.3)

- Recipe: `ngboost-Normal(challenger)` · metric **mae** (lower = better) · pooled baseline 3.3880
- Features: **167** in **144** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 132/144** covering **154/167** features → drop/consolidate candidates (≈92% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δmae) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C24 | 1 | +0.10935 | [+0.08826, +0.13056] | ✅ signal | `home_bp_eb_coverage_pct` |
| 2 | C26 | 1 | +0.07893 | [+0.05921, +0.09788] | ✅ signal | `away_bp_eb_coverage_pct` |
| 3 | C4 | 2 | +0.04470 | [+0.02996, +0.06139] | ✅ signal | `elo_diff, pythagorean_win_exp_diff` |
| 4 | C66 | 1 | +0.00552 | [-0.00426, +0.01527] | 🟡 noise → drop | `home_pit_bb_pct_std` |
| 5 | C79 | 1 | +0.00485 | [+0.00086, +0.00900] | ✅ signal | `away_vs_lhp_bb_pct_30d` |
| 6 | C3 | 2 | +0.00279 | [+0.00069, +0.00479] | ✅ signal | `home_bp_eb_uncertainty, away_bp_eb_uncertainty` |
| 7 | C30 | 1 | +0.00222 | [-0.00208, +0.00660] | 🟡 noise → drop | `away_starter_stuff_plus` |
| 8 | C15 | 2 | +0.00218 | [-0.00072, +0.00507] | 🟡 noise → drop | `home_off_bb_pct_std, home_off_bb_pct_30d` |
| 9 | C133 | 1 | +0.00206 | [+0.00020, +0.00406] | ✅ signal | `away_lineup_archetype_pa_coverage` |
| 10 | C59 | 1 | +0.00203 | [-0.00037, +0.00451] | 🟡 noise → drop | `home_avg_xwoba_30d` |
| 11 | C63 | 1 | +0.00174 | [+0.00031, +0.00314] | ✅ signal | `home_starter_avg_ip_last_3` |
| 12 | C42 | 1 | +0.00160 | [-0.00085, +0.00413] | 🟡 noise → drop | `home_away_bp_xwoba_against_30d_pct_diff` |
| 13 | C95 | 1 | +0.00150 | [-0.00024, +0.00315] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 14 | C67 | 1 | +0.00141 | [-0.00050, +0.00335] | 🟡 noise → drop | `home_avg_woba_vs_rhp` |
| 15 | C98 | 1 | +0.00138 | [-0.00019, +0.00290] | 🟡 noise → drop | `away_bullpen_pitches_prev_7d` |
| 16 | C14 | 2 | +0.00134 | [-0.00028, +0.00298] | 🟡 noise → drop | `away_starter_whiff_rate_std, away_starter_whiff_rate_14d` |
| 17 | C33 | 1 | +0.00131 | [-0.00182, +0.00449] | 🟡 noise → drop | `home_away_starter_k_pct_std_pct_diff` |
| 18 | C87 | 1 | +0.00123 | [-0.00129, +0.00402] | 🟡 noise → drop | `away_bp_bb_pct_14d` |
| 19 | C131 | 1 | +0.00122 | [-0.00069, +0.00318] | 🟡 noise → drop | `away_injured_player_count` |
| 20 | C134 | 1 | +0.00117 | [-0.00124, +0.00357] | 🟡 noise → drop | `away_pit_xwoba_7d_minus_30d` |
| 21 | C124 | 1 | +0.00111 | [+0.00029, +0.00202] | ✅ signal | `home_starter_bb_pct_vs_rhb` |
| 22 | C13 | 2 | +0.00101 | [-0.00194, +0.00412] | 🟡 noise → drop | `away_avg_woba_std, away_avg_woba_30d` |
| 23 | C86 | 1 | +0.00093 | [-0.00077, +0.00253] | 🟡 noise → drop | `home_starter_avg_fastball_velo` |
| 24 | C1 | 2 | +0.00093 | [+0.00006, +0.00182] | ✅ signal | `home_bp_eb_xwoba, home_team_sequential_bullpen_xwoba` |
| 25 | C56 | 1 | +0.00092 | [+0.00016, +0.00176] | ✅ signal | `home_starter_csw_pct_season` |
| 26 | C121 | 1 | +0.00091 | [-0.00001, +0.00193] | 🟡 noise → drop | `away_starter_hard_hit_pct_std` |
| 27 | C115 | 1 | +0.00086 | [-0.00043, +0.00208] | 🟡 noise → drop | `home_avg_hard_hit_pct_vs_lhp` |
| 28 | C60 | 1 | +0.00082 | [-0.00055, +0.00212] | 🟡 noise → drop | `away_starter_changeup_stuff_plus` |
| 29 | C83 | 1 | +0.00081 | [-0.00077, +0.00251] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 30 | C16 | 2 | +0.00078 | [-0.00124, +0.00285] | 🟡 noise → drop | `home_starter_xwoba_against_7d, home_starter_xwoba_7d_minus_std` |
| 31 | C2 | 2 | +0.00078 | [-0.00058, +0.00218] | 🟡 noise → drop | `away_bp_eb_xwoba, away_team_sequential_bullpen_xwoba` |
| 32 | C75 | 1 | +0.00077 | [-0.00199, +0.00371] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 33 | C107 | 1 | +0.00072 | [-0.00130, +0.00247] | 🟡 noise → drop | `away_pit_barrel_pct_30d` |
| 34 | C122 | 1 | +0.00072 | [-0.00068, +0.00218] | 🟡 noise → drop | `home_lineup_archetype_pa_coverage` |
| 35 | C18 | 2 | +0.00067 | [-0.00091, +0.00241] | 🟡 noise → drop | `home_off_xwoba_7d, home_off_xwoba_14d` |
| 36 | C99 | 1 | +0.00063 | [-0.00133, +0.00261] | 🟡 noise → drop | `away_avg_whiff_rate_30d` |
| 37 | C132 | 1 | +0.00062 | [-0.00055, +0.00182] | 🟡 noise → drop | `home_pythagorean_residual_season` |
| 38 | C19 | 2 | +0.00062 | [-0.00099, +0.00211] | 🟡 noise → drop | `home_bp_k_pct_30d, home_bp_k_pct_14d` |
| 39 | C104 | 1 | +0.00061 | [-0.00116, +0.00233] | 🟡 noise → drop | `away_starter_bb_pct_std` |
| 40 | C126 | 1 | +0.00055 | [-0.00041, +0.00143] | 🟡 noise → drop | `home_starter_barrel_pct_std` |
| 41 | C49 | 1 | +0.00052 | [-0.00049, +0.00156] | 🟡 noise → drop | `home_starter_k_pct_30d` |
| 42 | C68 | 1 | +0.00051 | [-0.00191, +0.00284] | 🟡 noise → drop | `away_lineup_iso_vs_starter_archetype` |
| 43 | C105 | 1 | +0.00049 | [-0.00036, +0.00144] | 🟡 noise → drop | `home_pit_barrel_pct_30d` |
| 44 | C71 | 1 | +0.00045 | [-0.00031, +0.00126] | 🟡 noise → drop | `home_lineup_bat_speed_vs_starter_velo` |
| 45 | C117 | 1 | +0.00043 | [-0.00003, +0.00094] | 🟡 noise → drop | `right_line_ft` |
| 46 | C12 | 2 | +0.00041 | [-0.00043, +0.00126] | 🟡 noise → drop | `away_avg_bb_pct_std, away_avg_bb_pct_30d` |
| 47 | C5 | 2 | +0.00039 | [-0.00366, +0.00435] | 🟡 noise → drop | `away_elo, away_team_sequential_win_prob` |
| 48 | C109 | 1 | +0.00038 | [-0.00081, +0.00162] | 🟡 noise → drop | `away_avg_k_pct_vs_rhp` |
| 49 | C92 | 1 | +0.00036 | [-0.00046, +0.00124] | 🟡 noise → drop | `away_starter_avg_fastball_velo` |
| 50 | C78 | 1 | +0.00032 | [-0.00162, +0.00214] | 🟡 noise → drop | `home_avg_hard_hit_pct_std` |
| 51 | C72 | 1 | +0.00028 | [-0.00045, +0.00111] | 🟡 noise → drop | `home_starter_changeup_stuff_plus` |
| 52 | C88 | 1 | +0.00027 | [-0.00118, +0.00163] | 🟡 noise → drop | `away_starter_batter_chase_rate_30d` |
| 53 | C120 | 1 | +0.00024 | [-0.00162, +0.00186] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 54 | C37 | 1 | +0.00023 | [-0.00193, +0.00233] | 🟡 noise → drop | `away_starter_csw_pct_season` |
| 55 | C55 | 1 | +0.00020 | [-0.00114, +0.00155] | 🟡 noise → drop | `home_pit_hard_hit_pct_std` |
| 56 | C61 | 1 | +0.00018 | [-0.00093, +0.00144] | 🟡 noise → drop | `away_off_barrel_pct_30d` |
| 57 | C116 | 1 | +0.00018 | [-0.00128, +0.00169] | 🟡 noise → drop | `home_woba_with_risp_30d` |
| 58 | C58 | 1 | +0.00017 | [-0.00222, +0.00244] | 🟡 noise → drop | `home_avg_xwoba_vs_lhp` |
| 59 | C6 | 2 | +0.00016 | [-0.00184, +0.00213] | 🟡 noise → drop | `away_pit_woba_against_14d, away_pit_woba_against_7d` |
| 60 | C94 | 1 | +0.00016 | [-0.00027, +0.00060] | 🟡 noise → drop | `home_vs_lhp_woba_std` |
| 61 | C53 | 1 | +0.00015 | [-0.00042, +0.00071] | 🟡 noise → drop | `away_lineup_xwoba_vs_starter_archetype` |
| 62 | C113 | 1 | +0.00015 | [-0.00051, +0.00083] | 🟡 noise → drop | `home_starter_bb_pct_30d` |
| 63 | C44 | 1 | +0.00014 | [-0.00036, +0.00067] | 🟡 noise → drop | `runs_per_game_at_park` |
| 64 | C48 | 1 | +0.00014 | [-0.00029, +0.00069] | 🟡 noise → drop | `home_starter_trailing_fip_30g` |
| 65 | C108 | 1 | +0.00011 | [-0.00087, +0.00114] | 🟡 noise → drop | `home_vs_lhp_slugging_30d` |
| 66 | C22 | 2 | +0.00011 | [-0.00063, +0.00093] | 🟡 noise → drop | `home_starter_hard_hit_pct_30d, home_starter_hard_hit_pct_14d` |
| 67 | C84 | 1 | +0.00010 | [-0.00003, +0.00024] | 🟡 noise → drop | `home_n_power_pull` |
| 68 | C123 | 1 | +0.00010 | [-0.00015, +0.00039] | 🟡 noise → drop | `series_game_number` |
| 69 | C93 | 1 | +0.00009 | [-0.00150, +0.00167] | 🟡 noise → drop | `home_avg_chase_rate_30d` |
| 70 | C118 | 1 | +0.00008 | [-0.00057, +0.00076] | 🟡 noise → drop | `away_high_leverage_used_prev_2d` |
| 71 | C64 | 1 | +0.00007 | [-0.00033, +0.00050] | 🟡 noise → drop | `away_starter_curveball_stuff_plus` |
| 72 | C34 | 1 | +0.00006 | [-0.00027, +0.00038] | 🟡 noise → drop | `away_off_runs_per_game_std` |
| 73 | C103 | 1 | +0.00003 | [-0.00022, +0.00028] | 🟡 noise → drop | `home_starter_xwoba_vs_rhb` |
| 74 | C74 | 1 | +0.00002 | [-0.00196, +0.00159] | 🟡 noise → drop | `home_bp_xwoba_against_30d` |
| 75 | C69 | 1 | +0.00001 | [-0.00060, +0.00063] | 🟡 noise → drop | `away_vs_lhp_woba_30d` |
| 76 | C90 | 1 | +0.00000 | [-0.00026, +0.00027] | 🟡 noise → drop | `away_starter_whiff_rate_vs_rhb` |
| 77 | C29 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_k_pct` |
| 78 | C38 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_bb_pct` |
| 79 | C39 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_woba` |
| 80 | C40 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_iso` |
| 81 | C41 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 82 | C45 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against` |
| 83 | C47 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_iso` |
| 84 | C57 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_bb_pct` |
| 85 | C89 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_uncertainty` |
| 86 | C111 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_bb_pct` |
| 87 | C140 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_woba_sequential` |
| 88 | C141 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against_sequential` |
| 89 | C142 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `has_starter_platoon_data` |
| 90 | C143 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 91 | C17 | 2 | -0.00000 | [-0.00075, +0.00073] | 🟡 noise → drop | `home_off_xwoba_30d, home_team_sequential_woba` |
| 92 | C73 | 1 | -0.00000 | [-0.00057, +0.00051] | 🟡 noise → drop | `away_starter_k_pct_vs_lhb` |
| 93 | C136 | 1 | -0.00001 | [-0.00098, +0.00099] | 🟡 noise → drop | `home_bp_innings_pitched_30d` |
| 94 | C137 | 1 | -0.00002 | [-0.00295, +0.00295] | 🟡 noise → drop | `home_starter_appearances_30d` |
| 95 | C127 | 1 | -0.00002 | [-0.00005, -0.00000] | ✅ signal | `away_closer_used_prev_1d` |
| 96 | C77 | 1 | -0.00003 | [-0.00025, +0.00020] | 🟡 noise → drop | `home_off_hard_hit_pct_std` |
| 97 | C125 | 1 | -0.00003 | [-0.00078, +0.00068] | 🟡 noise → drop | `home_lineup_k_pct_vs_starter_archetype` |
| 98 | C25 | 1 | -0.00003 | [-0.00087, +0.00084] | 🟡 noise → drop | `away_pit_woba_against_std` |
| 99 | C110 | 1 | -0.00004 | [-0.00075, +0.00065] | 🟡 noise → drop | `home_starter_xwoba_vs_lhb` |
| 100 | C91 | 1 | -0.00005 | [-0.00107, +0.00099] | 🟡 noise → drop | `home_avg_hard_hit_pct_vs_rhp` |
| 101 | C20 | 2 | -0.00006 | [-0.00253, +0.00227] | 🟡 noise → drop | `home_off_runs_per_game_14d, home_off_runs_per_game_7d` |
| 102 | C51 | 1 | -0.00006 | [-0.00038, +0.00026] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 103 | C31 | 1 | -0.00006 | [-0.00032, +0.00020] | 🟡 noise → drop | `home_away_off_woba_30d_pct_diff` |
| 104 | C8 | 2 | -0.00007 | [-0.00234, +0.00215] | 🟡 noise → drop | `away_pit_xwoba_against_14d, away_pit_xwoba_against_7d` |
| 105 | C138 | 1 | -0.00008 | [-0.00015, -0.00001] | ✅ signal | `home_injured_player_count` |
| 106 | C52 | 1 | -0.00008 | [-0.00028, +0.00011] | 🟡 noise → drop | `away_lineup_vs_home_starter_k_pct_adj` |
| 107 | C80 | 1 | -0.00008 | [-0.00030, +0.00014] | 🟡 noise → drop | `home_avg_woba_30d` |
| 108 | C119 | 1 | -0.00010 | [-0.00026, +0.00004] | 🟡 noise → drop | `away_n_high_whiff` |
| 109 | C62 | 1 | -0.00012 | [-0.00119, +0.00095] | 🟡 noise → drop | `home_starter_avg_ip_season` |
| 110 | C85 | 1 | -0.00013 | [-0.00233, +0.00195] | 🟡 noise → drop | `home_starter_whiff_rate_vs_rhb` |
| 111 | C23 | 2 | -0.00013 | [-0.00400, +0.00366] | 🟡 noise → drop | `ump_run_impact_zscore, ump_accuracy_zscore` |
| 112 | C21 | 2 | -0.00014 | [-0.00358, +0.00299] | 🟡 noise → drop | `home_bp_whiff_rate_30d, home_bp_whiff_rate_14d` |
| 113 | C112 | 1 | -0.00015 | [-0.00051, +0.00019] | 🟡 noise → drop | `away_vs_lhp_k_pct_30d` |
| 114 | C82 | 1 | -0.00016 | [-0.00062, +0.00029] | 🟡 noise → drop | `home_off_barrel_pct_30d` |
| 115 | C70 | 1 | -0.00017 | [-0.00137, +0.00100] | 🟡 noise → drop | `away_pit_bb_pct_7d` |
| 116 | C28 | 1 | -0.00019 | [-0.00045, +0.00007] | 🟡 noise → drop | `away_games_back` |
| 117 | C32 | 1 | -0.00019 | [-0.00054, +0.00015] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 118 | C76 | 1 | -0.00021 | [-0.00056, +0.00017] | 🟡 noise → drop | `away_avg_hard_hit_pct_std` |
| 119 | C101 | 1 | -0.00023 | [-0.00074, +0.00027] | 🟡 noise → drop | `home_starter_batter_chase_rate_7d` |
| 120 | C46 | 1 | -0.00024 | [-0.00125, +0.00047] | 🟡 noise → drop | `left_ft` |
| 121 | C43 | 1 | -0.00026 | [-0.00086, +0.00030] | 🟡 noise → drop | `home_starter_trailing_ra9_30g` |
| 122 | C81 | 1 | -0.00029 | [-0.00146, +0.00074] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 123 | C65 | 1 | -0.00030 | [-0.00157, +0.00091] | 🟡 noise → drop | `away_avg_woba_vs_rhp` |
| 124 | C9 | 2 | -0.00031 | [-0.00152, +0.00089] | 🟡 noise → drop | `home_off_runs_per_game_std, home_off_runs_per_game_30d` |
| 125 | C139 | 1 | -0.00032 | [-0.00138, +0.00060] | 🟡 noise → drop | `away_team_sequential_woba` |
| 126 | C135 | 1 | -0.00039 | [-0.00097, +0.00024] | 🟡 noise → drop | `home_starter_barrel_pct_7d` |
| 127 | C106 | 1 | -0.00040 | [-0.00247, +0.00159] | 🟡 noise → drop | `away_lineup_vs_home_starter_h2h_xwoba` |
| 128 | C97 | 1 | -0.00041 | [-0.00198, +0.00129] | 🟡 noise → drop | `away_team_oaa_prior_season` |
| 129 | C100 | 1 | -0.00041 | [-0.00244, +0.00158] | 🟡 noise → drop | `away_off_k_pct_std` |
| 130 | C102 | 1 | -0.00045 | [-0.00128, +0.00038] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 131 | C11 | 2 | -0.00050 | [-0.00180, +0.00080] | 🟡 noise → drop | `away_vs_lhp_xwoba_std, away_vs_lhp_xwoba_30d` |
| 132 | C27 | 1 | -0.00051 | [-0.00179, +0.00077] | 🟡 noise → drop | `home_pit_woba_against_30d` |
| 133 | C130 | 1 | -0.00052 | [-0.00188, +0.00080] | 🟡 noise → drop | `home_away_injury_adj_avg_woba_30d_pct_diff` |
| 134 | C96 | 1 | -0.00054 | [-0.00220, +0.00119] | 🟡 noise → drop | `home_vs_rhp_slugging_30d` |
| 135 | C129 | 1 | -0.00062 | [-0.00226, +0.00111] | 🟡 noise → drop | `home_off_bb_pct_7d` |
| 136 | C36 | 1 | -0.00063 | [-0.00371, +0.00249] | 🟡 noise → drop | `away_lineup_avg_woba_vs_cluster` |
| 137 | C35 | 1 | -0.00074 | [-0.00409, +0.00258] | 🟡 noise → drop | `home_away_starter_xwoba_against_std_pct_diff` |
| 138 | C10 | 2 | -0.00080 | [-0.00225, +0.00065] | 🟡 noise → drop | `away_avg_xwoba_std, away_avg_xwoba_30d` |
| 139 | C50 | 1 | -0.00080 | [-0.00184, +0.00019] | 🟡 noise → drop | `away_starter_xwoba_against_std` |
| 140 | C7 | 2 | -0.00100 | [-0.00470, +0.00271] | 🟡 noise → drop | `home_pit_xwoba_against_30d, home_pit_xwoba_against_14d` |
| 141 | C128 | 1 | -0.00104 | [-0.00261, +0.00048] | 🟡 noise → drop | `home_lineup_vs_away_starter_bb_pct_adj` |
| 142 | C54 | 1 | -0.00112 | [-0.00312, +0.00084] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 143 | C114 | 1 | -0.00222 | [-0.00612, +0.00158] | 🟡 noise → drop | `home_lineup_vs_away_starter_h2h_woba` |
| 144 | C0 | 3 | -0.00229 | [-0.00838, +0.00361] | 🟡 noise → drop | `home_elo, home_pythagorean_win_exp, home_team_sequential_win_prob` |

## Payoff (E1.3 AC)
Dropping the 132 noise clusters (154 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_run_diff_bullpen_v3.json`_