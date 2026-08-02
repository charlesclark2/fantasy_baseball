# NF1.5 — CAPSTONE feature-combination bake-off (market-aware refinements + the market-blind ceiling proof)

**Model:** `nfl_fantasy_nf1_5_v1` · **updated:** 2026-08-02T03:36:18.362292+00:00

> 🔒 **HONEST FRAME:** stage 1's bar is the NF1.3 STORED incumbent per position (the market-aware winner); stage 2's bar is the market-blind MVP-1 null — with the blind space exhausted 4×, a clean stage-2 NULL is the LIKELY + valuable outcome (it PROVES the incumbent is the feature-library ceiling). At market-leaning positions we INCORPORATE consensus and ⛔ never claim to beat the market we use. `best_alpha = 0`.

## Stage 1 — MARKET-AWARE refinements (PRIMARY: blend-vs-learned + dispersion-weighted)

targets [2019, 2020, 2021, 2022, 2023, 2024, 2025] · pool 6736 · 40 trials/class · oracle sane: True · market top-tier coverage {'QB': 1.0, 'RB': 0.944, 'WR': 0.979, 'TE': 1.0}

### QB

| candidate                                              |   top-tier ρ | hp                                                                 |
|:-------------------------------------------------------|-------------:|:-------------------------------------------------------------------|
| pos_null (MVP-1, blind)                                |       0.3681 |                                                                    |
| pos_market_only (consensus)                            |       0.5674 |                                                                    |
| NF1.3 incumbent (nf1_3_incumbent(pos_market_blend)) 🔒 |       0.5624 | {"blend_w": 0.9869973994939585}                                    |
| pos_learned_adaptive_blend                             |       0.5674 | {"blend_w": 0.9221115150810637, "disp_slope": 0.17300114503514258} |
| pos_learned_blend                                      |       0.5631 | {"blend_w": 0.9714449203068924}                                    |
| pos_adaptive_blend                                     |       0.5663 | {"blend_w": 0.8890660930092513, "disp_slope": 0.2317215499000329}  |
| pos_blend_flat                                         |       0.5627 | {"blend_w": 0.8316430355340343}                                    |

- **winner:** `pos_learned_adaptive_blend` · beats NF1.3 incumbent: **True** (Δ +0.0050) · beats blind null: True · beats pure consensus: False
- **deflation** (161 configs): PBO 0.6000 (spread 0.2560) · DSR 0.5837 · p 0.0033 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (pbo_ok, dsr_ok)

### RB

| candidate                                              |   top-tier ρ | hp                                                                 |
|:-------------------------------------------------------|-------------:|:-------------------------------------------------------------------|
| pos_null (MVP-1, blind)                                |       0.5095 |                                                                    |
| pos_market_only (consensus)                            |       0.6495 |                                                                    |
| NF1.3 incumbent (nf1_3_incumbent(pos_market_blend)) 🔒 |       0.656  | {"blend_w": 0.9583426412697418}                                    |
| pos_learned_adaptive_blend                             |       0.6552 | {"blend_w": 0.861976418103483, "disp_slope": 0.010870396913555513} |
| pos_learned_blend                                      |       0.6559 | {"blend_w": 0.8893629074612233}                                    |
| pos_adaptive_blend                                     |       0.6609 | {"blend_w": 0.8498927324601829, "disp_slope": 0.06435395916997594} |
| pos_blend_flat                                         |       0.6642 | {"blend_w": 0.9476636616777102}                                    |

- **winner:** `pos_blend_flat` · beats NF1.3 incumbent: **True** (Δ +0.0082) · beats blind null: True · beats pure consensus: True
- **deflation** (161 configs): PBO 0.4571 (spread 0.1369) · DSR 0.9562 · p 0.0004 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (pbo_ok)

### WR

