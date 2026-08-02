# NF1.5 — CAPSTONE feature-combination bake-off (market-aware refinements + the market-blind ceiling proof)

**Model:** `nfl_fantasy_nf1_5_v1` · **updated:** 2026-08-01T00:42:37.409071+00:00

> 🔒 **HONEST FRAME:** stage 1's bar is the NF1.3 STORED incumbent per position (the market-aware winner); stage 2's bar is the market-blind MVP-1 null — with the blind space exhausted 4×, a clean stage-2 NULL is the LIKELY + valuable outcome (it PROVES the incumbent is the feature-library ceiling). At market-leaning positions we INCORPORATE consensus and ⛔ never claim to beat the market we use. `best_alpha = 0`.

## Stage 1 — MARKET-AWARE refinements (PRIMARY: blend-vs-learned + dispersion-weighted)

targets [2021, 2022, 2023] · pool 1571 · 2 trials/class · oracle sane: True · market top-tier coverage {'QB': 1.0, 'RB': 1.0, 'WR': 0.979, 'TE': 1.0}

### QB

| candidate                                              |   top-tier ρ | hp                                                                  |
|:-------------------------------------------------------|-------------:|:--------------------------------------------------------------------|
| pos_null (MVP-1, blind)                                |       0.4997 |                                                                     |
| pos_market_only (consensus)                            |       0.6324 |                                                                     |
| NF1.3 incumbent (nf1_3_incumbent(pos_market_blend)) 🔒 |       0.6162 | {"blend_w": 0.9869973994939585}                                     |
| pos_learned_adaptive_blend                             |       0.5217 | {"blend_w": 0.2946650026871097, "disp_slope": 0.7958801334079412}   |
| pos_learned_blend                                      |       0.5365 | {"blend_w": 0.5305867556052941}                                     |
| pos_adaptive_blend                                     |       0.5275 | {"blend_w": 0.19152078694749486, "disp_slope": 0.10185053728693705} |
| pos_blend_flat ⭐                                      |       0.6104 | {"blend_w": 0.5305867556052941}                                     |

- **winner:** `pos_blend_flat` · beats NF1.3 incumbent: **False** (Δ -0.0058) · beats blind null: True · beats pure consensus: False
- **deflation** (9 configs): PBO — (spread 0.1565) · DSR 0.5863 · p 0.0789 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (beats_null, pbo_ok, dsr_ok)

### RB

| candidate                                              |   top-tier ρ | hp                                                                |
|:-------------------------------------------------------|-------------:|:------------------------------------------------------------------|
| pos_null (MVP-1, blind)                                |       0.4412 |                                                                   |
| pos_market_only (consensus)                            |       0.5722 |                                                                   |
| NF1.3 incumbent (nf1_3_incumbent(pos_market_blend)) 🔒 |       0.5776 | {"blend_w": 0.9583426412697418}                                   |
| pos_learned_adaptive_blend ⭐                          |       0.5871 | {"blend_w": 0.2946650026871097, "disp_slope": 0.7958801334079412} |
| pos_learned_blend                                      |       0.5644 | {"blend_w": 0.5305867556052941}                                   |
| pos_adaptive_blend                                     |       0.5822 | {"blend_w": 0.2946650026871097, "disp_slope": 0.7958801334079412} |
| pos_blend_flat                                         |       0.5381 | {"blend_w": 0.5305867556052941}                                   |

- **winner:** `pos_learned_adaptive_blend` · beats NF1.3 incumbent: **True** (Δ +0.0095) · beats blind null: True · beats pure consensus: True
- **deflation** (9 configs): PBO — (spread 0.0793) · DSR 0.9980 · p 0.0078 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (pbo_ok)

### WR

