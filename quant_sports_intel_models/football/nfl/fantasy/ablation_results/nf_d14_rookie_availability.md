# NF-D14 — the ROOKIE-QB AVAILABILITY prior (§0.5 bake-off)

**Generated:** 2026-07-31T20:52:28.734174+00:00 · **held-out draft classes:** 2019–2025 (7) · **leg-1 configs:** 49 · **leg-2 arms:** 15 · **held-out rookie-seasons:** 553

## ⭐ VERDICT — 🟡 CLEAN NULL — no availability form clears the pre-registered gate; NF1.8's band STANDS and the floor does NOT move

**Leg 1 — the availability signal is LARGE AND MEASURABLE, but does NOT clear the pre-registered deflation gate.** `tier_empirical[depth] · blend 1` cuts the held-out games CRPS from the position-empirical null's 3.2273 to 2.4546 (23.9% better overall; **31.1% at QB**), beats its own permutation (3.5195) decisively, scores BETTER than the peeking oracle (2.977) — which is the NF1.9 (f) CAPACITY effect, not an inversion, and the floor is therefore gated at MATCHED n, where it holds (2.977 ≤ 3.1677); see §1, and both degenerates lose. Deflation: PBO 0.0, DSR 0.0693 (gate ≥ 0.95 — the one gate it fails; see §3 for why that reading is not obvious and why it does not change the story's outcome), Bailey degradation 1.756%. Gate detail: `{'prior_is_real': False, 'beats_null': True, 'oracle_respected': True, 'degenerates_lose': True, 'permutation_beaten': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': True}`.

**Leg 2 — the story's GATE.** Rookie-QB held-out coverage under the SHIPPED NF1.8 band is 0.8148 at an interval score of 183.407. The selection rule (argmin interval score among floor-clearing arms) picks `SHIPPED NF1.8 band (NULL)` (IS80 183.407, QB 0.8148). Gate detail: `{'ship': False, 'qb_coverage_improves': False, 'floors_met': True, 'no_interval_score_harm': False, 'pbo_ok': False, 'point_invariant': True, 'selected_arm_uses_availability': False, 'anchor_degenerates_lose': True, 'anchor_permutation_beaten': True, 'anchor_oracle_respected': True}`.

⇒ **RECORDED NULL — and it is the answer, not a failure.** This story pre-registered that outcome: NF1.8's own diagnosis was that the residual rookie-QB gap is class-to-class VARIANCE on a ~12-QB/class cohort rather than fittable miscalibration, and that diagnosis now has a second, independent confirmation — a measurably real availability signal, fed into the band through both pre-registered channels and both pre-registered drivers, does not close it. **The QB interval variance is irreducible at this N.** The shipped NF1.8 band STANDS, the coverage floor does NOT move (E2.1-r; NF1.8 §1), and the question is retired rather than left open for a third recalibration attempt.

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. 🔒 The rookie POINT projection is byte-identical across every leg-2 arm (max drift **0.000000** PPR) — a band story must not smuggle a point change.

## 0. The cohort — reported BEFORE any fit, because the N *is* the risk

| position   |   held-out rookie-seasons |   classes |   per class |   played ZERO games |   zero rate |   mean games |   median games |   depth-proxy present |
|:-----------|--------------------------:|----------:|------------:|--------------------:|------------:|-------------:|---------------:|----------------------:|
| QB         |                        81 |         7 |     11.6000 |                  25 |      0.3090 |       5.9600 |         4.0000 |                0.7780 |
| RB         |                       148 |         7 |     21.1000 |                  11 |      0.0740 |      11.1900 |        13.0000 |                0.8450 |
| WR         |                       224 |         7 |     32.0000 |                  18 |      0.0800 |      11.5900 |        14.0000 |                0.8210 |
| TE         |                       100 |         7 |     14.3000 |                  10 |      0.1000 |      11.2300 |        13.5000 |                0.8200 |

**This is the whole risk of the story.** A rookie-QB availability prior is fitted on ~12 QBs a class; NF1.8 already showed the residual QB interval gap is class-to-class VARIANCE on exactly this cohort. A clean deflated NULL was pre-registered as a legitimate outcome.

⚠️ **PROVENANCE OF THE DEPTH-CHART PROXY.** The historical signal is the **week-1** depth chart (`stg_nfl_depth_charts`, weekly partitions back to 2001); the live board reads an August `stg_nfl_depth_charts_current` snapshot. The week-1 read is *post-final-cuts* and therefore marginally FRESHER than what the board has at draft time, which can only FLATTER the historical fit. Draft-capital-only (`capital`) arms are pre-registered beside every depth arm so the story always has an unambiguous-provenance answer — see §2.