| candidate                                     |   top-tier ρ | hp                                                                                                                                     |
|:----------------------------------------------|-------------:|:---------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1, blind)                       |       0.4113 |                                                                                                                                        |
| pos_market_only (consensus)                   |       0.595  |                                                                                                                                        |
| NF1.3 incumbent (nf1_3_incumbent(pos_gbm)) 🔒 |       0.5841 | {"n_estimators": 300, "num_leaves": 7, "learning_rate": 0.012050541345647812, "min_child_samples": 8, "reg_lambda": 4.368469237108717} |
| pos_learned_adaptive_blend                    |       0.5876 | {"blend_w": 0.6094478825507955, "disp_slope": 0.1607685732039351}                                                                      |
| pos_learned_blend                             |       0.5924 | {"blend_w": 0.849359320511512}                                                                                                         |
| pos_adaptive_blend                            |       0.5832 | {"blend_w": 0.861976418103483, "disp_slope": 0.010870396913555513}                                                                     |
| pos_blend_flat                                |       0.5866 | {"blend_w": 0.9304028356763766}                                                                                                        |

- **winner:** `pos_learned_blend` · beats NF1.3 incumbent: **True** (Δ +0.0083) · beats blind null: True · beats pure consensus: False
- **deflation** (161 configs): PBO 0.3714 (spread 0.2739) · DSR 0.8251 · p 0.0016 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (pbo_ok, dsr_ok)

### TE

| candidate                                              |   top-tier ρ | hp                                                                 |
|:-------------------------------------------------------|-------------:|:-------------------------------------------------------------------|
| pos_null (MVP-1, blind)                                |       0.4307 |                                                                    |
| pos_market_only (consensus)                            |       0.5042 |                                                                    |
| NF1.3 incumbent (nf1_3_incumbent(pos_market_blend)) 🔒 |       0.5162 | {"blend_w": 0.6000478605455821}                                    |
| pos_learned_adaptive_blend                             |       0.5304 | {"blend_w": 0.7218695434988335, "disp_slope": 0.24945178898125647} |
| pos_learned_blend                                      |       0.5305 | {"blend_w": 0.6472753095623965}                                    |
| pos_adaptive_blend                                     |       0.5175 | {"blend_w": 0.9941514189905954, "disp_slope": 0.2690393332470698}  |
| pos_blend_flat                                         |       0.5248 | {"blend_w": 0.6032143192246215}                                    |

- **winner:** `pos_learned_blend` · beats NF1.3 incumbent: **True** (Δ +0.0143) · beats blind null: True · beats pure consensus: True
- **deflation** (161 configs): PBO 0.8000 (spread 0.2243) · DSR 0.1588 · p 0.0434 · FDR pass True
- **verdict (vs the NF1.3 incumbent + full gates):** NULL — the NF1.3 incumbent stands (pbo_ok, dsr_ok)

**Placebo (labels shuffled within position×season — the same search must find nothing):**

| pos   |   winner_mean_top |   null_mean_top |   naive_delta_vs_null | gates_pass   |
|:------|------------------:|----------------:|----------------------:|:-------------|
| QB    |            0.0681 |          0.0098 |                0.0583 | False        |
| RB    |            0.0256 |         -0.0124 |                0.038  | False        |
| WR    |            0.1061 |         -0.0823 |                0.1884 | False        |
| TE    |            0.1782 |          0.1096 |                0.0686 | False        |

## Stage 2 — MARKET-BLIND combination sweep (ceiling proof; expected null)

targets [2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] · pool 6958 · 15 trials/cell · bundles: ['base', 'base_xfp', 'base_env', 'base_contract', 'base_opp', 'base_system_coach', 'env_coach', 'all_skill', 'kitchen_sink'] · candidates: ['pos_ridge', 'pos_gbm', 'pos_similarity', 'pos_mlp', 'pos_twopart', 'pos_rank'] · oracle sane: True

### QB