| candidate                                     |   top-tier ρ | hp                                                                                                                                     |
|:----------------------------------------------|-------------:|:---------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1, blind)                       |       0.479  |                                                                                                                                        |
| pos_market_only (consensus)                   |       0.6627 |                                                                                                                                        |
| NF1.3 incumbent (nf1_3_incumbent(pos_gbm)) 🔒 |       0.694  | {"n_estimators": 300, "num_leaves": 7, "learning_rate": 0.012050541345647812, "min_child_samples": 8, "reg_lambda": 4.368469237108717} |
| pos_learned_adaptive_blend                    |       0.6818 | {"blend_w": 0.19152078694749486, "disp_slope": 0.10185053728693705}                                                                    |
| pos_learned_blend ⭐                          |       0.6895 | {"blend_w": 0.5305867556052941}                                                                                                        |
| pos_adaptive_blend                            |       0.5308 | {"blend_w": 0.2946650026871097, "disp_slope": 0.7958801334079412}                                                                      |
| pos_blend_flat                                |       0.6243 | {"blend_w": 0.5305867556052941}                                                                                                        |

- **winner:** `pos_learned_blend` · beats NF1.3 incumbent: **False** (Δ -0.0045) · beats blind null: True · beats pure consensus: True
- **deflation** (9 configs): PBO — (spread 0.1634) · DSR 0.0517 · p 0.0078 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (beats_null, pbo_ok, dsr_ok)

### TE

| candidate                                              |   top-tier ρ | hp                                                                  |
|:-------------------------------------------------------|-------------:|:--------------------------------------------------------------------|
| pos_null (MVP-1, blind)                                |       0.4501 |                                                                     |
| pos_market_only (consensus)                            |       0.5337 |                                                                     |
| NF1.3 incumbent (nf1_3_incumbent(pos_market_blend)) 🔒 |       0.5747 | {"blend_w": 0.6000478605455821}                                     |
| pos_learned_adaptive_blend                             |       0.549  | {"blend_w": 0.2946650026871097, "disp_slope": 0.7958801334079412}   |
| pos_learned_blend ⭐                                   |       0.5761 | {"blend_w": 0.5305867556052941}                                     |
| pos_adaptive_blend                                     |       0.4866 | {"blend_w": 0.19152078694749486, "disp_slope": 0.10185053728693705} |
| pos_blend_flat                                         |       0.5647 | {"blend_w": 0.5305867556052941}                                     |

- **winner:** `pos_learned_blend` · beats NF1.3 incumbent: **True** (Δ +0.0014) · beats blind null: True · beats pure consensus: True
- **deflation** (9 configs): PBO — (spread 0.0913) · DSR 0.9994 · p 0.0260 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (pbo_ok)

**Placebo (labels shuffled within position×season — the same search must find nothing):**

| pos   |   winner_mean_top |   null_mean_top |   naive_delta_vs_null | gates_pass   |
|:------|------------------:|----------------:|----------------------:|:-------------|
| QB    |            0.1078 |         -0.0049 |                0.1127 | False        |
| RB    |           -0.0051 |         -0.0657 |                0.0606 | False        |
| WR    |            0.1756 |          0.1234 |                0.0522 | False        |
| TE    |           -0.0006 |         -0.1628 |                0.1622 | False        |

## Stage 2 — MARKET-BLIND combination sweep (ceiling proof; expected null)

targets [2021, 2022, 2023] · pool 1571 · 2 trials/cell · bundles: ['base', 'base_xfp', 'base_env', 'base_contract', 'base_opp', 'base_system_coach', 'env_coach', 'all_skill', 'kitchen_sink'] · candidates: ['pos_ridge', 'pos_gbm', 'pos_similarity', 'pos_mlp', 'pos_twopart', 'pos_rank'] · oracle sane: True

### QB

