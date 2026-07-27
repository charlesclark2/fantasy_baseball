# NF1.4 — rookie-prior refinement (the hot-curve fix)

**Model:** `nfl_fantasy_nf1_4_rookie_v1` · **cohorts scored:** [2019, 2020, 2021, 2022, 2023, 2024, 2025] · **configs evaluated:** 134 · **generated:** 2026-07-27T08:57:56.721028+00:00

> ⚖️ **Honest frame.** This is a PROJECTION-product story, not a betting edge — `best_alpha` does not apply. The win condition is rookie CALIBRATION (kill the level over-valuation), and the ordering claim is held to the full §0.5 deflation (CSCV-PBO / DSR / BH-FDR). The rookie sample is TINY (QB ≈ 12/class over a handful of cohorts) ⇒ the deflation is NOISY and "cannot distinguish from luck" is the expected ordering verdict, recorded as a null.

## 0. Verdict in one paragraph

**MODEL: NULL — the incumbent slot curve STANDS.** 134 pre-registered configs × 4 positions, walk-forward over 7 draft classes: no form beat the incumbent's draftable-tier accuracy and survived the deflation at ANY position, so the rookie POINT projection is unchanged. **The story's hot-curve premise is REFUTED as a level claim** — the incumbent rookie prior is *cold*, not hot, on the draftable tier at every position (`tier_bias` −32 to −58 PPR), and its projection for the #1-overall rookie QB is nearly unbiased over 2019–2025 (**+8.9** PPR against a realized mean of ~201). The dogfooding symptom is real but is a RANK effect, not a level one (§2). **ONE fix ships**: the rookie 80% interval, which claimed 80% and delivered **0.6799** (**0.444** at QB), recalibrated to **0.7902** with the point projection byte-identical (§6).

## 1. The measured defect — survivorship, tested and NOT the cure

MVP-1's `load_rookie_training` fits the slot curve under `where games > 0`, so every drafted rookie who never played is dropped from the fit. The positional mean, the P93 ceiling and the games-by-slot prior are therefore all estimated on SURVIVORS:

| position_group   |   n |   pct_zero_game |   mean_fp_all_drafted |   mean_fp_survivors_only |   inflation_pct |
|:-----------------|----:|----------------:|----------------------:|-------------------------:|----------------:|
| QB               | 119 |            35.3 |                  67.2 |                    103.8 |            54.5 |
| RB               | 221 |            11.8 |                  67.8 |                     76.8 |            13.3 |
| TE               | 138 |            13   |                  43.9 |                     50.5 |            15   |
| WR               | 320 |            10.9 |                  60.8 |                     68.3 |            12.3 |

That is a real and large bias at QB. **But removing the filter does not fix the board.** This arm re-fits the incumbent's EXACT functional form (same power law, same 0.15 shrink, same P93 clip, same P1A nudge — zero new degrees of freedom, so no deflation gate applies) on the full drafted population, and scores it on the same held-out classes:

| position   |   incumbent_tier_mae |   survivorship_fixed_tier_mae |
|:-----------|---------------------:|------------------------------:|
| QB         |                74.75 |                         77.13 |
| RB         |                80.43 |                         88.15 |
| WR         |                68.84 |                         70.19 |
| TE         |                53.92 |                         54.96 |

```json
{
  "survivorship_fixed": {
    "mean_tier_mae": 1.0562,
    "mean_tier_bias": -0.804,
    "mean_mae": 43.1584,
    "mean_bias": -28.3596,
    "mean_rho": 0.6143
  },
  "incumbent": {
    "mean_tier_mae": 1.0156,
    "mean_tier_bias": -0.704,
    "mean_mae": 43.2439,
    "mean_bias": -19.3399,
    "mean_rho": 0.6132
  }
}
```

Held-out tier accuracy gets WORSE at every position and the universe bias gets MORE negative — because the board was already too cold, so lowering the level further is a net loss. The survivorship filter is a genuine flaw in how the curve is estimated; it is not the flaw that produces the flagged board.

## 2. What the symptom actually is — a RANK effect, not a hot level

⚠️ **The story's premise needed sharpening, and the measurement says so.** Over ALL drafted rookies the incumbent is not hot, it is **COLD** — it under-projects almost every rookie (pooled `mean_bias` = `-19.3399` PPR) — and it stays cold on the DRAFTABLE tier at every position, QB included (§3, `incumbent_tier_bias` −32 to −58). The point projection for the very player the dogfooding flagged, the #1-overall rookie QB, is close to unbiased over seven classes.

So where does "a rookie QB floated to #1 overall" come from? From the **RANK**, not the level. On the emitted 2019–2025 boards the #1-overall QB is projected QB11–QB15 and finishes QB8–QB25 (mean ≈ QB19.5) — an over-placement of roughly six QB slots. Two things make a near-unbiased point projection land six slots high: rookie QB outcomes are enormously dispersed (Kyler Murray beat his projection by 85 PPR; Trevor Lawrence missed his by 62), and veteran QB projections are densely packed near that same level, so a few points of projection buys many ranks. **A rank error produced by variance around an unbiased point estimate is not fixed by shifting the level** — it is an UNCERTAINTY problem, which is exactly what §6 fixes.

The selection metric is nonetheless run **per position** on that position's DRAFTABLE-tier MAE (top QB 3, RB 6, WR 8, TE 3, the tier anchored on the incumbent so it is identical for every candidate): a pooled metric would average the positions together and could not answer "is the rookie prior better at QB?" at all. That is also NF1.1's own conclusion for this product.

### ⭐ The flagged symptom — the top-drafted rookie QB, per class