| class×bundle                     |   top-tier ρ |
|:---------------------------------|-------------:|
| pos_gbm×base_contract            |       0.4503 |
| pos_twopart×base_contract        |       0.4475 |
| pos_gbm×kitchen_sink             |       0.4408 |
| pos_twopart×base                 |       0.4284 |
| pos_twopart×base_xfp             |       0.4218 |
| pos_ridge×base_contract          |       0.4183 |
| pos_gbm×base                     |       0.4176 |
| pos_gbm×base_xfp                 |       0.4159 |
| pos_gbm×base_system_coach        |       0.4151 |
| pos_gbm×env_coach                |       0.4132 |
| pos_rank×base                    |       0.4124 |
| pos_mlp×base                     |       0.4112 |
| pos_twopart×kitchen_sink         |       0.4104 |
| pos_gbm×base_env                 |       0.4095 |
| pos_rank×base_contract           |       0.4094 |
| pos_ridge×base                   |       0.4093 |
| pos_rank×env_coach               |       0.4067 |
| pos_mlp×base_xfp                 |       0.4055 |
| pos_ridge×base_xfp               |       0.4048 |
| pos_rank×kitchen_sink            |       0.4044 |
| pos_twopart×base_env             |       0.4035 |
| pos_rank×base_env                |       0.4027 |
| pos_twopart×env_coach            |       0.3984 |
| pos_rank×base_xfp                |       0.3964 |
| pos_rank×base_system_coach       |       0.395  |
| pos_twopart×base_system_coach    |       0.3947 |
| pos_ridge×base_env               |       0.3932 |
| pos_mlp×base_contract            |       0.38   |
| pos_ridge×base_system_coach      |       0.3707 |
| pos_similarity×base_contract     |       0.3686 |
| pos_mlp×base_env                 |       0.3655 |
| pos_ridge×kitchen_sink           |       0.3642 |
| pos_ridge×env_coach              |       0.3631 |
| pos_similarity×env_coach         |       0.3604 |
| pos_similarity×base_system_coach |       0.3604 |
| pos_similarity×base              |       0.3588 |
| pos_mlp×base_system_coach        |       0.3576 |
| pos_similarity×base_xfp          |       0.3566 |
| pos_similarity×kitchen_sink      |       0.3466 |
| pos_similarity×base_env          |       0.3388 |
| pos_mlp×kitchen_sink             |       0.3187 |
| pos_mlp×env_coach                |       0.312  |

- null (MVP-1) 0.3481 · NF1.1 winner ref 0.3286
- **winner:** `pos_gbm` × `base_contract` ρ 0.4503 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (631 configs): PBO 0.1836 (spread 0.2545) · DSR 0.2188 · p 0.0018 · FDR pass True
- **verdict:** NULL — the incumbent stands (dsr_ok)

### RB

| class×bundle                     |   top-tier ρ |
|:---------------------------------|-------------:|
| pos_gbm×base_contract            |       0.5456 |
| pos_ridge×base_contract          |       0.5446 |
| pos_ridge×base_xfp               |       0.5425 |
| pos_gbm×kitchen_sink             |       0.5398 |
| pos_ridge×base_system_coach      |       0.5359 |
| pos_ridge×base                   |       0.5358 |
| pos_mlp×base                     |       0.5339 |
| pos_similarity×base              |       0.5255 |
| pos_ridge×base_env               |       0.5253 |
| pos_twopart×base_contract        |       0.5246 |
| pos_twopart×kitchen_sink         |       0.5236 |
| pos_ridge×env_coach              |       0.5219 |
| pos_twopart×base_opp             |       0.5206 |
| pos_rank×base                    |       0.52   |
| pos_mlp×base_xfp                 |       0.5196 |
| pos_rank×base_xfp                |       0.5174 |
| pos_twopart×all_skill            |       0.5169 |
| pos_similarity×base_xfp          |       0.516  |
| pos_twopart×base_xfp             |       0.5159 |
| pos_ridge×base_opp               |       0.5157 |
| pos_twopart×base_system_coach    |       0.515  |
| pos_rank×base_contract           |       0.5148 |
| pos_twopart×base                 |       0.5134 |
| pos_mlp×base_system_coach        |       0.5114 |
| pos_rank×base_system_coach       |       0.5105 |
| pos_twopart×base_env             |       0.5104 |
| pos_mlp×base_contract            |       0.5096 |
| pos_rank×base_opp                |       0.5088 |
| pos_similarity×base_contract     |       0.5086 |
| pos_mlp×env_coach                |       0.5084 |
| pos_similarity×base_env          |       0.5081 |
| pos_gbm×base_system_coach        |       0.5079 |
| pos_gbm×base_opp                 |       0.5078 |
| pos_twopart×env_coach            |       0.5076 |
| pos_rank×kitchen_sink            |       0.5074 |
| pos_mlp×base_env                 |       0.5072 |
| pos_rank×env_coach               |       0.5065 |
| pos_gbm×base_xfp                 |       0.5064 |
| pos_rank×base_env                |       0.5062 |
| pos_similarity×base_opp          |       0.5058 |
| pos_similarity×all_skill         |       0.5054 |
| pos_gbm×base                     |       0.5053 |
| pos_rank×all_skill               |       0.505  |
| pos_gbm×all_skill                |       0.5041 |
| pos_gbm×base_env                 |       0.5039 |
| pos_similarity×base_system_coach |       0.5033 |
| pos_gbm×env_coach                |       0.4996 |
| pos_similarity×env_coach         |       0.4987 |
| pos_mlp×base_opp                 |       0.4986 |
| pos_ridge×all_skill              |       0.4972 |
| pos_ridge×kitchen_sink           |       0.4953 |
| pos_similarity×kitchen_sink      |       0.4927 |
| pos_mlp×all_skill                |       0.486  |
| pos_mlp×kitchen_sink             |       0.4699 |

