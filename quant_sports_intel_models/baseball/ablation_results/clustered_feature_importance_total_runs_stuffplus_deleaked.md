# Clustered Feature Importance — total_runs (Epic E1.3)

- Recipe: `ngboost-Normal(challenger)` · metric **mae** (lower = better) · pooled baseline 3.3769
- Features: **111** in **102** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 83/102** covering **91/111** features → drop/consolidate candidates (≈82% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δmae) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C11 | 1 | +0.08472 | [+0.06831, +0.10173] | ✅ signal | `home_bp_eb_xwoba` |
| 2 | C12 | 1 | +0.06006 | [+0.04186, +0.07970] | ✅ signal | `away_bp_eb_xwoba` |
| 3 | C9 | 2 | +0.04409 | [+0.03240, +0.05471] | ✅ signal | `away_wins, away_losses` |
| 4 | C17 | 1 | +0.02908 | [+0.01905, +0.03986] | ✅ signal | `away_bp_eb_coverage_pct` |
| 5 | C16 | 1 | +0.02739 | [+0.01867, +0.03662] | ✅ signal | `home_bp_eb_coverage_pct` |
| 6 | C13 | 1 | +0.02297 | [+0.01295, +0.03279] | ✅ signal | `home_bp_eb_uncertainty` |
| 7 | C18 | 1 | +0.01709 | [+0.00790, +0.02683] | ✅ signal | `park_run_factor_3yr` |
| 8 | C14 | 1 | +0.01356 | [+0.00587, +0.02122] | ✅ signal | `away_bp_eb_uncertainty` |
| 9 | C1 | 2 | +0.00441 | [+0.00047, +0.00847] | ✅ signal | `home_pit_woba_against_std, home_pit_woba_against_30d` |
| 10 | C73 | 1 | +0.00297 | [-0.00094, +0.00670] | 🟡 noise → drop | `away_lineup_bat_speed_vs_starter_velo` |
| 11 | C97 | 1 | +0.00289 | [+0.00100, +0.00472] | ✅ signal | `home_team_sequential_win_prob` |
| 12 | C37 | 1 | +0.00214 | [-0.00169, +0.00614] | 🟡 noise → drop | `away_starter_xwoba_against_std` |
| 13 | C3 | 2 | +0.00180 | [-0.00186, +0.00546] | 🟡 noise → drop | `away_starter_csw_pct_season, away_starter_csw_pct_3start` |
| 14 | C24 | 1 | +0.00156 | [+0.00006, +0.00309] | ✅ signal | `home_pit_woba_against_14d` |
| 15 | C96 | 1 | +0.00144 | [-0.00135, +0.00424] | 🟡 noise → drop | `away_team_sequential_bullpen_xwoba` |
| 16 | C33 | 1 | +0.00142 | [-0.00061, +0.00350] | 🟡 noise → drop | `away_off_runs_per_game_30d` |
| 17 | C7 | 2 | +0.00127 | [+0.00017, +0.00248] | ✅ signal | `home_off_xwoba_30d, home_team_sequential_woba` |
| 18 | C80 | 1 | +0.00101 | [-0.00016, +0.00218] | 🟡 noise → drop | `home_pit_barrel_pct_30d` |
| 19 | C42 | 1 | +0.00088 | [-0.00051, +0.00230] | 🟡 noise → drop | `home_starter_k_pct_vs_lhb` |
| 20 | C68 | 1 | +0.00078 | [-0.00014, +0.00165] | 🟡 noise → drop | `home_starter_slider_stuff_plus` |
| 21 | C22 | 1 | +0.00075 | [+0.00010, +0.00141] | ✅ signal | `home_starter_stuff_plus` |
| 22 | C10 | 2 | +0.00057 | [-0.00104, +0.00224] | 🟡 noise → drop | `ump_run_impact_zscore, ump_accuracy_zscore` |
| 23 | C65 | 1 | +0.00045 | [-0.00067, +0.00157] | 🟡 noise → drop | `home_avg_woba_30d` |
| 24 | C71 | 1 | +0.00041 | [-0.00012, +0.00096] | 🟡 noise → drop | `away_avg_k_pct_std` |
| 25 | C4 | 2 | +0.00040 | [-0.00010, +0.00090] | 🟡 noise → drop | `away_lineup_vs_home_starter_k_pct_adj, home_starter_k_pct_vs_rhb` |
| 26 | C58 | 1 | +0.00037 | [-0.00027, +0.00100] | 🟡 noise → drop | `home_starter_changeup_stuff_plus` |
| 27 | C91 | 1 | +0.00036 | [-0.00064, +0.00144] | 🟡 noise → drop | `home_lineup_avg_bat_speed` |
| 28 | C54 | 1 | +0.00036 | [-0.00057, +0.00129] | 🟡 noise → drop | `home_starter_whiff_rate_14d` |
| 29 | C55 | 1 | +0.00034 | [+0.00005, +0.00065] | ✅ signal | `away_lineup_iso_vs_starter_archetype` |
| 30 | C5 | 2 | +0.00032 | [-0.00066, +0.00123] | 🟡 noise → drop | `away_xwoba_with_runners_on_30d, away_xwoba_with_risp_30d` |
| 31 | C74 | 1 | +0.00031 | [-0.00007, +0.00072] | 🟡 noise → drop | `right_center_ft` |
| 32 | C50 | 1 | +0.00031 | [-0.00013, +0.00075] | 🟡 noise → drop | `away_vs_lhp_xwoba_30d` |
| 33 | C51 | 1 | +0.00026 | [+0.00000, +0.00051] | ✅ signal | `home_starter_avg_ip_season` |
| 34 | C49 | 1 | +0.00026 | [-0.00036, +0.00100] | 🟡 noise → drop | `home_woba_against_with_risp_30d` |
| 35 | C79 | 1 | +0.00019 | [-0.00006, +0.00044] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 36 | C61 | 1 | +0.00018 | [-0.00183, +0.00176] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 37 | C95 | 1 | +0.00017 | [-0.00092, +0.00133] | 🟡 noise → drop | `home_team_sequential_bullpen_xwoba` |
| 38 | C81 | 1 | +0.00016 | [-0.00029, +0.00055] | 🟡 noise → drop | `away_avg_k_pct_vs_rhp` |
| 39 | C66 | 1 | +0.00014 | [-0.00034, +0.00059] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 40 | C48 | 1 | +0.00014 | [-0.00029, +0.00053] | 🟡 noise → drop | `home_pit_k_pct_7d` |
| 41 | C47 | 1 | +0.00014 | [-0.00055, +0.00086] | 🟡 noise → drop | `home_off_bb_pct_std` |
| 42 | C32 | 1 | +0.00013 | [-0.00074, +0.00099] | 🟡 noise → drop | `home_lineup_avg_xwoba_vs_cluster` |
| 43 | C19 | 1 | +0.00011 | [-0.00004, +0.00025] | 🟡 noise → drop | `away_pit_k_pct_std` |
| 44 | C75 | 1 | +0.00009 | [-0.00063, +0.00081] | 🟡 noise → drop | `away_starter_avg_fastball_velo` |
| 45 | C36 | 1 | +0.00009 | [-0.00066, +0.00082] | 🟡 noise → drop | `home_starter_k_pct_30d` |
| 46 | C64 | 1 | +0.00009 | [-0.00160, +0.00167] | 🟡 noise → drop | `away_vs_lhp_bb_pct_30d` |
| 47 | C77 | 1 | +0.00009 | [-0.00032, +0.00050] | 🟡 noise → drop | `away_bullpen_pitches_prev_7d` |
| 48 | C59 | 1 | +0.00007 | [-0.00039, +0.00052] | 🟡 noise → drop | `home_lineup_vs_away_starter_xwoba_adj` |
| 49 | C62 | 1 | +0.00007 | [-0.00041, +0.00056] | 🟡 noise → drop | `away_lineup_vs_home_starter_xwoba_adj` |
| 50 | C2 | 2 | +0.00007 | [-0.00051, +0.00068] | 🟡 noise → drop | `away_woba_against_with_runners_on_30d, away_woba_against_with_risp_30d` |
| 51 | C28 | 1 | +0.00006 | [-0.00018, +0.00030] | 🟡 noise → drop | `home_starter_proj_fip` |
| 52 | C53 | 1 | +0.00005 | [-0.00067, +0.00079] | 🟡 noise → drop | `away_starter_avg_ip_season` |
| 53 | C92 | 1 | +0.00005 | [-0.00060, +0.00070] | 🟡 noise → drop | `home_starter_barrel_pct_std` |
| 54 | C70 | 1 | +0.00004 | [-0.00100, +0.00110] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 55 | C86 | 1 | +0.00004 | [-0.00014, +0.00022] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 56 | C40 | 1 | +0.00002 | [-0.00039, +0.00043] | 🟡 noise → drop | `away_off_hard_hit_pct_std` |
| 57 | C23 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_k_pct` |
| 58 | C25 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_woba` |
| 59 | C29 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_iso` |
| 60 | C30 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 61 | C34 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_iso` |
| 62 | C82 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_uncertainty` |
| 63 | C98 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against_sequential` |
| 64 | C99 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against_sequential` |
| 65 | C100 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `has_starter_platoon_data` |
| 66 | C101 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 67 | C90 | 1 | -0.00001 | [-0.00037, +0.00037] | 🟡 noise → drop | `away_starter_xwoba_vs_lhb` |
| 68 | C93 | 1 | -0.00001 | [-0.00010, +0.00007] | 🟡 noise → drop | `away_starter_hard_hit_pct_7d` |
| 69 | C43 | 1 | -0.00003 | [-0.00087, +0.00087] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 70 | C0 | 2 | -0.00003 | [-0.00288, +0.00263] | 🟡 noise → drop | `away_pythagorean_win_exp, away_team_sequential_win_prob` |
| 71 | C39 | 1 | -0.00003 | [-0.00024, +0.00018] | 🟡 noise → drop | `home_lineup_iso_vs_starter_archetype` |
| 72 | C15 | 1 | -0.00004 | [-0.00060, +0.00050] | 🟡 noise → drop | `pythagorean_win_exp_diff` |
| 73 | C76 | 1 | -0.00004 | [-0.00065, +0.00055] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 74 | C84 | 1 | -0.00006 | [-0.00039, +0.00027] | 🟡 noise → drop | `home_woba_with_risp_30d` |
| 75 | C27 | 1 | -0.00007 | [-0.00101, +0.00081] | 🟡 noise → drop | `home_away_starter_k_pct_std_pct_diff` |
| 76 | C35 | 1 | -0.00008 | [-0.00042, +0.00027] | 🟡 noise → drop | `away_pit_woba_against_7d` |
| 77 | C41 | 1 | -0.00009 | [-0.00036, +0.00018] | 🟡 noise → drop | `away_avg_woba_std` |
| 78 | C63 | 1 | -0.00009 | [-0.00058, +0.00038] | 🟡 noise → drop | `home_catcher_defensive_runs` |
| 79 | C6 | 2 | -0.00010 | [-0.00352, +0.00312] | 🟡 noise → drop | `home_starter_xwoba_against_7d, home_starter_xwoba_7d_minus_std` |
| 80 | C69 | 1 | -0.00012 | [-0.00049, +0.00023] | 🟡 noise → drop | `home_off_barrel_pct_30d` |
| 81 | C52 | 1 | -0.00012 | [-0.00083, +0.00048] | 🟡 noise → drop | `away_avg_woba_vs_rhp` |
| 82 | C67 | 1 | -0.00013 | [-0.00042, +0.00015] | 🟡 noise → drop | `away_catcher_defensive_runs` |
| 83 | C87 | 1 | -0.00014 | [-0.00056, +0.00020] | 🟡 noise → drop | `away_starter_hard_hit_pct_std` |
| 84 | C94 | 1 | -0.00014 | [-0.00107, +0.00086] | 🟡 noise → drop | `away_team_sequential_woba` |
| 85 | C78 | 1 | -0.00016 | [-0.00050, +0.00014] | 🟡 noise → drop | `home_starter_curveball_stuff_plus` |
| 86 | C38 | 1 | -0.00019 | [-0.00052, +0.00012] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 87 | C88 | 1 | -0.00020 | [-0.00203, +0.00168] | 🟡 noise → drop | `away_avg_k_pct_vs_lhp` |
| 88 | C8 | 2 | -0.00020 | [-0.00142, +0.00110] | 🟡 noise → drop | `away_bp_bb_pct_30d, away_bp_bb_pct_14d` |
| 89 | C45 | 1 | -0.00021 | [-0.00193, +0.00148] | 🟡 noise → drop | `home_starter_csw_pct_season` |
| 90 | C46 | 1 | -0.00025 | [-0.00131, +0.00077] | 🟡 noise → drop | `away_starter_whiff_rate_std` |
| 91 | C85 | 1 | -0.00033 | [-0.00112, +0.00047] | 🟡 noise → drop | `home_bp_hard_hit_pct_14d` |
| 92 | C60 | 1 | -0.00036 | [-0.00067, -0.00005] | ✅ signal | `home_bp_xwoba_against_30d` |
| 93 | C89 | 1 | -0.00038 | [-0.00095, +0.00018] | 🟡 noise → drop | `home_avg_k_pct_vs_lhp` |
| 94 | C44 | 1 | -0.00038 | [-0.00089, +0.00012] | 🟡 noise → drop | `home_starter_xwoba_against_30d` |
| 95 | C72 | 1 | -0.00041 | [-0.00091, +0.00012] | 🟡 noise → drop | `home_pit_hard_hit_pct_30d` |
| 96 | C83 | 1 | -0.00050 | [-0.00107, -0.00004] | ✅ signal | `away_bp_innings_pitched_30d` |
| 97 | C26 | 1 | -0.00052 | [-0.00135, +0.00027] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 98 | C57 | 1 | -0.00058 | [-0.00332, +0.00215] | 🟡 noise → drop | `home_lineup_bat_speed_vs_starter_velo` |
| 99 | C20 | 1 | -0.00106 | [-0.00214, +0.00006] | 🟡 noise → drop | `elevation_ft` |
| 100 | C21 | 1 | -0.00106 | [-0.00256, +0.00031] | 🟡 noise → drop | `away_pit_xwoba_against_30d` |
| 101 | C31 | 1 | -0.00142 | [-0.00268, -0.00004] | ✅ signal | `home_starter_trailing_ra9_30g` |
| 102 | C56 | 1 | -0.00182 | [-0.00400, -0.00021] | ✅ signal | `away_pit_bb_pct_7d` |

## Payoff (E1.3 AC)
Dropping the 83 noise clusters (91 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_total_runs_stuffplus_deleaked.json`_