## 1. Selection metric — the DISCRETE CRPS, and the MAE inversion measured live

```
CRPS(F, y) = Σ_{g=0..17} ( F(g) − 1{g ≥ y} )²                      (lower is better)
```

Proper (uniquely minimised by the true predictive), on the integer support the outcome actually lives on — which matters because this target has a large point mass at exactly 0 and a hard ceiling at 17, and a Normal CRPS would misprice both.

⚠️ **THE MAE INVERSION, MEASURED PER POSITION — not asserted, and not pooled.** The `all_zero` degenerate ('project zero games for every rookie') scores MAE **10.593** pooled against the winner's **3.991**, and **5.963** vs **3.789** AT QB.

⭐ **The pooling would be the point if the inversion fired — so it is checked PER POSITION, because the effect is a property of the ZERO RATE and only QB carries a fat atom** (RB/WR/TE sit at 7–10%). At QB the degenerate **does NOT win** MAE. **The check comes back NEGATIVE here, and the reason sharpens the rule rather than excusing it.**

⚠️ **REFINEMENT OF THE LANDMINE, worth carrying forward: MAE inverts when the conditional MEDIAN is at (or next to) ZERO — NOT merely when the zero ATOM is fat.** MAE is minimised at the median, so a nihilist wins only if zero *is* the median. NF-D11's returner cohort had 43% zeros AND a median of 1 game, so it inverted. This rookie-QB cohort has 0.309 zeros but a median of **4.0 games** — the atom is fat, the median is not zero, and MAE duly does NOT invert (5.963 for the degenerate vs 3.789 for the winner). ⇒ **'zero-heavy' is not the test; score the degenerate and READ IT.** Which is exactly why the degenerate is in the field every run rather than reasoned about — this is the anchor set earning its keep by coming back negative.

CRPS is the selection metric either way, and it orders correctly in every reading: degenerate **10.5118** (QB 5.9259) against the winner's **2.4546** (QB 2.3246). MAE/RMSE stay reported; they are never selectable.

| anchor / arm        | what it is                                                                                                                         |    CRPS |   CRPS QB |   MAE games |   MAE QB |
|:--------------------|:-----------------------------------------------------------------------------------------------------------------------------------|--------:|----------:|------------:|---------:|
| oracle_empirical    | ORACLE FLOOR — the held-out class's OWN realized per-position games distribution. Peeks; nothing may beat it.                      |  2.9770 |    3.1725 |      4.8010 |   5.2580 |
| matched_n_candidate | the NF1.9 (f) guard that makes that floor well-posed — the winner's own arm trained on ONE prior class.                            |  3.1677 |    4.4943 |      5.0450 |   6.6690 |
| permuted            | the winner's own family fitted on SHUFFLED training outcomes. Same family, same n; only information moves. Must LOSE to the truth. |  3.5195 |    4.1801 |      5.5720 |   6.3810 |
| all_zero            | DEGENERATE — all mass at 0 games. Wins MAE; must LOSE CRPS.                                                                        | 10.5118 |    5.9259 |     10.5930 |   5.9630 |
| all_mean            | DEGENERATE — all mass at the pooled mean. Must LOSE.                                                                               |  5.4358 |    6.2963 |      5.5170 |   6.3330 |
| → LEG-1 WINNER      | tier_empirical[depth] · blend 1                                                                                                    |  2.4546 |    2.3246 |      3.9910 |   3.7890 |
| → NULL              | pos_empirical (NULL)                                                                                                               |  3.2273 |    3.3745 |      5.1890 |   5.2590 |

⭐ **READ THIS BEFORE READING THE ORACLE ROW: the winner (2.4546) SCORES BETTER THAN THE PEEKING ORACLE (2.977), and that is NOT a metric inversion — it is the NF1.9 (f) capacity effect, reproduced.** A peeking oracle is a floor only at MATCHED FAMILY *and* MATCHED SAMPLE SIZE. This oracle fits the ~79-row held-out class; the winner is fitted on ~500 training rows, so it estimates the same family's parameters far more precisely. Capacity, not leakage. **The check is therefore gated at matched n**: the oracle must beat `matched_n_candidate` — the winner's own arm trained on ONE prior class — and it does (2.977 ≤ 3.1677). The PERMUTATION anchor (3.5195) is the one that is well-posed at any n, and it is beaten decisively.