| class×bundle                     |   top-tier ρ |
|:---------------------------------|-------------:|
| pos_gbm×env_coach                |       0.5014 |
| pos_gbm×base_env                 |       0.4896 |
| pos_twopart×base                 |       0.4858 |
| pos_ridge×base                   |       0.4797 |
| pos_similarity×base_env          |       0.4785 |
| pos_ridge×kitchen_sink           |       0.4751 |
| pos_rank×base_env                |       0.4728 |
| pos_twopart×base_env             |       0.4704 |
| pos_twopart×base_xfp             |       0.4675 |
| pos_ridge×base_xfp               |       0.4675 |
| pos_rank×kitchen_sink            |       0.4628 |
| pos_twopart×kitchen_sink         |       0.46   |
| pos_similarity×base_contract     |       0.4591 |
| pos_ridge×base_env               |       0.4588 |
| pos_gbm×base_xfp                 |       0.4562 |
| pos_gbm×base                     |       0.4539 |
| pos_twopart×base_contract        |       0.4516 |
| pos_mlp×base_xfp                 |       0.4513 |
| pos_rank×base                    |       0.4498 |
| pos_ridge×base_contract          |       0.4478 |
| pos_mlp×base                     |       0.4438 |
| pos_similarity×kitchen_sink      |       0.4438 |
| pos_gbm×base_system_coach        |       0.4432 |
| pos_gbm×kitchen_sink             |       0.4394 |
| pos_twopart×env_coach            |       0.4394 |
| pos_rank×env_coach               |       0.4339 |
| pos_gbm×base_contract            |       0.4284 |
| pos_ridge×env_coach              |       0.4275 |
| pos_mlp×base_system_coach        |       0.4252 |
| pos_similarity×env_coach         |       0.4252 |
| pos_similarity×base_system_coach |       0.4238 |
| pos_mlp×base_env                 |       0.422  |
| pos_mlp×kitchen_sink             |       0.4165 |
| pos_rank×base_xfp                |       0.4111 |
| pos_rank×base_contract           |       0.4093 |
| pos_similarity×base_xfp          |       0.4087 |
| pos_rank×base_system_coach       |       0.4054 |
| pos_mlp×env_coach                |       0.3997 |
| pos_similarity×base              |       0.3991 |
| pos_mlp×base_contract            |       0.3629 |
| pos_twopart×base_system_coach    |       0.3629 |
| pos_ridge×base_system_coach      |       0.3055 |

- null (MVP-1) 0.4997 · NF1.1 winner ref 0.4240
- **winner:** `pos_gbm` × `env_coach` ρ 0.5014 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (85 configs): PBO — (spread 0.2165) · DSR 0.0007 · p 0.4860 · FDR pass False
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok, fdr_ok)

### RB

| class×bundle                     |   top-tier ρ |
|:---------------------------------|-------------:|
| pos_ridge×base_opp               |       0.5169 |
| pos_ridge×base_xfp               |       0.5121 |
| pos_gbm×env_coach                |       0.5095 |
| pos_gbm×kitchen_sink             |       0.5052 |
| pos_ridge×base                   |       0.5003 |
| pos_ridge×env_coach              |       0.5003 |
| pos_similarity×base              |       0.4915 |
| pos_gbm×all_skill                |       0.4898 |
| pos_ridge×base_contract          |       0.4898 |
| pos_ridge×base_system_coach      |       0.4891 |
| pos_gbm×base_env                 |       0.4865 |
| pos_ridge×base_env               |       0.4847 |
| pos_twopart×base_contract        |       0.4825 |
| pos_gbm×base_contract            |       0.4814 |
| pos_gbm×base_xfp                 |       0.4808 |
| pos_gbm×base_system_coach        |       0.4805 |
| pos_similarity×kitchen_sink      |       0.477  |
| pos_ridge×all_skill              |       0.475  |
| pos_similarity×base_contract     |       0.4748 |
| pos_gbm×base                     |       0.4686 |
| pos_twopart×kitchen_sink         |       0.4685 |
| pos_gbm×base_opp                 |       0.4679 |
| pos_twopart×base_opp             |       0.4666 |
| pos_similarity×base_env          |       0.4652 |
| pos_twopart×base_xfp             |       0.4648 |
| pos_similarity×base_system_coach |       0.4644 |
| pos_twopart×env_coach            |       0.4639 |
| pos_mlp×base                     |       0.4632 |
| pos_twopart×base                 |       0.462  |
| pos_twopart×base_system_coach    |       0.4614 |
| pos_similarity×all_skill         |       0.4608 |
| pos_mlp×all_skill                |       0.4553 |
| pos_mlp×base_contract            |       0.4551 |
| pos_mlp×base_xfp                 |       0.4519 |
| pos_twopart×all_skill            |       0.4473 |
| pos_twopart×base_env             |       0.4471 |
| pos_similarity×base_opp          |       0.4464 |
| pos_similarity×env_coach         |       0.4462 |
| pos_mlp×base_env                 |       0.4376 |
| pos_similarity×base_xfp          |       0.4367 |
| pos_ridge×kitchen_sink           |       0.4337 |
| pos_mlp×env_coach                |       0.433  |
| pos_mlp×base_system_coach        |       0.429  |
| pos_mlp×base_opp                 |       0.4278 |
| pos_rank×env_coach               |       0.4256 |
| pos_rank×base_opp                |       0.4251 |
| pos_rank×base_system_coach       |       0.4246 |
| pos_rank×all_skill               |       0.4229 |
| pos_rank×base_xfp                |       0.4183 |
| pos_mlp×kitchen_sink             |       0.4177 |
| pos_rank×base_env                |       0.4148 |
| pos_rank×base_contract           |       0.4123 |
| pos_rank×base                    |       0.4023 |
| pos_rank×kitchen_sink            |       0.3676 |

