# NF-D16 — a per-position LEVEL recalibration of the rookie POINT (RB/TE/WR) — §0.5 bake-off

**Generated:** 2026-08-01T04:22:48.477330+00:00 · **held-out draft classes:** 2019–2025 (7) · **arms:** 17 · **held-out rookie-seasons (RB/TE/WR):** 472 · **framing:** PRE-REGISTERED `pooled` · **DSR reading:** PRE-REGISTERED `whole_field`

## ⭐ VERDICT — ✅ SHIP — a per-position LEVEL recalibration of the rookie point at RB/TE/WR

**The pre-registered pooled test selects `ols_slope · λ 1`**, moving the pooled draftable-tier MAE **1.0738 → 0.9407** (Δ -0.1331) over 7 held-out draft classes, with PBO 0.0286, whole-field DSR 0.9963 (the pre-registered gate, ≥ 0.95) and a one-sided paired p of 0.0033 against α = 0.1.

⭐ **THE CEILING GAP READS (A) — ESTIMABLE.** The in-fold estimate carries real information about the next class's constant (`skill_vs_null` 0.3056) and the candidate captured 0.1331 of the 0.2954 available headroom, so the remaining gap is estimator quality rather than an unreachable target.

⇒ **SHIP.** The recalibration improves the metric the incumbent rookie point was itself selected on, does no ordering harm at any scaled position, and clears the pre-registered deflation and significance gates under the framing chosen before the run. ⚠️ It moves the rookie band's CENTRE, so `run_interval_revalidation` must be re-run and every coverage floor re-confirmed before this reaches the board. QB stays exactly where NF-D14 left it.

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
| oracle_posconst          | CEILING of the `mult_const` family — the held-out class's OWN per-position constant.                     |            0.9091 |       75.0040 |       38.8570 |       62.1310 |        40.6900 |
| oracle_addoffset         | CEILING of the `add_offset` family.                                                                      |            0.9107 |       70.7990 |       43.3990 |       59.2710 |        43.0780 |
| oracle_tierconst         | CEILING of the `mult_tier` family (RICHER than a constant).                                              |            0.8354 |       63.0560 |       38.9030 |       56.9240 |        38.1010 |
| oracle_ols               | CEILING of the `ols_slope` family (RICHER than a constant).                                              |            0.7784 |       59.4690 |       32.2690 |       58.2040 |        38.9960 |
| permuted_across          | constants from outcomes shuffled ACROSS positions — the level structure destroyed. Must LOSE.            |            1.1247 |       77.0330 |       50.9690 |       86.9010 |        49.0950 |
| permuted_within          | constants from outcomes shuffled WITHIN position — the marginal PRESERVED. ⭐ EXPECTED TO TIE (see §4b). |            1.0949 |       74.1630 |       47.9560 |       87.9230 |        49.2330 |
| zero_scale               | DEGENERATE — project nothing. Must LOSE.                                                                 |            2.0477 |      139.7000 |      105.3140 |      140.3610 |        62.2900 |
| pos_median               | DEGENERATE — NF1.4's MAE-collapse tell. Wins an INVERTED metric; must LOSE this one.                     |            1.6691 |      110.8560 |       86.5930 |      115.2810 |        54.0390 |
| → INCUMBENT (NULL)       | the shipped rookie point, unchanged                                                                      |            1.0738 |       80.4300 |       53.9190 |       68.8360 |        42.0540 |
| → BEST RECALIBRATION ARM | mult_tier · λ 1                                                                                          |            0.9398 |       73.5160 |       43.7110 |       62.5710 |        41.1540 |

- ✅ both degenerates lose the primary metric — it is not paying for pessimism
- ✅ the truth beats the ACROSS-position permutation — the per-position level structure is real information
- ✅ the full-resolution oracle floor holds
- ✅ every arm respects **its own form's** peeking ceiling (16 arms checked at MATCHED family and MATCHED resolution)
- ✅ QB is untouched on real emitted projections, not merely by assertion

⭐ **The degenerate check comes back NEGATIVE, and it is reported because it was SCORED, not because it was expected.** `zero_scale` (2.0477) and NF1.4's `pos_median` MAE-collapse tell (1.6691) both lose decisively to the reference arm (0.9398). NF-D14's refinement of the NF-D11 landmine is why this is a measurement rather than an argument: **MAE inverts when the conditional MEDIAN sits at the floor, not merely when the zero atom is fat** — and on the RB/TE/WR DRAFTABLE TIER the median is nowhere near zero. The right response to that rule is to keep the degenerate in the field and READ it every run, which is what this line is.

