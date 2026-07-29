# NF1.5 — CAPSTONE feature-combination bake-off (market-aware refinements + the market-blind ceiling proof)

**Model:** `nfl_fantasy_nf1_5_v1` · **updated:** 2026-07-28T02:01:53.242099+00:00

> 🔒 **HONEST FRAME:** stage 1's bar is the NF1.3 STORED incumbent per position (the market-aware winner); stage 2's bar is the market-blind MVP-1 null — with the blind space exhausted 4×, a clean stage-2 NULL is the LIKELY + valuable outcome (it PROVES the incumbent is the feature-library ceiling). At market-leaning positions we INCORPORATE consensus and ⛔ never claim to beat the market we use. `best_alpha = 0`.

## Stage 1 — MARKET-AWARE refinements (PRIMARY: blend-vs-learned + dispersion-weighted)

targets [2021, 2022, 2023] · pool 1522 · 2 trials/class · oracle sane: True · market top-tier coverage {'QB': 1.0, 'RB': 1.0, 'WR': 0.979, 'TE': 1.0}

### QB

| candidate                                              |   top-tier ρ | hp                                                                  |
|:-------------------------------------------------------|-------------:|:--------------------------------------------------------------------|
| pos_null (MVP-1, blind)                                |       0.4997 |                                                                     |
| pos_market_only (consensus)                            |       0.6324 |                                                                     |
| NF1.3 incumbent (nf1_3_incumbent(pos_market_blend)) 🔒 |       0.6162 | {"blend_w": 0.9869973994939585}                                     |
| pos_learned_adaptive_blend                             |       0.4907 | {"blend_w": 0.2946650026871097, "disp_slope": 0.7958801334079412}   |
| pos_learned_blend                                      |       0.5386 | {"blend_w": 0.5305867556052941}                                     |
| pos_adaptive_blend                                     |       0.529  | {"blend_w": 0.19152078694749486, "disp_slope": 0.10185053728693705} |
| pos_blend_flat                                         |       0.6099 | {"blend_w": 0.5305867556052941}                                     |

- **winner:** `pos_blend_flat` · beats NF1.3 incumbent: **False** (Δ -0.0063) · beats blind null: True · beats pure consensus: False
- **deflation** (9 configs): PBO — (spread 0.1791) · DSR 0.5443 · p 0.0877 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (beats_null, pbo_ok, dsr_ok)

### RB

| candidate                                              |   top-tier ρ | hp                                                                |
|:-------------------------------------------------------|-------------:|:------------------------------------------------------------------|
| pos_null (MVP-1, blind)                                |       0.4283 |                                                                   |
| pos_market_only (consensus)                            |       0.5749 |                                                                   |
| NF1.3 incumbent (nf1_3_incumbent(pos_market_blend)) 🔒 |       0.5809 | {"blend_w": 0.9583426412697418}                                   |
| pos_learned_adaptive_blend                             |       0.5866 | {"blend_w": 0.2946650026871097, "disp_slope": 0.7958801334079412} |
| pos_learned_blend                                      |       0.563  | {"blend_w": 0.5305867556052941}                                   |
| pos_adaptive_blend                                     |       0.5798 | {"blend_w": 0.2946650026871097, "disp_slope": 0.7958801334079412} |
| pos_blend_flat                                         |       0.5339 | {"blend_w": 0.5305867556052941}                                   |

- **winner:** `pos_learned_adaptive_blend` · beats NF1.3 incumbent: **True** (Δ +0.0057) · beats blind null: True · beats pure consensus: True
- **deflation** (9 configs): PBO — (spread 0.0858) · DSR 1.0000 · p 0.0199 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (pbo_ok)

### WR

| candidate                                     |   top-tier ρ | hp                                                                                                                                     |
|:----------------------------------------------|-------------:|:---------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1, blind)                       |       0.4824 |                                                                                                                                        |
| pos_market_only (consensus)                   |       0.6649 |                                                                                                                                        |
| NF1.3 incumbent (nf1_3_incumbent(pos_gbm)) 🔒 |       0.7004 | {"n_estimators": 300, "num_leaves": 7, "learning_rate": 0.012050541345647812, "min_child_samples": 8, "reg_lambda": 4.368469237108717} |
| pos_learned_adaptive_blend                    |       0.6926 | {"blend_w": 0.19152078694749486, "disp_slope": 0.10185053728693705}                                                                    |
| pos_learned_blend                             |       0.6953 | {"blend_w": 0.5305867556052941}                                                                                                        |
| pos_adaptive_blend                            |       0.5343 | {"blend_w": 0.19152078694749486, "disp_slope": 0.10185053728693705}                                                                    |
| pos_blend_flat                                |       0.6277 | {"blend_w": 0.5305867556052941}                                                                                                        |

