# NF1.3 — MARKET-AWARE, position-conditional per-position models (ADP/ECR consensus)

**Model:** `nfl_fantasy_nf1_3_v1` · **generated:** 2026-07-27T06:46:00.385189+00:00 · **base seasons:** 2017–2024 · **scored targets:** [2019, 2020, 2021, 2022, 2023, 2024, 2025] · **pool:** 2995 · **Optuna trials/class:** 40

> 🔒 **HONEST FRAME:** this is a PRODUCT variant, NOT a replacement of the market-blind differentiator. At positions that LEAN on the market (high blend `w`) we INCORPORATE consensus — a Δρ→0 vs ADP/ECR there is the DESIGN, **not** an edge, and we ⛔ NEVER claim to beat the market we use. The WR/TE independent view + fade edge is what must be PRESERVED. The market-blind NF1/MVP-1 remains the baseline. `best_alpha = 0`.

> **Selection metric:** top-tier within-position ρ (tier = top-N by the MVP-1 incumbent, N={'QB': 24, 'RB': 36, 'WR': 48, 'TE': 24}) — fixed across candidates, oracle-checked (E2.1-r). Candidates per position: **pos_market_blend** (the tuned position-conditional blend weight) / pos_ridge / pos_gbm / pos_similarity — the three market-blind classes now carry the market axes (`market_rank`, `market_dispersion`). Reference foils: pos_null (MVP-1, market-blind) + pos_market_only (pure consensus). Deflation gates for a repoint: PBO<0.2 · DSR≥0.95 · BH-FDR q=0.1.

- **oracle metric sane:** True
- **market top-tier coverage** (fraction of each draftable tier the consensus ranks): {'QB': 1.0, 'RB': 1.0, 'WR': 0.979, 'TE': 1.0}

## QB

| candidate                   |   top-tier ρ |   full ρ | hp                                                                                                                                      |
|:----------------------------|-------------:|---------:|:----------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1, blind)     |       0.3681 |   0.6485 |                                                                                                                                         |
| pos_market_only (consensus) |       0.5674 |   0.7606 |                                                                                                                                         |
| pos_market_blend ⭐         |       0.5619 |   0.6479 | {"blend_w": 0.9869973994939585}                                                                                                         |
| pos_ridge                   |       0.4949 |   0.7096 | {"alpha": 15.724136378377716}                                                                                                           |
| pos_gbm                     |       0.521  |   0.7424 | {"n_estimators": 200, "num_leaves": 13, "learning_rate": 0.015542496811557178, "min_child_samples": 7, "reg_lambda": 6.469595821576644} |
| pos_similarity              |       0.4876 |   0.7056 | {"k": 47, "weight_power": 2.4592459944950162, "mvp1_emphasis": 0.7165197203965211}                                                      |

- **winner:** `pos_market_blend` · beats MVP-1 null: **True** (Δ top-tier ρ +0.1938) · beats pure-consensus: **False**
- **market lean:** `market-led` (blend w=0.987) · top-tier coverage 1.0
- **deflation** (160 configs): PBO 0.4000 (spread 0.2943) · DSR 0.6781 · p 0.0036 · FDR pass True
- **verdict:** NULL — MVP-1 stands (pbo_ok, dsr_ok)

## RB

| candidate                   |   top-tier ρ |   full ρ | hp                                                                                                                                      |
|:----------------------------|-------------:|---------:|:----------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1, blind)     |       0.5095 |   0.7341 |                                                                                                                                         |
| pos_market_only (consensus) |       0.6495 |   0.7862 |                                                                                                                                         |
| pos_market_blend ⭐         |       0.6646 |   0.7582 | {"blend_w": 0.9583426412697418}                                                                                                         |
| pos_ridge                   |       0.6297 |   0.7665 | {"alpha": 7.462745122470182}                                                                                                            |
| pos_gbm                     |       0.6478 |   0.7906 | {"n_estimators": 150, "num_leaves": 4, "learning_rate": 0.018824019922010146, "min_child_samples": 19, "reg_lambda": 5.865721637697215} |
| pos_similarity              |       0.6102 |   0.7605 | {"k": 36, "weight_power": 1.2295599477563586, "mvp1_emphasis": 1.4585951103504269}                                                      |