⭐ **ONE CEILING PER FORM, NOT ONE FOR THE FIELD — and the first cut of this story had it wrong.** A peeking oracle is a floor only at MATCHED FAMILY *and* MATCHED RESOLUTION (NF1.7 (b) / NF1.9 (f)). `mult_tier` and `ols_slope` each CONTAIN the per-position constant as a special case, so either can legitimately score better than the best possible constant — a capacity effect, not an inversion. Flooring the whole field on `oracle_posconst` would have vetoed a real result for the wrong reason; each arm is therefore checked against the peeking version of its OWN form, where 'peeking can only help' genuinely holds:

| arm                 | form       | ceiling_anchor   |   ceiling |   arm_metric |   margin | ok   |
|:--------------------|:-----------|:-----------------|----------:|-------------:|---------:|:-----|
| mult_const · λ 0.25 | mult_const | oracle_posconst  |    0.9091 |       1.0341 |   0.1250 | True |
| mult_const · λ 0.5  | mult_const | oracle_posconst  |    0.9091 |       1.0035 |   0.0944 | True |
| mult_const · λ 0.75 | mult_const | oracle_posconst  |    0.9091 |       0.9832 |   0.0741 | True |
| mult_const · λ 1    | mult_const | oracle_posconst  |    0.9091 |       0.9693 |   0.0602 | True |
| add_offset · λ 0.25 | add_offset | oracle_addoffset |    0.9107 |       1.0482 |   0.1375 | True |
| add_offset · λ 0.5  | add_offset | oracle_addoffset |    0.9107 |       1.0238 |   0.1131 | True |
| add_offset · λ 0.75 | add_offset | oracle_addoffset |    0.9107 |       1.0005 |   0.0898 | True |
| add_offset · λ 1    | add_offset | oracle_addoffset |    0.9107 |       0.9784 |   0.0677 | True |
| mult_tier · λ 0.25  | mult_tier  | oracle_tierconst |    0.8354 |       1.0165 |   0.1811 | True |
| mult_tier · λ 0.5   | mult_tier  | oracle_tierconst |    0.8354 |       0.9764 |   0.1410 | True |
| mult_tier · λ 0.75  | mult_tier  | oracle_tierconst |    0.8354 |       0.9538 |   0.1184 | True |
| mult_tier · λ 1     | mult_tier  | oracle_tierconst |    0.8354 |       0.9398 |   0.1044 | True |
| ols_slope · λ 0.25  | ols_slope  | oracle_ols       |    0.7784 |       1.0321 |   0.2537 | True |
| ols_slope · λ 0.5   | ols_slope  | oracle_ols       |    0.7784 |       0.9949 |   0.2165 | True |
| ols_slope · λ 0.75  | ols_slope  | oracle_ols       |    0.7784 |       0.9653 |   0.1869 | True |
| ols_slope · λ 1     | ols_slope  | oracle_ols       |    0.7784 |       0.9407 |   0.1623 | True |

## 2. The full field (pooled over RB/TE/WR)