- **winner:** `pos_learned_blend` · beats NF1.3 incumbent: **False** (Δ -0.0051) · beats blind null: True · beats pure consensus: True
- **deflation** (9 configs): PBO — (spread 0.1681) · DSR 0.3541 · p 0.0055 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (beats_null, pbo_ok, dsr_ok)

### TE

| candidate                                              |   top-tier ρ | hp                                                                  |
|:-------------------------------------------------------|-------------:|:--------------------------------------------------------------------|
| pos_null (MVP-1, blind)                                |       0.4502 |                                                                     |
| pos_market_only (consensus)                            |       0.5333 |                                                                     |
| NF1.3 incumbent (nf1_3_incumbent(pos_market_blend)) 🔒 |       0.5817 | {"blend_w": 0.6000478605455821}                                     |
| pos_learned_adaptive_blend                             |       0.5545 | {"blend_w": 0.19152078694749486, "disp_slope": 0.10185053728693705} |
| pos_learned_blend                                      |       0.5751 | {"blend_w": 0.5305867556052941}                                     |
| pos_adaptive_blend                                     |       0.4884 | {"blend_w": 0.2946650026871097, "disp_slope": 0.7958801334079412}   |
| pos_blend_flat                                         |       0.5661 | {"blend_w": 0.5305867556052941}                                     |

- **winner:** `pos_learned_blend` · beats NF1.3 incumbent: **False** (Δ -0.0066) · beats blind null: True · beats pure consensus: True
- **deflation** (9 configs): PBO — (spread 0.0950) · DSR 0.0878 · p 0.0275 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (beats_null, pbo_ok, dsr_ok)

**Placebo (labels shuffled within position×season — the same search must find nothing):**

| pos   |   winner_mean_top |   null_mean_top |   naive_delta_vs_null | gates_pass   |
|:------|------------------:|----------------:|----------------------:|:-------------|
| QB    |            0.1527 |          0.2032 |               -0.0505 | False        |
| RB    |            0.1811 |          0.0387 |                0.1424 | False        |
| WR    |            0.0922 |         -0.1816 |                0.2738 | False        |
| TE    |            0.082  |         -0.0722 |                0.1542 | False        |

## Stage 2 — MARKET-BLIND combination sweep (ceiling proof; expected null)

targets [2021, 2022, 2023] · pool 1522 · 2 trials/cell · bundles: ['base', 'base_xfp', 'base_env', 'base_contract', 'base_opp', 'all_skill', 'kitchen_sink'] · candidates: ['pos_ridge', 'pos_gbm', 'pos_similarity', 'pos_mlp', 'pos_twopart', 'pos_rank'] · oracle sane: True

### QB

| class×bundle                 |   top-tier ρ |
|:-----------------------------|-------------:|
| pos_similarity×base_env      |       0.5258 |
| pos_ridge×base               |       0.5041 |
| pos_ridge×kitchen_sink       |       0.4907 |
| pos_mlp×base                 |       0.4849 |
| pos_ridge×base_xfp           |       0.4771 |
| pos_gbm×base_env             |       0.4658 |
| pos_twopart×base             |       0.4583 |
| pos_gbm×kitchen_sink         |       0.4577 |
| pos_twopart×base_contract    |       0.4571 |
| pos_twopart×base_xfp         |       0.4568 |
| pos_similarity×base_contract |       0.4556 |
| pos_ridge×base_contract      |       0.4528 |
| pos_mlp×base_env             |       0.4516 |
| pos_rank×base_env            |       0.4488 |
| pos_gbm×base                 |       0.44   |
| pos_ridge×base_env           |       0.4397 |
| pos_twopart×kitchen_sink     |       0.4385 |
| pos_rank×base                |       0.4364 |
| pos_similarity×kitchen_sink  |       0.4348 |
| pos_gbm×base_xfp             |       0.4328 |
| pos_rank×kitchen_sink        |       0.4278 |
| pos_gbm×base_contract        |       0.4215 |
| pos_mlp×kitchen_sink         |       0.4177 |
| pos_mlp×base_xfp             |       0.4159 |
| pos_twopart×base_env         |       0.4136 |
| pos_rank×base_contract       |       0.4046 |
| pos_similarity×base_xfp      |       0.3997 |
| pos_rank×base_xfp            |       0.3996 |
| pos_similarity×base          |       0.3864 |
| pos_mlp×base_contract        |       0.3785 |

