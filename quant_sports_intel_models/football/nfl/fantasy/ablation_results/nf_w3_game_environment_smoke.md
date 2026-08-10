# NF-W3 — game environment: team play-volume + pass/rush allocation (§0.5 bake-off)

**Generated:** 2026-08-10T02:02:04+00:00 · **folds:** 2 half-season blocks (2025H1…2025H2, the NF-W1 axis verbatim) · **team-games:** 5278 · **player-weeks:** 0

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (serving is NF-W8 / NF-C6 Ph2). Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects. Every direction word below is three-way and **derived from the interval at report time**, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a `assert_point_in_time`):** 175 weeks / 5278 team-game records checked; 0 rows in 0 weeks dropped fail-closed.

## ⭐ Headline

- **Layer A (does the component beat its own baseline?)** — off_plays: **UNDEFINED** · pass_share: **UNDEFINED**
- **Layer B (does it improve the ASSEMBLED player projection vs the NF-W1 champion?)** — **NOT RUN** (`--skip-layer-b`) — ⛔ a run without Layer B is a development artifact, never a verdict: Layer A alone cannot say whether the component is worth serving.

## Layer A — the component bake-offs

### `off_plays` — **UNDEFINED**

`negbin_glm` TIES `foil_team_eb` by +0.0077 CRPS (interval unevaluable)

| label                        |   mean_crps |
|:-----------------------------|------------:|
| oracle__lgbm_quantile        |      2.9416 |
| oracle__negbin_glm           |      4.5990 |
| oracle__pois_glm             |      4.6002 |
| oracle__knn_quantile         |      4.9130 |
| oracle__foil_team_eb         |      4.9673 |
| matched_n__knn_quantile      |      4.9843 |
| negbin_glm                   |      4.9860 |
| foil_team_eb                 |      4.9937 |
| pois_glm                     |      4.9948 |
| knn_quantile                 |      5.0069 |
| permuted_within_week         |      5.0632 |
| marginal_train               |      5.0853 |
| lgbm_quantile                |      5.1250 |
| oracle__foil_team_eb_matchup |      5.2843 |
| foil_team_eb_matchup         |      5.3040 |
| matched_n__lgbm_quantile     |      5.3781 |
| zero_width                   |      6.8572 |
| matched_n__negbin_glm        |      7.1321 |
| matched_n__pois_glm          |      7.1375 |
| max_width                    |      7.1686 |
| nihilist_zero                |     60.5449 |

- fold wins 1/2 (clause requires None) · PBO None · DSR None · p None · BH own-family False / pooled False (binding False)
- anchors: {'nihilist_loses': True, 'marginal_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): {'pois_glm': {'arm': 4.9948, 'own_form_oracle': 4.6002, 'matched_n': 7.1375, 'oracle_beats_matched_n': True}, 'negbin_glm': {'arm': 4.986, 'own_form_oracle': 4.599, 'matched_n': 7.1321, 'oracle_beats_matched_n': True}, 'lgbm_quantile': {'arm': 5.125, 'own_form_oracle': 2.9416, 'matched_n': 5.3781, 'oracle_beats_matched_n': True}, 'knn_quantile': {'arm': 5.0069, 'own_form_oracle': 4.913, 'matched_n': 4.9843, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_foil_mean': -0.0696, 'permuted_lift_p_one_sided': None} · coverage(80) {'winner_coverage_80': 0.8051, 'n_rows': 544, 'binomial_se': 0.0171, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'negbin_glm': 6.852, 'foil_team_eb': 6.8426, 'nihilist_zero': 60.5449, 'marginal_train': 7.0403}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True}

### `pass_share` — **UNDEFINED**

`betabinom` TIES `foil_team_eb` by +0.0016 CRPS (interval unevaluable)