| arm                 | recal?   | monotone?             |   pooled tier MAE |   tier MAE RB |   tier MAE TE |   tier MAE WR |   universe MAE |   universe bias |
|:--------------------|:---------|:----------------------|------------------:|--------------:|--------------:|--------------:|---------------:|----------------:|
| mult_tier · λ 1     | yes      | —                     |            0.9398 |       73.5160 |       43.7110 |       62.5710 |        41.1540 |         -3.2780 |
| ols_slope · λ 1     | yes      | —                     |            0.9407 |       72.3010 |       42.2860 |       65.3330 |        42.9630 |         -5.4050 |
| mult_tier · λ 0.75  | yes      | —                     |            0.9538 |       73.5660 |       46.2610 |       61.5870 |        40.6210 |         -7.6760 |
| ols_slope · λ 0.75  | yes      | —                     |            0.9653 |       72.6190 |       45.1930 |       65.8860 |        42.3380 |         -9.2710 |
| mult_const · λ 1    | yes      | yes (0 rank movement) |            0.9693 |       74.1300 |       44.0830 |       67.7170 |        42.1540 |         -6.1740 |
| mult_tier · λ 0.5   | yes      | —                     |            0.9764 |       74.2130 |       48.8130 |       61.8340 |        40.4970 |        -12.0740 |
| add_offset · λ 1    | yes      | yes (0 rank movement) |            0.9784 |       72.1960 |       48.8970 |       63.7890 |        43.7200 |         -4.8410 |
| mult_const · λ 0.75 | yes      | yes (0 rank movement) |            0.9832 |       74.5970 |       46.5400 |       66.4390 |        41.7150 |         -9.8480 |
| ols_slope · λ 0.5   | yes      | —                     |            0.9949 |       73.8760 |       48.1000 |       66.6760 |        41.9560 |        -13.1370 |
| add_offset · λ 0.75 | yes      | yes (0 rank movement) |            1.0005 |       74.2540 |       50.1510 |       64.6910 |        42.9970 |         -8.8480 |
| mult_const · λ 0.5  | yes      | yes (0 rank movement) |            1.0035 |       75.7160 |       48.9990 |       65.9170 |        41.5000 |        -13.5220 |
| mult_tier · λ 0.25  | yes      | —                     |            1.0165 |       76.7610 |       51.3610 |       64.0770 |        40.9080 |        -16.4710 |
| add_offset · λ 0.5  | yes      | yes (0 rank movement) |            1.0238 |       76.3110 |       51.4040 |       65.8360 |        42.4910 |        -12.8550 |
| ols_slope · λ 0.25  | yes      | —                     |            1.0321 |       76.7290 |       51.0070 |       67.6670 |        41.8630 |        -17.0030 |
| mult_const · λ 0.25 | yes      | yes (0 rank movement) |            1.0341 |       77.7760 |       51.4540 |       66.6990 |        41.6200 |        -17.1960 |
| add_offset · λ 0.25 | yes      | yes (0 rank movement) |            1.0482 |       78.3700 |       52.6560 |       67.2140 |        42.1690 |        -16.8620 |
| incumbent (NULL)    | —        |                       |            1.0738 |       80.4300 |       53.9190 |       68.8360 |        42.0540 |        -20.8690 |

## 3. ⭐ THE PRE-REGISTERED POOLED SELECTION — one hypothesis, one test

The ship UNIT is the WHOLE per-position constant vector: a level recalibration is ONE change to `project_rookies` that applies at RB/TE/WR together or not at all. Eligible arms (13 of 17) are those that are shippable AND do no ordering harm at EVERY scaled position.

|   incumbent pooled tier MAE | selected arm    |   pooled tier MAE |   Δ vs incumbent |    PBO |   Bailey degradation % |   contender spread % |   DSR (whole-field, THE GATE) |   DSR (contender, reported) |   one-sided paired p (1 test) |   α (pre-registered) |
|----------------------------:|:----------------|------------------:|-----------------:|-------:|-----------------------:|---------------------:|------------------------------:|----------------------------:|------------------------------:|---------------------:|
|                      1.0738 | ols_slope · λ 1 |            0.9407 |          -0.1331 | 0.0286 |                 0.0000 |               4.0100 |                        0.9963 |                      0.9977 |                        0.0033 |               0.1000 |

Per-class deltas (incumbent − winner, > 0 ⇒ the winner is better): `[0.026, 0.143, 0.105, 0.135, 0.158, 0.064, 0.299]` over classes `[2019, 2020, 2021, 2022, 2023, 2024, 2025]`.

**The flip distribution** (NF1.8: a rank statistic alone cannot tell a TIE from an unstable pick — mass on two arms a fraction of a percent apart IS a tie; mass spread thinly over a dozen unrelated arms is a search that learnt nothing):

| config           |   IS-half wins |   share |   full-sample pooled tier MAE |   Δ vs best % |
|:-----------------|---------------:|--------:|------------------------------:|--------------:|
| ols_slope · λ 1  |             27 |  0.7710 |                        0.9410 |        0.0000 |
| mult_const · λ 1 |              8 |  0.2290 |                        0.9690 |        3.0400 |

**Ship decision under the pre-registered framing:** `{'ship': True, 'framing': 'pooled', 'has_eligible_winner': True, 'recalibrates': True, 'beats_incumbent': True, 'ordering_ok_every_position': True, 'pbo_ok': True, 'dsr_ok': True, 'significant': True}`

### 3b. Is the answer resting on a gate level I chose? — the sensitivity, computed

