# Clustered Feature Importance — total_runs (Epic E1.3)

- Recipe: `ngboost_normal(scorer)` · metric **mae** (lower = better) · pooled baseline 3.3603
- Features: **87** in **78** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 68/78** covering **75/87** features → drop/consolidate candidates (≈86% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δmae) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C9 | 1 | +0.11766 | [+0.09572, +0.14131] | ✅ signal | `home_bp_eb_xwoba_seasonnorm` |
| 2 | C10 | 1 | +0.09004 | [+0.06661, +0.11417] | ✅ signal | `away_bp_eb_xwoba_seasonnorm` |
| 3 | C12 | 1 | +0.03291 | [+0.02153, +0.04434] | ✅ signal | `away_bp_eb_coverage_pct` |
| 4 | C0 | 4 | +0.00541 | [+0.00120, +0.00945] | ✅ signal | `home_bp_eb_uncertainty, away_bp_eb_uncertainty, away_wins, away_losses` |
| 5 | C72 | 1 | +0.00354 | [+0.00017, +0.00696] | ✅ signal | `away_team_sequential_bullpen_xwoba_seasonnorm` |
| 6 | C13 | 1 | +0.00344 | [-0.00595, +0.01233] | 🟡 noise → drop | `park_run_factor_3yr` |
| 7 | C7 | 2 | +0.00285 | [+0.00043, +0.00540] | ✅ signal | `home_off_xwoba_30d_seasonnorm, home_team_sequential_woba` |
| 8 | C73 | 1 | +0.00155 | [-0.00092, +0.00398] | 🟡 noise → drop | `home_team_sequential_win_prob` |
| 9 | C28 | 1 | +0.00155 | [-0.00005, +0.00307] | 🟡 noise → drop | `away_starter_xwoba_against_std_seasonnorm` |
| 10 | C19 | 1 | +0.00138 | [-0.00011, +0.00289] | 🟡 noise → drop | `home_pit_woba_against_14d` |
| 11 | C4 | 2 | +0.00130 | [-0.00220, +0.00487] | 🟡 noise → drop | `away_starter_csw_pct_season, away_starter_csw_pct_3start` |
| 12 | C1 | 2 | +0.00129 | [-0.00316, +0.00558] | 🟡 noise → drop | `away_pythagorean_win_exp, away_team_sequential_win_prob` |
| 13 | C50 | 1 | +0.00127 | [+0.00001, +0.00262] | ✅ signal | `home_starter_slider_stuff_plus` |
| 14 | C46 | 1 | +0.00098 | [-0.00193, +0.00369] | 🟡 noise → drop | `home_pit_xwoba_against_7d_seasonnorm` |
| 15 | C2 | 2 | +0.00095 | [-0.00249, +0.00458] | 🟡 noise → drop | `home_pit_woba_against_std, home_pit_woba_against_30d` |
| 16 | C42 | 1 | +0.00094 | [+0.00012, +0.00180] | ✅ signal | `home_starter_whiff_rate_14d` |
| 17 | C35 | 1 | +0.00082 | [-0.00020, +0.00196] | 🟡 noise → drop | `away_starter_whiff_rate_std` |
| 18 | C22 | 1 | +0.00074 | [-0.00034, +0.00174] | 🟡 noise → drop | `home_starter_proj_fip` |
| 19 | C8 | 2 | +0.00064 | [-0.00135, +0.00265] | 🟡 noise → drop | `away_bp_bb_pct_30d, away_bp_bb_pct_14d` |
| 20 | C30 | 1 | +0.00062 | [-0.00014, +0.00138] | 🟡 noise → drop | `away_off_hard_hit_pct_std_seasonnorm` |
| 21 | C27 | 1 | +0.00058 | [-0.00109, +0.00220] | 🟡 noise → drop | `home_starter_k_pct_30d` |
| 22 | C40 | 1 | +0.00057 | [-0.00022, +0.00141] | 🟡 noise → drop | `home_starter_avg_ip_season` |
| 23 | C53 | 1 | +0.00054 | [+0.00010, +0.00108] | ✅ signal | `home_pit_hard_hit_pct_30d_seasonnorm` |
| 24 | C3 | 2 | +0.00049 | [-0.00047, +0.00145] | 🟡 noise → drop | `away_woba_against_with_runners_on_30d, away_woba_against_with_risp_30d` |
| 25 | C60 | 1 | +0.00040 | [-0.00041, +0.00126] | 🟡 noise → drop | `home_pit_barrel_pct_30d_seasonnorm` |
| 26 | C17 | 1 | +0.00039 | [-0.00042, +0.00113] | 🟡 noise → drop | `home_starter_stuff_plus` |
| 27 | C21 | 1 | +0.00032 | [-0.00031, +0.00099] | 🟡 noise → drop | `home_away_starter_k_pct_std_pct_diff` |
| 28 | C66 | 1 | +0.00032 | [-0.00043, +0.00105] | 🟡 noise → drop | `away_starter_hard_hit_pct_std_seasonnorm` |
| 29 | C15 | 1 | +0.00027 | [-0.00064, +0.00121] | 🟡 noise → drop | `elevation_ft` |
| 30 | C37 | 1 | +0.00023 | [-0.00033, +0.00078] | 🟡 noise → drop | `home_pit_k_pct_7d` |
| 31 | C68 | 1 | +0.00016 | [-0.00036, +0.00068] | 🟡 noise → drop | `home_starter_barrel_pct_std_seasonnorm` |
| 32 | C62 | 1 | +0.00015 | [-0.00059, +0.00085] | 🟡 noise → drop | `away_bp_innings_pitched_30d` |
| 33 | C16 | 1 | +0.00014 | [-0.00014, +0.00044] | 🟡 noise → drop | `away_pit_xwoba_against_30d_seasonnorm` |
| 34 | C39 | 1 | +0.00014 | [-0.00007, +0.00034] | 🟡 noise → drop | `away_vs_lhp_xwoba_30d_seasonnorm` |
| 35 | C36 | 1 | +0.00012 | [-0.00032, +0.00062] | 🟡 noise → drop | `home_off_bb_pct_std` |
| 36 | C25 | 1 | +0.00012 | [-0.00018, +0.00042] | 🟡 noise → drop | `away_off_runs_per_game_30d` |
| 37 | C14 | 1 | +0.00011 | [-0.00005, +0.00029] | 🟡 noise → drop | `away_pit_k_pct_std` |
| 38 | C33 | 1 | +0.00007 | [-0.00054, +0.00064] | 🟡 noise → drop | `home_starter_xwoba_against_30d_seasonnorm` |
| 39 | C64 | 1 | +0.00005 | [-0.00041, +0.00051] | 🟡 noise → drop | `home_bp_hard_hit_pct_14d_seasonnorm` |
| 40 | C29 | 1 | +0.00005 | [-0.00023, +0.00033] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 41 | C32 | 1 | +0.00004 | [-0.00059, +0.00067] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 42 | C44 | 1 | +0.00004 | [-0.00048, +0.00058] | 🟡 noise → drop | `home_starter_changeup_stuff_plus` |
| 43 | C67 | 1 | +0.00003 | [-0.00051, +0.00057] | 🟡 noise → drop | `away_starter_xwoba_vs_lhb_seasonnorm` |
| 44 | C47 | 1 | +0.00003 | [-0.00020, +0.00026] | 🟡 noise → drop | `home_starter_k_pct_vs_rhb` |
| 45 | C58 | 1 | +0.00003 | [-0.00015, +0.00020] | 🟡 noise → drop | `home_starter_curveball_stuff_plus` |
| 46 | C41 | 1 | +0.00001 | [-0.00078, +0.00079] | 🟡 noise → drop | `away_starter_avg_ip_season` |
| 47 | C31 | 1 | +0.00001 | [-0.00114, +0.00115] | 🟡 noise → drop | `home_starter_k_pct_vs_lhb` |
| 48 | C18 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_k_pct` |
| 49 | C23 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 50 | C61 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_uncertainty_seasonnorm` |
| 51 | C74 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against_sequential_seasonnorm` |
| 52 | C75 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against_sequential_seasonnorm` |
| 53 | C76 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `has_starter_platoon_data` |
| 54 | C77 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 55 | C56 | 1 | -0.00001 | [-0.00048, +0.00045] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d_seasonnorm` |
| 56 | C26 | 1 | -0.00005 | [-0.00055, +0.00042] | 🟡 noise → drop | `away_pit_woba_against_7d` |
| 57 | C49 | 1 | -0.00005 | [-0.00080, +0.00058] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 58 | C59 | 1 | -0.00007 | [-0.00065, +0.00046] | 🟡 noise → drop | `home_bp_xwoba_against_14d_seasonnorm` |
| 59 | C55 | 1 | -0.00007 | [-0.00106, +0.00098] | 🟡 noise → drop | `away_starter_avg_fastball_velo` |
| 60 | C57 | 1 | -0.00009 | [-0.00054, +0.00038] | 🟡 noise → drop | `away_bullpen_pitches_prev_7d` |
| 61 | C69 | 1 | -0.00009 | [-0.00038, +0.00017] | 🟡 noise → drop | `away_starter_hard_hit_pct_7d_seasonnorm` |
| 62 | C48 | 1 | -0.00009 | [-0.00028, +0.00009] | 🟡 noise → drop | `away_vs_lhp_bb_pct_30d` |
| 63 | C52 | 1 | -0.00010 | [-0.00096, +0.00077] | 🟡 noise → drop | `away_off_hard_hit_pct_7d_seasonnorm` |
| 64 | C54 | 1 | -0.00011 | [-0.00024, +0.00002] | 🟡 noise → drop | `right_center_ft` |
| 65 | C11 | 1 | -0.00012 | [-0.00057, +0.00032] | 🟡 noise → drop | `pythagorean_win_exp_diff` |
| 66 | C71 | 1 | -0.00013 | [-0.00190, +0.00168] | 🟡 noise → drop | `home_team_sequential_bullpen_xwoba_seasonnorm` |
| 67 | C63 | 1 | -0.00016 | [-0.00087, +0.00066] | 🟡 noise → drop | `home_woba_with_risp_30d` |
| 68 | C51 | 1 | -0.00016 | [-0.00043, +0.00012] | 🟡 noise → drop | `home_off_barrel_pct_30d_seasonnorm` |
| 69 | C38 | 1 | -0.00017 | [-0.00094, +0.00059] | 🟡 noise → drop | `home_woba_against_with_risp_30d` |
| 70 | C5 | 2 | -0.00022 | [-0.00117, +0.00073] | 🟡 noise → drop | `away_xwoba_with_runners_on_30d_seasonnorm, away_xwoba_with_risp_30d_seasonnorm` |
| 71 | C20 | 1 | -0.00027 | [-0.00104, +0.00046] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 72 | C65 | 1 | -0.00033 | [-0.00060, -0.00005] | ✅ signal | `home_bp_hard_hit_pct_30d_seasonnorm` |
| 73 | C45 | 1 | -0.00044 | [-0.00119, +0.00030] | 🟡 noise → drop | `home_bp_xwoba_against_30d_seasonnorm` |
| 74 | C70 | 1 | -0.00056 | [-0.00146, +0.00027] | 🟡 noise → drop | `away_team_sequential_woba` |
| 75 | C34 | 1 | -0.00056 | [-0.00287, +0.00177] | 🟡 noise → drop | `home_starter_csw_pct_season` |
| 76 | C6 | 2 | -0.00089 | [-0.00452, +0.00268] | 🟡 noise → drop | `home_starter_xwoba_against_7d_seasonnorm, home_starter_xwoba_7d_minus_std_seasonnorm` |
| 77 | C43 | 1 | -0.00099 | [-0.00316, +0.00071] | 🟡 noise → drop | `away_pit_bb_pct_7d` |
| 78 | C24 | 1 | -0.00141 | [-0.00325, +0.00053] | 🟡 noise → drop | `home_starter_trailing_ra9_30g` |

## Payoff (E1.3 AC)
Dropping the 68 noise clusters (75 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_total_runs_bullpen_v3_stuffplus_deleaked_scorer_ngboost_normal_pre_lineup_total_runs.json`_