- null (MVP-1) 0.4997 · NF1.1 winner ref 0.4093
- **winner:** `pos_similarity` × `base_env` ρ 0.5258 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (61 configs): PBO — (spread 0.2877) · DSR 0.0174 · p 0.0971 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok)

### RB

| class×bundle                 |   top-tier ρ |
|:-----------------------------|-------------:|
| pos_ridge×base_xfp           |       0.5227 |
| pos_ridge×base_opp           |       0.5157 |
| pos_gbm×base_contract        |       0.5035 |
| pos_gbm×base_xfp             |       0.4958 |
| pos_ridge×base               |       0.4951 |
| pos_ridge×base_contract      |       0.4947 |
| pos_gbm×base_opp             |       0.4867 |
| pos_similarity×base          |       0.4812 |
| pos_ridge×base_env           |       0.4781 |
| pos_gbm×kitchen_sink         |       0.4777 |
| pos_ridge×all_skill          |       0.4774 |
| pos_twopart×base_contract    |       0.4719 |
| pos_gbm×base                 |       0.4667 |
| pos_similarity×base_contract |       0.4658 |
| pos_gbm×base_env             |       0.4621 |
| pos_ridge×kitchen_sink       |       0.4613 |
| pos_similarity×kitchen_sink  |       0.4592 |
| pos_twopart×base_xfp         |       0.4572 |
| pos_twopart×kitchen_sink     |       0.4561 |
| pos_mlp×base_xfp             |       0.454  |
| pos_mlp×base                 |       0.454  |
| pos_gbm×all_skill            |       0.453  |
| pos_twopart×base_opp         |       0.4529 |
| pos_mlp×all_skill            |       0.4466 |
| pos_similarity×base_xfp      |       0.4456 |
| pos_similarity×base_opp      |       0.4456 |
| pos_twopart×base_env         |       0.4447 |
| pos_mlp×base_opp             |       0.4435 |
| pos_similarity×all_skill     |       0.4406 |
| pos_rank×base_env            |       0.4384 |
| pos_twopart×all_skill        |       0.4375 |
| pos_mlp×base_contract        |       0.4374 |
| pos_twopart×base             |       0.4367 |
| pos_rank×base_opp            |       0.43   |
| pos_similarity×base_env      |       0.4292 |
| pos_rank×all_skill           |       0.4236 |
| pos_rank×base                |       0.4231 |
| pos_rank×base_contract       |       0.4222 |
| pos_rank×base_xfp            |       0.4142 |
| pos_rank×kitchen_sink        |       0.4111 |
| pos_mlp×kitchen_sink         |       0.4023 |
| pos_mlp×base_env             |       0.3761 |

- null (MVP-1) 0.4283 · NF1.1 winner ref 0.5247
- **winner:** `pos_ridge` × `base_xfp` ρ 0.5227 · beats null: **True** · beats NF1.1 ref: False
- **deflation** (85 configs): PBO — (spread 0.2007) · DSR 0.0362 · p 0.0696 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok)

### WR

| class×bundle                 |   top-tier ρ |
|:-----------------------------|-------------:|
| pos_ridge×kitchen_sink       |       0.7047 |
| pos_ridge×base_contract      |       0.7042 |
| pos_ridge×base               |       0.7039 |
| pos_mlp×base                 |       0.7037 |
| pos_ridge×base_opp           |       0.7025 |
| pos_twopart×base             |       0.6907 |
| pos_ridge×base_env           |       0.6897 |
| pos_twopart×base_contract    |       0.6863 |
| pos_mlp×base_contract        |       0.6848 |
| pos_similarity×base          |       0.6847 |
| pos_ridge×all_skill          |       0.6842 |
| pos_twopart×base_opp         |       0.6724 |
| pos_twopart×base_env         |       0.6694 |
| pos_similarity×base_opp      |       0.6659 |
| pos_twopart×kitchen_sink     |       0.6556 |
| pos_twopart×all_skill        |       0.6554 |
| pos_mlp×base_env             |       0.6545 |
| pos_mlp×base_opp             |       0.6544 |
| pos_mlp×kitchen_sink         |       0.651  |
| pos_mlp×all_skill            |       0.644  |
| pos_similarity×all_skill     |       0.6311 |
| pos_gbm×base_env             |       0.6308 |
| pos_gbm×all_skill            |       0.6295 |
| pos_gbm×base                 |       0.6287 |
| pos_similarity×base_contract |       0.627  |
| pos_similarity×kitchen_sink  |       0.6235 |
| pos_gbm×base_opp             |       0.6224 |
| pos_gbm×kitchen_sink         |       0.6168 |
| pos_gbm×base_contract        |       0.6114 |
| pos_similarity×base_env      |       0.6089 |
| pos_rank×base_opp            |       0.597  |
| pos_rank×base                |       0.5946 |
| pos_rank×kitchen_sink        |       0.5915 |
| pos_rank×base_env            |       0.5881 |
| pos_rank×all_skill           |       0.5773 |
| pos_rank×base_contract       |       0.5751 |