- **winner:** `pos_market_blend` · beats MVP-1 null: **True** (Δ top-tier ρ +0.1551) · beats pure-consensus: **True**
- **market lean:** `market-led` (blend w=0.958) · top-tier coverage 1.0
- **deflation** (160 configs): PBO 0.2286 (spread 0.1512) · DSR 0.8374 · p 0.0004 · FDR pass True
- **verdict:** NULL — MVP-1 stands (pbo_ok, dsr_ok)

## WR

| candidate                   |   top-tier ρ |   full ρ | hp                                                                                                                                     |
|:----------------------------|-------------:|---------:|:---------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1, blind)     |       0.4113 |   0.7503 |                                                                                                                                        |
| pos_market_only (consensus) |       0.595  |   0.8015 |                                                                                                                                        |
| pos_market_blend            |       0.5994 |   0.6669 | {"blend_w": 0.926870526807281}                                                                                                         |
| pos_ridge                   |       0.557  |   0.7699 | {"alpha": 35.865998099445854}                                                                                                          |
| pos_gbm ⭐                  |       0.6066 |   0.7929 | {"n_estimators": 300, "num_leaves": 7, "learning_rate": 0.012050541345647812, "min_child_samples": 8, "reg_lambda": 4.368469237108717} |
| pos_similarity              |       0.5817 |   0.7734 | {"k": 69, "weight_power": 2.394820682355927, "mvp1_emphasis": 0.6306536418582478}                                                      |

- **winner:** `pos_gbm` · beats MVP-1 null: **True** (Δ top-tier ρ +0.1953) · beats pure-consensus: **True**
- **market lean:** `market-informed` (blend w=0.927) · top-tier coverage 0.979
- **deflation** (168 configs): PBO 0.3429 (spread 0.1892) · DSR 0.9950 · p 0.0030 · FDR pass True
- **verdict:** NULL — MVP-1 stands (pbo_ok)

**Feature ablation on the winner (drop-one group; negative Δ = the group carries signal):**

| drop   |   mean_top |   delta |
|:-------|-----------:|--------:|
| usage  |     0.6102 |  0.0036 |
| mover  |     0.607  |  0.0004 |
| env    |     0.5957 | -0.0109 |
| injury |     0.6058 | -0.0008 |
| age    |     0.6038 | -0.0028 |
| role   |     0.6001 | -0.0065 |
| xfp    |     0.6026 | -0.004  |
| market |     0.5291 | -0.0775 |

## TE

| candidate                   |   top-tier ρ |   full ρ | hp                                                                                                                                       |
|:----------------------------|-------------:|---------:|:-----------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1, blind)     |       0.4307 |   0.7398 |                                                                                                                                          |
| pos_market_only (consensus) |       0.5042 |   0.7816 |                                                                                                                                          |
| pos_market_blend ⭐         |       0.5243 |   0.6569 | {"blend_w": 0.6000478605455821}                                                                                                          |
| pos_ridge                   |       0.5101 |   0.7275 | {"alpha": 5.781667247840213}                                                                                                             |
| pos_gbm                     |       0.5183 |   0.7592 | {"n_estimators": 100, "num_leaves": 11, "learning_rate": 0.019471061662730833, "min_child_samples": 19, "reg_lambda": 18.34271691239154} |
| pos_similarity              |       0.5186 |   0.7356 | {"k": 19, "weight_power": 2.4590894178607767, "mvp1_emphasis": 2.875034815855183}                                                        |

- **winner:** `pos_market_blend` · beats MVP-1 null: **True** (Δ top-tier ρ +0.0936) · beats pure-consensus: **True**
- **market lean:** `market-blend` (blend w=0.600) · top-tier coverage 1.0
- **deflation** (160 configs): PBO 0.6857 (spread 0.1449) · DSR 0.8103 · p 0.0200 · FDR pass True
- **verdict:** NULL — MVP-1 stands (pbo_ok, dsr_ok)

## Verdict

- positions beating the MVP-1 null on the top-tier metric: **['QB', 'RB', 'WR', 'TE']**
- positions passing the FULL deflation gate (repoint-eligible): **none**
- next: `grade` mode delivers the PRODUCT-metric verdict (NF-D3 vs consensus, apples-to-apples with the stored MVP-1/NF1/NF1.1 scorecards). The honest read: QB/RB accuracy LIFT (where we now incorporate the market — NOT an edge claim) WITHOUT eroding the WR/TE independent fade edge.