|   draft_class | player          |   draft_overall |   incumbent_fp |   selected_fp |   realized_fp |
|--------------:|:----------------|----------------:|---------------:|--------------:|--------------:|
|          2019 | Kyler Murray    |               1 |          200.1 |         200.1 |         285.3 |
|          2020 | Joe Burrow      |               1 |          236.5 |         236.5 |         173.7 |
|          2021 | Trevor Lawrence |               1 |          261   |         261   |         199   |
|          2022 | Kenny Pickett   |              20 |           50.1 |          50.1 |         149.9 |
|          2023 | Bryce Young     |               1 |          232.4 |         232.4 |         156.4 |
|          2024 | Caleb Williams  |               1 |          229.9 |         229.9 |         254.5 |
|          2025 | Cam Ward        |               1 |          258.1 |         258.1 |         186.7 |

Incumbent mean error on this one player: **+8.9** PPR against a realized mean of 200.8; the shipped NF1.4 composite: **+8.9**.

## 3. Per-position selection + deflation (every evaluated config counts)

| position   |   incumbent_tier_mae |   incumbent_tier_bias | winner                                           |   winner_tier_mae |   winner_tier_bias |    pbo |   spread |      dsr |        p | fdr   | REPOINT   |
|:-----------|---------------------:|----------------------:|:-------------------------------------------------|------------------:|-------------------:|-------:|---------:|---------:|---------:|:------|:----------|
| QB         |              74.7543 |              -32.4086 |                                                  |          nan      |           nan      | 0.1143 |  86.4314 | nan      | nan      | False | False     |
| RB         |              80.43   |              -57.6857 | slot_ridge[slot+athletic]{alpha=1.0|shrink=0.0}  |           71.7929 |           -46.6914 | 0.3429 |  39.1714 |   0.2262 |   0.0765 | False | False     |
| WR         |              68.8357 |              -48.8129 | slot_ridge[slot+breakout]{alpha=10.0|shrink=0.0} |           68.67   |           -37.5557 | 0.1714 |  46.6114 |   0.0123 |   0.4836 | False | False     |
| TE         |              53.9186 |              -44.45   | slot_ridge[slot+p1a]{alpha=3.0|shrink=0.0}       |           52.4957 |           -44.9143 | 0.0857 |  37.93   |   0.0174 |   0.2289 | False | False     |

`tier_mae` is in **fantasy points of error on the rookies you would actually draft** at that position. `tier_bias` = mean(projected − realized) on that tier: **positive = the hot curve**, negative = too cold. A position REPOINTS only when its winner beats the incumbent, does no ordering harm, and clears PBO < 0.2 / DSR ≥ 0.0 / BH-FDR at q=0.1.

**Positions repointed:** `[]` — every other position keeps the incumbent slot curve untouched.

> 📖 **RB: PBO 0.3429 against a config spread of 39.1714** — per §0.5 a high PBO over a TIGHT spread is the NULL (the candidates genuinely tie, so "which one wins" is noise); a high PBO over a WIDE spread is overfitting. The spread is the discriminator, not the PBO alone.

Oracle-floor guard (E2.1-r): **True** — the realized-outcome oracle scores 0 on the selection metric and nothing beat it, so the metric is not inverted.

### Per-cohort tier MAE (incumbent → selected composite)

|   draft_class |   QB_inc |   RB_inc |   WR_inc |   TE_inc |
|--------------:|---------:|---------:|---------:|---------:|
|          2019 |    76.15 |    89.43 |    74.81 |    19.53 |
|          2020 |   112.02 |    84.15 |    85.72 |    23.66 |
|          2021 |    59.85 |   102.66 |    50.5  |    69.68 |
|          2022 |    45.88 |    72.32 |    43.7  |    44.12 |
|          2023 |    57.45 |    61    |    99.72 |    84.41 |
|          2024 |    76.64 |    72.28 |    68.95 |    75.04 |
|          2025 |    95.29 |    81.17 |    58.45 |    60.99 |

## 4. Block ablation (drop-one on each repointed position's winner)

_not run — no position cleared the gate, so there is no selected form to ablate. The pre-registered blocks were still all evaluated: see the candidate table below._

## 5. Full candidate table

Pooled across positions (the per-position selection tables are in §3); shown for the search record — every one of these configs counted toward the deflation.