- ✅ the oracle floor holds AT MATCHED n (the only reading of it that is well-posed)
- ✅ both degenerates lose the primary metric
- ✅ the truth beats its own permutation

## 2. Leg 1 — the availability bake-off (all configs, sorted by the primary metric)

| config                                       |   CRPS |   CRPS QB |   CRPS RB |   CRPS WR |   CRPS TE |   MAE games |   RMSE games |
|:---------------------------------------------|-------:|----------:|----------:|----------:|----------:|------------:|-------------:|
| tier_empirical[depth] · blend 1              | 2.4546 |    2.3246 |    2.5244 |    2.3648 |    2.6578 |      3.9910 |       4.6870 |
| hurdle_logit[capital+depth+p1a] · blend 1    | 2.4588 |    2.4066 |    2.5431 |    2.3842 |    2.5432 |      4.0620 |       4.6980 |
| hurdle_logit[capital+depth] · blend 1        | 2.4596 |    2.3961 |    2.5490 |    2.3863 |    2.5431 |      4.0680 |       4.7000 |
| tier_empirical[round_depth] · blend 1        | 2.4980 |    2.4436 |    2.5974 |    2.3697 |    2.6821 |      4.1160 |       4.7720 |
| tier_empirical[depth] · blend 0.7            | 2.5629 |    2.5094 |    2.6108 |    2.4612 |    2.7632 |      4.2870 |       4.8990 |
| learned_gbm[capital+depth] · blend 1         | 2.5634 |    2.5946 |    2.6932 |    2.4311 |    2.6424 |      3.9840 |       4.6970 |
| learned_gbm[capital+depth+p1a] · blend 1     | 2.5668 |    2.5643 |    2.7514 |    2.4195 |    2.6259 |      4.0050 |       4.7150 |
| learned_gbm[capital+depth] · blend 0.7       | 2.5925 |    2.7011 |    2.6684 |    2.4691 |    2.6683 |      4.2570 |       4.8830 |
| learned_gbm[capital+depth+p1a] · blend 0.7   | 2.5956 |    2.6823 |    2.7122 |    2.4596 |    2.6576 |      4.2710 |       4.8960 |
| hurdle_logit[capital+depth+p1a] · blend 0.7  | 2.6061 |    2.5767 |    2.6623 |    2.5457 |    2.6821 |      4.3640 |       4.9730 |
| hurdle_logit[capital+depth] · blend 0.7      | 2.6069 |    2.5693 |    2.6664 |    2.5478 |    2.6820 |      4.3680 |       4.9750 |
| tier_empirical[round_depth] · blend 0.7      | 2.6318 |    2.6384 |    2.6914 |    2.5060 |    2.8203 |      4.4030 |       5.0220 |
| learned_gbm[capital+depth] · blend 0.5       | 2.6928 |    2.8328 |    2.7293 |    2.5808 |    2.7763 |      4.4930 |       5.1030 |
| tier_empirical[depth] · blend 0.5            | 2.6939 |    2.6946 |    2.7170 |    2.5935 |    2.8841 |      4.5190 |       5.1250 |
| learned_gbm[capital+depth+p1a] · blend 0.5   | 2.6955 |    2.8205 |    2.7621 |    2.5734 |    2.7690 |      4.5050 |       5.1120 |
| haircut_ratio[capital+depth+p1a] · blend 0.7 | 2.7089 |    2.7405 |    2.8285 |    2.6316 |    2.6792 |      4.4080 |       5.1290 |
| haircut_ratio[capital+depth] · blend 0.7     | 2.7131 |    2.7382 |    2.8281 |    2.6353 |    2.6967 |      4.4120 |       5.1330 |
| haircut_ratio[capital+depth+p1a] · blend 0.5 | 2.7313 |    2.8466 |    2.7946 |    2.6483 |    2.7301 |      4.5710 |       5.2150 |
| haircut_ratio[capital+depth] · blend 0.5     | 2.7348 |    2.8450 |    2.7957 |    2.6513 |    2.7426 |      4.5730 |       5.2190 |
| hurdle_logit[capital+depth+p1a] · blend 0.5  | 2.7440 |    2.7473 |    2.7721 |    2.6876 |    2.8258 |      4.5850 |       5.2050 |
| hurdle_logit[capital+depth] · blend 0.5      | 2.7447 |    2.7420 |    2.7750 |    2.6894 |    2.8257 |      4.5880 |       5.2060 |
| tier_empirical[round_depth] · blend 0.5      | 2.7615 |    2.8084 |    2.7887 |    2.6452 |    2.9439 |      4.6170 |       5.2380 |
| haircut_ratio[capital+depth+p1a] · blend 0.3 | 2.8543 |    3.0128 |    2.8620 |    2.7730 |    2.8967 |      4.7900 |       5.4200 |
| haircut_ratio[capital+depth] · blend 0.3     | 2.8567 |    3.0118 |    2.8635 |    2.7750 |    2.9042 |      4.7930 |       5.4230 |
| learned_gbm[capital+depth] · blend 0.3       | 2.8580 |    3.0131 |    2.8523 |    2.7616 |    2.9568 |      4.7560 |       5.3890 |
| learned_gbm[capital+depth+p1a] · blend 0.3   | 2.8598 |    3.0064 |    2.8729 |    2.7568 |    2.9526 |      4.7640 |       5.3940 |
| haircut_ratio[capital+depth+p1a] · blend 1   | 2.8637 |    2.6939 |    3.0694 |    2.8089 |    2.8197 |      4.2840 |       5.2320 |
| haircut_ratio[capital+depth] · blend 1       | 2.8682 |    2.6904 |    3.0646 |    2.8132 |    2.8448 |      4.2870 |       5.2360 |
| tier_empirical[depth] · blend 0.3            | 2.8720 |    2.9293 |    2.8622 |    2.7802 |    3.0455 |      4.7750 |       5.4080 |
| hurdle_logit[capital] · blend 1              | 2.8972 |    2.6786 |    3.0000 |    2.8733 |    2.9758 |      4.6560 |       5.3960 |
| tier_empirical[round] · blend 1              | 2.8977 |    2.5024 |    3.1452 |    2.8500 |    2.9584 |      4.5980 |       5.4070 |
| hurdle_logit[capital+depth+p1a] · blend 0.3  | 2.9135 |    2.9638 |    2.9063 |    2.8570 |    3.0103 |      4.8210 |       5.4710 |
| hurdle_logit[capital+depth] · blend 0.3      | 2.9140 |    2.9607 |    2.9080 |    2.8583 |    3.0102 |      4.8230 |       5.4710 |
| tier_empirical[round] · blend 0.7            | 2.9195 |    2.6486 |    3.0871 |    2.8592 |    3.0259 |      4.7330 |       5.4600 |
| tier_empirical[round_depth] · blend 0.3      | 2.9236 |    3.0107 |    2.9136 |    2.8231 |    3.0928 |      4.8390 |       5.4900 |
| hurdle_logit[capital] · blend 0.7            | 2.9543 |    2.8015 |    3.0141 |    2.9294 |    3.0452 |      4.7900 |       5.5030 |
| tier_empirical[round] · blend 0.5            | 2.9708 |    2.8011 |    3.0772 |    2.9056 |    3.0966 |      4.8470 |       5.5460 |
| hurdle_logit[capital] · blend 0.5            | 3.0123 |    2.9243 |    3.0387 |    2.9814 |    3.1138 |      4.8940 |       5.6000 |
| learned_gbm[capital] · blend 0.5             | 3.0191 |    2.9663 |    3.0622 |    2.9907 |    3.0616 |      4.8760 |       5.5950 |
| learned_gbm[capital] · blend 0.7             | 3.0260 |    2.8854 |    3.1169 |    3.0104 |    3.0402 |      4.7920 |       5.5470 |
| tier_empirical[round] · blend 0.3            | 3.0514 |    2.9975 |    3.0902 |    2.9842 |    3.1879 |      4.9710 |       5.6700 |
| learned_gbm[capital] · blend 0.3             | 3.0637 |    3.0943 |    3.0594 |    3.0216 |    3.1397 |      4.9890 |       5.6910 |
| hurdle_logit[capital] · blend 0.3            | 3.0863 |    3.0798 |    3.0753 |    3.0450 |    3.2003 |      5.0040 |       5.7150 |
| haircut_ratio[capital] · blend 0.3           | 3.1080 |    3.1389 |    3.1406 |    3.0460 |    3.1737 |      5.0700 |       5.7700 |
| learned_gbm[capital] · blend 1               | 3.1331 |    2.8523 |    3.2967 |    3.1346 |    3.1148 |      4.7140 |       5.5680 |
| haircut_ratio[capital] · blend 0.5           | 3.1704 |    3.0551 |    3.2869 |    3.1193 |    3.2059 |      5.0630 |       5.8150 |
| pos_empirical (NULL)                         | 3.2273 |    3.3745 |    3.1530 |    3.1624 |    3.3635 |      5.1890 |       5.9210 |
| haircut_ratio[capital] · blend 0.7           | 3.3464 |    3.0301 |    3.5570 |    3.3132 |    3.3652 |      5.1270 |       5.9730 |
| haircut_ratio[capital] · blend 1             | 3.8232 |    3.1025 |    4.1942 |    3.8303 |    3.8421 |      5.3220 |       6.4040 |