- null (MVP-1) 0.4466 · NF1.1 winner ref 0.5414
- **winner:** `pos_gbm` × `base_contract` ρ 0.5456 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (811 configs): PBO 0.1992 (spread 0.1430) · DSR 0.8879 · p 0.0001 · FDR pass True
- **verdict:** NULL — the incumbent stands (dsr_ok)

### WR

| class×bundle                     |   top-tier ρ |
|:---------------------------------|-------------:|
| pos_twopart×base                 |       0.5848 |
| pos_twopart×all_skill            |       0.5845 |
| pos_twopart×base_env             |       0.5836 |
| pos_mlp×base                     |       0.583  |
| pos_twopart×base_contract        |       0.5806 |
| pos_twopart×env_coach            |       0.5802 |
| pos_mlp×base_env                 |       0.5799 |
| pos_twopart×base_opp             |       0.5795 |
| pos_twopart×base_system_coach    |       0.5786 |
| pos_ridge×base                   |       0.578  |
| pos_twopart×kitchen_sink         |       0.5775 |
| pos_ridge×base_env               |       0.5745 |
| pos_ridge×base_contract          |       0.5678 |
| pos_gbm×base_env                 |       0.5659 |
| pos_gbm×base                     |       0.5654 |
| pos_mlp×base_system_coach        |       0.5651 |
| pos_mlp×base_contract            |       0.5628 |
| pos_ridge×all_skill              |       0.5627 |
| pos_mlp×env_coach                |       0.5626 |
| pos_ridge×base_opp               |       0.5622 |
| pos_gbm×all_skill                |       0.5618 |
| pos_gbm×base_opp                 |       0.5605 |
| pos_mlp×base_opp                 |       0.5604 |
| pos_gbm×base_contract            |       0.5595 |
| pos_gbm×kitchen_sink             |       0.5589 |
| pos_gbm×base_system_coach        |       0.558  |
| pos_gbm×env_coach                |       0.5577 |
| pos_ridge×base_system_coach      |       0.5538 |
| pos_ridge×env_coach              |       0.5537 |
| pos_similarity×base              |       0.5529 |
| pos_mlp×all_skill                |       0.5502 |
| pos_similarity×base_opp          |       0.5462 |
| pos_rank×base                    |       0.5449 |
| pos_rank×base_env                |       0.5444 |
| pos_rank×env_coach               |       0.5432 |
| pos_mlp×kitchen_sink             |       0.5423 |
| pos_rank×base_opp                |       0.5413 |
| pos_rank×base_system_coach       |       0.5412 |
| pos_rank×all_skill               |       0.5405 |
| pos_ridge×kitchen_sink           |       0.5398 |
| pos_rank×kitchen_sink            |       0.5371 |
| pos_similarity×base_env          |       0.5368 |
| pos_rank×base_contract           |       0.536  |
| pos_similarity×all_skill         |       0.5309 |
| pos_similarity×base_contract     |       0.5296 |
| pos_similarity×base_system_coach |       0.5183 |
| pos_similarity×env_coach         |       0.4994 |
| pos_similarity×kitchen_sink      |       0.4979 |

- null (MVP-1) 0.4146 · NF1.1 winner ref 0.5746
- **winner:** `pos_twopart` × `base` ρ 0.5848 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (721 configs): PBO 0.1914 (spread 0.1564) · DSR 0.8744 · p 0.0001 · FDR pass True
- **verdict:** NULL — the incumbent stands (dsr_ok)

### TE