| key                                                                          | learner    |   mean_tier_mae |   mean_tier_bias |   mean_mae |   mean_rmse |   mean_bias |   mean_slope |   mean_rho |
|:-----------------------------------------------------------------------------|:-----------|----------------:|-----------------:|-----------:|------------:|------------:|-------------:|-----------:|
| slot_ridge[slot+breakout]{alpha=10.0|shrink=0.0}                             | slot_ridge |          1.0105 |          -0.7492 |    41.5446 |     65.6151 |    -28.741  |       1.1229 |     0.5711 |
| slot_ridge[slot+breakout]{alpha=3.0|shrink=0.0}                              | slot_ridge |          1.0155 |          -0.6904 |    41.6016 |     65.7013 |    -27.4686 |       1.0591 |     0.5728 |
| slot_ridge[slot+p1a]{alpha=1.0|shrink=0.0}                                   | slot_ridge |          1.0293 |          -0.7308 |    41.5067 |     65.28   |    -28.0809 |       1.0721 |     0.5922 |
| slot_ridge[slot+p1a]{alpha=3.0|shrink=0.0}                                   | slot_ridge |          1.0323 |          -0.756  |    41.5839 |     65.1571 |    -28.634  |       1.122  |     0.5949 |
| slot_ridge[slot+breakout]{alpha=1.0|shrink=0.0}                              | slot_ridge |          1.037  |          -0.6534 |    41.916  |     65.9564 |    -26.7267 |       1.0116 |     0.5745 |
| slot_ridge[slot]{alpha=3.0|shrink=0.0}                                       | slot_ridge |          1.0392 |          -0.7733 |    41.6653 |     65.3201 |    -28.7341 |       1.1283 |     0.5865 |
| slot_ridge[slot]{alpha=1.0|shrink=0.0}                                       | slot_ridge |          1.0395 |          -0.7482 |    41.6233 |     65.4437 |    -28.1836 |       1.0789 |     0.5862 |
| slot_ridge[slot+recruit]{alpha=1.0|shrink=0.0}                               | slot_ridge |          1.042  |          -0.7322 |    41.8634 |     65.4263 |    -27.628  |       1.041  |     0.5919 |
| slot_ridge[slot+breakout]{alpha=3.0|shrink=0.15}                             | slot_ridge |          1.0424 |          -0.7688 |    42.202  |     64.552  |    -24.3276 |       1.242  |     0.5728 |
| slot_ridge[slot+breakout]{alpha=10.0|shrink=0.15}                            | slot_ridge |          1.0429 |          -0.8188 |    42.1797 |     64.6193 |    -25.4094 |       1.3169 |     0.5711 |
| slot_ridge[slot+p1a]{alpha=10.0|shrink=0.0}                                  | slot_ridge |          1.043  |          -0.7927 |    41.7849 |     65.1729 |    -29.4921 |       1.1803 |     0.5869 |
| slot_ridge[slot]{alpha=10.0|shrink=0.0}                                      | slot_ridge |          1.049  |          -0.809  |    41.8207 |     65.3059 |    -29.5836 |       1.1866 |     0.5849 |
| slot_ridge[slot+breakout]{alpha=1.0|shrink=0.15}                             | slot_ridge |          1.0499 |          -0.7374 |    42.3144 |     64.6533 |    -23.6973 |       1.1863 |     0.5745 |
| slot_ridge[slot+recruit]{alpha=3.0|shrink=0.0}                               | slot_ridge |          1.0538 |          -0.7593 |    42.0246 |     65.267  |    -28.2393 |       1.0909 |     0.5935 |
| slot_ridge[slot+p1a]{alpha=1.0|shrink=0.15}                                  | slot_ridge |          1.0582 |          -0.8031 |    42.1519 |     64.3426 |    -24.8484 |       1.2557 |     0.5922 |
| slot_ridge[slot+p1a]{alpha=3.0|shrink=0.15}                                  | slot_ridge |          1.062  |          -0.8246 |    42.2494 |     64.3287 |    -25.3181 |       1.3143 |     0.5949 |
| slot_ridge[slot+recruit]{alpha=10.0|shrink=0.0}                              | slot_ridge |          1.0641 |          -0.7993 |    42.1733 |     65.2443 |    -29.2123 |       1.1547 |     0.5914 |
| slot_ridge[slot]{alpha=1.0|shrink=0.15}                                      | slot_ridge |          1.0692 |          -0.8179 |    42.2943 |     64.5249 |    -24.9356 |       1.2643 |     0.5862 |
| slot_ridge[slot+p1a]{alpha=10.0|shrink=0.15}                                 | slot_ridge |          1.073  |          -0.8557 |    42.4303 |     64.4371 |    -26.0479 |       1.3827 |     0.5869 |
| slot_ridge[slot]{alpha=3.0|shrink=0.15}                                      | slot_ridge |          1.0739 |          -0.8393 |    42.3926 |     64.5087 |    -25.4033 |       1.3217 |     0.5865 |
| slot_ridge[slot+recruit]{alpha=1.0|shrink=0.15}                              | slot_ridge |          1.0741 |          -0.8043 |    42.59   |     64.455  |    -24.4631 |       1.2199 |     0.5919 |
| slot_ridge[slot+breakout]{alpha=1.0|shrink=0.3}                              | slot_ridge |          1.0802 |          -0.8213 |    43.6477 |     64.3131 |    -20.6679 |       1.4226 |     0.5745 |
| slot_ridge[slot+breakout]{alpha=3.0|shrink=0.3}                              | slot_ridge |          1.0804 |          -0.8472 |    43.662  |     64.3299 |    -21.187  |       1.4889 |     0.5728 |
| slot_ridge[slot]{alpha=10.0|shrink=0.15}                                     | slot_ridge |          1.0826 |          -0.8696 |    42.5684 |     64.5924 |    -26.1254 |       1.3903 |     0.5849 |
| slot_ridge[slot+recruit]{alpha=3.0|shrink=0.15}                              | slot_ridge |          1.0831 |          -0.8274 |    42.6976 |     64.419  |    -24.9826 |       1.278  |     0.5935 |
| slot_ridge[slot+breakout]{alpha=10.0|shrink=0.3}                             | slot_ridge |          1.0897 |          -0.8884 |    43.7884 |     64.5064 |    -22.0777 |       1.5787 |     0.5711 |
| slot_ridge[slot+recruit]{alpha=10.0|shrink=0.15}                             | slot_ridge |          1.091  |          -0.8613 |    42.81   |     64.51   |    -25.8099 |       1.3529 |     0.5914 |
| slot_ridge[slot+p1a]{alpha=1.0|shrink=0.3}                                   | slot_ridge |          1.0993 |          -0.8755 |    43.7116 |     64.2879 |    -21.6157 |       1.5059 |     0.5922 |
| slot_ridge[slot+athletic]{alpha=1.0|shrink=0.0}                              | slot_ridge |          1.0993 |          -0.7956 |    42.1069 |     66.2309 |    -28.5779 |       1.0561 |     0.5738 |
| slot_ridge[slot+p1a]{alpha=3.0|shrink=0.3}                                   | slot_ridge |          1.1038 |          -0.8931 |    43.8133 |     64.3539 |    -22.0027 |       1.5749 |     0.5949 |
| slot_gbm[slot]{learning_rate=0.06|shrink=0.0}                                | slot_gbm   |          1.1051 |          -0.8774 |    42.1819 |     65.4344 |    -29.5799 |       1.224  |     0.5883 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=3.0|shrink=0.0}         | slot_ridge |          1.1086 |          -0.7446 |    42.8517 |     67.0799 |    -27.9306 |       0.965  |     0.5755 |
| slot_ridge[slot]{alpha=1.0|shrink=0.3}                                       | slot_ridge |          1.1092 |          -0.8877 |    43.8367 |     64.4731 |    -21.6876 |       1.5161 |     0.5862 |
| slot_ridge[slot+athletic]{alpha=3.0|shrink=0.0}                              | slot_ridge |          1.1094 |          -0.8207 |    42.2464 |     66.1847 |    -29.1693 |       1.103  |     0.5732 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=1.0|shrink=0.0}         | slot_ridge |          1.1108 |          -0.7089 |    42.9293 |     67.4513 |    -27.0851 |       0.9134 |     0.5719 |
| slot_ridge[slot+recruit]{alpha=1.0|shrink=0.3}                               | slot_ridge |          1.1135 |          -0.8765 |    44.0979 |     64.3706 |    -21.2984 |       1.4633 |     0.5919 |
| slot_eb[slot]{eb_k=6.0|shrink=0.0}                                           | slot_eb    |          1.114  |          -0.8012 |    45.8266 |     63.3709 |    -10.536  |       1.2837 |     0.5354 |
| slot_ridge[slot+p1a]{alpha=10.0|shrink=0.3}                                  | slot_ridge |          1.1142 |          -0.9188 |    44.0044 |     64.524  |    -22.6034 |       1.657  |     0.5869 |
| slot_ridge[slot]{alpha=3.0|shrink=0.3}                                       | slot_ridge |          1.1145 |          -0.9053 |    43.9439 |     64.536  |    -22.073  |       1.584  |     0.5865 |
| slot_gbm[slot]{learning_rate=0.03|shrink=0.0}                                | slot_gbm   |          1.1165 |          -0.9072 |    42.5086 |     65.8437 |    -30.5723 |       1.3073 |     0.5848 |
| slot_ridge[slot+recruit]{alpha=3.0|shrink=0.3}                               | slot_ridge |          1.1172 |          -0.8954 |    44.1623 |     64.4261 |    -21.7263 |       1.532  |     0.5935 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=1.0|shrink=0.15}        | slot_ridge |          1.1175 |          -0.7845 |    43.1903 |     65.9294 |    -24.0039 |       1.0707 |     0.5708 |
| slot_ridge[slot+athletic]{alpha=1.0|shrink=0.15}                             | slot_ridge |          1.1177 |          -0.8582 |    42.5423 |     65.2813 |    -25.2713 |       1.2363 |     0.5739 |
| slot_gbm[slot+recruit]{learning_rate=0.06|shrink=0.0}                        | slot_gbm   |          1.1206 |          -0.8404 |    42.3169 |     65.4421 |    -28.2826 |       1.1231 |     0.5853 |
| slot_gbm[slot+recruit]{learning_rate=0.03|shrink=0.0}                        | slot_gbm   |          1.1217 |          -0.8885 |    42.4243 |     65.4574 |    -29.7439 |       1.2771 |     0.5853 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=10.0|shrink=0.0}        | slot_ridge |          1.1233 |          -0.8053 |    43.0124 |     66.7937 |    -29.4234 |       1.0484 |     0.5834 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=3.0|shrink=0.15}        | slot_ridge |          1.1238 |          -0.8148 |    43.2423 |     65.7529 |    -24.7221 |       1.131  |     0.5734 |
| slot_ridge[slot+athletic]{alpha=3.0|shrink=0.15}                             | slot_ridge |          1.124  |          -0.8796 |    42.6381 |     65.3311 |    -25.7737 |       1.2911 |     0.5733 |
| slot_ridge[slot+athletic]{alpha=10.0|shrink=0.0}                             | slot_ridge |          1.124  |          -0.8578 |    42.5257 |     66.2807 |    -30.1279 |       1.1631 |     0.5725 |
| slot_ridge[slot+recruit]{alpha=10.0|shrink=0.3}                              | slot_ridge |          1.1243 |          -0.9234 |    44.2704 |     64.5954 |    -22.4074 |       1.6214 |     0.5914 |
| slot_ridge[slot]{alpha=10.0|shrink=0.3}                                      | slot_ridge |          1.1252 |          -0.9302 |    44.1649 |     64.6869 |    -22.6676 |       1.666  |     0.5849 |
| slot_gbm[slot]{learning_rate=0.06|shrink=0.15}                               | slot_gbm   |          1.132  |          -0.9277 |    42.8899 |     64.8737 |    -26.1224 |       1.4279 |     0.5883 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=10.0|shrink=0.15}       | slot_ridge |          1.1361 |          -0.8664 |    43.3476 |     65.6986 |    -25.9899 |       1.2289 |     0.583  |
| slot_ridge[slot+breakout]{alpha=1.0|shrink=0.5}                              | slot_ridge |          1.1373 |          -0.9332 |    46.7103 |     65.4026 |    -16.6284 |       1.8811 |     0.5745 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=1.0|shrink=0.3}         | slot_ridge |          1.1382 |          -0.8602 |    44.3934 |     65.3604 |    -20.9201 |       1.286  |     0.5708 |
| slot_gbm[slot+recruit]{learning_rate=0.06|shrink=0.15}                       | slot_gbm   |          1.1394 |          -0.8963 |    42.93   |     64.7486 |    -25.0199 |       1.313  |     0.5853 |
| slot_gbm[slot+p1a]{learning_rate=0.06|shrink=0.0}                            | slot_gbm   |          1.1427 |          -0.8817 |    42.6277 |     65.4576 |    -27.684  |       1.0997 |     0.5712 |
| slot_gbm[slot+breakout]{learning_rate=0.03|shrink=0.0}                       | slot_gbm   |          1.1441 |          -0.929  |    43.2937 |     67.2009 |    -30.9606 |       1.2727 |     0.5788 |
| slot_ridge[slot+athletic]{alpha=10.0|shrink=0.15}                            | slot_ridge |          1.1442 |          -0.9111 |    43.0331 |     65.5119 |    -26.588  |       1.3616 |     0.5725 |
| slot_ridge[slot+athletic]{alpha=1.0|shrink=0.3}                              | slot_ridge |          1.1452 |          -0.9209 |    43.8734 |     65.1667 |    -21.964  |       1.4807 |     0.5739 |
| slot_gbm[slot]{learning_rate=0.03|shrink=0.15}                               | slot_gbm   |          1.1463 |          -0.953  |    43.2724 |     65.3313 |    -26.966  |       1.5266 |     0.5848 |
| slot_gbm[slot+recruit]{learning_rate=0.03|shrink=0.15}                       | slot_gbm   |          1.1466 |          -0.9372 |    43.2451 |     64.982  |    -26.2617 |       1.4919 |     0.5853 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=3.0|shrink=0.3}         | slot_ridge |          1.1469 |          -0.8851 |    44.4874 |     65.3377 |    -21.5116 |       1.3577 |     0.5734 |
| slot_ridge[slot+breakout]{alpha=3.0|shrink=0.5}                              | slot_ridge |          1.1471 |          -0.9517 |    46.8571 |     65.5109 |    -16.9993 |       1.9654 |     0.5728 |
| slot_eb[slot]{eb_k=6.0|shrink=0.15}                                          | slot_eb    |          1.1502 |          -0.863  |    47.2429 |     64.2339 |     -9.935  |       1.4741 |     0.5354 |
| slot_ridge[slot+athletic]{alpha=3.0|shrink=0.3}                              | slot_ridge |          1.153  |          -0.9384 |    44.0417 |     65.2826 |    -22.3776 |       1.5454 |     0.5733 |
| slot_gbm[slot+breakout]{learning_rate=0.06|shrink=0.0}                       | slot_gbm   |          1.1548 |          -0.8866 |    43.5707 |     67.6049 |    -29.1484 |       1.1283 |     0.5742 |
| slot_gbm[slot+p1a]{learning_rate=0.06|shrink=0.15}                           | slot_gbm   |          1.1585 |          -0.9314 |    43.14   |     64.6439 |    -24.5123 |       1.2854 |     0.5712 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=10.0|shrink=0.3}        | slot_ridge |          1.1593 |          -0.9276 |    44.5914 |     65.4551 |    -22.5559 |       1.4741 |     0.583  |
| slot_ridge[slot+p1a]{alpha=1.0|shrink=0.5}                                   | slot_ridge |          1.1651 |          -0.9719 |    46.9404 |     65.6071 |    -17.3053 |       1.9967 |     0.5922 |
| slot_gbm[slot+p1a]{learning_rate=0.03|shrink=0.0}                            | slot_gbm   |          1.1652 |          -0.9581 |    43.0236 |     66.2429 |    -30.4053 |       1.3016 |     0.5855 |
| slot_gbm[slot+athletic]{learning_rate=0.06|shrink=0.0}                       | slot_gbm   |          1.1658 |          -0.8772 |    42.7936 |     66.2377 |    -28.1634 |       1.013  |     0.5677 |
| slot_gbm[slot+recruit]{learning_rate=0.06|shrink=0.3}                        | slot_gbm   |          1.1666 |          -0.9522 |    44.4524 |     64.8541 |    -21.7569 |       1.5691 |     0.5853 |
| slot_ridge[slot+breakout]{alpha=10.0|shrink=0.5}                             | slot_ridge |          1.1667 |          -0.9811 |    47.1053 |     65.7537 |    -17.6353 |       2.0824 |     0.5711 |
| slot_gbm[slot+breakout]{learning_rate=0.03|shrink=0.15}                      | slot_gbm   |          1.1674 |          -0.9716 |    43.8973 |     66.3669 |    -27.296  |       1.4877 |     0.5788 |
| slot_ridge[slot+recruit]{alpha=1.0|shrink=0.5}                               | slot_ridge |          1.1683 |          -0.9726 |    47.1364 |     65.6571 |    -17.0789 |       1.9446 |     0.5919 |
| slot_gbm[slot]{learning_rate=0.06|shrink=0.3}                                | slot_gbm   |          1.1684 |          -0.9781 |    44.4479 |     65.0639 |    -22.665  |       1.6996 |     0.5883 |
| slot_ridge[slot+athletic]{alpha=10.0|shrink=0.3}                             | slot_ridge |          1.17   |          -0.9644 |    44.3713 |     65.514  |    -23.0484 |       1.6291 |     0.5725 |
| slot_ridge[slot]{alpha=1.0|shrink=0.5}                                       | slot_ridge |          1.1725 |          -0.9806 |    47.0241 |     65.7696 |    -17.3569 |       2.01   |     0.5862 |
| slot_ridge[slot+p1a]{alpha=3.0|shrink=0.5}                                   | slot_ridge |          1.1732 |          -0.9845 |    47.0844 |     65.7273 |    -17.5819 |       2.0819 |     0.5949 |
| slot_gbm[slot+breakout]{learning_rate=0.06|shrink=0.15}                      | slot_gbm   |          1.174  |          -0.9355 |    44.0191 |     66.4603 |    -25.7566 |       1.3193 |     0.5741 |
| slot_ridge[slot+recruit]{alpha=3.0|shrink=0.5}                               | slot_ridge |          1.176  |          -0.9862 |    47.2686 |     65.7781 |    -17.3844 |       2.03   |     0.5935 |
| slot_gbm[slot+recruit]{learning_rate=0.03|shrink=0.3}                        | slot_gbm   |          1.1774 |          -0.9859 |    44.7767 |     65.2279 |    -22.7794 |       1.7796 |     0.5853 |
| slot_gbm[slot+p1a]{learning_rate=0.06|shrink=0.3}                            | slot_gbm   |          1.1778 |          -0.9811 |    44.3827 |     64.6703 |    -21.3391 |       1.5346 |     0.5712 |
| slot_ridge[slot]{alpha=3.0|shrink=0.5}                                       | slot_ridge |          1.1813 |          -0.9932 |    47.1821 |     65.8863 |    -17.6319 |       2.0936 |     0.5865 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=1.0|shrink=0.5}         | slot_ridge |          1.1814 |          -0.961  |    47.1894 |     66.141  |    -16.8086 |       1.7177 |     0.5708 |
| slot_gbm[slot+athletic]{learning_rate=0.06|shrink=0.15}                      | slot_gbm   |          1.1824 |          -0.9276 |    43.271  |     65.242  |    -24.9193 |       1.188  |     0.5676 |
| slot_gbm[slot]{learning_rate=0.03|shrink=0.3}                                | slot_gbm   |          1.1834 |          -0.999  |    44.826  |     65.5287 |    -23.3596 |       1.8181 |     0.5848 |
| slot_ridge[slot+p1a]{alpha=10.0|shrink=0.5}                                  | slot_ridge |          1.1847 |          -1.0028 |    47.2887 |     65.9257 |    -18.011  |       2.1854 |     0.5869 |
| slot_gbm[slot+athletic]{learning_rate=0.03|shrink=0.0}                       | slot_gbm   |          1.1862 |          -0.9651 |    43.3941 |     67.0723 |    -31.0857 |       1.2673 |     0.581  |
| slot_eb[slot]{eb_k=12.0|shrink=0.0}                                          | slot_eb    |          1.1879 |          -0.9151 |    47.626  |     65.2676 |    -11.8363 |       1.508  |     0.5294 |
| slot_gbm[slot+p1a]{learning_rate=0.03|shrink=0.15}                           | slot_gbm   |          1.1884 |          -0.9964 |    43.7499 |     65.7349 |    -26.8246 |       1.5196 |     0.5854 |
| slot_eb[slot]{eb_k=6.0|shrink=0.3}                                           | slot_eb    |          1.1892 |          -0.9248 |    48.9736 |     65.4524 |     -9.334  |       1.7141 |     0.5354 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=3.0|shrink=0.5}         | slot_ridge |          1.1893 |          -0.9788 |    47.3039 |     66.2429 |    -17.2311 |       1.808  |     0.5734 |
| slot_ridge[slot+recruit]{alpha=10.0|shrink=0.5}                              | slot_ridge |          1.1894 |          -1.0062 |    47.4711 |     65.9877 |    -17.871  |       2.1426 |     0.5914 |
| slot_ridge[slot]{alpha=10.0|shrink=0.5}                                      | slot_ridge |          1.1931 |          -1.011  |    47.3954 |     66.0724 |    -18.0564 |       2.1969 |     0.5849 |
| slot_gbm[slot+breakout]{learning_rate=0.06|shrink=0.3}                       | slot_gbm   |          1.197  |          -0.9845 |    45.2074 |     66.13   |    -22.3637 |       1.575  |     0.5741 |
| slot_gbm[slot+breakout]{learning_rate=0.03|shrink=0.3}                       | slot_gbm   |          1.1978 |          -1.0142 |    45.2416 |     66.2729 |    -23.6313 |       1.7729 |     0.5788 |
| slot_ridge[slot+athletic]{alpha=1.0|shrink=0.5}                              | slot_ridge |          1.2005 |          -1.0043 |    47.0484 |     66.3271 |    -17.5544 |       1.9577 |     0.5739 |
| slot_gbm[slot+athletic]{learning_rate=0.06|shrink=0.3}                       | slot_gbm   |          1.2066 |          -0.9779 |    44.6104 |     65.1026 |    -21.6741 |       1.4273 |     0.5676 |
| slot_ridge[slot+p1a+athletic+breakout+recruit]{alpha=10.0|shrink=0.5}        | slot_ridge |          1.2067 |          -1.0092 |    47.513  |     66.4813 |    -17.977  |       1.9554 |     0.583  |
| slot_gbm[slot+athletic]{learning_rate=0.03|shrink=0.15}                      | slot_gbm   |          1.2075 |          -1.0023 |    43.9789 |     66.4244 |    -27.4021 |       1.4853 |     0.581  |
| slot_ridge[slot+athletic]{alpha=3.0|shrink=0.5}                              | slot_ridge |          1.2108 |          -1.0169 |    47.2531 |     66.4796 |    -17.8497 |       2.0369 |     0.5733 |
| slot_gbm[slot+p1a]{learning_rate=0.03|shrink=0.3}                            | slot_gbm   |          1.2137 |          -1.0346 |    45.2001 |     65.9136 |    -23.2431 |       1.8084 |     0.5854 |
| slot_gbm[slot+recruit]{learning_rate=0.06|shrink=0.5}                        | slot_gbm   |          1.2142 |          -1.0267 |    47.5454 |     66.2367 |    -17.4063 |       2.0653 |     0.5853 |
| slot_eb[slot]{eb_k=12.0|shrink=0.15}                                         | slot_eb    |          1.2155 |          -0.9598 |    49.0036 |     66.1503 |    -11.0403 |       1.7091 |     0.5294 |
| slot_gbm[slot+p1a+athletic+breakout+recruit]{learning_rate=0.06|shrink=0.0}  | slot_gbm   |          1.2204 |          -0.9731 |    43.649  |     67.5974 |    -29.6643 |       1.0553 |     0.5672 |
| slot_gbm[slot+p1a]{learning_rate=0.06|shrink=0.5}                            | slot_gbm   |          1.223  |          -1.0474 |    47.4511 |     66.0171 |    -17.1079 |       2.0104 |     0.5712 |
| slot_ridge[slot+athletic]{alpha=10.0|shrink=0.5}                             | slot_ridge |          1.2241 |          -1.0355 |    47.5147 |     66.7213 |    -18.3289 |       2.141  |     0.5725 |
| slot_gbm[slot]{learning_rate=0.06|shrink=0.5}                                | slot_gbm   |          1.225  |          -1.0452 |    47.6187 |     66.4809 |    -18.055  |       2.2107 |     0.5883 |
| slot_gbm[slot+recruit]{learning_rate=0.03|shrink=0.5}                        | slot_gbm   |          1.2276 |          -1.0508 |    47.8399 |     66.6677 |    -18.1367 |       2.3196 |     0.5853 |
| slot_gbm[slot+p1a+athletic+breakout+recruit]{learning_rate=0.06|shrink=0.15} | slot_gbm   |          1.2304 |          -1.0091 |    44.113  |     66.5314 |    -26.1953 |       1.2366 |     0.5672 |
| slot_gbm[slot+athletic]{learning_rate=0.03|shrink=0.3}                       | slot_gbm   |          1.2323 |          -1.0395 |    45.3624 |     66.4619 |    -23.7189 |       1.7793 |     0.581  |
| slot_gbm[slot]{learning_rate=0.03|shrink=0.5}                                | slot_gbm   |          1.2358 |          -1.0601 |    47.8823 |     66.8909 |    -18.551  |       2.3597 |     0.5848 |
| slot_gbm[slot+p1a+athletic+breakout+recruit]{learning_rate=0.03|shrink=0.0}  | slot_gbm   |          1.2379 |          -1.0405 |    44.2691 |     68.534  |    -32.5786 |       1.3113 |     0.5831 |
| slot_gbm[slot+breakout]{learning_rate=0.06|shrink=0.5}                       | slot_gbm   |          1.2395 |          -1.0498 |    48.0214 |     67.0026 |    -17.8397 |       2.0586 |     0.5741 |
| slot_eb[slot]{eb_k=6.0|shrink=0.5}                                           | slot_eb    |          1.2427 |          -1.0071 |    51.5196 |     67.5963 |     -8.5329 |       2.114  |     0.5354 |
| slot_eb[slot]{eb_k=12.0|shrink=0.3}                                          | slot_eb    |          1.2439 |          -1.0045 |    50.5261 |     67.2664 |    -10.2443 |       1.9467 |     0.5294 |
| slot_gbm[slot+breakout]{learning_rate=0.03|shrink=0.5}                       | slot_gbm   |          1.2449 |          -1.071  |    48.1453 |     67.3131 |    -18.7451 |       2.2981 |     0.5788 |
| slot_gbm[slot+athletic]{learning_rate=0.06|shrink=0.5}                       | slot_gbm   |          1.247  |          -1.0451 |    47.5696 |     66.2614 |    -17.3471 |       1.9061 |     0.5676 |
| slot_gbm[slot+p1a+athletic+breakout+recruit]{learning_rate=0.06|shrink=0.3}  | slot_gbm   |          1.2475 |          -1.045  |    45.3743 |     66.2657 |    -22.7251 |       1.4829 |     0.5672 |
| slot_gbm[slot+p1a+athletic+breakout+recruit]{learning_rate=0.03|shrink=0.15} | slot_gbm   |          1.2536 |          -1.0664 |    44.838  |     67.7384 |    -28.6714 |       1.5347 |     0.5831 |
| slot_gbm[slot+p1a]{learning_rate=0.03|shrink=0.5}                            | slot_gbm   |          1.2553 |          -1.0856 |    48.1931 |     67.212  |    -18.468  |       2.3409 |     0.5854 |
| slot_eb[slot]{eb_k=25.0|shrink=0.0}                                          | slot_eb    |          1.2586 |          -1.0235 |    49.9774 |     67.5871 |    -12.3261 |       1.8411 |     0.5272 |
| slot_gbm[slot+athletic]{learning_rate=0.03|shrink=0.5}                       | slot_gbm   |          1.2701 |          -1.0891 |    48.2541 |     67.5779 |    -18.8079 |       2.3367 |     0.581  |
| slot_gbm[slot+p1a+athletic+breakout+recruit]{learning_rate=0.03|shrink=0.3}  | slot_gbm   |          1.2706 |          -1.0923 |    46.1136 |     67.5951 |    -24.7641 |       1.8324 |     0.5831 |
| slot_eb[slot]{eb_k=25.0|shrink=0.15}                                         | slot_eb    |          1.2767 |          -1.052  |    51.1286 |     68.3793 |    -11.4564 |       2.03   |     0.5272 |
| slot_gbm[slot+p1a+athletic+breakout+recruit]{learning_rate=0.06|shrink=0.5}  | slot_gbm   |          1.2768 |          -1.093  |    48.1849 |     67.1771 |    -18.0979 |       1.964  |     0.5672 |
| slot_eb[slot]{eb_k=12.0|shrink=0.5}                                          | slot_eb    |          1.2827 |          -1.0641 |    52.68   |     69.0977 |     -9.1833 |       2.2863 |     0.5294 |
| slot_eb[slot]{eb_k=25.0|shrink=0.3}                                          | slot_eb    |          1.2949 |          -1.0804 |    52.3449 |     69.3034 |    -10.5871 |       2.2217 |     0.5272 |
| slot_gbm[slot+p1a+athletic+breakout+recruit]{learning_rate=0.03|shrink=0.5}  | slot_gbm   |          1.297  |          -1.1268 |    48.8071 |     68.426  |    -19.5544 |       2.3786 |     0.5831 |
| slot_eb[slot]{eb_k=25.0|shrink=0.5}                                          | slot_eb    |          1.3194 |          -1.1183 |    54.0423 |     70.7319 |     -9.428  |       2.4081 |     0.5272 |
| pos_mean[slot]{}                                                             | pos_mean   |          1.3847 |          -1.2131 |    58.9887 |     75.1956 |     -6.53   |       0.5777 |     0      |
| pos_median[slot]{}                                                           | pos_median |          1.7159 |          -1.6633 |    56.5163 |     84.342  |    -37.0306 |       0.0547 |     0      |