## 3. Leg 1 deflation — CSCV/PBO + Bailey's companions, DSR, BH-FDR

**PBO = 0.0** over 35 balanced class splits · Bailey performance degradation (median OS gap) **1.756%** · contender (top-quartile) spread **7.26%** · whole-field spread **55.71%** · **DSR = 0.0693** (pre-registered gate ≥ 0.95).

⚠️ **THE DSR IS THE ONE GATE THIS SIGNAL FAILS, AND THE READING IS NOT OBVIOUS — so both readings are given and the PRE-REGISTERED one binds.** `deflated_sharpe`'s expected-max-SR term scales with the DISPERSION of the trial Sharpes, and this field deliberately CONTAINS its own known-bad arms (the worst config scores 55.71% off the best). So the whole-field DSR deflates against the NULLS rather than against the contest at the top — the NF1.8 lesson ('a spread computed over a field that contains its own nulls measures the nulls') one statistic over. Restricted to the CONTENDER set the same statistic reads **0.9448**.

**The pre-registered gate is the whole-field DSR and it stands: the leg-1 signal does not clear it.** The contender reading is reported so the two are distinguishable, NOT to re-open the gate after seeing the answer — that would be the E2.1-r inversion. ⭐ And in the event the distinction is moot: even the GENEROUS reading (0.9448) sits below the pre-registered 0.95, so there is no version of this statistic under which the signal clears its bar.