- null (MVP-1) 0.4412 · NF1.1 winner ref 0.5198
- **winner:** `pos_ridge` × `base_opp` ρ 0.5169 · beats null: **True** · beats NF1.1 ref: False
- **deflation** (109 configs): PBO — (spread 0.1787) · DSR 0.1812 · p 0.0495 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok)

### WR

| class×bundle                     |   top-tier ρ |
|:---------------------------------|-------------:|
| pos_ridge×base_contract          |       0.6922 |
| pos_twopart×base                 |       0.6894 |
| pos_ridge×base                   |       0.6873 |
| pos_twopart×base_contract        |       0.6871 |
| pos_ridge×base_opp               |       0.6857 |
| pos_ridge×base_env               |       0.6824 |
| pos_similarity×base              |       0.68   |
| pos_mlp×base                     |       0.6761 |
| pos_ridge×all_skill              |       0.6755 |
| pos_twopart×base_system_coach    |       0.6733 |
| pos_twopart×base_env             |       0.6697 |
| pos_mlp×base_contract            |       0.6697 |
| pos_mlp×base_opp                 |       0.6654 |
| pos_twopart×base_opp             |       0.6601 |
| pos_similarity×base_opp          |       0.653  |
| pos_twopart×env_coach            |       0.6479 |
| pos_mlp×all_skill                |       0.6437 |
| pos_twopart×all_skill            |       0.6408 |
| pos_mlp×base_env                 |       0.6397 |
| pos_gbm×env_coach                |       0.6364 |
| pos_gbm×base                     |       0.6322 |
| pos_similarity×base_contract     |       0.6308 |
| pos_gbm×base_env                 |       0.6286 |
| pos_rank×base                    |       0.628  |
| pos_similarity×all_skill         |       0.6189 |
| pos_gbm×all_skill                |       0.6172 |
| pos_rank×base_system_coach       |       0.6164 |
| pos_gbm×base_contract            |       0.6155 |
| pos_twopart×kitchen_sink         |       0.6152 |
| pos_similarity×base_env          |       0.6146 |
| pos_gbm×kitchen_sink             |       0.6125 |
| pos_rank×base_env                |       0.6123 |
| pos_rank×env_coach               |       0.6113 |
| pos_rank×base_contract           |       0.6102 |
| pos_rank×base_opp                |       0.6069 |
| pos_gbm×base_system_coach        |       0.6062 |
| pos_gbm×base_opp                 |       0.6062 |
| pos_rank×all_skill               |       0.6036 |
| pos_ridge×kitchen_sink           |       0.6008 |
| pos_rank×kitchen_sink            |       0.5959 |
| pos_similarity×base_system_coach |       0.5878 |
| pos_similarity×env_coach         |       0.5875 |
| pos_ridge×base_system_coach      |       0.5864 |
| pos_ridge×env_coach              |       0.5722 |
| pos_mlp×kitchen_sink             |       0.5692 |
| pos_similarity×kitchen_sink      |       0.5679 |
| pos_mlp×env_coach                |       0.5674 |
| pos_mlp×base_system_coach        |       0.5638 |

- null (MVP-1) 0.4790 · NF1.1 winner ref 0.6759
- **winner:** `pos_ridge` × `base_contract` ρ 0.6922 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (97 configs): PBO — (spread 0.1884) · DSR 0.0000 · p 0.0252 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok)

### TE