## 6. ⭐ Rookie uncertainty — the one shippable fix

MVP-1 widened rookie intervals by `fp × cv`, with the cv estimated on the same SURVIVOR-filtered sample as the curve (`uncertainty_type='parameter'`, and its own report said "recalibrate before pricing"). Measured walk-forward, that nominal **80%** band covers **0.6799** — and **0.444** at QB. It is not an 80% interval; it is a decoration. A multiplicative width also collapses toward zero as the projection does, so the late-round rookies who most often surprise get the NARROWEST band.

NF1.4 replaces it with an EMPIRICAL band: within a position, the q10/q90 of what drafted rookies in that prediction tercile actually scored, over the FULL drafted population (never-played rookies carried as real zeros). Coverage becomes a measured claim:

```json
{
  "legacy_cv_band": {
    "hit": 376,
    "n": 553,
    "by_pos": {
      "QB": 0.444,
      "RB": 0.757,
      "TE": 0.6,
      "WR": 0.75
    },
    "coverage": 0.6799
  },
  "calibrated_band": {
    "hit": 437,
    "n": 553,
    "by_pos": {
      "QB": 0.741,
      "RB": 0.831,
      "TE": 0.72,
      "WR": 0.812
    },
    "coverage": 0.7902
  },
  "nominal": 0.8,
  "point_projection_max_abs_change": 0.0
}
```