⭐ **Either way it does not change the story's outcome: leg 2 is a null under BOTH readings** (§4). Worth saying plainly, because a gate that only binds when it is convenient is not a gate.

⚠️ Reading it (CLAUDE.md + NF1.8): PBO alone cannot tell *'my pick is unstable'* from *'my pick is tied'*, and a whole-field spread computed over a field that CONTAINS its own nulls measures the nulls. The flip distribution below is the discriminator — mass on two arms a fraction of a percent apart is a TIE; mass spread thinly over a dozen unrelated arms is a search that has learnt nothing.

| config                                    |   IS-half wins |   share |   full-sample IS80 |   Δ vs best % |
|:------------------------------------------|---------------:|--------:|-------------------:|--------------:|
| tier_empirical[depth] · blend 1           |             16 |  0.4570 |             2.4540 |        0.0000 |
| hurdle_logit[capital+depth+p1a] · blend 1 |             12 |  0.3430 |             2.4600 |        0.2600 |
| hurdle_logit[capital+depth] · blend 1     |              6 |  0.1710 |             2.4610 |        0.2900 |
| tier_empirical[round_depth] · blend 1     |              1 |  0.0290 |             2.4990 |        1.8100 |

Per-position one-sided paired p-values of the winner's lift over the null: `{'QB': 0.019, 'RB': 0.0198, 'WR': 0.0002, 'TE': 0.0044}` → BH-FDR (q=0.1) survivors: `{'QB': True, 'RB': True, 'WR': True, 'TE': True}`.

## 4. Leg 2 — what it does to the rookie interval (NF1.8's machinery, unchanged)

The winner's per-player availability read is attached as `avail_risk_z` and scored through NF1.8's OWN harness: the same folds, the same row-pooled reducer, the same per-position floors, the same Winkler interval score. Two channels (a quantile-regression FEATURE, and a strictly WIDEN-ONLY widener) × two drivers.

⭐ **`sd` is the principled driver and `pshort` the naive one, pre-registered together.** Availability risk is NOT monotone in expected games — it peaks where the outcome is a coin flip (a 7th-round QB3 at `p_play ≈ 0.05` is confidently near-zero; a second-rounder in an open camp battle at `p_play ≈ 0.5` is not). A 'bust risk' widener would widen the wrong rookies.

