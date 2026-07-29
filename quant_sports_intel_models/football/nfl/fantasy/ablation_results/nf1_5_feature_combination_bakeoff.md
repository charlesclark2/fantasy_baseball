# NF1.5 — CAPSTONE feature-combination bake-off (market-aware refinements + the market-blind ceiling proof)

**Model:** `nfl_fantasy_nf1_5_v1` · **updated:** 2026-07-29T04:24:19.382424+00:00

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

targets [2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] · pool 6736 · 15 trials/cell · bundles: ['base', 'base_xfp', 'base_env', 'base_contract', 'base_opp', 'all_skill', 'kitchen_sink'] · candidates: ['pos_ridge', 'pos_gbm', 'pos_similarity', 'pos_mlp', 'pos_twopart', 'pos_rank'] · oracle sane: True

### QB

| class×bundle                 |   top-tier ρ |
|:-----------------------------|-------------:|
| pos_twopart×base_contract    |       0.4269 |
| pos_twopart×base             |       0.4236 |
| pos_gbm×base_contract        |       0.4189 |
| pos_gbm×kitchen_sink         |       0.4166 |
| pos_twopart×base_xfp         |       0.4123 |
| pos_twopart×base_env         |       0.4087 |
| pos_ridge×base_contract      |       0.4042 |
| pos_ridge×base               |       0.3978 |
| pos_twopart×kitchen_sink     |       0.3971 |
| pos_mlp×base                 |       0.3952 |
| pos_ridge×base_xfp           |       0.3946 |
| pos_gbm×base_xfp             |       0.3892 |
| pos_gbm×base                 |       0.3885 |
| pos_mlp×base_xfp             |       0.3883 |
| pos_rank×base_env            |       0.3865 |
| pos_rank×base                |       0.3842 |
| pos_gbm×base_env             |       0.384  |
| pos_rank×base_contract       |       0.3822 |
| pos_rank×base_xfp            |       0.3819 |
| pos_rank×kitchen_sink        |       0.3812 |
| pos_ridge×kitchen_sink       |       0.3737 |
| pos_ridge×base_env           |       0.3734 |
| pos_similarity×base_contract |       0.3647 |
| pos_mlp×base_contract        |       0.3544 |
| pos_similarity×kitchen_sink  |       0.3542 |
| pos_similarity×base          |       0.354  |
| pos_similarity×base_xfp      |       0.3486 |
| pos_mlp×base_env             |       0.3454 |
| pos_similarity×base_env      |       0.3444 |
| pos_mlp×kitchen_sink         |       0.3137 |

- null (MVP-1) 0.3344 · NF1.1 winner ref 0.3630
- **winner:** `pos_twopart` × `base_contract` ρ 0.4269 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (451 configs): PBO 0.2930 (spread 0.1621) · DSR 0.3563 · p 0.0026 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok)

### RB