|   DSR whole-field (THE GATE) |   DSR contender-set (reported) | ships at pre-registered DSR ≥ 0.95   | ships at NF1.4's DSR ≥ 0.0   | ships with the DSR dropped entirely   | ships on the CONTENDER DSR reading   |
|-----------------------------:|-------------------------------:|:-------------------------------------|:-----------------------------|:--------------------------------------|:-------------------------------------|
|                       0.9963 |                         0.9977 | True                                 | True                         | True                                  | True                                 |

⚠️ **THE GATE LEVEL IS LOAD-BEARING.** The pre-registered DSR is the only thing standing between this story and a ship. **The pre-registered gate GOVERNS** — a bar moved after seeing the answer is not a bar (E2.1-r) — but a reader is entitled to know it, and the honest next step is a story that earns more held-out draft classes, not a re-read of this one.

### 3c. The margin in DRAFT CLASSES — what kind of answer this is

|   classes now |   mean Δ (pooled tier MAE) |   sd Δ |   one-sided p |   α (single hypothesis) |   classes needed |
|--------------:|---------------------------:|-------:|--------------:|------------------------:|-----------------:|
|        7.0000 |                     0.1329 | 0.0869 |        0.0033 |                  0.1000 |           7.0000 |

NF1.8's 'state the margin in ROWS' convention, one unit over. A p-value decimal cannot distinguish **underpowered** from **absent**: an effect that needs a plausible number of further draft classes is a story to re-run when they exist; one that needs dozens is a null at any n this program will ever have.

### 3d. ⭐ THE DISCLOSED PER-POSITION READING — the framing this story did NOT pre-register

NF-D15 pre-registered per-position and disclosed pooled; NF-D16 does the exact opposite, and owes the same duty. **Reported, never selected on** — the pre-registered pooled framing governs (E2.1-r). This table exists so 'the framing did not decide the answer' is a number rather than a shrug.

| position   |   incumbent_metric | winner             |   metric |    delta |    pbo |    dsr |   pvalue | BH-FDR (3 tests)   |
|:-----------|-------------------:|:-------------------|---------:|---------:|-------:|-------:|---------:|:-------------------|
| RB         |            80.4300 | add_offset · λ 1   |  72.1957 |  -8.2340 | 0.3714 | 0.8205 |   0.0128 | survives           |
| TE         |            53.9186 | ols_slope · λ 1    |  42.2857 | -11.6330 | 0.0000 | 0.9997 |   0.0259 | survives           |
| WR         |            68.8357 | mult_tier · λ 0.75 |  61.5871 |  -7.2490 | 0.5143 | 0.3266 |   0.1785 | no                 |

BH cutoff a position must clear UNCONDITIONALLY under the 3-test framing: **0.0333** — against the pooled framing's α of **0.1**. ✅ **The two framings AGREE**: the pooled test clears α and `['RB', 'TE']` also survive the 3-test BH-FDR, so the pre-registered choice of framing did not decide the answer.

## 4. ⭐ THE CEILING GAP, READ — is a better constant available, or is the truth class-variable?

|   incumbent (pooled tier MAE) |   best candidate |   CEILING (peeking per-position constant) |   headroom (inc − ceiling) |   captured (inc − candidate) |   share of headroom captured |   in-fold skill vs 'predict 1.0' |
|------------------------------:|-----------------:|------------------------------------------:|---------------------------:|-----------------------------:|-----------------------------:|---------------------------------:|
|                        1.0738 |           0.9407 |                                    0.7784 |                     0.2954 |                       0.1331 |                       0.4506 |                           0.3056 |

The peeking per-position constant is the CEILING of this entire family: pooled tier MAE **0.7784** against the incumbent's **1.0738**, i.e. **0.2954** of headroom exists IN PRINCIPLE for a per-position level correction. The best candidate captured **0.1331** of it (45.1%). ⇒ **READING (A) — ESTIMABLE.** The in-fold estimator carries real information about the next class's constant (`skill_vs_null` 0.3056 > 0, i.e. it removes that share of the error a naive 'predict 1.0' makes), and the candidate captured a material share of the available headroom. The level effect is learnable in-fold and the gap to the ceiling is estimator quality, not an unreachable target.

**The per-class constants themselves** — the raw material of that reading:

| position   |   sd_of_peek_constant |   mean_peek_constant |   mean_infold_constant |   skill_vs_null |
|:-----------|----------------------:|---------------------:|-----------------------:|----------------:|
| RB         |                0.2806 |               1.3726 |                 1.2800 |          0.4305 |
| TE         |                0.5179 |               1.4729 |                 1.3231 |          0.3140 |
| WR         |                0.6257 |               1.5979 |                 1.4204 |          0.2204 |

|   class | position   |   k_infold |   k_peek |   err_infold |   err_null |
|--------:|:-----------|-----------:|---------:|-------------:|-----------:|
|    2019 | RB         |     1.1714 |   0.9418 |       0.2296 |     0.0582 |
|    2019 | TE         |     1.1756 |   1.0246 |       0.1510 |     0.0246 |
|    2019 | WR         |     1.4372 |   2.3619 |       0.9248 |     1.3619 |
|    2020 | RB         |     1.2622 |   1.4093 |       0.1471 |     0.4093 |
|    2020 | TE         |     1.2658 |   0.6697 |       0.5961 |     0.3303 |
|    2020 | WR         |     1.4590 |   1.7837 |       0.3247 |     0.7837 |
|    2021 | RB         |     1.2583 |   1.6265 |       0.3682 |     0.6265 |
|    2021 | TE         |     1.3760 |   1.8707 |       0.4947 |     0.8707 |
|    2021 | WR         |     1.4069 |   0.9045 |       0.5024 |     0.0955 |
|    2022 | RB         |     1.2540 |   1.2951 |       0.0411 |     0.2951 |
|    2022 | TE         |     1.3761 |   2.1666 |       0.7905 |     1.1666 |
|    2022 | WR         |     1.4419 |   1.1089 |       0.3330 |     0.1089 |
|    2023 | RB         |     1.3178 |   1.0955 |       0.2223 |     0.0955 |
|    2023 | TE         |     1.3897 |   1.2988 |       0.0908 |     0.2988 |
|    2023 | WR         |     1.4039 |   2.4818 |       1.0780 |     1.4818 |
|    2024 | RB         |     1.3161 |   1.5315 |       0.2154 |     0.5315 |
|    2024 | TE         |     1.3309 |   1.5027 |       0.1719 |     0.5027 |
|    2024 | WR         |     1.3982 |   1.1780 |       0.2202 |     0.1780 |
|    2025 | RB         |     1.3805 |   1.7087 |       0.3282 |     0.7087 |
|    2025 | TE         |     1.3479 |   1.7769 |       0.4290 |     0.7769 |
|    2025 | WR         |     1.3954 |   1.3665 |       0.0289 |     0.3665 |

⚠️ **A THIRD EXPLANATION THE STORY'S FRAMING DID NOT NAME — IN-SAMPLE OPTIMISM, measured at -0.0504.** The in-fold constant is estimated against point projections the fold's OWN slot curve was fitted on, so those points are better calibrated than the held-out ones the constant is then applied to. The same draft class yields a different constant depending on whether its points came from a curve that had seen it (`k_in_sample_point`) or not (`k_out_of_sample_point`), and the gap between them is a part of the ceiling gap that is neither 'a better estimator' nor 'the truth moves'. The direction is CONSERVATIVE — it biases the estimated correction toward 1, i.e. it UNDER-states it — so it cannot manufacture a lift, but it is not zero.

|   class | position   |   k_in_sample_point |   k_out_of_sample_point |   optimism |
|--------:|:-----------|--------------------:|------------------------:|-----------:|
|    2019 | RB         |              1.0832 |                  0.9418 |     0.1413 |
|    2019 | TE         |              1.1131 |                  1.0246 |     0.0885 |
|    2019 | WR         |              1.9833 |                  2.3619 |    -0.3787 |
|    2020 | RB         |              1.3740 |                  1.4093 |    -0.0353 |
|    2020 | TE         |              0.6671 |                  0.6697 |    -0.0026 |
|    2020 | WR         |              1.6091 |                  1.7837 |    -0.1746 |
|    2021 | RB         |              1.7222 |                  1.6265 |     0.0957 |
|    2021 | TE         |              1.5766 |                  1.8707 |    -0.2941 |
|    2021 | WR         |              0.9061 |                  0.9045 |     0.0016 |
|    2022 | RB         |              1.4307 |                  1.2951 |     0.1357 |
|    2022 | TE         |              1.9158 |                  2.1666 |    -0.2507 |
|    2022 | WR         |              1.0332 |                  1.1089 |    -0.0757 |
|    2023 | RB         |              1.1409 |                  1.0955 |     0.0454 |
|    2023 | TE         |              1.2196 |                  1.2988 |    -0.0792 |
|    2023 | WR         |              2.2867 |                  2.4818 |    -0.1951 |
|    2024 | RB         |              1.5811 |                  1.5315 |     0.0495 |
|    2024 | TE         |              1.5068 |                  1.5027 |     0.0041 |
|    2024 | WR         |              1.1950 |                  1.1780 |     0.0169 |

