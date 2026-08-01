# NF-D16 — a per-position LEVEL recalibration of the rookie POINT (RB/TE/WR) — §0.5 bake-off

**Generated:** 2026-08-01T04:22:52.721341+00:00 · **held-out draft classes:** 2019–2025 (7) · **arms:** 17 · **held-out rookie-seasons (RB/TE/WR):** 472 · **framing:** PRE-REGISTERED `pooled` · **DSR reading:** PRE-REGISTERED `whole_field`

## ⭐ VERDICT — 🟡 RECORDED NULL — no pre-registered level recalibration clears its own gate; the shipped rookie point STANDS

**The pre-registered pooled test selects `incumbent (NULL)`**, moving the pooled draftable-tier MAE **0.9407 → 0.9407** (Δ 0.0) over 7 held-out draft classes, with PBO 0.0571, whole-field DSR None (the pre-registered gate, ≥ 0.95) and a one-sided paired p of 1.0 against α = 0.1. **Failing gate(s): `['recalibrates', 'beats_incumbent', 'dsr_ok', 'significant']`.**

⭐ **AND THE RUN ANSWERS ITS OWN SCOPING QUESTION, WHICH IS THE MOST DURABLE THING IN IT.** The gap between the incumbent and the PEEKING per-position constant is real and large (0.0152 pooled tier MAE), and the story pre-registered two readings of it: either a better-estimated constant closes more of it, or the correct constant is strongly class-to-class variable and therefore not learnable in-fold at all. **The run supports the second.** The in-fold estimate does not predict the held-out class's own constant better than 'predict 1.0' does (`skill_vs_null` -0.0166), so the headroom the oracle displays is not available to any real estimator — which converts 'there is room here, keep trying' into a measured 'there is not', and closes the lead rather than deferring it.

⇒ **RECORDED NULL — and NF-D15's second lead is now CLOSED rather than left dangling.** The clean pre-registration is the whole point: the effect that motivated this story was the best of 33 arms chosen after seeing them, and asked as its own hypothesis under a framing fixed in advance it does not clear its gate. The shipped rookie point STANDS, the interval is untouched, and the QB exclusion was never re-opened.

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. ⛔ **QB is EXCLUDED by pre-registration and PROVEN untouched** (max |Δ| over every arm and every held-out QB: **0.000000000** PPR). 🔒 The rookie INTERVAL's WIDTH model is untouched — NF-D14 settled that question.

## 0. What was pre-registered, and when

Everything that could otherwise have been chosen after seeing a result is a CONSTANT in `rookie_point_recalibration.py`; this report READS those constants rather than restating them, so 'what was pre-registered' has exactly one owner.