| class×bundle                 |   top-tier ρ |
|:-----------------------------|-------------:|
| pos_ridge×base_xfp           |       0.5397 |
| pos_gbm×base_contract        |       0.5381 |
| pos_gbm×kitchen_sink         |       0.5374 |
| pos_ridge×base_contract      |       0.5367 |
| pos_ridge×base               |       0.5345 |
| pos_mlp×base                 |       0.532  |
| pos_twopart×base_contract    |       0.5283 |
| pos_similarity×base          |       0.5236 |
| pos_mlp×base_xfp             |       0.5233 |
| pos_ridge×base_env           |       0.5207 |
| pos_twopart×kitchen_sink     |       0.5205 |
| pos_rank×base                |       0.5191 |
| pos_mlp×base_env             |       0.5154 |
| pos_ridge×base_opp           |       0.5146 |
| pos_twopart×base_opp         |       0.5145 |
| pos_twopart×base_xfp         |       0.5133 |
| pos_twopart×all_skill        |       0.5122 |
| pos_similarity×base_xfp      |       0.5109 |
| pos_twopart×base             |       0.5104 |
| pos_similarity×base_env      |       0.5077 |
| pos_twopart×base_env         |       0.5067 |
| pos_gbm×base                 |       0.5055 |
| pos_rank×base_env            |       0.5046 |
| pos_mlp×base_contract        |       0.5045 |
| pos_rank×base_xfp            |       0.5043 |
| pos_similarity×base_contract |       0.5039 |
| pos_similarity×all_skill     |       0.5035 |
| pos_rank×kitchen_sink        |       0.5023 |
| pos_gbm×base_xfp             |       0.5022 |
| pos_gbm×base_opp             |       0.5018 |
| pos_rank×base_opp            |       0.5014 |
| pos_similarity×base_opp      |       0.5008 |
| pos_rank×base_contract       |       0.5005 |
| pos_rank×all_skill           |       0.5001 |
| pos_gbm×base_env             |       0.4992 |
| pos_gbm×all_skill            |       0.4983 |
| pos_ridge×all_skill          |       0.4982 |
| pos_similarity×kitchen_sink  |       0.4939 |
| pos_ridge×kitchen_sink       |       0.4926 |
| pos_mlp×base_opp             |       0.487  |
| pos_mlp×all_skill            |       0.484  |
| pos_mlp×kitchen_sink         |       0.4806 |

- null (MVP-1) 0.4420 · NF1.1 winner ref 0.5376
- **winner:** `pos_ridge` × `base_xfp` ρ 0.5397 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (631 configs): PBO 0.2852 (spread 0.1619) · DSR 0.5276 · p 0.0007 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok)

### WR

| class×bundle                 |   top-tier ρ |
|:-----------------------------|-------------:|
| pos_mlp×base                 |       0.5803 |
| pos_twopart×base_env         |       0.5781 |
| pos_twopart×all_skill        |       0.5724 |
| pos_twopart×base             |       0.5711 |
| pos_twopart×base_contract    |       0.5703 |
| pos_twopart×base_opp         |       0.5695 |
| pos_twopart×kitchen_sink     |       0.5675 |
| pos_ridge×base               |       0.5675 |
| pos_mlp×base_env             |       0.5637 |
| pos_ridge×base_env           |       0.5627 |
| pos_ridge×base_contract      |       0.561  |
| pos_mlp×base_contract        |       0.5608 |
| pos_mlp×all_skill            |       0.5557 |
| pos_gbm×base_env             |       0.5554 |
| pos_gbm×all_skill            |       0.5535 |
| pos_ridge×all_skill          |       0.5519 |
| pos_ridge×base_opp           |       0.5517 |
| pos_gbm×kitchen_sink         |       0.551  |
| pos_gbm×base                 |       0.5507 |
| pos_gbm×base_contract        |       0.5504 |
| pos_gbm×base_opp             |       0.5492 |
| pos_mlp×base_opp             |       0.5465 |
| pos_ridge×kitchen_sink       |       0.5439 |
| pos_similarity×base          |       0.5421 |
| pos_similarity×base_opp      |       0.5408 |
| pos_rank×base_env            |       0.538  |
| pos_rank×base                |       0.5339 |
| pos_mlp×kitchen_sink         |       0.5325 |
| pos_rank×all_skill           |       0.5313 |
| pos_rank×base_opp            |       0.5308 |
| pos_rank×base_contract       |       0.5303 |
| pos_similarity×all_skill     |       0.5261 |
| pos_similarity×base_contract |       0.5237 |
| pos_rank×kitchen_sink        |       0.5235 |
| pos_similarity×base_env      |       0.5196 |
| pos_similarity×kitchen_sink  |       0.5093 |

- null (MVP-1) 0.4006 · NF1.1 winner ref 0.5656
- **winner:** `pos_mlp` × `base` ρ 0.5803 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (541 configs): PBO 0.2188 (spread 0.1615) · DSR 0.9640 · p 0.0000 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok)