### 4b. ⭐ THE PERMUTATION ANCHOR IS NEAR-VACUOUS AGAINST A LEVEL HYPOTHESIS — measured, not glossed

`add_offset`'s statistic is `mean(y) − mean(point)`, which is EXACTLY invariant under a within-position permutation of `y`. Measured over every position and every held-out class, the maximum absolute difference between the real offset and the within-permuted one is **0.000000000000** — exactly invariant, as the algebra requires. That is why BOTH permutations are in the anchor set: the WITHIN-position one is expected to tie and is reported as a property of the hypothesis (a level IS a marginal statistic), while the ACROSS-position one is the anchor that actually has to be beaten. Presenting a near-tie as a passed permutation test would be a check that examined nothing.

## 5. Ordering — the structural claim, MEASURED on emitted projections

| form       | expected monotone (0 rank movement)   |   max rank movement RB |   max rank movement TE |   max rank movement WR |   worst | structural claim holds   |
|:-----------|:--------------------------------------|-----------------------:|-----------------------:|-----------------------:|--------:|:-------------------------|
| mult_const | True                                  |                 0.0000 |                 0.0000 |                 0.0000 |  0.0000 | True                     |
| add_offset | True                                  |                 0.0000 |                 0.0000 |                 0.0000 |  0.0000 | True                     |
| mult_tier  | False                                 |                 5.0000 |                 2.0000 |                10.0000 | 10.0000 | True                     |
| ols_slope  | False                                 |                 0.0000 |                 0.0000 |                 0.0000 |  0.0000 | True                     |

⭐ The two **monotone-by-construction** forms must show max rank movement exactly 0 at every position — a strictly monotone transform of a position's projections moves no rank. Two things could break that in practice and neither is visible in the algebra (a multiplicative constant clipping to different values in different cells; the physical floor at 0 creating TIES among rookies an additive offset pushed below zero), so the claim is checked on the numbers the arms actually emit rather than asserted from their definitions.