| arm                                     |     IS80 |   cov80 |   cov QB |   cov RB |   cov TE |   cov WR |   mean width |   QB width | floors met                            |
|:----------------------------------------|---------:|--------:|---------:|---------:|---------:|---------:|-------------:|-----------:|:--------------------------------------|
| +avail FEATURE+WIDEN [pshort] gain 0.35 | 174.4630 |  0.8373 |   0.8395 |   0.7973 |   0.8700 |   0.8482 |     132.5800 |   141.9000 | NO (RB 0.7973<0.800)                  |
| +avail FEATURE+WIDEN [pshort] gain 0.2  | 175.1380 |  0.8318 |   0.8148 |   0.7973 |   0.8600 |   0.8482 |     130.3000 |   135.4000 | NO (RB 0.7973<0.800)                  |
| +avail FEATURE+WIDEN [pshort] gain 0.1  | 175.6240 |  0.8300 |   0.8025 |   0.7973 |   0.8600 |   0.8482 |     129.0600 |   131.9000 | NO (RB 0.7973<0.800)                  |
| +avail FEATURE [pshort]                 | 176.0980 |  0.8228 |   0.7778 |   0.7905 |   0.8600 |   0.8438 |     127.9900 |   129.0000 | NO (QB 0.7778<0.800; RB 0.7905<0.800) |
| SHIPPED NF1.8 band (NULL)               | 183.4070 |  0.8354 |   0.8148 |   0.8041 |   0.9000 |   0.8348 |     130.7500 |   166.0000 | yes                                   |
| +avail WIDEN [pshort] gain 0.1          | 184.6060 |  0.8608 |   0.8642 |   0.8243 |   0.9300 |   0.8527 |     133.2300 |   173.3000 | yes                                   |
| +avail WIDEN [sd] gain 0.1              | 185.3510 |  0.8517 |   0.8272 |   0.8176 |   0.9300 |   0.8482 |     133.9500 |   177.1000 | yes                                   |
| +avail FEATURE+WIDEN [sd] gain 0.2      | 185.7290 |  0.8535 |   0.8025 |   0.8243 |   0.8900 |   0.8750 |     132.4700 |   175.3000 | yes                                   |
| +avail FEATURE+WIDEN [sd] gain 0.35     | 185.7640 |  0.8626 |   0.8272 |   0.8243 |   0.9100 |   0.8795 |     136.0600 |   187.4000 | yes                                   |
| +avail FEATURE [sd]                     | 186.0840 |  0.8391 |   0.8025 |   0.8108 |   0.8600 |   0.8616 |     127.8800 |   159.4000 | yes                                   |
| +avail FEATURE+WIDEN [sd] gain 0.1      | 186.2140 |  0.8535 |   0.8025 |   0.8243 |   0.8900 |   0.8750 |     130.4000 |   168.5000 | yes                                   |
| +avail WIDEN [sd] gain 0.2              | 186.9540 |  0.8553 |   0.8395 |   0.8176 |   0.9300 |   0.8527 |     136.7200 |   185.9000 | yes                                   |
| +avail WIDEN [pshort] gain 0.2          | 187.0610 |  0.8626 |   0.8765 |   0.8243 |   0.9300 |   0.8527 |     136.0000 |   181.4000 | yes                                   |
| +avail WIDEN [sd] gain 0.35             | 190.7700 |  0.8608 |   0.8519 |   0.8243 |   0.9400 |   0.8527 |     141.6000 |   201.5000 | yes                                   |
| +avail WIDEN [pshort] gain 0.35         | 192.1000 |  0.8644 |   0.8889 |   0.8243 |   0.9300 |   0.8527 |     141.1200 |   196.7000 | yes                                   |