### TE

| class×bundle                 |   top-tier ρ |
|:-----------------------------|-------------:|
| pos_mlp×base_opp             |       0.4878 |
| pos_similarity×kitchen_sink  |       0.4832 |
| pos_rank×kitchen_sink        |       0.4801 |
| pos_similarity×base          |       0.4788 |
| pos_mlp×all_skill            |       0.4748 |
| pos_rank×base_contract       |       0.4697 |
| pos_mlp×base                 |       0.4676 |
| pos_mlp×base_env             |       0.4668 |
| pos_mlp×base_xfp             |       0.4634 |
| pos_mlp×kitchen_sink         |       0.4618 |
| pos_mlp×base_contract        |       0.4584 |
| pos_ridge×base_env           |       0.4578 |
| pos_twopart×base             |       0.4572 |
| pos_twopart×base_env         |       0.456  |
| pos_similarity×all_skill     |       0.4552 |
| pos_similarity×base_opp      |       0.4547 |
| pos_ridge×base_contract      |       0.4545 |
| pos_twopart×base_contract    |       0.4534 |
| pos_twopart×base_xfp         |       0.4533 |
| pos_similarity×base_xfp      |       0.4524 |
| pos_ridge×base               |       0.4514 |
| pos_rank×base_opp            |       0.451  |
| pos_ridge×base_xfp           |       0.4506 |
| pos_rank×all_skill           |       0.4496 |
| pos_rank×base                |       0.4495 |
| pos_similarity×base_contract |       0.4464 |
| pos_rank×base_xfp            |       0.441  |
| pos_gbm×base                 |       0.4378 |
| pos_gbm×kitchen_sink         |       0.4369 |
| pos_gbm×base_contract        |       0.436  |
| pos_similarity×base_env      |       0.4355 |
| pos_gbm×all_skill            |       0.4348 |
| pos_gbm×base_opp             |       0.4336 |
| pos_rank×base_env            |       0.4302 |
| pos_ridge×all_skill          |       0.4298 |
| pos_ridge×base_opp           |       0.424  |
| pos_ridge×kitchen_sink       |       0.4238 |
| pos_gbm×base_xfp             |       0.4233 |
| pos_gbm×base_env             |       0.4224 |
| pos_twopart×base_opp         |       0.4056 |
| pos_twopart×all_skill        |       0.4055 |
| pos_twopart×kitchen_sink     |       0.405  |

- null (MVP-1) 0.4330 · NF1.1 winner ref 0.4514
- **winner:** `pos_mlp` × `base_opp` ρ 0.4878 · beats null: **True** · beats NF1.1 ref: True
- **deflation** (631 configs): PBO 0.5312 (spread 0.1575) · DSR 0.4399 · p 0.0462 · FDR pass True
- **verdict:** NULL — the incumbent stands (pbo_ok, dsr_ok)

**Placebo (labels shuffled — the same sweep must find nothing):**

| pos   |   winner_mean_top |   null_mean_top |   naive_delta_vs_null | gates_pass   |
|:------|------------------:|----------------:|----------------------:|:-------------|
| QB    |            0.0078 |         -0.0085 |                0.0163 | False        |
| RB    |            0.0457 |         -0.0537 |                0.0994 | False        |
| WR    |            0.0698 |         -0.0047 |                0.0745 | False        |
| TE    |            0.0665 |          0.0538 |                0.0127 | False        |

## Serving decision (NF1.5-owned)

- **serve:** `refined-dual-board`
- why: the refined market-aware board beats the NF1.3 incumbent on the product metric with a verified calibrated interval; the market-blind MVP-1 board stays the fade-claim baseline (dual-board)
- calibration verify: calib_80 = 0.804 (floor 0.80, tolerance ≥0.78) · product Δρ-vs-ADP (refined − NF1.3): 0.011