| label                        |   mean_crps |
|:-----------------------------|------------:|
| oracle__lgbm_quantile        |      0.0330 |
| oracle__betabinom            |      0.0538 |
| oracle__binom_glm            |      0.0555 |
| betabinom                    |      0.0574 |
| knn_quantile                 |      0.0579 |
| oracle__knn_quantile         |      0.0582 |
| lgbm_quantile                |      0.0583 |
| oracle__foil_team_eb         |      0.0586 |
| foil_team_eb                 |      0.0590 |
| matched_n__knn_quantile      |      0.0592 |
| binom_glm                    |      0.0598 |
| oracle__foil_team_eb_matchup |      0.0601 |
| marginal_train               |      0.0601 |
| foil_team_eb_matchup         |      0.0601 |
| permuted_within_week         |      0.0612 |
| matched_n__lgbm_quantile     |      0.0615 |
| zero_width                   |      0.0818 |
| matched_n__betabinom         |      0.0875 |
| max_width                    |      0.0877 |
| matched_n__binom_glm         |      0.0905 |
| nihilist_zero                |      0.5682 |

- fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · BH own-family False / pooled False (binding False)
- anchors: {'nihilist_loses': True, 'marginal_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': False, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): {'binom_glm': {'arm': 0.0598, 'own_form_oracle': 0.0555, 'matched_n': 0.0905, 'oracle_beats_matched_n': True}, 'betabinom': {'arm': 0.0574, 'own_form_oracle': 0.0538, 'matched_n': 0.0875, 'oracle_beats_matched_n': True}, 'lgbm_quantile': {'arm': 0.0583, 'own_form_oracle': 0.033, 'matched_n': 0.0615, 'oracle_beats_matched_n': True}, 'knn_quantile': {'arm': 0.0579, 'own_form_oracle': 0.0582, 'matched_n': 0.0592, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_foil_mean': -0.0022, 'permuted_lift_p_one_sided': None} · coverage(80) {'winner_coverage_80': 0.7996, 'n_rows': 544, 'binomial_se': 0.0171, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'betabinom': 0.0801, 'foil_team_eb': 0.0818, 'nihilist_zero': 0.5682, 'marginal_train': 0.0842}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True}

## ⭐ Layer B — the gate: does the environment layer move the PLAYER projection?

Env forms carried into Layer B (the Layer-A winners): `{'off_plays': 'negbin_glm', 'pass_share': 'betabinom'}`.

**NOT RUN** in this invocation (`--skip-layer-b`).

## Null-state classification

```json
{
  "layer_a::off_plays": {
    "state": "UNDEFINED",
    "reason": "`nf_w3_off_plays_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::pass_share": {
    "state": "UNDEFINED",
    "reason": "`nf_w3_pass_share_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  }
}
```

## Pre-registration echo

```json
{
  "real_arms": {
    "off_plays": [
      "pois_glm",
      "negbin_glm",
      "lgbm_quantile",
      "knn_quantile"
    ],
    "pass_share": [
      "binom_glm",
      "betabinom",
      "lgbm_quantile",
      "knn_quantile"
    ]
  },
  "foils": [
    "foil_team_eb",
    "foil_team_eb_matchup"
  ],
  "anchors": {
    "off_plays": [
      "nihilist_zero",
      "marginal_train",
      "zero_width",
      "max_width",
      "permuted_within_week",
      "oracle__pois_glm",
      "oracle__negbin_glm",
      "oracle__lgbm_quantile",
      "oracle__knn_quantile",
      "oracle__foil_team_eb",
      "oracle__foil_team_eb_matchup",
      "matched_n__pois_glm",
      "matched_n__negbin_glm",
      "matched_n__lgbm_quantile",
      "matched_n__knn_quantile"
    ],
    "pass_share": [
      "nihilist_zero",
      "marginal_train",
      "zero_width",
      "max_width",
      "permuted_within_week",
      "oracle__binom_glm",
      "oracle__betabinom",
      "oracle__lgbm_quantile",
      "oracle__knn_quantile",
      "oracle__foil_team_eb",
      "oracle__foil_team_eb_matchup",
      "matched_n__binom_glm",
      "matched_n__betabinom",
      "matched_n__lgbm_quantile",
      "matched_n__knn_quantile"
    ]
  },
  "eligible": {
    "off_plays": [
      "pois_glm",
      "negbin_glm",
      "lgbm_quantile",
      "knn_quantile",
      "foil_team_eb",
      "foil_team_eb_matchup"
    ],
    "pass_share": [
      "binom_glm",
      "betabinom",
      "lgbm_quantile",
      "knn_quantile",
      "foil_team_eb",
      "foil_team_eb_matchup"
    ]
  },
  "layer_b_eligible": [
    "champion",
    "champion_env"
  ],
  "layer_b_anchors": [
    "champion_env_shuffled",
    "champion_env_oracle"
  ],
  "test_blocks": [
    [
      2022,
      1
    ],
    [
      2022,
      2
    ],
    [
      2023,
      1
    ],
    [
      2023,
      2
    ],
    [
      2024,
      1
    ],
    [
      2024,
      2
    ],
    [
      2025,
      1
    ],
    [
      2025,
      2
    ]
  ],
  "purge_weeks": 2,
  "pbo_max": 0.2,
  "dsr_min": 0.95,
  "fdr_q": 0.1,
  "fdr_families": {
    "component": [
      "off_plays",
      "pass_share"
    ],
    "downstream": [
      "QB",
      "RB",
      "WR",
      "TE"
    ]
  },
  "coverage_floor": 0.8,
  "eb_kappa_team": 4.0,
  "matchup_clip": [
    0.9,
    1.1
  ],
  "features": [
    "game_context__is_home",
    "game_context__div_game",
    "game_context__week_index",
    "game_context__days_since_last_game",
    "team_environment__off_plays_l4",
    "team_environment__off_plays_l8",
    "team_environment__off_plays_ewm",
    "team_environment__off_plays_s2d",
    "team_environment__off_plays_prior_season",
    "team_environment__pass_share_l4",
    "team_environment__pass_share_l8",
    "team_environment__pass_share_ewm",
    "team_environment__pass_share_s2d",
    "team_environment__pass_share_prior_season",
    "team_environment__neutral_pass_rate_l4",
    "team_environment__proe_l4",
    "team_environment__no_huddle_l4",
    "team_environment__sec_per_play_l4",
    "team_environment__drives_l4",
    "team_environment__plays_per_drive_l4",
    "team_environment__epa_per_play_l4",
    "team_environment__success_rate_l4",
    "team_environment__points_l4",
    "team_environment__sack_rate_l4",
    "team_environment__games_prior_season",
    "opponent_matchup__def_plays_faced_l4",
    "opponent_matchup__def_pass_share_faced_l4",
    "opponent_matchup__def_epa_allowed_l4",
    "opponent_matchup__def_success_allowed_l4",
    "opponent_matchup__def_sec_per_play_faced_l4",
    "opponent_matchup__def_points_allowed_l4",
    "opponent_matchup__def_drives_faced_l4",
    "opponent_matchup__opp_off_plays_l4",
    "opponent_matchup__opp_off_pass_share_l4",
    "opponent_matchup__opp_off_epa_l4",
    "opponent_matchup__opp_off_sec_per_play_l4"
  ],
  "env_features": [
    "team_environment__proj_off_plays",
    "team_environment__proj_pass_plays",
    "team_environment__proj_rush_plays",
    "team_environment__proj_pass_share",
    "team_environment__proj_off_plays_sd",
    "opponent_matchup__proj_opp_off_plays",
    "opponent_matchup__proj_opp_pass_plays"
  ],
  "era_forbidden_tokens": [
    "pressure",
    "coverage",
    "route",
    "ngs_air_yards"
  ],
  "banned_source_tokens": [
    "spread_line",
    "total_line",
    "vegas_wp",
    "vegas_home_wp",
    "vegas_wpa",
    "vegas_home_wpa",
    "temp",
    "wind",
    "moneyline",
    "depth_team",
    "depth_chart"
  ]
}
```