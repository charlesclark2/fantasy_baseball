# NF-D15 — the AVAILABILITY-SCALED rookie POINT projection (RB/TE/WR) — §0.5 bake-off

**Generated:** 2026-08-01T03:16:24.040943+00:00 · **held-out draft classes:** 2019–2025 (7) · **arms:** 33 · **held-out rookie-seasons (RB/TE/WR):** 472 · **availability prior:** `tier_empirical[depth] · blend 1` (NF-D14 leg-1 winner, REUSED not refitted)

## ⭐ VERDICT — 🟡 RECORDED NULL — no availability-scaled rookie POINT arm clears its own gate; the shipped rookie point STANDS

**The availability lift NF-D14 surfaced REPRODUCES on the universe read** — the best availability arm `learned scale · λ 1` moves the RB/TE/WR universe MAE 42.054 → 38.595 and the bias -20.869 → -22.439 (NF-D14 §6's lead, re-measured). **On the metric that selects — NF1.4's draftable-tier MAE — it reads 1.0738 → 0.9835 pooled.**

**RB — 🟡 does not ship.** `learned scale · λ 1` moves the draftable-tier MAE 80.43 → 68.4371 PPR with ρ 0.5898 → 0.5929; PBO 0.0286, DSR 0.0223, paired p 0.0735, BH-FDR does NOT survive. Failing gate(s): `['dsr_ok', 'fdr_ok']`. Matched foil: the same base and λ with the per-player content stripped scores 87.3257 against the arm's 68.4371 (paired Δ 18.8886, p 0.034) — **so the availability content, not the level correction, is what earned it**.
**TE — 🟡 does not ship.** `learned scale · λ 1` moves the draftable-tier MAE 53.9186 → 47.3257 PPR with ρ 0.6075 → 0.6303; PBO 0.0571, DSR 0.0076, paired p 0.0585, BH-FDR does NOT survive. Failing gate(s): `['dsr_ok', 'fdr_ok']`. Matched foil: the same base and λ with the per-player content stripped scores 55.4871 against the arm's 47.3257 (paired Δ 8.1614, p 0.0216) — **so the availability content, not the level correction, is what earned it**.
**WR — 🟡 does not ship.** `MATCHED FOIL mean[residual] · λ 1` moves the draftable-tier MAE 68.8357 → 66.7657 PPR with ρ 0.6208 → 0.6208; PBO 0.4571, DSR 0.0007, paired p 0.1902, BH-FDR does NOT survive. Failing gate(s): `['uses_availability', 'pbo_ok', 'dsr_ok', 'fdr_ok']`.

⭐ **THE MATCHED FOIL SETTLES THE MECHANISM, AND IT CONTRADICTS NF-D14's STATED ONE.** NF-D14 explained its RB/TE/WR lift as the ratio 'partially correcting the COLD bias NF1.4 documented' — i.e. as a LEVEL correction, which a per-position CONSTANT delivers with zero per-player information and zero ordering risk. That constant is registered here at the identical base and the identical λ. At RB and TE it does not merely lose to the availability arm — at every one of those positions it **fails to beat the incumbent at all** (**RB** — foil 87.3257 vs incumbent 80.43, arm 68.4371, paired Δ 18.8886 PPR at p 0.034; **TE** — foil 55.4871 vs incumbent 53.9186, arm 47.3257, paired Δ 8.1614 PPR at p 0.0216). So whatever is happening at those positions is PER-PLAYER, and it is NOT the recalibration NF-D14 named — which is the opposite of NF-D14's reading, and a thing only the matched pairing could establish (a leaderboard rank cannot tell 'my feature works' from 'anything that inflates RB/TE/WR works': NF-D10).

⭐ **AND THE BIAS CORROBORATES IT FROM THE OTHER SIDE.** If the lift were the cold-bias correction NF-D14 described, the winning arm would move the bias TOWARD zero. It does not: pooled over RB/TE/WR the bias goes -20.869 → -22.439 — marginally FURTHER from zero — while the MAE improves anyway. A level story cannot produce that pattern; a per-player one can, by moving the right rookies in both directions.

⚠️ **Where an availability arm wins at all (RB, TE), the winner is the DIRECT-LEARNED FOIL — not any of the three prescribed ratio forms, and specifically not `ratio_pos`, which is NF-D14 §6's own construction.** The prescribed multiplicative haircut is therefore not the right functional form for this correction even where the correction is real, which is a second, independent reason NF-D14 §6's arm should not have been shipped on its measured MAE alone.

⇒ **RECORDED NULL — and NF-D14's open lead is now CLOSED rather than left dangling.** The MAE improvement NF-D14 measured is real and reproduces here; what it does not do is clear a gate built for a point projection. The shipped rookie point STANDS, the interval is untouched, and the QB exclusion was never re-opened.

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. ⛔ **QB is EXCLUDED by pre-registration and PROVEN untouched** (max |Δ| over every arm and every held-out QB: **0.000000000** PPR). 🔒 The rookie INTERVAL's width model is untouched — NF-D14 settled that question.

## 0. Step 0 — the REUSE, and the wiring proof that it is faithful

The availability signal is NF-D14's leg-1 winner `tier_empirical[depth] · blend 1`, read back out of `ablation_results/nf_d14_rookie_availability.json` and re-fitted STRICTLY IN-FOLD per held-out draft class. It is not re-selected here — `require_reused_prior` fails loudly if NF-D14 is re-run with a different winner, because every number below would then be about a prior nobody selected.

**The wiring proof.** This harness rebuilds NF-D14 §6's scale in new code, so it is required to REPRODUCE §6's published numbers before any selection is read (tolerance ±0.05 PPR): **✅ REPRODUCED**.

| position   |   NF-D14 §6 MAE base |   NF-D15 MAE base |   NF-D14 §6 MAE scaled |   NF-D15 MAE scaled | checked                            |
|:-----------|---------------------:|------------------:|-----------------------:|--------------------:|:-----------------------------------|
| QB         |              50.1500 |           50.1500 |                58.5600 |             58.5600 | reported only (QB is out of scope) |
| RB         |              46.4000 |           46.4000 |                42.8600 |             42.8600 | yes                                |
| TE         |              31.2400 |           31.2400 |                30.0500 |             30.0500 | yes                                |
| WR         |              44.0100 |           44.0100 |                41.9200 |             41.9200 | yes                                |

⭐ **The QB row is REPORTED, not checked, and the difference is the whole story.** NF-D14 §6 scaled QB — that is what it measured and declined. NF-D15 cannot: `apply_position_scale` passes QB through unchanged. So the QB row above is this harness re-deriving NF-D14's finding *as a measurement it is forbidden to act on*, and it lands in the same place: the ratio prices draft-capital playing time a second time on top of the slot curve that already prices it.

## 1. Selection metric, the constraint, and the anchor set

**Primary metric — `tier_mae`, NF1.4's, INHERITED RATHER THAN CHOSEN.** The incumbent rookie point was selected on the draftable-tier MAE, on a tier FIXED by the incumbent's own projection (NF1.1's fixed-anchor rule, so no arm can buy a friendlier subset). NF-D15 changes that same product; grading it on a different metric would be metric-shopping. Per position the metric is that position's tier MAE in RAW PPR — nothing is pooled, so it stays readable as *PPR of error on the rookies you would actually draft*.

⚠️ **NF-D14's headline for this lead is a UNIVERSE MAE** (all ~75 drafted rookies a class). It is reported in every table below — it is the bridge back to §6 — and it **never selects**: the universe read is dominated by late-round rookies nobody drafts, and the product is a draft board.

**The constraint — DO NO ORDERING HARM.** A per-player multiplicative scale REORDERS the board within a position, and a point-MAE win that scrambles the draft order is a loss for this product. Each scaled position's within-position Spearman ρ must stay within `ORDERING_DO_NO_HARM = 0.02` of the incumbent's — NF1.4's own constant, inherited verbatim so the bar is not re-negotiated by the story that needs it. Checked PER POSITION, never as a pooled mean (a pooled ρ can sit flat while one position collapses).

### The anchors, scored on THIS run

| anchor                  | what it is                                                                                                                      |   tier MAE RB |   tier MAE TE |   tier MAE WR |   universe MAE |
|:------------------------|:--------------------------------------------------------------------------------------------------------------------------------|--------------:|--------------:|--------------:|---------------:|
| oracle_perplayer        | ORACLE FLOOR, full resolution (k = realized/point). Peeks; nothing may beat it.                                                 |        0.0000 |        0.0000 |        0.0000 |         0.0040 |
| oracle_posconst         | ORACLE FLOOR at the MATCHED FAMILY of the constant foil — the held-out class's OWN per-position mean correction.                |       75.0040 |       38.8570 |       62.1310 |        40.6900 |
| permuted                | the availability prior fitted on SHUFFLED training games. Same family, same n; only information moves. Must LOSE.               |       80.2330 |       56.7710 |       68.1060 |        42.1600 |
| zero_scale              | DEGENERATE — k = 0, project nothing. Must LOSE.                                                                                 |      139.7000 |      105.3140 |      140.3610 |        62.2900 |
| pos_median              | DEGENERATE — NF1.4's MAE-collapse tell (the in-fold position median for everyone). Wins an INVERTED metric; must LOSE this one. |      110.8560 |       86.5930 |      115.2810 |        54.0390 |
| → INCUMBENT (NULL)      | the shipped rookie point, unscaled                                                                                              |       80.4300 |       53.9190 |       68.8360 |        42.0540 |
| → BEST AVAILABILITY ARM | learned scale · λ 1                                                                                                             |       68.4370 |       47.3260 |       69.9010 |        38.5950 |

- ✅ both degenerates lose the primary metric — the metric is not paying for pessimism
- ✅ the truth beats its own permutation — the scale carries information, not just shape
- ✅ the full-resolution oracle floor holds
- ✅ QB is untouched on real emitted projections, not merely by assertion

⭐ **READ THE `oracle_posconst` ROW BEFORE CONCLUDING ANYTHING FROM IT: the best availability arm BEATS that peeking oracle at RB, and that is NOT a metric inversion.** It is the NF1.7 (b) / NF1.9 (f) capacity effect, reproduced. A peeking oracle is a floor only at MATCHED FAMILY *and* MATCHED RESOLUTION, and this one is a per-position CONSTANT — it knows the held-out class's average correction and nothing about any individual rookie. An honest PER-PLAYER arm is free to beat it, because it is answering a finer question. **The floor that is well-posed against a per-player arm is `oracle_perplayer`** (full resolution, scored 0.0), and it holds; `oracle_posconst` is the floor for the CONSTANT foils, where it does its job. This is exactly why both resolutions are in the anchor set rather than one.

⭐ **The degenerate check comes back NEGATIVE, and it is reported because it was SCORED, not because it was expected.** `zero_scale` (2.0477) and NF1.4's `pos_median` MAE-collapse tell (1.6691) both lose the primary metric decisively to the reference arm (0.9835). NF-D14's refinement of the NF-D11 landmine is the reason this is a measurement rather than an argument: **MAE inverts when the conditional MEDIAN sits at the floor, not merely when the zero atom is fat** — and on the RB/TE/WR DRAFTABLE TIER the median is nowhere near zero, so it does not invert here. The right response to that rule is to keep the degenerate in the field and READ it every run, which is what this line is.

## 2. The full field (pooled over the SCALED positions RB/TE/WR)

| arm                                  | avail?   |   pooled tier MAE (scale-free) |   tier MAE RB |   tier MAE TE |   tier MAE WR |   universe MAE |   universe bias |   mean scale |
|:-------------------------------------|:---------|-------------------------------:|--------------:|--------------:|--------------:|---------------:|----------------:|-------------:|
| learned scale · λ 1                  | yes      |                         0.9835 |       68.4370 |       47.3260 |       69.9010 |        38.5950 |        -22.4390 |       0.8343 |
| learned scale · λ 0.75               | yes      |                         0.9966 |       71.3470 |       47.8000 |       69.4460 |        38.9120 |        -23.2230 |       0.8418 |
| learned scale · λ 0.5                | yes      |                         1.0246 |       74.1730 |       50.2290 |       69.2960 |        39.5780 |        -23.3010 |       0.8688 |
| MATCHED FOIL mean[residual] · λ 1    | —        |                         1.0301 |       77.3860 |       50.9560 |       66.7660 |        41.4110 |        -18.0960 |       1.0720 |
| avail ratio[pos] · λ 1               | yes      |                         1.0337 |       71.1270 |       53.7340 |       68.9560 |        39.7010 |        -17.5140 |       1.0349 |
| avail ratio[pos] · λ 0.75            | yes      |                         1.0400 |       73.0010 |       53.8560 |       68.4330 |        40.0210 |        -18.7190 |       1.0163 |
| MATCHED FOIL mean[residual] · λ 0.75 | —        |                         1.0440 |       78.1100 |       51.9010 |       67.6360 |        41.5740 |        -19.3420 |       1.0407 |
| MATCHED FOIL mean[pos] · λ 1         | —        |                         1.0448 |       78.3170 |       51.9260 |       67.7560 |        41.5670 |        -19.4990 |       1.0349 |
| avail ratio[pos] · λ 0.5             | yes      |                         1.0494 |       75.3500 |       53.9260 |       68.2210 |        40.5130 |        -19.6990 |       1.0036 |
| learned scale · λ 0.25               | yes      |                         1.0497 |       77.3300 |       52.2630 |       68.8790 |        40.5370 |        -22.5710 |       0.9196 |
| MATCHED FOIL mean[pos] · λ 0.75      | —        |                         1.0560 |       79.1130 |       52.6090 |       68.3410 |        41.7250 |        -20.2580 |       1.0163 |
| MATCHED FOIL mean[residual] · λ 0.5  | —        |                         1.0568 |       79.1330 |       52.7160 |       68.1990 |        41.7570 |        -20.2290 |       1.0181 |
| avail ratio[pos] · λ 0.25            | yes      |                         1.0595 |       77.8840 |       53.9470 |       68.0860 |        41.1620 |        -20.4290 |       0.9978 |
| MATCHED FOIL mean[pos] · λ 0.5       | —        |                         1.0643 |       79.7440 |       53.1570 |       68.6640 |        41.8520 |        -20.7680 |       1.0036 |
| MATCHED FOIL mean[residual] · λ 0.25 | —        |                         1.0663 |       79.9170 |       53.3700 |       68.5360 |        41.9120 |        -20.7460 |       1.0044 |
| MATCHED FOIL mean[pos] · λ 0.25      | —        |                         1.0699 |       80.1910 |       53.5490 |       68.8270 |        41.9580 |        -20.9890 |       0.9978 |
| incumbent (NULL)                     | —        |                         1.0738 |       80.4300 |       53.9190 |       68.8360 |        42.0540 |        -20.8690 |       1.0000 |
| avail ratio[residual] · λ 0.25       | yes      |                         1.0777 |       79.2370 |       55.0110 |       69.0810 |        41.7870 |        -21.0380 |       1.0044 |
| avail ratio[residual] · λ 0.5        | yes      |                         1.0828 |       78.2030 |       56.0190 |       69.5070 |        41.6960 |        -20.8970 |       1.0181 |
| avail ratio[residual] · λ 0.75       | yes      |                         1.0875 |       77.2910 |       56.9400 |       69.9160 |        41.7320 |        -20.4770 |       1.0407 |
| avail ratio[residual] · λ 1          | yes      |                         1.0927 |       76.4710 |       57.7840 |       70.4460 |        41.9040 |        -19.7980 |       1.0720 |
| MATCHED FOIL mean[slot] · λ 0.25     | —        |                         1.0939 |       81.7800 |       54.9660 |       70.2260 |        42.2350 |        -22.5700 |       0.9595 |
| avail ratio[slot] · λ 0.25           | yes      |                         1.0942 |       80.5430 |       56.0890 |       69.7130 |        41.7120 |        -22.4230 |       0.9595 |
| MATCHED FOIL mean[slot] · λ 0.5      | —        |                         1.1145 |       83.0700 |       55.9240 |       71.9170 |        42.4780 |        -23.8860 |       0.9281 |
| MATCHED FOIL mean[learned] · λ 0.25  | —        |                         1.1149 |       83.3990 |       55.4110 |       72.5490 |        42.6270 |        -24.2530 |       0.9196 |
| avail ratio[slot] · λ 0.5            | yes      |                         1.1167 |       80.7970 |       58.2170 |       70.9240 |        41.5840 |        -23.6530 |       0.9281 |
| MATCHED FOIL mean[slot] · λ 0.75     | —        |                         1.1310 |       84.1560 |       56.6890 |       73.2110 |        42.6680 |        -24.8980 |       0.9039 |
| avail ratio[slot] · λ 0.75           | yes      |                         1.1386 |       81.2730 |       60.1740 |       72.0910 |        41.5890 |        -24.6260 |       0.9039 |
| MATCHED FOIL mean[slot] · λ 1        | —        |                         1.1435 |       85.0640 |       57.2890 |       74.1070 |        42.8030 |        -25.6690 |       0.8854 |
| MATCHED FOIL mean[learned] · λ 0.5   | —        |                         1.1443 |       85.4730 |       56.0830 |       75.8560 |        43.1440 |        -26.3990 |       0.8688 |
| avail ratio[slot] · λ 1              | yes      |                         1.1590 |       81.8140 |       61.9810 |       73.0870 |        41.6560 |        -25.3950 |       0.8854 |
| MATCHED FOIL mean[learned] · λ 0.75  | —        |                         1.1592 |       86.8140 |       56.0990 |       77.7740 |        43.4680 |        -27.5590 |       0.8418 |
| MATCHED FOIL mean[learned] · λ 1     | —        |                         1.1601 |       87.3260 |       55.4870 |       78.4760 |        43.5950 |        -27.9050 |       0.8343 |

⭐ **Read the `MATCHED FOIL` rows against their `avail ratio` partners at the same base and the same λ, not against the leaderboard.** The foil delivers the IDENTICAL average level correction with ZERO per-player information; the paired difference between a pair is the availability content, and a rank cannot tell that apart from 'anything that inflates RB/TE/WR helps' (NF-D10).

## 3. Per-position selection, deflation, and the SHIP decision

| position   |   incumbent tier MAE | selected arm                      |   tier MAE |   Δ vs incumbent | ρ inc → arm     |    PBO |    DSR |   paired p | BH-FDR   | SHIP   |
|:-----------|---------------------:|:----------------------------------|-----------:|-----------------:|:----------------|-------:|-------:|-----------:|:---------|:-------|
| RB         |              80.4300 | learned scale · λ 1               |    68.4371 |         -11.9930 | 0.5898 → 0.5929 | 0.0286 | 0.0223 |     0.0735 | no       | —      |
| TE         |              53.9186 | learned scale · λ 1               |    47.3257 |          -6.5930 | 0.6075 → 0.6303 | 0.0571 | 0.0076 |     0.0585 | no       | —      |
| WR         |              68.8357 | MATCHED FOIL mean[residual] · λ 1 |    66.7657 |          -2.0700 | 0.6208 → 0.6208 | 0.4571 | 0.0007 |     0.1902 | no       | —      |

### RB — 🟡 does NOT ship

Gate detail: `{'position': 'RB', 'ship': False, 'has_eligible_winner': True, 'uses_availability': True, 'beats_incumbent': True, 'ordering_ok': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': False}`

Deflation over the ELIGIBLE set (31 of 33 arms): **PBO 0.0286** · Bailey degradation 2.737% · contender spread 12.99% · **DSR 0.0223** (gate ≥ 0.95; contender-set reading 0.7643, reported for distinguishability, NOT the gate) · one-sided paired p 0.0735.

| config                               |   IS-half wins |   share |   full-sample tier MAE |   Δ vs best % |
|:-------------------------------------|---------------:|--------:|-----------------------:|--------------:|
| learned scale · λ 1                  |             23 |  0.6570 |                68.4370 |        0.0000 |
| avail ratio[pos] · λ 1               |             10 |  0.2860 |                71.1270 |        3.9300 |
| MATCHED FOIL mean[pos] · λ 1         |              1 |  0.0290 |                78.3170 |       14.4400 |
| MATCHED FOIL mean[residual] · λ 0.75 |              1 |  0.0290 |                78.1100 |       14.1300 |

⭐ **THE MATCHED FOIL — the attribution.** `learned scale · λ 1` (68.4371) against its identical-base, identical-λ constant foil `MATCHED FOIL mean[learned] · λ 1` (87.3257): paired mean delta **18.8886** PPR in the availability arm's favour (one-sided paired p 0.034), winning **5 of 7** held-out classes. The foil does NOT beat the incumbent on its own.

| position   |   incumbent |   candidate |   delta | ok   |
|:-----------|------------:|------------:|--------:|:-----|
| RB         |      0.5898 |      0.5929 |  0.0031 | True |

### TE — 🟡 does NOT ship

Gate detail: `{'position': 'TE', 'ship': False, 'has_eligible_winner': True, 'uses_availability': True, 'beats_incumbent': True, 'ordering_ok': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': False}`

Deflation over the ELIGIBLE set (30 of 33 arms): **PBO 0.0571** · Bailey degradation 1.829% · contender spread 10.43% · **DSR 0.0076** (gate ≥ 0.95; contender-set reading 0.9368, reported for distinguishability, NOT the gate) · one-sided paired p 0.0585.

| config                            |   IS-half wins |   share |   full-sample tier MAE |   Δ vs best % |
|:----------------------------------|---------------:|--------:|-----------------------:|--------------:|
| learned scale · λ 1               |             22 |  0.6290 |                47.3260 |        0.0000 |
| learned scale · λ 0.75            |              8 |  0.2290 |                47.8000 |        1.0000 |
| MATCHED FOIL mean[residual] · λ 1 |              4 |  0.1140 |                50.9560 |        7.6700 |
| avail ratio[pos] · λ 1            |              1 |  0.0290 |                53.7340 |       13.5400 |

⭐ **THE MATCHED FOIL — the attribution.** `learned scale · λ 1` (47.3257) against its identical-base, identical-λ constant foil `MATCHED FOIL mean[learned] · λ 1` (55.4871): paired mean delta **8.1614** PPR in the availability arm's favour (one-sided paired p 0.0216), winning **6 of 7** held-out classes. The foil does NOT beat the incumbent on its own.

| position   |   incumbent |   candidate |   delta | ok   |
|:-----------|------------:|------------:|--------:|:-----|
| TE         |      0.6075 |      0.6303 |  0.0228 | True |

### WR — 🟡 does NOT ship

Gate detail: `{'position': 'WR', 'ship': False, 'has_eligible_winner': True, 'uses_availability': False, 'beats_incumbent': True, 'ordering_ok': True, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False}`

Deflation over the ELIGIBLE set (32 of 33 arms): **PBO 0.4571** · Bailey degradation 5.891% · contender spread 2.5% · **DSR 0.0007** (gate ≥ 0.95; contender-set reading 0.7349, reported for distinguishability, NOT the gate) · one-sided paired p 0.1902.

| config                            |   IS-half wins |   share |   full-sample tier MAE |   Δ vs best % |
|:----------------------------------|---------------:|--------:|-----------------------:|--------------:|
| MATCHED FOIL mean[residual] · λ 1 |             13 |  0.3710 |                66.7660 |        0.0000 |
| learned scale · λ 1               |              8 |  0.2290 |                69.9010 |        4.7000 |
| avail ratio[pos] · λ 1            |              5 |  0.1430 |                68.9560 |        3.2800 |
| avail ratio[pos] · λ 0.25         |              5 |  0.1430 |                68.0860 |        1.9800 |
| avail ratio[pos] · λ 0.75         |              2 |  0.0570 |                68.4330 |        2.5000 |
| incumbent (NULL)                  |              1 |  0.0290 |                68.8360 |        3.1000 |

| position   |   incumbent |   candidate |   delta | ok   |
|:-----------|------------:|------------:|--------:|:-----|
| WR         |      0.6208 |      0.6208 |  0.0000 | True |

### The BH-FDR is CONSUMED, not printed

One-sided paired p-values across the three scaled positions: `{'RB': 0.0735, 'TE': 0.0585, 'WR': 0.1902}` → BH-FDR (q=0.1) survivors: `{'RB': False, 'TE': False, 'WR': False}`. ⭐ Each position's survival is an ARGUMENT to its own ship decision (`per_position_ship`), so a position that fails its multiplicity correction cannot receive the scaling whatever its point estimate says. That is E7.12's landmine — a statistic computed, printed, and then never allowed to gate anything — closed by construction.

### ⭐ 3b. IS THE ANSWER RESTING ON A GATE LEVEL I CHOSE? — the sensitivity, computed

This story pre-registered NF-D14's stricter **DSR ≥ 0.95** rather than NF1.4's own **DSR ≥ 0.0**, on the stated ground that the availability signal it consumes is the one that failed exactly that gate in NF-D14. That reasoning is sound going in and worth nothing if the choice silently decides the outcome — so the ship decision is RE-RUN at NF1.4's level, and with the DSR dropped entirely, and all three answers are reported.

| position   |    dsr |   dsr_contenders | ships_at_0.95   | ships_at_0.0   | ships_without_dsr   |
|:-----------|-------:|-----------------:|:----------------|:---------------|:--------------------|
| RB         | 0.0223 |           0.7643 | False           | False          | False               |
| TE         | 0.0076 |           0.9368 | False           | False          | False               |
| WR         | 0.0007 |           0.7349 | False           | False          | False               |

- ships at the pre-registered DSR ≥ 0.95: `none`
- ships at NF1.4's DSR ≥ 0.0: `none`
- ships with the DSR gate REMOVED ALTOGETHER: `none`

⭐ **THE ANSWER DOES NOT TURN ON THE DISPUTABLE GATE, AND THAT IS THE POINT OF COMPUTING IT.** Nothing ships even with the DSR removed entirely, because the **BH-FDR blocks all three positions independently**. So the null is not an artefact of preferring NF-D14's 0.95 to NF1.4's 0.0 — a reader who disagrees with that choice reaches the same verdict. (Had they disagreed, the pre-registered gate would still govern and this section would be the disclosure that the answer was close — never a licence to take the other reading, which is the E2.1-r inversion facing outward.)

⚠️ Note also the whole-field vs contender-set DSR gap in the table above — the NF-D14/NF1.8 lesson firing again: `deflated_sharpe`'s expected-max-SR term scales with the DISPERSION of the trial Sharpes, so a 33-arm field that deliberately contains its own weak arms (every λ 0.25 shrink, every constant foil) deflates against those arms rather than against the contest at the top. Both readings are reported; the **whole-field one is the pre-registered gate** and it binds.

### ⭐ 3c. THE MARGIN IN DRAFT CLASSES — what kind of null this is

| position   |   classes now |   mean Δ (PPR) |   sd Δ (PPR) |   one-sided p |   BH cutoff to clear unconditionally |   classes needed |
|:-----------|--------------:|---------------:|-------------:|--------------:|-------------------------------------:|-----------------:|
| RB         |             7 |        11.9900 |      19.0600 |        0.0735 |                               0.0333 |               11 |
| TE         |             7 |         6.5900 |       9.5300 |        0.0585 |                               0.0333 |               10 |
| WR         |             7 |         2.0700 |       5.7900 |        0.1902 |                               0.0333 |               29 |

'p = 0.07 against a cutoff of 0.067' reads like a hair's breadth of evidence. What it actually is, is SEVEN held-out draft classes of a quantity whose per-class spread is larger than its mean — the same shape NF1.8 diagnosed on rookie QBs and NF-D14 confirmed. Stating the margin in CLASSES rather than in p-value decimals is NF1.8's 'state the margin in ROWS' convention one unit over, and it is what separates **'underpowered'** from **'absent'**: an effect that needs a plausible number of further classes is a story to re-run when they exist; one that needs dozens is a null at any n this program will have.

### ⭐ 3d. THE FRAMING I CHOSE — the pooled single-hypothesis reading, and a POST-HOC LEAD

The DSR level was not the only choice this story made. Splitting the question into THREE per-position searches carries a multiplicity penalty a single POOLED test would not — so the pooled framing ('does availability scaling help RB/TE/WR JOINTLY?') is computed here too, on the pooled scale-free tier_mae (incumbent 1.0738). **Reported, never selected on:** the pre-registered per-position framing governs, and this table exists so the disclosure is a number rather than a shrug.

| arm                               |   pooled tier MAE |   mean Δ |   sd Δ |   one-sided p (POOLED, 1 test) | classes won   |
|:----------------------------------|------------------:|---------:|-------:|-------------------------------:|:--------------|
| learned scale · λ 1               |            0.9835 |   0.0903 | 0.1498 |                         0.0810 | 6/7           |
| avail ratio[pos] · λ 1            |            1.0337 |   0.0401 | 0.0809 |                         0.1187 | 4/7           |
| MATCHED FOIL mean[residual] · λ 1 |            1.0301 |   0.0437 | 0.0315 |                         0.0052 | 6/7           |

⚠️ **The framing IS partly load-bearing for the availability claim, and that is worth saying plainly.** Pooled as ONE test the best availability arm reads p 0.081 against the three-test BH cutoff of 0.0333 it actually faced. **The pre-registered framing governs** — a story that re-frames its hypothesis after seeing which framing passes has no hypothesis (E2.1-r) — and the per-position framing is the right one for a per-position product, which is why it was chosen in advance. But it is the multiplicity correction, not the effect size, that is doing the blocking here, and a reader should know that.

🔎 **A POST-HOC LEAD, FLAGGED AS ONE — the low-risk half of this study has the strongest evidence in it.** The best CONSTANT arm (`MATCHED FOIL mean[residual] · λ 1`) — a per-position recalibration carrying ZERO per-player information and doing ZERO ordering harm by construction — reads pooled tier MAE 1.0301 against the incumbent's 1.0738, winning 6/7 classes at p 0.0052, with a per-class spread (sd 0.0315) a FIFTH of the availability arm's. It beats the incumbent at all three scaled positions.

⚠️⚠️ **THIS IS A LEAD, NOT A RESULT, AND THE DISTINCTION IS THE WHOLE POINT.** That arm is the best of 33 chosen AFTER seeing them; its p-value is undeflated, it was never pre-registered as its own hypothesis, and reading it as shippable here would be exactly the E2.1-r inversion — re-reading a field until something in it clears. It belongs in its OWN pre-registered story (a rookie-point LEVEL recalibration of NF1.4's documented cold bias), where it gets a clean gate and its own deflation.

⭐ **AND IT SHARPENS §3's MECHANISM FINDING RATHER THAN CONTRADICTING IT — read the two together.** The matched foil showed the AVAILABILITY arm's lift is NOT a level correction (the constant built at its own base fails to beat the incumbent at RB and TE). This lead shows a level correction independently DOES help. Both are true, and they are SEPARATE effects: NF-D14's mechanism claim was wrong about what makes the availability arm win, and right that there is something cold to correct. Neither statement implies the other, and collapsing them is how a report ends up asserting more than it measured.

## 4. What this does to the board (the ordering movement, measured)

| position   | arm                               |   mean abs Δ (PPR) |   max abs Δ (PPR) |   mean abs rank Δ | tier displacements   | would ship   |
|:-----------|:----------------------------------|-------------------:|------------------:|------------------:|:---------------------|:-------------|
| RB         | learned scale · λ 1               |            21.3700 |          124.6300 |            2.5000 | 11 of 42             | no           |
| TE         | learned scale · λ 1               |            12.0200 |           62.5900 |            1.7400 | 2 of 21              | no           |
| WR         | MATCHED FOIL mean[residual] · λ 1 |             3.6000 |           27.0000 |            0.0000 | 0 of 56              | no           |

A scale that does no ordering harm can still MOVE the board; 'no harm' is a statement about rank correlation with the realized outcome, not about the board being unchanged. The churn above is what a user would actually see, and it is reported because a projection change nobody can see is not worth shipping and one that reshuffles a tier silently is worth knowing about.

## 5. Honest limitations

- ⚠️ **THE SELECTED ARM IS DEPTH-DRIVEN, SO THE PROVENANCE CAVEAT IS LIVE AND IT IS A HARD PRECONDITION ON ANY FUTURE REVIVAL.** The availability signal is REUSED, so NF-D14's caveats are inherited in full — most importantly that the historical depth feature is the WEEK-1 chart (a post-final-cuts read) while the live board reads an August `stg_nfl_depth_charts_current` snapshot. The proxy is therefore marginally FRESHER than the served signal and can only FLATTER the historical fit. Nothing ships here, so no re-measurement was required to reach this verdict — but **the measured lift above is an UPPER BOUND on what the served signal could deliver, and any story that revives this arm must FIRST re-measure it on the served August snapshot.** That is also why `ratio_residual` (the depth increment ALONE, net of draft capital) is registered and reported separately: it is the arm whose provenance risk is largest and most legible.
- **The learned foil's training-row point projections are IN-SAMPLE for that fold's slot curve.** It learns the multiplicative correction against a point that is slightly better-fitted than the held-out point it is then applied to, so the correction it learns is if anything UNDER-stated. The direction is conservative — it cannot manufacture the lift — but it is not zero, and a revival should fit the correction against out-of-fold training predictions.
- ⛔ **QB is out of scope by pre-registration, not by result.** NF-D14 measured the double-pricing (+16.8% MAE, bias −10.66 → +11.36) and this story does not re-open it. A future story that wants rookie-QB availability in the point needs to model what the slot curve already prices, not to multiply on top of it.
- **`tier_mae` grades the DRAFTABLE TIER, which is ~6 RB / 8 WR / 3 TE per class.** A per-position claim here is a claim about a few dozen rookie-seasons across seven classes; the paired per-class deltas are reported so the reader can see the spread rather than only the mean.
- **Do-no-ordering-harm is a rank-correlation constraint, not a promise the board will not move.** §4 reports the actual churn — mean |Δ| in PPR, rank movement, and tier displacements — because 'no harm' and 'no change' are different claims and only the first one is being made.
- **The scale is bounded** (`SCALE_CLIP`, and a floor on every ratio denominator). Those bounds are physical rather than tuned — a rookie cannot play negative games — but they do mean this story's `ratio_pos` arm is not byte-identical to NF-D14 §6's unbounded form. Both are computed and the §6 form is reported as the wiring proof, so the difference is visible rather than implied.
- **No edge claim.** A projection-quality product: `best_alpha = 0`, no CLV/ROI statement.