- null (MVP-1) 0.4824 · NF1.1 winner ref 0.6870
- **winner:** `pos_ridge` × `kitchen_sink` ρ 0.7047 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (73 configs): PBO — (spread 0.1792) · DSR 0.0000 · p 0.0252 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok)

### TE

| class×bundle                 |   top-tier ρ |
|:-----------------------------|-------------:|
| pos_rank×base_opp            |       0.5641 |
| pos_rank×base_xfp            |       0.5383 |
| pos_similarity×base          |       0.5197 |
| pos_similarity×base_opp      |       0.5125 |
| pos_mlp×base                 |       0.504  |
| pos_rank×all_skill           |       0.5026 |
| pos_ridge×base_xfp           |       0.4986 |
| pos_rank×base                |       0.4983 |
| pos_similarity×base_xfp      |       0.4971 |
| pos_similarity×base_env      |       0.4968 |
| pos_ridge×base_opp           |       0.4939 |
| pos_similarity×base_contract |       0.4913 |
| pos_ridge×all_skill          |       0.4867 |
| pos_ridge×base_env           |       0.4858 |
| pos_ridge×base               |       0.4821 |
| pos_mlp×base_opp             |       0.4817 |
| pos_similarity×all_skill     |       0.4791 |
| pos_rank×base_contract       |       0.4751 |
| pos_ridge×base_contract      |       0.467  |
| pos_mlp×base_xfp             |       0.4623 |
| pos_rank×base_env            |       0.4603 |
| pos_ridge×kitchen_sink       |       0.4513 |
| pos_similarity×kitchen_sink  |       0.4455 |
| pos_mlp×all_skill            |       0.438  |
| pos_mlp×base_contract        |       0.4281 |
| pos_gbm×all_skill            |       0.4258 |
| pos_rank×kitchen_sink        |       0.4223 |
| pos_mlp×base_env             |       0.4157 |
| pos_gbm×base_env             |       0.415  |
| pos_mlp×kitchen_sink         |       0.4128 |
| pos_twopart×base             |       0.4127 |
| pos_gbm×base                 |       0.4122 |
| pos_gbm×base_opp             |       0.4099 |
| pos_twopart×base_env         |       0.4058 |
| pos_gbm×base_xfp             |       0.4029 |
| pos_twopart×base_contract    |       0.3907 |
| pos_gbm×kitchen_sink         |       0.3832 |
| pos_twopart×base_xfp         |       0.382  |
| pos_gbm×base_contract        |       0.3782 |
| pos_twopart×base_opp         |       0.3736 |
| pos_twopart×kitchen_sink     |       0.3687 |
| pos_twopart×all_skill        |       0.3678 |

- null (MVP-1) 0.4502 · NF1.1 winner ref 0.5055
- **winner:** `pos_rank` × `base_opp` ρ 0.5641 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (85 configs): PBO — (spread 0.3647) · DSR 0.0000 · p 0.0166 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok)

**Placebo (labels shuffled — the same sweep must find nothing):**

| pos   |   winner_mean_top |   null_mean_top |   naive_delta_vs_null | gates_pass   |
|:------|------------------:|----------------:|----------------------:|:-------------|
| QB    |            0.1301 |          0.2032 |               -0.0731 | False        |
| RB    |            0.2604 |          0.0387 |                0.2217 | False        |
| WR    |            0.1193 |         -0.1816 |                0.3009 | False        |
| TE    |            0.1909 |         -0.0722 |                0.2631 | False        |

## Serving decision (NF1.5-owned)

- **serve:** `nf1_3-dual-board`
- why: no refinement improved on NF1.3, whose product win over consensus stands (first board to beat ADP pooled) and whose calibration verifies; serve the NF1.3 board with honest market-lean labels + keep MVP-1 as the fade baseline
- calibration verify: calib_80 = 0.803 (floor 0.80, tolerance ≥0.78) · product Δρ-vs-ADP (refined − NF1.3): -0.003