⭐ `point_projection_max_abs_change` is **0.0** — the point projection is byte-identical. This is an interval-CALIBRATION fix, not a model change, so the null verdict above stands untouched and no deflation gate applies to it (a mis-stated interval is a defect, not a search result).

## 7. Face validity

```json
{
  "per_cohort": {
    "2019": {
      "incumbent": [
        {
          "position": "QB",
          "max_projected": 200.1,
          "hist_cap": 185.0
        },
        {
          "position": "TE",
          "max_projected": 112.5,
          "hist_cap": 106.7
        }
      ],
      "selected": [
        {
          "position": "QB",
          "max_projected": 200.1,
          "hist_cap": 185.0
        },
        {
          "position": "TE",
          "max_projected": 112.5,
          "hist_cap": 106.7
        }
      ]
    },
    "2020": {
      "incumbent": [
        {
          "position": "QB",
          "max_projected": 236.5,
          "hist_cap": 214.2
        }
      ],
      "selected": [
        {
          "position": "QB",
          "max_projected": 236.5,
          "hist_cap": 214.2
        }
      ]
    },
    "2021": {
      "incumbent": [
        {
          "position": "QB",
          "max_projected": 261.0,
          "hist_cap": 214.0
        },
        {
          "position": "WR",
          "max_projected": 190.0,
          "hist_cap": 166.1
        },
        {
          "position": "TE",
          "max_projected": 107.6,
          "hist_cap": 98.0
        }
      ],
      "selected": [
        {
          "position": "QB",
          "max_projected": 261.0,
          "hist_cap": 214.0
        },
        {
          "position": "WR",
          "max_projected": 190.0,
          "hist_cap": 166.1
        },
        {
          "position": "TE",
          "max_projected": 107.6,
          "hist_cap": 98.0
        }
      ]
    },
    "2022": {
      "incumbent": [
        {
          "position": "WR",
          "max_projected": 191.9,
          "hist_cap": 168.5
        }
      ],
      "selected": [
        {
          "position": "WR",
          "max_projected": 191.9,
          "hist_cap": 168.5
        }
      ]
    },
    "2023": {
      "incumbent": [
        {
          "position": "QB",
          "max_projected": 232.4,
          "hist_cap": 207.6
        },
        {
          "position": "RB",
          "max_projected": 208.3,
          "hist_cap": 178.8
        }
      ],
      "selected": [
        {
          "position": "QB",
          "max_projected": 232.4,
          "hist_cap": 207.6
        },
        {
          "position": "RB",
          "max_projected": 208.3,
          "hist_cap": 178.8
        }
      ]
    },
    "2024": {
      "incumbent": [
        {
          "position": "QB",
          "max_projected": 229.9,
          "hist_cap": 204.5
        },
        {
          "position": "WR",
          "max_projected": 200.5,
          "hist_cap": 177.9
        },
        {
          "position": "TE",
          "max_projected": 111.4,
          "hist_cap": 97.6
        }
      ],
      "selected": [
        {
          "position": "QB",
          "max_projected": 229.9,
          "hist_cap": 204.5
        },
        {
          "position": "WR",
          "max_projected": 200.5,
          "hist_cap": 177.9
        },
        {
          "position": "TE",
          "max_projected": 111.4,
          "hist_cap": 97.6
        }
      ]
    },
    "2025": {
      "incumbent": [
        {
          "position": "QB",
          "max_projected": 258.1,
          "hist_cap": 214.6
        },
        {
          "position": "RB",
          "max_projected": 216.3,
          "hist_cap": 186.1
        },
        {
          "position": "WR",
          "max_projected": 205.5,
          "hist_cap": 184.4
        },
        {
          "position": "TE",
          "max_projected": 111.8,
          "hist_cap": 97.0
        }
      ],
      "selected": [
        {
          "position": "QB",
          "max_projected": 258.1,
          "hist_cap": 214.6
        },
        {
          "position": "RB",
          "max_projected": 216.3,
          "hist_cap": 186.1
        },
        {
          "position": "WR",
          "max_projected": 205.5,
          "hist_cap": 184.4
        },
        {
          "position": "TE",
          "max_projected": 111.8,
          "hist_cap": 97.0
        }
      ]
    }
  },
  "note": "level check only; the top-10-overall check needs the merged veteran board (season_projection).",
  "incumbent_cohorts_over_cap": 7,
  "selected_cohorts_over_cap": 7,
  "n_cohorts": 7
}
```

## 8. Limitations

- **Small-N by construction** — ~75 drafted skill rookies per class, ~12 at QB. Every positional read is thin; the interval width is the honest expression of that.
- **Breakout age is a CLASS-YEAR proxy, not a birth date** (the sports lake has no DOB), and `stg_ncaaf_roster` starts at 2014, so the earliest classes carry `has_breakout = 0` where their freshman season predates the feed. Kept NULL + flagged, never back-filled with a guess.
- **Combine coverage is partial** (forty ≈ 50% at QB, ≈ 73% at RB/WR) — a player who did not test stays NaN with `has_combine = 0` carrying the missingness.
- **The rookie label is the rookie SEASON only** — this prior prices year 1, which is what the redraft board needs. A dynasty (multi-year) rookie value is a different target.
- **P1A is used as the BACKBONE, not rebuilt** — its own verdict stands (draft slot beats college production 0.64 vs 0.79 MAE), so `projected_nfl_z` enters as a slot RESIDUAL.