| class×bundle                     |   top-tier ρ |
|:---------------------------------|-------------:|
| pos_similarity×base              |       0.5431 |
| pos_rank×base_opp                |       0.5396 |
| pos_mlp×base_env                 |       0.5318 |
| pos_rank×base                    |       0.5298 |
| pos_mlp×base                     |       0.5166 |
| pos_ridge×base_xfp               |       0.5083 |
| pos_ridge×base_env               |       0.5048 |
| pos_ridge×base_opp               |       0.5031 |
| pos_similarity×base_xfp          |       0.5013 |
| pos_mlp×all_skill                |       0.5002 |
| pos_similarity×all_skill         |       0.5    |
| pos_rank×base_xfp                |       0.497  |
| pos_rank×all_skill               |       0.4961 |
| pos_rank×base_contract           |       0.4913 |
| pos_similarity×base_opp          |       0.4909 |
| pos_ridge×base                   |       0.4892 |
| pos_ridge×all_skill              |       0.4886 |
| pos_similarity×base_contract     |       0.488  |
| pos_rank×base_system_coach       |       0.4858 |
| pos_mlp×base_opp                 |       0.4734 |
| pos_similarity×base_env          |       0.4717 |
| pos_gbm×base_env                 |       0.4713 |
| pos_gbm×base_xfp                 |       0.47   |
| pos_similarity×kitchen_sink      |       0.4663 |
| pos_gbm×all_skill                |       0.4648 |
| pos_mlp×base_xfp                 |       0.4625 |
| pos_rank×kitchen_sink            |       0.46   |
| pos_similarity×env_coach         |       0.457  |
| pos_ridge×base_contract          |       0.4535 |
| pos_gbm×base                     |       0.4525 |
| pos_gbm×env_coach                |       0.4518 |
| pos_rank×base_env                |       0.4483 |
| pos_rank×env_coach               |       0.4478 |
| pos_gbm×base_system_coach        |       0.4354 |
| pos_gbm×base_opp                 |       0.4318 |
| pos_mlp×base_contract            |       0.4192 |
| pos_gbm×kitchen_sink             |       0.4179 |
| pos_twopart×base_opp             |       0.3976 |
| pos_similarity×base_system_coach |       0.3918 |
| pos_gbm×base_contract            |       0.3834 |
| pos_twopart×all_skill            |       0.3825 |
| pos_twopart×base                 |       0.3662 |
| pos_twopart×base_xfp             |       0.3567 |
| pos_twopart×base_env             |       0.3536 |
| pos_ridge×base_system_coach      |       0.3518 |
| pos_twopart×base_contract        |       0.3504 |
| pos_twopart×base_system_coach    |       0.3485 |
| pos_ridge×env_coach              |       0.3397 |
| pos_twopart×env_coach            |       0.3241 |
| pos_mlp×env_coach                |       0.3209 |
| pos_mlp×base_system_coach        |       0.3076 |
| pos_ridge×kitchen_sink           |       0.2935 |
| pos_twopart×kitchen_sink         |       0.2619 |
| pos_mlp×kitchen_sink             |       0.2518 |

- null (MVP-1) 0.4501 · NF1.1 winner ref 0.5022
- **winner:** `pos_similarity` × `base` ρ 0.5431 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (109 configs): PBO — (spread 0.4519) · DSR 0.0048 · p 0.0287 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok)

**Placebo (labels shuffled — the same sweep must find nothing):**

| pos   |   winner_mean_top |   null_mean_top |   naive_delta_vs_null | gates_pass   |
|:------|------------------:|----------------:|----------------------:|:-------------|
| QB    |            0.2038 |         -0.0049 |                0.2087 | False        |
| RB    |            0.2148 |         -0.0657 |                0.2805 | False        |
| WR    |            0.1671 |          0.1234 |                0.0437 | False        |
| TE    |            0.2222 |         -0.1628 |                0.385  | False        |

## Serving decision (NF1.5-owned)

- **serve:** `nf1_3-dual-board`
- why: no refinement improved on NF1.3, whose product win over consensus stands (first board to beat ADP pooled) and whose calibration verifies; serve the NF1.3 board with honest market-lean labels + keep MVP-1 as the fade baseline
- calibration verify: calib_80 = 0.803 (floor 0.80, tolerance ≥0.78) · product Δρ-vs-ADP (refined − NF1.3): -0.003