⚠️ **`ols_slope` IS ONLY *CONDITIONALLY* MONOTONE, AND THIS RUN'S ZERO IS A MEASUREMENT RATHER THAN A PROPERTY OF THE FORM.** An affine `a + b·point` moves no rank when `b > 0` and INVERTS a whole position's board when `b < 0`. Every fitted slope in this run is positive (`all_slopes_positive` = True, range 0.6663–1.46 over 21 position × class fits), which is WHY its measured rank movement is 0 — not because the form guarantees it. A future draft class that produced a negative slope would flip that, and the ordering CONSTRAINT (not the form's description) is what would catch it. **`mult_tier` is the only form that genuinely reorders** — and it is ineligible at every λ for exactly that reason, which is what makes the constraint non-vacuous in this field.

**The fitted corrections themselves** — what the arms actually apply, per class and position:

|   class | position   |   mult_const k |   add_offset c (PPR) |   ols intercept |   ols slope |
|--------:|:-----------|---------------:|---------------------:|----------------:|------------:|
|    2019 | RB         |         1.1714 |              16.1744 |         -5.3440 |      1.3928 |
|    2019 | TE         |         1.1756 |               6.3882 |          7.1780 |      0.9773 |
|    2019 | WR         |         1.4372 |              15.0745 |         18.4350 |      0.8890 |
|    2020 | RB         |         1.2622 |              18.6858 |         -1.0190 |      1.4183 |
|    2020 | TE         |         1.2658 |               9.0289 |          2.8840 |      1.2052 |
|    2020 | WR         |         1.4590 |              16.4425 |         27.9640 |      0.6663 |
|    2021 | RB         |         1.2583 |              19.7056 |         -2.7220 |      1.4585 |
|    2021 | TE         |         1.3760 |               9.5439 |          5.9380 |      1.1404 |
|    2021 | WR         |         1.4069 |              16.8971 |         23.7610 |      0.8266 |
|    2022 | RB         |         1.2540 |              18.8287 |         -0.7130 |      1.3864 |
|    2022 | TE         |         1.3761 |              11.4779 |          2.0300 |      1.3584 |
|    2022 | WR         |         1.4419 |              17.3114 |         18.9460 |      0.9575 |
|    2023 | RB         |         1.3178 |              20.1913 |          0.0000 |      1.4251 |
|    2023 | TE         |         1.3897 |              11.5574 |          2.3520 |      1.3432 |
|    2023 | WR         |         1.4039 |              16.1051 |         18.2050 |      0.9482 |
|    2024 | RB         |         1.3161 |              19.8905 |          3.2990 |      1.3458 |
|    2024 | TE         |         1.3309 |              11.2299 |          0.8290 |      1.3599 |
|    2024 | WR         |         1.3982 |              16.9141 |         19.7480 |      0.9349 |
|    2025 | RB         |         1.3805 |              20.7630 |          4.7720 |      1.3509 |
|    2025 | TE         |         1.3479 |              11.9658 |         -1.4210 |      1.4600 |
|    2025 | WR         |         1.3954 |              17.2077 |         18.7980 |      0.9639 |

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

| position   | arm             |   mean abs Δ (PPR) |   max abs Δ (PPR) |   mean abs rank Δ | tier displacements   | would ship   |
|:-----------|:----------------|-------------------:|------------------:|------------------:|:---------------------|:-------------|
| RB         | ols_slope · λ 1 |            18.1500 |           88.5400 |            0.0000 | 0 of 42              | yes          |
| TE         | ols_slope · λ 1 |            10.2100 |           49.9900 |            0.0000 | 0 of 21              | yes          |
| WR         | ols_slope · λ 1 |            16.2400 |           22.7700 |            0.0000 | 0 of 56              | yes          |

Reported whether or not anything ships — if nothing ships this is the size of what was declined, which is the number a reader needs to judge whether the null is expensive.

## 6. Honest limitations

- ⭐ **NO DEPTH-CHART PROVENANCE CAVEAT APPLIES HERE, and that is a deliberate design property rather than luck.** NF-D14/NF-D15's measured lift carries a hard upper-bound qualifier because their availability signal reads a WEEK-1 depth chart historically and an AUGUST snapshot live. NF-D16's forms are estimated from exactly two quantities the board already owns — the served point projection and the realized rookie fantasy points — so there is no train/serve provenance asymmetry to bound. This is why `mult_const` was registered as the clean in-fold mean of `realized / point` rather than inherited from NF-D15's `mean_ratio` foil, which was a mean of a DEPTH-derived ratio and would have dragged the caveat into a story that touches no depth feature.
- **The in-fold constants are estimated against IN-SAMPLE point projections.** The training rows' points come from the fold's own slot curve, which was fitted on them, so they are better calibrated than the held-out points the constant is then applied to. §4 measures the resulting optimism directly. The direction is CONSERVATIVE — it biases the estimated correction toward 1, i.e. UNDER-states it, so it cannot manufacture a lift — but it is not zero, and a revival should estimate the correction against out-of-fold training predictions.
- ⛔ **QB is out of scope by pre-registration, not by result.** NF-D14 MEASURED the rookie-QB double-pricing and NF-D15 enforced the exclusion at max drift 0.0; NF-D16 inherits the scope by IMPORT (`RECALIBRATED_POSITIONS` is `rookie_point_scaling.SCALED_POSITIONS`) so the two stories cannot drift apart. Whether the rookie-QB point is cold is a separate question this story does not answer.
- **`tier_mae` grades the DRAFTABLE TIER — ~6 RB / 8 WR / 3 TE per class.** A claim here is a claim about a few dozen rookie-seasons across seven draft classes; the paired per-class deltas are reported so a reader sees the spread rather than only the mean.
- **The permutation anchor is WEAK against this hypothesis by construction**, and §4b measures rather than glosses it: a level is a MARGINAL statistic, so a within-position permutation preserves it exactly for the additive form. The ACROSS-position permutation is the one that has to be beaten, and the anchors that do the real work here are the family CEILING and the two degenerates.
- **Do-no-ordering-harm is a rank-correlation constraint, not a promise the board will not move** — though for the two monotone forms it is a promise the ORDER will not move, which §5 measures at exactly 0. The PPR magnitudes still change, and §5 reports that churn.
- **No edge claim.** A projection-quality product: `best_alpha = 0`, no CLV/ROI statement.