| decision               | value                                        | why (written BEFORE the run)                                                                                                                                                                                                                                                                                                                                                                                                           |
|:-----------------------|:---------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| framing                | pooled                                       | A LEVEL effect is a-priori COMMON across positions (NF1.4's documented bias is the same sign and comparable magnitude at RB/WR/TE), and the ship UNIT is the whole per-position constant vector — a level recalibration is ONE change to `project_rookies` that applies at RB/TE/WR together or not at all. Splitting one hypothesis into three tests pays a multiplicity penalty for a decomposition the hypothesis does not require. |
| DSR reading that BINDS | whole_field                                  | NF-D14 and NF-D15 were both bitten by a deflation statistic computed over a field containing its own weak arms. Naming which reading binds in advance is what stops that from becoming a choice made after seeing the answer.                                                                                                                                                                                                          |
| DSR level              | 0.95                                         | The STRICTER of the two available bars (NF-D14/NF-D15's rather than NF1.4's 0.0), because this hypothesis was surfaced by re-reading NF-D15's field — a story born that way must not also be granted a looser bar than the field it was born in.                                                                                                                                                                                       |
| α (single hypothesis)  | 0.1                                          | One test under the pooled framing, so NF1.4's q is used directly as α with NO multiplicity correction. The per-position reading's 3-test BH-FDR is computed as a DISCLOSURE in §3d and does not gate.                                                                                                                                                                                                                                  |
| selection metric       | tier_mae                                     | NF1.4's draftable-tier MAE, INHERITED. The incumbent rookie point was selected on it; grading a change to that same product on a different metric is metric-shopping.                                                                                                                                                                                                                                                                  |
| forms                  | mult_const, add_offset, mult_tier, ols_slope | ≥3 correction classes + a direct-learned foil + the incumbent NULL. Two are monotone (zero ordering movement by construction) and two can reorder — which is what gives the ordering constraint something to refuse instead of passing vacuously.                                                                                                                                                                                      |

🚨 **THE MOTIVATION IS NOT THE RESULT.** NF-D15 observed a per-position constant beating the incumbent at all three scaled positions. That observation was the best of 33 arms chosen AFTER seeing the field, undeflated, and never registered as its own hypothesis — it is the REASON this story exists and it is cited exactly once, in `rookie_point_recalibration`'s module docstring, labelled as prior motivation. It appears nowhere in this report as evidence. If the clean pre-registration shrinks the effect, **the shrinkage is the answer** (E2.1-r).

## 1. The metric, the constraint, and the anchor set

**Primary metric — `tier_mae`, NF1.4's, INHERITED RATHER THAN CHOSEN.** The draftable-tier MAE on a tier FIXED by the incumbent's own projection (NF1.1's fixed-anchor rule, so no arm can buy a friendlier subset), pooled scale-free over RB/TE/WR for the pre-registered pooled test and reported per position in raw PPR beside it.

**The constraint — DO NO ORDERING HARM**, `ORDERING_DO_NO_HARM = 0.02`, NF1.4's own constant inherited verbatim, checked PER POSITION and never as a pooled mean. ⚠️ **It is NON-BINDING for the two monotone forms BY CONSTRUCTION and BINDING for the other two** — which is precisely why both kinds are in the field. A field of only constants would leave the constraint passing having examined nothing.

### The anchors, scored on THIS run

| anchor                   | what it is                                                                                               |   pooled tier MAE |   tier MAE RB |   tier MAE TE |   tier MAE WR |   universe MAE |
|:-------------------------|:---------------------------------------------------------------------------------------------------------|------------------:|--------------:|--------------:|--------------:|---------------:|
| oracle_perplayer         | ORACLE FLOOR, full resolution (peeks per player). Nothing may beat it.                                   |            0.0000 |        0.0000 |        0.0000 |        0.0000 |         0.0040 |
| oracle_posconst          | CEILING of the `mult_const` family — the held-out class's OWN per-position constant.                     |            0.9255 |       73.7190 |       38.8510 |       66.4010 |        42.1160 |
| oracle_addoffset         | CEILING of the `add_offset` family.                                                                      |            0.8750 |       70.1390 |       37.5860 |       60.7470 |        42.4930 |
| oracle_tierconst         | CEILING of the `mult_tier` family (RICHER than a constant).                                              |            0.8126 |       62.6840 |       38.4140 |       53.2840 |        37.8420 |
| oracle_ols               | CEILING of the `ols_slope` family (RICHER than a constant).                                              |            0.7785 |       59.4700 |       32.2730 |       58.2060 |        38.9980 |
| permuted_across          | constants from outcomes shuffled ACROSS positions — the level structure destroyed. Must LOSE.            |            1.0398 |       75.0340 |       53.9640 |       65.5960 |        47.6710 |
| permuted_within          | constants from outcomes shuffled WITHIN position — the marginal PRESERVED. ⭐ EXPECTED TO TIE (see §4b). |            0.9413 |       72.1490 |       42.2900 |       66.0270 |        46.2560 |
| zero_scale               | DEGENERATE — project nothing. Must LOSE.                                                                 |            2.0477 |      139.7000 |      105.3140 |      140.3610 |        62.2900 |
| pos_median               | DEGENERATE — NF1.4's MAE-collapse tell. Wins an INVERTED metric; must LOSE this one.                     |            1.6691 |      110.8560 |       86.5930 |      115.2810 |        54.0390 |
| → INCUMBENT (NULL)       | the shipped rookie point, unchanged                                                                      |            0.9407 |       72.3070 |       42.2870 |       65.3370 |        42.9640 |
| → BEST RECALIBRATION ARM | mult_tier · λ 0.5                                                                                        |            0.9265 |       72.1940 |       42.7830 |       61.8570 |        41.4710 |

- ✅ both degenerates lose the primary metric — it is not paying for pessimism
- ✅ the truth beats the ACROSS-position permutation — the per-position level structure is real information
- ✅ the full-resolution oracle floor holds
- ✅ every arm respects **its own form's** peeking ceiling (16 arms checked at MATCHED family and MATCHED resolution)
- ✅ QB is untouched on real emitted projections, not merely by assertion

⭐ **The degenerate check comes back NEGATIVE, and it is reported because it was SCORED, not because it was expected.** `zero_scale` (2.0477) and NF1.4's `pos_median` MAE-collapse tell (1.6691) both lose decisively to the reference arm (0.9265). NF-D14's refinement of the NF-D11 landmine is why this is a measurement rather than an argument: **MAE inverts when the conditional MEDIAN sits at the floor, not merely when the zero atom is fat** — and on the RB/TE/WR DRAFTABLE TIER the median is nowhere near zero. The right response to that rule is to keep the degenerate in the field and READ it every run, which is what this line is.

⭐ **ONE CEILING PER FORM, NOT ONE FOR THE FIELD — and the first cut of this story had it wrong.** A peeking oracle is a floor only at MATCHED FAMILY *and* MATCHED RESOLUTION (NF1.7 (b) / NF1.9 (f)). `mult_tier` and `ols_slope` each CONTAIN the per-position constant as a special case, so either can legitimately score better than the best possible constant — a capacity effect, not an inversion. Flooring the whole field on `oracle_posconst` would have vetoed a real result for the wrong reason; each arm is therefore checked against the peeking version of its OWN form, where 'peeking can only help' genuinely holds:

| arm                 | form       | ceiling_anchor   |   ceiling |   arm_metric |   margin | ok   |
|:--------------------|:-----------|:-----------------|----------:|-------------:|---------:|:-----|
| mult_const · λ 0.25 | mult_const | oracle_posconst  |    0.9255 |       0.9452 |   0.0197 | True |
| mult_const · λ 0.5  | mult_const | oracle_posconst  |    0.9255 |       0.9507 |   0.0252 | True |
| mult_const · λ 0.75 | mult_const | oracle_posconst  |    0.9255 |       0.9563 |   0.0308 | True |
| mult_const · λ 1    | mult_const | oracle_posconst  |    0.9255 |       0.9629 |   0.0374 | True |
| add_offset · λ 0.25 | add_offset | oracle_addoffset |    0.8750 |       0.9407 |   0.0657 | True |
| add_offset · λ 0.5  | add_offset | oracle_addoffset |    0.8750 |       0.9407 |   0.0657 | True |
| add_offset · λ 0.75 | add_offset | oracle_addoffset |    0.8750 |       0.9407 |   0.0657 | True |
| add_offset · λ 1    | add_offset | oracle_addoffset |    0.8750 |       0.9407 |   0.0657 | True |
| mult_tier · λ 0.25  | mult_tier  | oracle_tierconst |    0.8126 |       0.9291 |   0.1165 | True |
| mult_tier · λ 0.5   | mult_tier  | oracle_tierconst |    0.8126 |       0.9265 |   0.1139 | True |
| mult_tier · λ 0.75  | mult_tier  | oracle_tierconst |    0.8126 |       0.9266 |   0.1140 | True |
| mult_tier · λ 1     | mult_tier  | oracle_tierconst |    0.8126 |       0.9315 |   0.1189 | True |
| ols_slope · λ 0.25  | ols_slope  | oracle_ols       |    0.7785 |       0.9407 |   0.1622 | True |
| ols_slope · λ 0.5   | ols_slope  | oracle_ols       |    0.7785 |       0.9407 |   0.1622 | True |
| ols_slope · λ 0.75  | ols_slope  | oracle_ols       |    0.7785 |       0.9408 |   0.1623 | True |
| ols_slope · λ 1     | ols_slope  | oracle_ols       |    0.7785 |       0.9408 |   0.1623 | True |

## 2. The full field (pooled over RB/TE/WR)

| arm                 | recal?   | monotone?             |   pooled tier MAE |   tier MAE RB |   tier MAE TE |   tier MAE WR |   universe MAE |   universe bias |
|:--------------------|:---------|:----------------------|------------------:|--------------:|--------------:|--------------:|---------------:|----------------:|
| mult_tier · λ 0.5   | yes      | —                     |            0.9265 |       72.1940 |       42.7830 |       61.8570 |        41.4710 |         -5.3020 |
| mult_tier · λ 0.75  | yes      | —                     |            0.9266 |       72.4200 |       43.0310 |       61.3400 |        41.0670 |         -5.2510 |
| mult_tier · λ 0.25  | yes      | —                     |            0.9291 |       72.0100 |       42.5360 |       62.8770 |        42.0370 |         -5.3530 |
| mult_tier · λ 1     | yes      | —                     |            0.9315 |       72.6440 |       43.3510 |       61.6870 |        40.8880 |         -5.1990 |
| incumbent (NULL)    | —        |                       |            0.9407 |       72.3070 |       42.2870 |       65.3370 |        42.9640 |         -5.4050 |
| add_offset · λ 0.25 | yes      | yes (0 rank movement) |            0.9407 |       72.3070 |       42.2890 |       65.3370 |        42.9640 |         -5.4050 |
| add_offset · λ 0.5  | yes      | yes (0 rank movement) |            0.9407 |       72.3070 |       42.2890 |       65.3370 |        42.9640 |         -5.4050 |
| add_offset · λ 0.75 | yes      | yes (0 rank movement) |            0.9407 |       72.3070 |       42.2890 |       65.3370 |        42.9640 |         -5.4050 |
| add_offset · λ 1    | yes      | yes (0 rank movement) |            0.9407 |       72.3070 |       42.2890 |       65.3370 |        42.9640 |         -5.4050 |
| ols_slope · λ 0.25  | yes      | —                     |            0.9407 |       72.3070 |       42.2890 |       65.3370 |        42.9640 |         -5.4050 |
| ols_slope · λ 0.5   | yes      | —                     |            0.9407 |       72.3070 |       42.2890 |       65.3370 |        42.9640 |         -5.4050 |
| ols_slope · λ 0.75  | yes      | —                     |            0.9408 |       72.3070 |       42.2890 |       65.3370 |        42.9640 |         -5.4050 |
| ols_slope · λ 1     | yes      | —                     |            0.9408 |       72.3070 |       42.2890 |       65.3370 |        42.9640 |         -5.4050 |
| mult_const · λ 0.25 | yes      | yes (0 rank movement) |            0.9452 |       72.5090 |       42.6300 |       65.5760 |        42.8550 |         -6.3480 |
| mult_const · λ 0.5  | yes      | yes (0 rank movement) |            0.9507 |       72.7130 |       42.9700 |       66.0190 |        42.7720 |         -7.2920 |
| mult_const · λ 0.75 | yes      | yes (0 rank movement) |            0.9563 |       72.9190 |       43.3130 |       66.4940 |        42.7000 |         -8.2360 |
| mult_const · λ 1    | yes      | yes (0 rank movement) |            0.9629 |       73.1210 |       43.7260 |       67.0610 |        42.6500 |         -9.1790 |

## 3. ⭐ THE PRE-REGISTERED POOLED SELECTION — one hypothesis, one test

The ship UNIT is the WHOLE per-position constant vector: a level recalibration is ONE change to `project_rookies` that applies at RB/TE/WR together or not at all. Eligible arms (13 of 17) are those that are shippable AND do no ordering harm at EVERY scaled position.

|   incumbent pooled tier MAE | selected arm     |   pooled tier MAE |   Δ vs incumbent |    PBO |   Bailey degradation % |   contender spread % | DSR (whole-field, THE GATE)   | DSR (contender, reported)   |   one-sided paired p (1 test) |   α (pre-registered) |
|----------------------------:|:-----------------|------------------:|-----------------:|-------:|-----------------------:|---------------------:|:------------------------------|:----------------------------|------------------------------:|---------------------:|
|                      0.9407 | incumbent (NULL) |            0.9407 |           0.0000 | 0.0571 |                 0.0000 |               0.0000 |                               |                             |                        1.0000 |               0.1000 |

Per-class deltas (incumbent − winner, > 0 ⇒ the winner is better): `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]` over classes `[2019, 2020, 2021, 2022, 2023, 2024, 2025]`.

**The flip distribution** (NF1.8: a rank statistic alone cannot tell a TIE from an unstable pick — mass on two arms a fraction of a percent apart IS a tie; mass spread thinly over a dozen unrelated arms is a search that learnt nothing):

| config              |   IS-half wins |   share |   full-sample pooled tier MAE |   Δ vs best % |
|:--------------------|---------------:|--------:|------------------------------:|--------------:|
| incumbent (NULL)    |             33 |  0.9430 |                        0.9410 |        0.0000 |
| mult_const · λ 0.75 |              1 |  0.0290 |                        0.9560 |        1.6500 |
| mult_const · λ 0.25 |              1 |  0.0290 |                        0.9450 |        0.4800 |

**Ship decision under the pre-registered framing:** `{'ship': False, 'framing': 'pooled', 'has_eligible_winner': True, 'recalibrates': False, 'beats_incumbent': False, 'ordering_ok_every_position': True, 'pbo_ok': True, 'dsr_ok': False, 'significant': False}`

### 3b. Is the answer resting on a gate level I chose? — the sensitivity, computed

| DSR whole-field (THE GATE)   | DSR contender-set (reported)   | ships at pre-registered DSR ≥ 0.95   | ships at NF1.4's DSR ≥ 0.0   | ships with the DSR dropped entirely   | ships on the CONTENDER DSR reading   |
|:-----------------------------|:-------------------------------|:-------------------------------------|:-----------------------------|:--------------------------------------|:-------------------------------------|
|                              |                                | False                                | False                        | False                                 | False                                |

⭐ **THE ANSWER DOES NOT TURN ON THE DISPUTABLE GATE, AND THAT IS THE POINT OF COMPUTING IT.** Nothing ships even with the DSR removed ENTIRELY and even on the kinder contender-set reading, because `['recalibrates', 'beats_incumbent', 'significant']` blocks independently. So the verdict is not an artefact of pre-registering the stricter of the two DSR bars, nor of naming the whole-field reading as the binding one — a reader who disagrees with either choice reaches the same verdict.

### 3c. The margin in DRAFT CLASSES — what kind of answer this is

|   classes now | mean Δ (pooled tier MAE)   | sd Δ   |   one-sided p |   α (single hypothesis) | classes needed   |
|--------------:|:---------------------------|:-------|--------------:|------------------------:|:-----------------|
|             7 |                            |        |        1.0000 |                  0.1000 |                  |

NF1.8's 'state the margin in ROWS' convention, one unit over. A p-value decimal cannot distinguish **underpowered** from **absent**: an effect that needs a plausible number of further draft classes is a story to re-run when they exist; one that needs dozens is a null at any n this program will ever have.

### 3d. ⭐ THE DISCLOSED PER-POSITION READING — the framing this story did NOT pre-register

NF-D15 pre-registered per-position and disclosed pooled; NF-D16 does the exact opposite, and owes the same duty. **Reported, never selected on** — the pre-registered pooled framing governs (E2.1-r). This table exists so 'the framing did not decide the answer' is a number rather than a shrug.

| position   |   incumbent_metric | winner             |   metric |   delta |    pbo |      dsr |   pvalue | BH-FDR (3 tests)   |
|:-----------|-------------------:|:-------------------|---------:|--------:|-------:|---------:|---------:|:-------------------|
| RB         |            72.3071 | mult_tier · λ 0.25 |  72.0100 | -0.2970 | 0.8286 |   0.4457 |   0.4117 | no                 |
| TE         |            42.2871 | incumbent (NULL)   |  42.2871 |  0.0000 | 0.1429 | nan      |   1.0000 | no                 |
| WR         |            65.3371 | mult_tier · λ 0.75 |  61.3400 | -3.9970 | 0.2857 |   0.0956 |   0.2001 | no                 |

BH cutoff a position must clear UNCONDITIONALLY under the 3-test framing: **0.0333** — against the pooled framing's α of **0.1**. ✅ **The two framings AGREE**: neither the pooled single-hypothesis test nor any per-position BH-FDR survivor clears its bar, so the pre-registered choice of framing did not decide the answer.

## 4. ⭐ THE CEILING GAP, READ — is a better constant available, or is the truth class-variable?

|   incumbent (pooled tier MAE) |   best candidate |   CEILING (peeking per-position constant) |   headroom (inc − ceiling) |   captured (inc − candidate) |   share of headroom captured |   in-fold skill vs 'predict 1.0' |
|------------------------------:|-----------------:|------------------------------------------:|---------------------------:|-----------------------------:|-----------------------------:|---------------------------------:|
|                        0.9407 |           0.9407 |                                    0.9255 |                     0.0152 |                       0.0000 |                       0.0000 |                          -0.0166 |

The peeking per-position constant is the CEILING of this entire family: pooled tier MAE **0.9255** against the incumbent's **0.9407**, i.e. **0.0152** of headroom exists IN PRINCIPLE for a per-position level correction. The best candidate captured **0.0** of it (0.0%). ⇒ **READING (B) — CLASS-VARIABLE, i.e. THE CEILING IS UNREACHABLE IN PRINCIPLE.** The in-fold estimate does **not** predict the held-out class's own constant better than the incumbent's implicit 1.0 does (`skill_vs_null` -0.0166; mean |error| 0.2461 in-fold vs 0.2421 for 'predict 1.0'). The correct constant swings from draft class to draft class faster than any in-fold estimator can follow, so the headroom the peeking oracle shows is **not available to a real estimator at any level of estimator effort**. ⭐ That distinction is the whole reason the ceiling was computed: a large gap to a peeking oracle looks like an invitation to keep trying, and here it is a measurement that further trying would not pay. This is the reading the run supports.

**The per-class constants themselves** — the raw material of that reading:

| position   |   sd_of_peek_constant |   mean_peek_constant |   mean_infold_constant |   skill_vs_null |
|:-----------|----------------------:|---------------------:|-----------------------:|----------------:|
| RB         |                0.1725 |               0.9770 |                 0.9167 |         -0.1647 |
| TE         |                0.3352 |               1.0508 |                 0.9531 |         -0.0202 |
| WR         |                0.3804 |               1.0812 |                 0.9401 |          0.0488 |

|   class | position   |   k_infold |   k_peek |   err_infold |   err_null |
|--------:|:-----------|-----------:|---------:|-------------:|-----------:|
|    2019 | RB         |     0.9136 |   0.7351 |       0.1785 |     0.2649 |
|    2019 | TE         |     0.9409 |   0.7987 |       0.1422 |     0.2013 |
|    2019 | WR         |     0.9509 |   1.5302 |       0.5793 |     0.5302 |
|    2020 | RB         |     0.9056 |   1.0078 |       0.1022 |     0.0078 |
|    2020 | TE         |     0.9551 |   0.5084 |       0.4467 |     0.4916 |
|    2020 | WR         |     0.9620 |   1.2748 |       0.3128 |     0.2748 |
|    2021 | RB         |     0.9023 |   1.1759 |       0.2737 |     0.1759 |
|    2021 | TE         |     0.9523 |   1.3237 |       0.3714 |     0.3237 |
|    2021 | WR         |     0.9395 |   0.6568 |       0.2827 |     0.3432 |
|    2022 | RB         |     0.9154 |   0.9473 |       0.0319 |     0.0527 |
|    2022 | TE         |     0.9460 |   1.4697 |       0.5236 |     0.4697 |
|    2022 | WR         |     0.9276 |   0.7795 |       0.1481 |     0.2205 |
|    2023 | RB         |     0.9247 |   0.7687 |       0.1560 |     0.2313 |
|    2023 | TE         |     0.9593 |   0.9124 |       0.0468 |     0.0876 |
|    2023 | WR         |     0.9316 |   1.5943 |       0.6627 |     0.5943 |
|    2024 | RB         |     0.9210 |   1.0578 |       0.1368 |     0.0578 |
|    2024 | TE         |     0.9537 |   1.0762 |       0.1226 |     0.0762 |
|    2024 | WR         |     0.9372 |   0.8338 |       0.1033 |     0.1662 |
|    2025 | RB         |     0.9342 |   1.1467 |       0.2125 |     0.1467 |
|    2025 | TE         |     0.9646 |   1.2665 |       0.3019 |     0.2665 |
|    2025 | WR         |     0.9316 |   0.8987 |       0.0329 |     0.1013 |

⚠️ **A THIRD EXPLANATION THE STORY'S FRAMING DID NOT NAME — IN-SAMPLE OPTIMISM, measured at -0.0564.** The in-fold constant is estimated against point projections the fold's OWN slot curve was fitted on, so those points are better calibrated than the held-out ones the constant is then applied to. The same draft class yields a different constant depending on whether its points came from a curve that had seen it (`k_in_sample_point`) or not (`k_out_of_sample_point`), and the gap between them is a part of the ceiling gap that is neither 'a better estimator' nor 'the truth moves'. The direction is CONSERVATIVE — it biases the estimated correction toward 1, i.e. it UNDER-states it — so it cannot manufacture a lift, but it is not zero.

|   class | position   |   k_in_sample_point |   k_out_of_sample_point |   optimism |
|--------:|:-----------|--------------------:|------------------------:|-----------:|
|    2019 | RB         |              0.7353 |                  0.7351 |     0.0002 |
|    2019 | TE         |              0.7996 |                  0.7987 |     0.0008 |
|    2019 | WR         |              1.2721 |                  1.5302 |    -0.2581 |
|    2020 | RB         |              0.9505 |                  1.0078 |    -0.0573 |
|    2020 | TE         |              0.5000 |                  0.5084 |    -0.0084 |
|    2020 | WR         |              1.0921 |                  1.2748 |    -0.1827 |
|    2021 | RB         |              1.1544 |                  1.1759 |    -0.0215 |
|    2021 | TE         |              1.1225 |                  1.3237 |    -0.2012 |
|    2021 | WR         |              0.6350 |                  0.6568 |    -0.0218 |
|    2022 | RB         |              0.9580 |                  0.9473 |     0.0107 |
|    2022 | TE         |              1.3810 |                  1.4697 |    -0.0886 |
|    2022 | WR         |              0.7429 |                  0.7795 |    -0.0366 |
|    2023 | RB         |              0.7795 |                  0.7687 |     0.0107 |
|    2023 | TE         |              0.8646 |                  0.9124 |    -0.0478 |
|    2023 | WR         |              1.4815 |                  1.5943 |    -0.1128 |
|    2024 | RB         |              1.0520 |                  1.0578 |    -0.0058 |
|    2024 | TE         |              1.0794 |                  1.0762 |     0.0032 |
|    2024 | WR         |              0.8355 |                  0.8338 |     0.0016 |

### 4b. ⭐ THE PERMUTATION ANCHOR IS NEAR-VACUOUS AGAINST A LEVEL HYPOTHESIS — measured, not glossed

`add_offset`'s statistic is `mean(y) − mean(point)`, which is EXACTLY invariant under a within-position permutation of `y`. Measured over every position and every held-out class, the maximum absolute difference between the real offset and the within-permuted one is **0.000000000000** — exactly invariant, as the algebra requires. That is why BOTH permutations are in the anchor set: the WITHIN-position one is expected to tie and is reported as a property of the hypothesis (a level IS a marginal statistic), while the ACROSS-position one is the anchor that actually has to be beaten. Presenting a near-tie as a passed permutation test would be a check that examined nothing.

## 5. Ordering — the structural claim, MEASURED on emitted projections

| form       | expected monotone (0 rank movement)   |   max rank movement RB |   max rank movement TE |   max rank movement WR |   worst | structural claim holds   |
|:-----------|:--------------------------------------|-----------------------:|-----------------------:|-----------------------:|--------:|:-------------------------|
| mult_const | True                                  |                 0.0000 |                 0.0000 |                 0.0000 |  0.0000 | True                     |
| add_offset | True                                  |                 0.0000 |                 0.0000 |                 0.0000 |  0.0000 | True                     |
| mult_tier  | False                                 |                 5.0000 |                 2.0000 |                13.0000 | 13.0000 | True                     |
| ols_slope  | False                                 |                 0.0000 |                 0.0000 |                 0.0000 |  0.0000 | True                     |

⭐ The two **monotone-by-construction** forms must show max rank movement exactly 0 at every position — a strictly monotone transform of a position's projections moves no rank. Two things could break that in practice and neither is visible in the algebra (a multiplicative constant clipping to different values in different cells; the physical floor at 0 creating TIES among rookies an additive offset pushed below zero), so the claim is checked on the numbers the arms actually emit rather than asserted from their definitions.

⚠️ **`ols_slope` IS ONLY *CONDITIONALLY* MONOTONE, AND THIS RUN'S ZERO IS A MEASUREMENT RATHER THAN A PROPERTY OF THE FORM.** An affine `a + b·point` moves no rank when `b > 0` and INVERTS a whole position's board when `b < 0`. Every fitted slope in this run is positive (`all_slopes_positive` = True, range 0.9999–1.0002 over 21 position × class fits), which is WHY its measured rank movement is 0 — not because the form guarantees it. A future draft class that produced a negative slope would flip that, and the ordering CONSTRAINT (not the form's description) is what would catch it. **`mult_tier` is the only form that genuinely reorders** — and it is ineligible at every λ for exactly that reason, which is what makes the constraint non-vacuous in this field.

**The fitted corrections themselves** — what the arms actually apply, per class and position:

|   class | position   |   mult_const k |   add_offset c (PPR) |   ols intercept |   ols slope |
|--------:|:-----------|---------------:|---------------------:|----------------:|------------:|
|    2019 | RB         |         0.9136 |              -0.0008 |         -0.0030 |      1.0000 |
|    2019 | TE         |         0.9409 |               0.0004 |          0.0010 |      1.0000 |
|    2019 | WR         |         0.9509 |               0.0015 |         -0.0070 |      1.0002 |
|    2020 | RB         |         0.9056 |               0.0009 |         -0.0030 |      1.0001 |
|    2020 | TE         |         0.9551 |               0.0006 |         -0.0010 |      1.0000 |
|    2020 | WR         |         0.9620 |              -0.0002 |          0.0010 |      1.0000 |
|    2021 | RB         |         0.9023 |              -0.0009 |         -0.0020 |      1.0000 |
|    2021 | TE         |         0.9523 |               0.0027 |          0.0010 |      1.0000 |
|    2021 | WR         |         0.9395 |              -0.0009 |          0.0060 |      0.9999 |
|    2022 | RB         |         0.9154 |              -0.0010 |         -0.0000 |      1.0000 |
|    2022 | TE         |         0.9460 |              -0.0017 |         -0.0000 |      1.0000 |
|    2022 | WR         |         0.9276 |               0.0002 |         -0.0040 |      1.0001 |
|    2023 | RB         |         0.9247 |               0.0011 |          0.0000 |      1.0000 |
|    2023 | TE         |         0.9593 |               0.0026 |          0.0060 |      0.9999 |
|    2023 | WR         |         0.9316 |               0.0001 |         -0.0010 |      1.0000 |
|    2024 | RB         |         0.9210 |              -0.0004 |         -0.0000 |      1.0000 |
|    2024 | TE         |         0.9537 |               0.0006 |          0.0020 |      1.0000 |
|    2024 | WR         |         0.9372 |              -0.0004 |          0.0030 |      0.9999 |
|    2025 | RB         |         0.9342 |              -0.0004 |          0.0000 |      1.0000 |
|    2025 | TE         |         0.9646 |               0.0002 |          0.0040 |      0.9999 |
|    2025 | WR         |         0.9316 |               0.0001 |          0.0000 |      1.0000 |

### ⭐ 5b. THE CHECK THIS STORY'S FRAMING DID NOT ANTICIPATE — rookies move against VETERANS

The story's risk argument is 'a level shift moves no ranks, so it is the low-risk half.' That is true WITHIN a position and **false across the board**: rookies and veterans share ONE draft board, so lifting every rookie necessarily moves rookies UP against veterans — and NF1.4 already owns the gate for that failure, because MVP-3 dogfooding surfaced a rookie floating to #1 overall.

⭐⭐ **AND THE GATE IS TWO-SIDED, WHICH IS THE ONLY REASON IT IS USABLE HERE.** NF1.4 measured that the COLD incumbent breaches the level cap in **0 of 28** cohort-positions while the REALIZED outcomes breach it in **9 of 28**. A projection that never projects above what a strong class's best rookie actually does is not passing this gate — it is displaying exactly the coldness NF1.4 documented. So 'zero breaches' is the SYMPTOM, not the target, and **reality's own breach rate is the reference**:

|   cohort-positions |   incumbent breaches (cold) |   → CANDIDATE breaches |   REALITY breaches (the reference) | over-corrected?   |
|-------------------:|----------------------------:|-----------------------:|-----------------------------------:|:------------------|
|                 28 |                           0 |                      0 |                                  9 | no                |

⚠️ **DISCLOSED: this check was added AFTER the run showed the arm clearing its pre-registered gate.** That is admissible in exactly one direction — it can only VETO a ship, never enable one, and it cannot change which arm the pre-registered metric selected. A constraint that can only make the story more conservative is not metric-shopping; one that could have manufactured the win would be. ⏭️ Only the LEVEL half is computable in this harness — the 'no rookie in an overall top-10 slot' half needs veterans on the same board and is checked by `season_projection.rookie_board_face_validity` at export time, so it is named as an OPERATOR step rather than claimed as passed here.

|   class | incumbent   | candidate   | reality                        |
|--------:|:------------|:------------|:-------------------------------|
|    2019 | —           | —           | QB 285.3>277.5                 |
|    2020 | —           | —           | QB 332.8>286.4, WR 274.2>244.1 |
|    2021 | —           | —           | WR 304.6>266.8, TE 176.6>156.1 |
|    2022 | —           | —           | —                              |
|    2023 | —           | —           | WR 298.5>286.4, TE 239.3>174.8 |
|    2024 | —           | —           | QB 355.8>300.7, TE 262.7>195.4 |
|    2025 | —           | —           | —                              |

### What a shipped recalibration would do to the board

| position   | arm              |   mean abs Δ (PPR) |   max abs Δ (PPR) |   mean abs rank Δ | tier displacements   | would ship   |
|:-----------|:-----------------|-------------------:|------------------:|------------------:|:---------------------|:-------------|
| RB         | incumbent (NULL) |             0.0000 |            0.0000 |            0.0000 | 0 of 42              | no           |
| TE         | incumbent (NULL) |             0.0000 |            0.0000 |            0.0000 | 0 of 21              | no           |
| WR         | incumbent (NULL) |             0.0000 |            0.0000 |            0.0000 | 0 of 56              | no           |

Reported whether or not anything ships — if nothing ships this is the size of what was declined, which is the number a reader needs to judge whether the null is expensive.

## 6. Honest limitations

- ⭐ **NO DEPTH-CHART PROVENANCE CAVEAT APPLIES HERE, and that is a deliberate design property rather than luck.** NF-D14/NF-D15's measured lift carries a hard upper-bound qualifier because their availability signal reads a WEEK-1 depth chart historically and an AUGUST snapshot live. NF-D16's forms are estimated from exactly two quantities the board already owns — the served point projection and the realized rookie fantasy points — so there is no train/serve provenance asymmetry to bound. This is why `mult_const` was registered as the clean in-fold mean of `realized / point` rather than inherited from NF-D15's `mean_ratio` foil, which was a mean of a DEPTH-derived ratio and would have dragged the caveat into a story that touches no depth feature.
- **The in-fold constants are estimated against IN-SAMPLE point projections.** The training rows' points come from the fold's own slot curve, which was fitted on them, so they are better calibrated than the held-out points the constant is then applied to. §4 measures the resulting optimism directly. The direction is CONSERVATIVE — it biases the estimated correction toward 1, i.e. UNDER-states it, so it cannot manufacture a lift — but it is not zero, and a revival should estimate the correction against out-of-fold training predictions.
- ⛔ **QB is out of scope by pre-registration, not by result.** NF-D14 MEASURED the rookie-QB double-pricing and NF-D15 enforced the exclusion at max drift 0.0; NF-D16 inherits the scope by IMPORT (`RECALIBRATED_POSITIONS` is `rookie_point_scaling.SCALED_POSITIONS`) so the two stories cannot drift apart. Whether the rookie-QB point is cold is a separate question this story does not answer.
- **`tier_mae` grades the DRAFTABLE TIER — ~6 RB / 8 WR / 3 TE per class.** A claim here is a claim about a few dozen rookie-seasons across seven draft classes; the paired per-class deltas are reported so a reader sees the spread rather than only the mean.
- **The permutation anchor is WEAK against this hypothesis by construction**, and §4b measures rather than glosses it: a level is a MARGINAL statistic, so a within-position permutation preserves it exactly for the additive form. The ACROSS-position permutation is the one that has to be beaten, and the anchors that do the real work here are the family CEILING and the two degenerates.
- **Do-no-ordering-harm is a rank-correlation constraint, not a promise the board will not move** — though for the two monotone forms it is a promise the ORDER will not move, which §5 measures at exactly 0. The PPR magnitudes still change, and §5 reports that churn.
- **No edge claim.** A projection-quality product: `best_alpha = 0`, no CLV/ROI statement.

