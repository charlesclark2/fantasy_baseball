# Clustered Feature Importance — total_runs (Epic E1.3)

- Recipe: `ngboost-Normal(challenger)` · metric **mae** (lower = better) · pooled baseline 3.3767
- Features: **111** in **102** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 90/102** covering **99/111** features → drop/consolidate candidates (≈89% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δmae) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C11 | 1 | +0.07807 | [+0.06189, +0.09403] | ✅ signal | `home_bp_eb_xwoba` |
| 2 | C12 | 1 | +0.06546 | [+0.04576, +0.08402] | ✅ signal | `away_bp_eb_xwoba` |
| 3 | C9 | 2 | +0.03892 | [+0.02700, +0.04992] | ✅ signal | `away_wins, away_losses` |
| 4 | C13 | 1 | +0.02630 | [+0.01659, +0.03624] | ✅ signal | `home_bp_eb_uncertainty` |
| 5 | C17 | 1 | +0.02523 | [+0.01516, +0.03607] | ✅ signal | `away_bp_eb_coverage_pct` |
| 6 | C16 | 1 | +0.02377 | [+0.01522, +0.03205] | ✅ signal | `home_bp_eb_coverage_pct` |
| 7 | C18 | 1 | +0.01215 | [+0.00227, +0.02252] | ✅ signal | `park_run_factor_3yr` |
| 8 | C14 | 1 | +0.00844 | [+0.00063, +0.01633] | ✅ signal | `away_bp_eb_uncertainty` |
| 9 | C22 | 1 | +0.00650 | [+0.00167, +0.01109] | ✅ signal | `home_starter_stuff_plus` |
| 10 | C1 | 2 | +0.00214 | [-0.00153, +0.00570] | 🟡 noise → drop | `home_pit_woba_against_std, home_pit_woba_against_30d` |
| 11 | C97 | 1 | +0.00213 | [+0.00008, +0.00420] | ✅ signal | `home_team_sequential_win_prob` |
| 12 | C96 | 1 | +0.00191 | [-0.00082, +0.00472] | 🟡 noise → drop | `away_team_sequential_bullpen_xwoba` |
| 13 | C3 | 2 | +0.00183 | [-0.00164, +0.00518] | 🟡 noise → drop | `away_starter_csw_pct_season, away_starter_csw_pct_3start` |
| 14 | C24 | 1 | +0.00139 | [-0.00022, +0.00308] | 🟡 noise → drop | `home_pit_woba_against_14d` |
| 15 | C7 | 2 | +0.00133 | [+0.00035, +0.00238] | ✅ signal | `home_off_xwoba_30d, home_team_sequential_woba` |
| 16 | C33 | 1 | +0.00128 | [-0.00096, +0.00360] | 🟡 noise → drop | `away_off_runs_per_game_30d` |
| 17 | C10 | 2 | +0.00123 | [-0.00055, +0.00301] | 🟡 noise → drop | `ump_run_impact_zscore, ump_accuracy_zscore` |
| 18 | C80 | 1 | +0.00111 | [-0.00021, +0.00240] | 🟡 noise → drop | `home_pit_barrel_pct_30d` |
| 19 | C52 | 1 | +0.00083 | [-0.00028, +0.00207] | 🟡 noise → drop | `away_avg_woba_vs_rhp` |
| 20 | C27 | 1 | +0.00071 | [-0.00058, +0.00183] | 🟡 noise → drop | `home_away_starter_k_pct_std_pct_diff` |
| 21 | C43 | 1 | +0.00070 | [-0.00016, +0.00154] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 22 | C73 | 1 | +0.00068 | [-0.00279, +0.00410] | 🟡 noise → drop | `away_lineup_bat_speed_vs_starter_velo` |
| 23 | C65 | 1 | +0.00059 | [-0.00058, +0.00175] | 🟡 noise → drop | `home_avg_woba_30d` |
| 24 | C95 | 1 | +0.00058 | [-0.00048, +0.00180] | 🟡 noise → drop | `home_team_sequential_bullpen_xwoba` |
| 25 | C70 | 1 | +0.00056 | [-0.00094, +0.00208] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 26 | C54 | 1 | +0.00050 | [-0.00030, +0.00127] | 🟡 noise → drop | `home_starter_whiff_rate_14d` |
| 27 | C51 | 1 | +0.00028 | [-0.00007, +0.00062] | 🟡 noise → drop | `home_starter_avg_ip_season` |
| 28 | C64 | 1 | +0.00027 | [-0.00081, +0.00140] | 🟡 noise → drop | `away_vs_lhp_bb_pct_30d` |
| 29 | C4 | 2 | +0.00025 | [-0.00015, +0.00065] | 🟡 noise → drop | `away_lineup_vs_home_starter_k_pct_adj, home_starter_k_pct_vs_rhb` |
| 30 | C50 | 1 | +0.00024 | [-0.00024, +0.00072] | 🟡 noise → drop | `away_vs_lhp_xwoba_30d` |
| 31 | C47 | 1 | +0.00024 | [-0.00026, +0.00073] | 🟡 noise → drop | `home_off_bb_pct_std` |
| 32 | C79 | 1 | +0.00023 | [-0.00014, +0.00065] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 33 | C55 | 1 | +0.00023 | [-0.00002, +0.00049] | 🟡 noise → drop | `away_lineup_iso_vs_starter_archetype` |
| 34 | C0 | 2 | +0.00021 | [-0.00253, +0.00276] | 🟡 noise → drop | `away_pythagorean_win_exp, away_team_sequential_win_prob` |
| 35 | C90 | 1 | +0.00021 | [+0.00004, +0.00036] | ✅ signal | `away_starter_xwoba_vs_lhb` |
| 36 | C32 | 1 | +0.00020 | [-0.00075, +0.00123] | 🟡 noise → drop | `home_lineup_avg_xwoba_vs_cluster` |
| 37 | C48 | 1 | +0.00018 | [-0.00009, +0.00045] | 🟡 noise → drop | `home_pit_k_pct_7d` |
| 38 | C75 | 1 | +0.00016 | [-0.00083, +0.00116] | 🟡 noise → drop | `away_starter_avg_fastball_velo` |
| 39 | C36 | 1 | +0.00016 | [-0.00031, +0.00059] | 🟡 noise → drop | `home_starter_k_pct_30d` |
| 40 | C61 | 1 | +0.00016 | [-0.00184, +0.00166] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 41 | C69 | 1 | +0.00015 | [-0.00041, +0.00073] | 🟡 noise → drop | `home_off_barrel_pct_30d` |
| 42 | C28 | 1 | +0.00011 | [-0.00004, +0.00025] | 🟡 noise → drop | `home_starter_proj_fip` |
| 43 | C84 | 1 | +0.00009 | [-0.00029, +0.00046] | 🟡 noise → drop | `home_woba_with_risp_30d` |
| 44 | C59 | 1 | +0.00007 | [-0.00004, +0.00019] | 🟡 noise → drop | `home_lineup_vs_away_starter_xwoba_adj` |
| 45 | C49 | 1 | +0.00006 | [-0.00070, +0.00090] | 🟡 noise → drop | `home_woba_against_with_risp_30d` |
| 46 | C6 | 2 | +0.00005 | [-0.00304, +0.00308] | 🟡 noise → drop | `home_starter_xwoba_against_7d, home_starter_xwoba_7d_minus_std` |
| 47 | C53 | 1 | +0.00005 | [-0.00086, +0.00103] | 🟡 noise → drop | `away_starter_avg_ip_season` |
| 48 | C71 | 1 | +0.00003 | [-0.00028, +0.00035] | 🟡 noise → drop | `away_avg_k_pct_std` |
| 49 | C19 | 1 | +0.00003 | [-0.00000, +0.00008] | 🟡 noise → drop | `away_pit_k_pct_std` |
| 50 | C44 | 1 | +0.00001 | [-0.00001, +0.00003] | 🟡 noise → drop | `home_starter_xwoba_against_30d` |
| 51 | C23 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_k_pct` |
| 52 | C25 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_woba` |
| 53 | C29 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_iso` |
| 54 | C30 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 55 | C34 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_iso` |
| 56 | C82 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_uncertainty` |
| 57 | C98 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against_sequential` |
| 58 | C99 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against_sequential` |
| 59 | C100 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `has_starter_platoon_data` |
| 60 | C101 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 61 | C58 | 1 | -0.00000 | [-0.00027, +0.00027] | 🟡 noise → drop | `home_starter_changeup_stuff_plus` |
| 62 | C35 | 1 | -0.00001 | [-0.00042, +0.00037] | 🟡 noise → drop | `away_pit_woba_against_7d` |
| 63 | C91 | 1 | -0.00001 | [-0.00106, +0.00107] | 🟡 noise → drop | `home_lineup_avg_bat_speed` |
| 64 | C78 | 1 | -0.00001 | [-0.00026, +0.00023] | 🟡 noise → drop | `home_starter_curveball_stuff_plus` |
| 65 | C66 | 1 | -0.00002 | [-0.00051, +0.00040] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 66 | C93 | 1 | -0.00002 | [-0.00022, +0.00018] | 🟡 noise → drop | `away_starter_hard_hit_pct_7d` |
| 67 | C38 | 1 | -0.00002 | [-0.00033, +0.00029] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 68 | C39 | 1 | -0.00003 | [-0.00018, +0.00012] | 🟡 noise → drop | `home_lineup_iso_vs_starter_archetype` |
| 69 | C15 | 1 | -0.00003 | [-0.00034, +0.00028] | 🟡 noise → drop | `pythagorean_win_exp_diff` |
| 70 | C74 | 1 | -0.00004 | [-0.00011, +0.00003] | 🟡 noise → drop | `right_center_ft` |
| 71 | C62 | 1 | -0.00004 | [-0.00092, +0.00086] | 🟡 noise → drop | `away_lineup_vs_home_starter_xwoba_adj` |
| 72 | C2 | 2 | -0.00011 | [-0.00098, +0.00069] | 🟡 noise → drop | `away_woba_against_with_runners_on_30d, away_woba_against_with_risp_30d` |
| 73 | C85 | 1 | -0.00012 | [-0.00068, +0.00043] | 🟡 noise → drop | `home_bp_hard_hit_pct_14d` |
| 74 | C86 | 1 | -0.00015 | [-0.00047, +0.00020] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 75 | C87 | 1 | -0.00015 | [-0.00060, +0.00021] | 🟡 noise → drop | `away_starter_hard_hit_pct_std` |
| 76 | C40 | 1 | -0.00017 | [-0.00042, +0.00006] | 🟡 noise → drop | `away_off_hard_hit_pct_std` |
| 77 | C94 | 1 | -0.00018 | [-0.00120, +0.00095] | 🟡 noise → drop | `away_team_sequential_woba` |
| 78 | C77 | 1 | -0.00020 | [-0.00050, +0.00010] | 🟡 noise → drop | `away_bullpen_pitches_prev_7d` |
| 79 | C42 | 1 | -0.00020 | [-0.00069, +0.00030] | 🟡 noise → drop | `home_starter_k_pct_vs_lhb` |
| 80 | C46 | 1 | -0.00022 | [-0.00139, +0.00092] | 🟡 noise → drop | `away_starter_whiff_rate_std` |
| 81 | C89 | 1 | -0.00022 | [-0.00068, +0.00022] | 🟡 noise → drop | `home_avg_k_pct_vs_lhp` |
| 82 | C81 | 1 | -0.00023 | [-0.00080, +0.00023] | 🟡 noise → drop | `away_avg_k_pct_vs_rhp` |
| 83 | C41 | 1 | -0.00023 | [-0.00054, +0.00006] | 🟡 noise → drop | `away_avg_woba_std` |
| 84 | C67 | 1 | -0.00023 | [-0.00056, +0.00008] | 🟡 noise → drop | `away_catcher_defensive_runs` |
| 85 | C68 | 1 | -0.00026 | [-0.00112, +0.00062] | 🟡 noise → drop | `home_starter_slider_stuff_plus` |
| 86 | C63 | 1 | -0.00028 | [-0.00075, +0.00018] | 🟡 noise → drop | `home_catcher_defensive_runs` |
| 87 | C88 | 1 | -0.00031 | [-0.00231, +0.00160] | 🟡 noise → drop | `away_avg_k_pct_vs_lhp` |
| 88 | C76 | 1 | -0.00033 | [-0.00104, +0.00040] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 89 | C60 | 1 | -0.00038 | [-0.00085, +0.00009] | 🟡 noise → drop | `home_bp_xwoba_against_30d` |
| 90 | C21 | 1 | -0.00039 | [-0.00163, +0.00079] | 🟡 noise → drop | `away_pit_xwoba_against_30d` |
| 91 | C92 | 1 | -0.00039 | [-0.00115, +0.00037] | 🟡 noise → drop | `home_starter_barrel_pct_std` |
| 92 | C5 | 2 | -0.00042 | [-0.00118, +0.00033] | 🟡 noise → drop | `away_xwoba_with_runners_on_30d, away_xwoba_with_risp_30d` |
| 93 | C83 | 1 | -0.00050 | [-0.00120, +0.00008] | 🟡 noise → drop | `away_bp_innings_pitched_30d` |
| 94 | C20 | 1 | -0.00050 | [-0.00132, +0.00034] | 🟡 noise → drop | `elevation_ft` |
| 95 | C72 | 1 | -0.00061 | [-0.00134, +0.00006] | 🟡 noise → drop | `home_pit_hard_hit_pct_30d` |
| 96 | C31 | 1 | -0.00062 | [-0.00171, +0.00046] | 🟡 noise → drop | `home_starter_trailing_ra9_30g` |
| 97 | C37 | 1 | -0.00069 | [-0.00436, +0.00314] | 🟡 noise → drop | `away_starter_xwoba_against_std` |
| 98 | C45 | 1 | -0.00073 | [-0.00158, +0.00008] | 🟡 noise → drop | `home_starter_csw_pct_season` |
| 99 | C26 | 1 | -0.00074 | [-0.00154, +0.00000] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 100 | C8 | 2 | -0.00080 | [-0.00191, +0.00032] | 🟡 noise → drop | `away_bp_bb_pct_30d, away_bp_bb_pct_14d` |
| 101 | C57 | 1 | -0.00169 | [-0.00443, +0.00113] | 🟡 noise → drop | `home_lineup_bat_speed_vs_starter_velo` |
| 102 | C56 | 1 | -0.00180 | [-0.00428, +0.00002] | 🟡 noise → drop | `away_pit_bb_pct_7d` |

## Payoff (E1.3 AC)
Dropping the 90 noise clusters (99 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_total_runs.json`_