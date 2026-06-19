# Clustered Feature Importance — run_diff (Epic E1.3)

- Recipe: `ngboost-Normal(challenger)` · metric **mae** (lower = better) · pooled baseline 3.3961
- Features: **167** in **144** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 134/144** covering **156/167** features → drop/consolidate candidates (≈93% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δmae) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C24 | 1 | +0.10935 | [+0.08795, +0.13034] | ✅ signal | `home_bp_eb_coverage_pct` |
| 2 | C26 | 1 | +0.07734 | [+0.05815, +0.09632] | ✅ signal | `away_bp_eb_coverage_pct` |
| 3 | C4 | 2 | +0.04392 | [+0.02866, +0.06090] | ✅ signal | `elo_diff, pythagorean_win_exp_diff` |
| 4 | C66 | 1 | +0.00444 | [-0.00407, +0.01273] | 🟡 noise → drop | `home_pit_bb_pct_std` |
| 5 | C79 | 1 | +0.00443 | [+0.00026, +0.00879] | ✅ signal | `away_vs_lhp_bb_pct_30d` |
| 6 | C3 | 2 | +0.00254 | [+0.00047, +0.00458] | ✅ signal | `home_bp_eb_uncertainty, away_bp_eb_uncertainty` |
| 7 | C87 | 1 | +0.00242 | [-0.00039, +0.00537] | 🟡 noise → drop | `away_bp_bb_pct_14d` |
| 8 | C15 | 2 | +0.00215 | [-0.00013, +0.00448] | 🟡 noise → drop | `home_off_bb_pct_std, home_off_bb_pct_30d` |
| 9 | C63 | 1 | +0.00186 | [+0.00031, +0.00338] | ✅ signal | `home_starter_avg_ip_last_3` |
| 10 | C133 | 1 | +0.00183 | [-0.00007, +0.00377] | 🟡 noise → drop | `away_lineup_archetype_pa_coverage` |
| 11 | C33 | 1 | +0.00148 | [-0.00221, +0.00504] | 🟡 noise → drop | `home_away_starter_k_pct_std_pct_diff` |
| 12 | C99 | 1 | +0.00145 | [-0.00065, +0.00354] | 🟡 noise → drop | `away_avg_whiff_rate_30d` |
| 13 | C59 | 1 | +0.00141 | [-0.00115, +0.00404] | 🟡 noise → drop | `home_avg_xwoba_30d` |
| 14 | C95 | 1 | +0.00133 | [-0.00050, +0.00305] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 15 | C98 | 1 | +0.00123 | [-0.00032, +0.00271] | 🟡 noise → drop | `away_bullpen_pitches_prev_7d` |
| 16 | C42 | 1 | +0.00121 | [-0.00174, +0.00433] | 🟡 noise → drop | `home_away_bp_xwoba_against_30d_pct_diff` |
| 17 | C1 | 2 | +0.00117 | [+0.00033, +0.00202] | ✅ signal | `home_bp_eb_xwoba, home_team_sequential_bullpen_xwoba` |
| 18 | C67 | 1 | +0.00113 | [-0.00071, +0.00305] | 🟡 noise → drop | `home_avg_woba_vs_rhp` |
| 19 | C19 | 2 | +0.00100 | [-0.00061, +0.00246] | 🟡 noise → drop | `home_bp_k_pct_30d, home_bp_k_pct_14d` |
| 20 | C92 | 1 | +0.00097 | [+0.00017, +0.00190] | ✅ signal | `away_starter_avg_fastball_velo` |
| 21 | C122 | 1 | +0.00083 | [-0.00053, +0.00218] | 🟡 noise → drop | `home_lineup_archetype_pa_coverage` |
| 22 | C134 | 1 | +0.00082 | [-0.00182, +0.00344] | 🟡 noise → drop | `away_pit_xwoba_7d_minus_30d` |
| 23 | C56 | 1 | +0.00077 | [+0.00012, +0.00152] | ✅ signal | `home_starter_csw_pct_season` |
| 24 | C131 | 1 | +0.00076 | [-0.00111, +0.00260] | 🟡 noise → drop | `away_injured_player_count` |
| 25 | C75 | 1 | +0.00076 | [-0.00141, +0.00305] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 26 | C115 | 1 | +0.00072 | [-0.00040, +0.00184] | 🟡 noise → drop | `home_avg_hard_hit_pct_vs_lhp` |
| 27 | C104 | 1 | +0.00071 | [-0.00086, +0.00228] | 🟡 noise → drop | `away_starter_bb_pct_std` |
| 28 | C71 | 1 | +0.00069 | [-0.00045, +0.00187] | 🟡 noise → drop | `home_lineup_bat_speed_vs_starter_velo` |
| 29 | C72 | 1 | +0.00065 | [-0.00088, +0.00223] | 🟡 noise → drop | `home_starter_changeup_stuff_plus` |
| 30 | C14 | 2 | +0.00062 | [-0.00112, +0.00233] | 🟡 noise → drop | `away_starter_whiff_rate_std, away_starter_whiff_rate_14d` |
| 31 | C6 | 2 | +0.00062 | [-0.00169, +0.00282] | 🟡 noise → drop | `away_pit_woba_against_14d, away_pit_woba_against_7d` |
| 32 | C13 | 2 | +0.00055 | [-0.00235, +0.00354] | 🟡 noise → drop | `away_avg_woba_std, away_avg_woba_30d` |
| 33 | C37 | 1 | +0.00054 | [-0.00211, +0.00299] | 🟡 noise → drop | `away_starter_csw_pct_season` |
| 34 | C2 | 2 | +0.00053 | [-0.00093, +0.00195] | 🟡 noise → drop | `away_bp_eb_xwoba, away_team_sequential_bullpen_xwoba` |
| 35 | C83 | 1 | +0.00052 | [-0.00134, +0.00250] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 36 | C16 | 2 | +0.00048 | [-0.00131, +0.00224] | 🟡 noise → drop | `home_starter_xwoba_against_7d, home_starter_xwoba_7d_minus_std` |
| 37 | C12 | 2 | +0.00045 | [-0.00032, +0.00119] | 🟡 noise → drop | `away_avg_bb_pct_std, away_avg_bb_pct_30d` |
| 38 | C121 | 1 | +0.00045 | [-0.00021, +0.00119] | 🟡 noise → drop | `away_starter_hard_hit_pct_std` |
| 39 | C49 | 1 | +0.00044 | [-0.00045, +0.00134] | 🟡 noise → drop | `home_starter_k_pct_30d` |
| 40 | C68 | 1 | +0.00039 | [-0.00211, +0.00286] | 🟡 noise → drop | `away_lineup_iso_vs_starter_archetype` |
| 41 | C120 | 1 | +0.00038 | [-0.00079, +0.00148] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 42 | C117 | 1 | +0.00036 | [-0.00013, +0.00094] | 🟡 noise → drop | `right_line_ft` |
| 43 | C126 | 1 | +0.00035 | [-0.00032, +0.00099] | 🟡 noise → drop | `home_starter_barrel_pct_std` |
| 44 | C18 | 2 | +0.00035 | [-0.00140, +0.00218] | 🟡 noise → drop | `home_off_xwoba_7d, home_off_xwoba_14d` |
| 45 | C88 | 1 | +0.00033 | [-0.00130, +0.00180] | 🟡 noise → drop | `away_starter_batter_chase_rate_30d` |
| 46 | C109 | 1 | +0.00032 | [-0.00097, +0.00168] | 🟡 noise → drop | `away_avg_k_pct_vs_rhp` |
| 47 | C93 | 1 | +0.00027 | [-0.00145, +0.00196] | 🟡 noise → drop | `home_avg_chase_rate_30d` |
| 48 | C108 | 1 | +0.00025 | [-0.00038, +0.00089] | 🟡 noise → drop | `home_vs_lhp_slugging_30d` |
| 49 | C105 | 1 | +0.00023 | [-0.00031, +0.00082] | 🟡 noise → drop | `home_pit_barrel_pct_30d` |
| 50 | C94 | 1 | +0.00022 | [-0.00037, +0.00078] | 🟡 noise → drop | `home_vs_lhp_woba_std` |
| 51 | C113 | 1 | +0.00017 | [-0.00047, +0.00084] | 🟡 noise → drop | `home_starter_bb_pct_30d` |
| 52 | C44 | 1 | +0.00017 | [-0.00033, +0.00068] | 🟡 noise → drop | `runs_per_game_at_park` |
| 53 | C91 | 1 | +0.00017 | [-0.00092, +0.00131] | 🟡 noise → drop | `home_avg_hard_hit_pct_vs_rhp` |
| 54 | C55 | 1 | +0.00015 | [-0.00134, +0.00168] | 🟡 noise → drop | `home_pit_hard_hit_pct_std` |
| 55 | C110 | 1 | +0.00015 | [-0.00081, +0.00108] | 🟡 noise → drop | `home_starter_xwoba_vs_lhb` |
| 56 | C123 | 1 | +0.00012 | [-0.00013, +0.00042] | 🟡 noise → drop | `series_game_number` |
| 57 | C82 | 1 | +0.00012 | [-0.00037, +0.00058] | 🟡 noise → drop | `home_off_barrel_pct_30d` |
| 58 | C17 | 2 | +0.00010 | [-0.00052, +0.00068] | 🟡 noise → drop | `home_off_xwoba_30d, home_team_sequential_woba` |
| 59 | C61 | 1 | +0.00010 | [-0.00101, +0.00131] | 🟡 noise → drop | `away_off_barrel_pct_30d` |
| 60 | C103 | 1 | +0.00010 | [-0.00022, +0.00042] | 🟡 noise → drop | `home_starter_xwoba_vs_rhb` |
| 61 | C90 | 1 | +0.00009 | [-0.00008, +0.00026] | 🟡 noise → drop | `away_starter_whiff_rate_vs_rhb` |
| 62 | C53 | 1 | +0.00008 | [-0.00044, +0.00064] | 🟡 noise → drop | `away_lineup_xwoba_vs_starter_archetype` |
| 63 | C84 | 1 | +0.00008 | [-0.00007, +0.00023] | 🟡 noise → drop | `home_n_power_pull` |
| 64 | C73 | 1 | +0.00007 | [-0.00040, +0.00053] | 🟡 noise → drop | `away_starter_k_pct_vs_lhb` |
| 65 | C78 | 1 | +0.00007 | [-0.00215, +0.00223] | 🟡 noise → drop | `home_avg_hard_hit_pct_std` |
| 66 | C97 | 1 | +0.00007 | [-0.00141, +0.00160] | 🟡 noise → drop | `away_team_oaa_prior_season` |
| 67 | C21 | 2 | +0.00005 | [-0.00325, +0.00307] | 🟡 noise → drop | `home_bp_whiff_rate_30d, home_bp_whiff_rate_14d` |
| 68 | C125 | 1 | +0.00003 | [-0.00087, +0.00087] | 🟡 noise → drop | `home_lineup_k_pct_vs_starter_archetype` |
| 69 | C70 | 1 | +0.00002 | [-0.00151, +0.00149] | 🟡 noise → drop | `away_pit_bb_pct_7d` |
| 70 | C119 | 1 | +0.00001 | [-0.00000, +0.00002] | 🟡 noise → drop | `away_n_high_whiff` |
| 71 | C29 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_k_pct` |
| 72 | C38 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_bb_pct` |
| 73 | C39 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_woba` |
| 74 | C40 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_iso` |
| 75 | C41 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 76 | C45 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against` |
| 77 | C47 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_iso` |
| 78 | C57 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_bb_pct` |
| 79 | C89 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_uncertainty` |
| 80 | C111 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_bb_pct` |
| 81 | C140 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_woba_sequential` |
| 82 | C141 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against_sequential` |
| 83 | C142 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `has_starter_platoon_data` |
| 84 | C143 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 85 | C136 | 1 | -0.00001 | [-0.00082, +0.00080] | 🟡 noise → drop | `home_bp_innings_pitched_30d` |
| 86 | C127 | 1 | -0.00001 | [-0.00004, +0.00001] | 🟡 noise → drop | `away_closer_used_prev_1d` |
| 87 | C32 | 1 | -0.00003 | [-0.00041, +0.00040] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 88 | C86 | 1 | -0.00003 | [-0.00037, +0.00030] | 🟡 noise → drop | `home_starter_avg_fastball_velo` |
| 89 | C138 | 1 | -0.00003 | [-0.00015, +0.00008] | 🟡 noise → drop | `home_injured_player_count` |
| 90 | C31 | 1 | -0.00004 | [-0.00047, +0.00038] | 🟡 noise → drop | `home_away_off_woba_30d_pct_diff` |
| 91 | C77 | 1 | -0.00006 | [-0.00033, +0.00021] | 🟡 noise → drop | `home_off_hard_hit_pct_std` |
| 92 | C118 | 1 | -0.00006 | [-0.00091, +0.00081] | 🟡 noise → drop | `away_high_leverage_used_prev_2d` |
| 93 | C51 | 1 | -0.00007 | [-0.00026, +0.00013] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 94 | C139 | 1 | -0.00007 | [-0.00114, +0.00087] | 🟡 noise → drop | `away_team_sequential_woba` |
| 95 | C69 | 1 | -0.00007 | [-0.00069, +0.00057] | 🟡 noise → drop | `away_vs_lhp_woba_30d` |
| 96 | C76 | 1 | -0.00009 | [-0.00033, +0.00014] | 🟡 noise → drop | `away_avg_hard_hit_pct_std` |
| 97 | C58 | 1 | -0.00010 | [-0.00218, +0.00196] | 🟡 noise → drop | `home_avg_xwoba_vs_lhp` |
| 98 | C52 | 1 | -0.00010 | [-0.00026, +0.00006] | 🟡 noise → drop | `away_lineup_vs_home_starter_k_pct_adj` |
| 99 | C81 | 1 | -0.00013 | [-0.00130, +0.00098] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 100 | C116 | 1 | -0.00014 | [-0.00140, +0.00106] | 🟡 noise → drop | `home_woba_with_risp_30d` |
| 101 | C112 | 1 | -0.00015 | [-0.00044, +0.00010] | 🟡 noise → drop | `away_vs_lhp_k_pct_30d` |
| 102 | C60 | 1 | -0.00016 | [-0.00096, +0.00057] | 🟡 noise → drop | `away_starter_changeup_stuff_plus` |
| 103 | C48 | 1 | -0.00021 | [-0.00065, +0.00022] | 🟡 noise → drop | `home_starter_trailing_fip_30g` |
| 104 | C62 | 1 | -0.00023 | [-0.00145, +0.00102] | 🟡 noise → drop | `home_starter_avg_ip_season` |
| 105 | C100 | 1 | -0.00023 | [-0.00242, +0.00181] | 🟡 noise → drop | `away_off_k_pct_std` |
| 106 | C9 | 2 | -0.00023 | [-0.00133, +0.00082] | 🟡 noise → drop | `home_off_runs_per_game_std, home_off_runs_per_game_30d` |
| 107 | C80 | 1 | -0.00023 | [-0.00053, +0.00007] | 🟡 noise → drop | `home_avg_woba_30d` |
| 108 | C34 | 1 | -0.00023 | [-0.00068, +0.00021] | 🟡 noise → drop | `away_off_runs_per_game_std` |
| 109 | C130 | 1 | -0.00024 | [-0.00171, +0.00121] | 🟡 noise → drop | `home_away_injury_adj_avg_woba_30d_pct_diff` |
| 110 | C85 | 1 | -0.00024 | [-0.00239, +0.00177] | 🟡 noise → drop | `home_starter_whiff_rate_vs_rhb` |
| 111 | C43 | 1 | -0.00025 | [-0.00081, +0.00026] | 🟡 noise → drop | `home_starter_trailing_ra9_30g` |
| 112 | C28 | 1 | -0.00027 | [-0.00051, -0.00003] | ✅ signal | `away_games_back` |
| 113 | C101 | 1 | -0.00030 | [-0.00078, +0.00019] | 🟡 noise → drop | `home_starter_batter_chase_rate_7d` |
| 114 | C107 | 1 | -0.00031 | [-0.00224, +0.00149] | 🟡 noise → drop | `away_pit_barrel_pct_30d` |
| 115 | C54 | 1 | -0.00031 | [-0.00244, +0.00178] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 116 | C25 | 1 | -0.00035 | [-0.00132, +0.00070] | 🟡 noise → drop | `away_pit_woba_against_std` |
| 117 | C137 | 1 | -0.00036 | [-0.00328, +0.00252] | 🟡 noise → drop | `home_starter_appearances_30d` |
| 118 | C74 | 1 | -0.00037 | [-0.00278, +0.00154] | 🟡 noise → drop | `home_bp_xwoba_against_30d` |
| 119 | C124 | 1 | -0.00039 | [-0.00136, +0.00049] | 🟡 noise → drop | `home_starter_bb_pct_vs_rhb` |
| 120 | C20 | 2 | -0.00040 | [-0.00312, +0.00213] | 🟡 noise → drop | `home_off_runs_per_game_14d, home_off_runs_per_game_7d` |
| 121 | C22 | 2 | -0.00045 | [-0.00122, +0.00029] | 🟡 noise → drop | `home_starter_hard_hit_pct_30d, home_starter_hard_hit_pct_14d` |
| 122 | C135 | 1 | -0.00045 | [-0.00121, +0.00033] | 🟡 noise → drop | `home_starter_barrel_pct_7d` |
| 123 | C23 | 2 | -0.00046 | [-0.00384, +0.00301] | 🟡 noise → drop | `ump_run_impact_zscore, ump_accuracy_zscore` |
| 124 | C46 | 1 | -0.00047 | [-0.00163, +0.00034] | 🟡 noise → drop | `left_ft` |
| 125 | C65 | 1 | -0.00050 | [-0.00211, +0.00111] | 🟡 noise → drop | `away_avg_woba_vs_rhp` |
| 126 | C11 | 2 | -0.00055 | [-0.00176, +0.00064] | 🟡 noise → drop | `away_vs_lhp_xwoba_std, away_vs_lhp_xwoba_30d` |
| 127 | C96 | 1 | -0.00063 | [-0.00232, +0.00119] | 🟡 noise → drop | `home_vs_rhp_slugging_30d` |
| 128 | C8 | 2 | -0.00065 | [-0.00213, +0.00073] | 🟡 noise → drop | `away_pit_xwoba_against_14d, away_pit_xwoba_against_7d` |
| 129 | C132 | 1 | -0.00069 | [-0.00230, +0.00089] | 🟡 noise → drop | `home_pythagorean_residual_season` |
| 130 | C102 | 1 | -0.00070 | [-0.00145, +0.00006] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 131 | C106 | 1 | -0.00073 | [-0.00277, +0.00114] | 🟡 noise → drop | `away_lineup_vs_home_starter_h2h_xwoba` |
| 132 | C35 | 1 | -0.00078 | [-0.00457, +0.00282] | 🟡 noise → drop | `home_away_starter_xwoba_against_std_pct_diff` |
| 133 | C129 | 1 | -0.00079 | [-0.00294, +0.00127] | 🟡 noise → drop | `home_off_bb_pct_7d` |
| 134 | C10 | 2 | -0.00081 | [-0.00223, +0.00066] | 🟡 noise → drop | `away_avg_xwoba_std, away_avg_xwoba_30d` |
| 135 | C64 | 1 | -0.00090 | [-0.00194, +0.00007] | 🟡 noise → drop | `away_starter_curveball_stuff_plus` |
| 136 | C50 | 1 | -0.00090 | [-0.00209, +0.00029] | 🟡 noise → drop | `away_starter_xwoba_against_std` |
| 137 | C27 | 1 | -0.00093 | [-0.00227, +0.00039] | 🟡 noise → drop | `home_pit_woba_against_30d` |
| 138 | C30 | 1 | -0.00096 | [-0.00227, +0.00037] | 🟡 noise → drop | `away_starter_stuff_plus` |
| 139 | C5 | 2 | -0.00103 | [-0.00560, +0.00322] | 🟡 noise → drop | `away_elo, away_team_sequential_win_prob` |
| 140 | C7 | 2 | -0.00103 | [-0.00395, +0.00197] | 🟡 noise → drop | `home_pit_xwoba_against_30d, home_pit_xwoba_against_14d` |
| 141 | C36 | 1 | -0.00115 | [-0.00433, +0.00193] | 🟡 noise → drop | `away_lineup_avg_woba_vs_cluster` |
| 142 | C128 | 1 | -0.00122 | [-0.00308, +0.00064] | 🟡 noise → drop | `home_lineup_vs_away_starter_bb_pct_adj` |
| 143 | C114 | 1 | -0.00269 | [-0.00595, +0.00053] | 🟡 noise → drop | `home_lineup_vs_away_starter_h2h_woba` |
| 144 | C0 | 3 | -0.00620 | [-0.01303, +0.00024] | 🟡 noise → drop | `home_elo, home_pythagorean_win_exp, home_team_sequential_win_prob` |

## Payoff (E1.3 AC)
Dropping the 134 noise clusters (156 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_run_diff_bullpen_v3_stuffplus_deleaked.json`_