| class×bundle                     |   top-tier ρ |
|:---------------------------------|-------------:|
| pos_similarity×base              |       0.4767 |
| pos_mlp×base                     |       0.471  |
| pos_rank×kitchen_sink            |       0.4708 |
| pos_mlp×base_xfp                 |       0.4703 |
| pos_twopart×base_contract        |       0.4657 |
| pos_twopart×base                 |       0.4657 |
| pos_mlp×base_opp                 |       0.4647 |
| pos_rank×base_contract           |       0.4641 |
| pos_mlp×all_skill                |       0.464  |
| pos_mlp×base_contract            |       0.4618 |
| pos_mlp×base_env                 |       0.4617 |
| pos_similarity×base_xfp          |       0.4592 |
| pos_twopart×base_system_coach    |       0.4583 |
| pos_twopart×base_env             |       0.4578 |
| pos_similarity×kitchen_sink      |       0.4553 |
| pos_similarity×base_env          |       0.4547 |
| pos_twopart×base_xfp             |       0.4541 |
| pos_ridge×base_env               |       0.4526 |
| pos_similarity×all_skill         |       0.4503 |
| pos_rank×all_skill               |       0.4501 |
| pos_similarity×base_opp          |       0.4498 |
| pos_ridge×base                   |       0.4497 |
| pos_rank×base_env                |       0.4496 |
| pos_ridge×base_contract          |       0.4488 |
| pos_twopart×env_coach            |       0.4486 |
| pos_ridge×base_xfp               |       0.4483 |
| pos_rank×base                    |       0.4468 |
| pos_rank×base_opp                |       0.4442 |
| pos_gbm×base                     |       0.4434 |
| pos_similarity×base_contract     |       0.4391 |
| pos_gbm×base_opp                 |       0.4382 |
| pos_mlp×base_system_coach        |       0.4364 |
| pos_rank×base_xfp                |       0.4359 |
| pos_rank×base_system_coach       |       0.4348 |
| pos_gbm×base_contract            |       0.434  |
| pos_rank×env_coach               |       0.434  |
| pos_ridge×env_coach              |       0.4332 |
| pos_mlp×kitchen_sink             |       0.4328 |
| pos_gbm×kitchen_sink             |       0.432  |
| pos_gbm×all_skill                |       0.4313 |
| pos_similarity×base_system_coach |       0.43   |
| pos_gbm×base_system_coach        |       0.43   |
| pos_mlp×env_coach                |       0.4283 |
| pos_ridge×base_system_coach      |       0.4278 |
| pos_gbm×base_xfp                 |       0.4269 |
| pos_ridge×all_skill              |       0.4263 |
| pos_ridge×base_opp               |       0.4209 |
| pos_similarity×env_coach         |       0.4208 |
| pos_gbm×base_env                 |       0.4202 |
| pos_gbm×env_coach                |       0.4188 |
| pos_twopart×all_skill            |       0.4105 |
| pos_twopart×kitchen_sink         |       0.4081 |
| pos_twopart×base_opp             |       0.4046 |
| pos_ridge×kitchen_sink           |       0.3978 |

- null (MVP-1) 0.4166 · NF1.1 winner ref 0.4540
- **winner:** `pos_similarity` × `base` ρ 0.4767 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (811 configs): PBO 0.6523 (spread 0.1643) · DSR 0.4634 · p 0.0221 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok)

**Placebo (labels shuffled — the same sweep must find nothing):**

| pos   |   winner_mean_top |   null_mean_top |   naive_delta_vs_null | gates_pass   |
|:------|------------------:|----------------:|----------------------:|:-------------|
| QB    |            0.0925 |         -0.0175 |                0.11   | False        |
| RB    |            0.1427 |          0.0664 |                0.0763 | False        |
| WR    |            0.0715 |          0.0128 |                0.0587 | False        |
| TE    |            0.1006 |          0.0632 |                0.0374 | False        |

## Serving decision (NF1.5-owned)

- **serve:** `refined-dual-board`
- why: the refined market-aware board beats the NF1.3 incumbent on the product metric with a verified calibrated interval; the market-blind MVP-1 board stays the fade-claim baseline (dual-board)
- calibration verify: calib_80 = 0.847 (floor 0.80, tolerance ≥0.78) · product Δρ-vs-ADP (refined − NF1.3): 0.007