**SELECTION RULE (NF1.8's, unchanged): argmin interval score among the arms that clear EVERY per-position floor.** The NULL is in that field. Selected: **`SHIPPED NF1.8 band (NULL)`** (IS80 183.407, QB coverage 0.8148).

⚠️ **Two things in this table are the whole leg-2 result, and both are pre-registered landmines firing rather than surprises:**

1. **The WIDEN arms buy rookie-QB coverage by paying interval score.** That is a coverage TARGET winning, and it is exactly what E2.1-r/NF1.8 forbid: coverage is a FLOOR, never something to maximise, because 'more headroom above the floor' is MONOTONE IN WIDENING — the `max_width` degenerate wins that criterion outright. An arm that widens QB and loses the proper score has not improved the interval; it has moved along the width axis.
2. **The availability FEATURE channel can make QB coverage WORSE.** Handed the driver as a quantile-regression feature, the fit is free to SHARPEN the rookies whose availability it considers predictable, and it does. That is the NF1.7 (d) hazard — a two-sided knob on an uncertainty covariate — showing up on a channel where the widen-only clamp does not apply, and it is why the widener carries `clip(z, 0, 2)` while the feature does not pretend to.

### The anchor set, re-scored on THIS run

| anchor       |     IS80 |   cov80 |   cov QB |   mean width |
|:-------------|---------:|--------:|---------:|-------------:|
| oracle_qreg  | 159.2710 |  0.8698 |   0.8148 |     125.4500 |
| oracle_knn   | 174.7930 |  0.8354 |   0.7901 |     125.8300 |
| permuted_own | 227.2420 |  0.8807 |   0.8395 |     169.5000 |
| zero_width   | 431.9980 |  0.0036 |   0.0000 |       0.1000 |
| max_width    | 305.9950 |  0.9819 |   0.9506 |     302.1600 |
| const_width  | 230.0060 |  0.8770 |   0.8519 |     166.0900 |

Checks: `{'degenerates_lose': True, 'permutation_beaten': True, 'oracle_respected': True}`. ⭐ `max_width` is the constraint-vs-criterion proof (NF1.8): it SATISFIES every coverage floor and still loses the primary metric by a wide margin — which is the right shape. A constraint a degenerate satisfies is fine, because the metric eliminates it; a CRITERION a degenerate wins is fatal.

### 4b. ⭐ THE NEAR-MISS — the most tempting number in this story, stated in ROWS

The SHARPEST arm in the whole field is **`+avail FEATURE+WIDEN [pshort] gain 0.35`** at IS80 **174.463** — **4.88% better** than the shipped band, and it lifts rookie QB too. It is **INELIGIBLE**.

| position   |   n |   floor |   coverage |   covered rows |   rows the floor requires |   shortfall (rows) |
|:-----------|----:|--------:|-----------:|---------------:|--------------------------:|-------------------:|
| QB         |  81 |  0.8000 |     0.8395 |             68 |                        65 |                 -3 |
| RB         | 148 |  0.8000 |     0.7973 |            118 |                       119 |                  1 |
| TE         | 100 |  0.8000 |     0.8700 |             87 |                        80 |                 -7 |
| WR         | 224 |  0.8000 |     0.8482 |            190 |                       180 |                -10 |

**We are not taking it, and the reason has to be stated precisely rather than implied.**

- The miss is small — a shortfall of a handful of covered rookie-seasons — and NF1.8's own power analysis says a hard point-estimate floor at nominal rejects a PERFECTLY-calibrated arm about half the time. So this arm may well be fine. That is *not* a reason to admit it: the same argument admits every arm that misses by a little, in every direction, forever.
- **The documented Tier-2 fallback does not rescue it either, and its trigger condition is not met.** Tier 2 relaxes only the structurally-thin positions (`('QB',)`) and only when Tier 1 admits NO config — Tier 1 admits several here. Scored anyway as a sensitivity: Tier-2 floors `{'QB': 0.7269, 'RB': 0.8, 'TE': 0.8, 'WR': 0.8}` would **STILL REJECT** this arm.
- Admitting it would be **reverse-engineering the floor from the answer** — the E2.1-r inversion facing the other way, and precisely what NF1.8 §1 forbids. A floor that moves until something clears it is not a floor.

⚠️ Note also WHICH arm it is: the sharpening comes from the availability driver entering as a quantile-regression FEATURE, i.e. from the fit being free to NARROW the rookies whose availability it thinks it can predict. It buys the primary metric by under-covering, and the per-position floor is the thing that caught it. That is the floor doing its job on a live example, not a technicality.

### The per-position floor margin, in ROWS (the NF1.8 convention)

A coverage decimal hides how few outcomes a per-position floor rests on. 'QB 0.741 → 0.815' reads like a calibration change; it is **six covered rookie-seasons out of 81**.

| position   |   n (held-out) |   floor |   coverage — NULL (shipped NF1.8) |   coverage — best ELIGIBLE availability arm |   slack rows — NULL |   slack rows — availability arm |   mean width — NULL |   mean width — availability arm |
|:-----------|---------------:|--------:|----------------------------------:|--------------------------------------------:|--------------------:|--------------------------------:|--------------------:|--------------------------------:|
| QB         |             81 |  0.8000 |                            0.8148 |                                      0.8642 |                   1 |                               5 |            166.0000 |                        173.3000 |
| RB         |            148 |  0.8000 |                            0.8041 |                                      0.8243 |                   0 |                               3 |            124.3000 |                        125.9000 |
| TE         |            100 |  0.8000 |                            0.9000 |                                      0.9300 |                  10 |                              13 |            107.4000 |                        108.7000 |
| WR         |            224 |  0.8000 |                            0.8348 |                                      0.8527 |                   7 |                              11 |            132.7000 |                        134.5000 |

## 5. Leg 2 deflation

**PBO = 0.3714** over 35 splits · Bailey degradation 0.973% · contender (top-quartile) spread 1.32% · eligible configs 11.

| config                              |   IS-half wins |   share |   full-sample IS80 |   Δ vs best % |
|:------------------------------------|---------------:|--------:|-------------------:|--------------:|
| SHIPPED NF1.8 band (NULL)           |             22 |  0.6290 |           183.5390 |        0.0000 |
| +avail FEATURE [sd]                 |             10 |  0.2860 |           186.4030 |        1.5600 |
| +avail FEATURE+WIDEN [sd] gain 0.35 |              2 |  0.0570 |           185.9570 |        1.3200 |
| +avail FEATURE+WIDEN [sd] gain 0.2  |              1 |  0.0290 |           185.9770 |        1.3300 |

## 6. The POINT channel — measured, reported, NOT shipped

Scaling the rookie point projection by the availability prior's expected-games ratio is the other thing an availability prior can drive, and the story asked for the point change to be ATTRIBUTABLE. So it is measured rather than argued about:

| position   |   n |   MAE base |   MAE availability-scaled |   bias base |   bias availability-scaled |
|:-----------|----:|-----------:|--------------------------:|------------:|---------------------------:|
| QB         |  81 |    50.1500 |                   58.5600 |    -10.6600 |                    11.3600 |
| RB         | 148 |    46.4000 |                   42.8600 |    -19.6900 |                   -15.9700 |
| TE         | 100 |    31.2400 |                   30.0500 |    -16.0100 |                   -14.2700 |
| WR         | 224 |    44.0100 |                   41.9200 |    -23.8200 |                   -19.9800 |

⚠️ **THE RESULT IS SPLIT, AND NOT IN THE DIRECTION THE STORY ASSUMED — so it is reported as measured rather than summarised into the expected shape.** The ratio is not a haircut: it exceeds 1 for high-capital rookies, so at RB, TE, WR it modestly IMPROVES MAE by partially correcting the COLD bias NF1.4 documented (tier bias RB −58 / WR −49 / TE −44 PPR).

⭐ **And it BREAKS the one position this story is about.** At QB it moves MAE **50.15 → 58.56** (**+16.8%**) and flips the bias from **-10.66** (cold) to **+11.36** (hot) — because a rookie QB's expected games already vary enormously with draft capital, so the slot curve has effectively priced that variation once and the ratio prices it a second time.

⇒ **The point channel is DECLINED on the evidence, not on principle.** A change that helps three positions a little and damages the fourth badly is not a projection improvement; it is a trade nobody asked for, on the position the story exists to fix. The shipped rookie point is unchanged and byte-identical (§0), and this table is the attribution.

## 7. Honest limitations

- **The depth-chart proxy is FRESHER than the served signal.** The historical feature is the WEEK-1 depth chart (a post-final-cuts read); the live board reads an August `stg_nfl_depth_charts_current` snapshot. That can only FLATTER the historical fit, which is why the draft-capital-only arms are pre-registered beside every depth arm and reported in full.
- **`n` is small by construction** — ~12 drafted QBs a class, 81 held-out rookie-QB seasons over seven classes. A per-position claim on that cohort is a claim about six or seven covered rows; the floor margins are therefore reported in ROWS, not in coverage decimals (NF1.8's convention).
- **The prior predicts GAMES, not the per-game line.** A rookie who plays 17 games as a backup and one who plays 17 as a starter are the same availability outcome; the ROLE term lives in the point projection's depth-chart features, not here.
- **A coverage floor is a CONSTRAINT, never a target** (E2.1-r; NF1.8 §1). No arm is preferred for having more headroom above the floor — that criterion is monotone in widening, so the `max_width` degenerate wins it outright.
- **No edge claim.** This is a projection-quality product: `best_alpha = 0`, no CLV/ROI statement.
- ⭐ **ONE OPEN LEAD, recorded rather than pursued (it is a different story).** §6's point channel IMPROVES held-out MAE at RB/TE/WR by 1.2–3.5 PPR, by partially correcting the COLD bias NF1.4 measured. NF-D14 declines it because it BREAKS QB and because a NON-QB point change is outside this story's pre-registered scope — selecting it here would be scope creep dressed as a finding. If a future story wants it, it needs its OWN §0.5 gate on the point (a proper score, the do-no-ordering-harm constraint, and per-position deflation), not this story's interval gate.

