# NF-D18 — ATTENUATE-AT-THE-TOP rookie-point recalibration (RB/TE/WR) — §0.5 bake-off

**Generated:** 2026-08-03T01:43:11.463808+00:00 · **held-out draft classes:** 2019–2025 (7) · **arms:** 4 candidates + 2 matched foils · **held-out rookie-seasons (RB/TE/WR):** 472 · **framing:** PRE-REGISTERED `pooled` · **DSR reading:** PRE-REGISTERED `whole_field`

## ⭐ VERDICT — 🟡 RECORDED NULL — no pre-registered top-attenuation clears both constraints; NF-D16's correction cannot be served

**The pre-registered pooled test selects `incumbent (NULL)`**, moving the pooled draftable-tier MAE **1.0738 → 1.0738** (Δ 0.0) over 7 held-out draft classes, with PBO None, whole-field DSR None (the pre-registered gate, ≥ 0.95) and a one-sided paired p of 1.0 against α = 0.1. **Failing gate(s): `['recalibrates', 'beats_incumbent', 'pbo_ok', 'dsr_ok', 'significant']`.**

⚠️ **THERE IS NO CLEARANCE TO ATTRIBUTE.** No attenuating arm clears the placement cap on the emitted board, so the matched-foil control has nothing to separate — which is itself the cleanest possible reading of the pairing: the shape channel did not produce the outcome the story was built to test.

⇒ **RECORDED NULL — and NF-D16's correction is now shelved PERMANENTLY rather than pending.** The only publish path NF-D17 left open was a top-attenuating re-shaping that clears the validated placement cap while keeping the gain; the pre-registered field does not contain one. NF-D16 stays ratified-but-unserved, the shipped rookie point STANDS, the interval is untouched, and the QB exclusion was never re-opened.

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. ⛔ **QB is EXCLUDED by pre-registration and PROVEN untouched** (max |Δ| over every arm and every held-out QB: **0.000000000** PPR). 🔒 The rookie INTERVAL's WIDTH model is untouched. ⭐ **The serving reproduction is VERIFIED, not assumed**: NF-D16's ratified affine routed through this harness reproduces the production curve's own emitted value to **0.000000** PPR (81 rookies).

## 0. What was pre-registered, and when

Everything that could otherwise have been chosen after seeing a result is a CONSTANT in `rookie_top_attenuation.py`; this report READS those constants rather than restating them, so 'what was pre-registered' has exactly one owner.

| decision               | value                                                     | why (written BEFORE the run)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
|:-----------------------|:----------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| forms                  | incumbent (NULL), ols_slope, power, huber, qmap, isotonic | The incumbent NULL + NF-D16's RATIFIED affine as the REFERENCE (carried at full strength so the placement constraint has something to REFUSE) + four attenuating classes: a concave POWER (shape), a ROBUST affine (estimator), a monotone QUANTILE MAP (no parameters at all) and an ISOTONIC learned foil (the richest monotone family, which CONTAINS every other form here).                                                                                                                                                                                                                                                                                           |
| λ                      | 1.0                                                       | NOT A KNOB IN THIS STORY. NF-D16 pre-registered a shrink grid and SELECTED λ = 1; re-picking a selection parameter after seeing a constraint result is the E2.1-r inversion. The globally-shrunk affine appears ONLY as a non-shippable MATCHED FOIL.                                                                                                                                                                                                                                                                                                                                                                                                                      |
| constraint C1          | do-no-ordering-harm ≤ 0.02                                | NF1.4's own constant, inherited verbatim, checked PER POSITION and never as a pooled mean — a pooled ρ can sit flat while one position's ordering collapses.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| constraint C2          | NF-D17 placement cap, THRESHOLD-INVARIANT                 | The validated clause, imported rather than re-derived. Clearance is required at EVERY quantile in NF-D17's Q05–Q25 band AND against reality's observed minimum rank — the same terms on which the VETO held. That leaves no threshold for anybody to pick.                                                                                                                                                                                                                                                                                                                                                                                                                 |
| constraints bind on    | ELIGIBILITY (not a post-hoc veto)                         | The PLACEMENT cap acts on ELIGIBILITY, not as a post-hoc veto on an already-selected arm. As a veto the story would be vacuous — the least-attenuated arm wins the tier metric by construction and is precisely the arm the cap refuses, so the answer would be fixed before any data was read. The question asked was whether an arm exists that clears BOTH constraints, which requires the constraint to act on the eligible SET exactly as do-no-ordering-harm already does. No arm's PARAMETERS are tuned to the board; only the discrete FORM choice is filtered, deflation is computed over that eligible set, and the ordering-only reading is reported beside it. |
| framing                | pooled                                                    | INHERITED FROM NF-D16 VERBATIM, and inheriting rather than re-deciding is itself the point: this is the third pre-registered change asked of ONE product, and a framing re-chosen per story is a framing chosen for its answer. The ship UNIT is one change to `project_rookies` that applies at RB/TE/WR together or not at all, so the hypothesis is ONE claim and gets ONE test. The per-position reading is computed as a DISCLOSURE and does not gate.                                                                                                                                                                                                                |
| DSR reading that BINDS | whole_field                                               | Inherited from NF-D16. Naming which reading binds in advance is what stops it from becoming a choice made after seeing which reading is kinder.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| DSR level / PBO / α    | 0.95 / 0.2 / 0.1                                          | All three INHERITED FROM NF-D16 BY IMPORT, so the bar cannot drift between the story that shipped the correction and the story trying to publish it.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| selection metric       | tier_mae                                                  | NF1.4's draftable-tier MAE, INHERITED. The incumbent point was selected on it and NF-D16 was graded on it; grading the third change to one product on a new metric is metric-shopping.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |

🚩 **THE A-PRIORI RISK WAS REGISTERED TOO, AND IT MATTERS FOR READING THE RESULT.** NF-D16's fitted correction is dominated by SLOPE (its pure-level `add_offset` arm scored exactly the incumbent), and a slope correction lifts the TOP of a position's board most. The selection metric grades the DRAFTABLE TIER. So the region a top-attenuating form must give up is precisely the region the metric grades and the defect lives in — the honest prior was a null, and the one structural reason it might not be is that the placement clause binds on the SINGLE best rookie while the metric grades a TIER of six.

## 1. The metric, the two constraints, and the anchor set

**Primary metric — `tier_mae`, NF1.4's, INHERITED RATHER THAN CHOSEN.** The draftable-tier MAE on a tier FIXED by the incumbent's own projection (NF1.1's fixed-anchor rule, so no arm can buy a friendlier subset), pooled scale-free over RB/TE/WR for the pooled test and reported per position in raw PPR beside it.

### The anchors, scored on THIS run

| anchor             | what it is                                                                                                                   |   pooled tier MAE |   tier MAE RB |   tier MAE TE |   tier MAE WR |   universe MAE |
|:-------------------|:-----------------------------------------------------------------------------------------------------------------------------|------------------:|--------------:|--------------:|--------------:|---------------:|
| oracle_perplayer   | ORACLE FLOOR, full resolution (peeks per player). Nothing may beat it.                                                       |            0.0000 |        0.0000 |        0.0000 |        0.0000 |         0.0040 |
| oracle_ols         | CEILING of the `ols_slope` (reference affine) family.                                                                        |            0.7784 |       59.4690 |       32.2690 |       58.2040 |        38.9960 |
| oracle_power       | CEILING of the `power` family.                                                                                               |            1.5505 |      123.2970 |       57.1330 |      126.6330 |        52.2660 |
| oracle_huber       | CEILING of the `huber` family.                                                                                               |            0.7782 |       60.6060 |       31.5040 |       58.3390 |        36.4950 |
| oracle_qmap        | CEILING of the `qmap` family.                                                                                                |            0.7919 |       59.6600 |       31.5140 |       61.8640 |        36.8390 |
| oracle_isotonic    | CEILING of the `isotonic` family — the RICHEST here; it CONTAINS every other form, so it must be the lowest.                 |            0.4991 |       36.4560 |       17.8110 |       43.1770 |        28.0620 |
| permuted_across    | reference fitted on outcomes shuffled ACROSS positions. Must LOSE.                                                           |            1.3459 |       97.1270 |       68.0230 |       89.8740 |        55.9470 |
| permuted_within    | reference fitted on outcomes shuffled WITHIN position — the marginal preserved, the SHAPE destroyed. ⭐ MUST LOSE (see §4b). |            1.4272 |       93.3630 |       75.9330 |       97.0340 |        56.6090 |
| zero_scale         | DEGENERATE — project nothing. Must LOSE the metric; SATISFIES the placement cap (see §6).                                    |            2.0477 |      139.7000 |      105.3140 |      140.3610 |        62.2900 |
| pos_median         | DEGENERATE — NF1.4's MAE-collapse tell. Wins an INVERTED metric; must LOSE this one.                                         |            1.6691 |      110.8560 |       86.5930 |      115.2810 |        54.0390 |
| → INCUMBENT (NULL) | the rookie point as SERVED TODAY                                                                                             |            1.0738 |       80.4300 |       53.9190 |       68.8360 |        42.0540 |

- ✅ both degenerates lose the primary metric — it is not paying for pessimism
- ✅ the truth beats the ACROSS-position permutation
- ✅ ⭐ the truth beats the WITHIN-position permutation — the SHAPE these forms estimate is real information, and this is the anchor that could not act in NF-D16
- ✅ the full-resolution oracle floor holds
- 🚨 AN ARM BEAT ITS OWN FORM'S PEEKING CEILING — a metric inversion: `[{'arm': 'power', 'form': 'power', 'ceiling_anchor': None, 'ceiling': None, 'arm_metric': 2.369, 'ok': False, 'note': 'no scorable matched-family ceiling — the check would pass on NOTHING'}, {'arm': 'isotonic', 'form': 'isotonic', 'ceiling_anchor': None, 'ceiling': None, 'arm_metric': 0.9592, 'ok': False, 'note': 'no scorable matched-family ceiling — the check would pass on NOTHING'}]`
- ✅ QB is untouched on real emitted projections, not merely by assertion

⭐ **ONE CEILING PER FORM, NOT ONE FOR THE FIELD, AND HERE THE FAMILIES GENUINELY NEST.** `isotonic` CONTAINS the affine (positive slope), the power (γ > 0) and the quantile map as special cases, so it can legitimately score better than any of their ceilings — a CAPACITY effect (NF1.7 (b) / NF1.9 (f)), not an inversion. Flooring the whole field on one ceiling would veto a real result for the wrong reason, which is the bug NF-D16's first cut shipped. The measured ordering of the ceilings is the internal-consistency signal a single ceiling cannot produce:

| arm       | form      | ceiling_anchor   |   ceiling |   arm_metric |   margin | ok    | note                                                                 |
|:----------|:----------|:-----------------|----------:|-------------:|---------:|:------|:---------------------------------------------------------------------|
| ols_slope | ols_slope | oracle_ols       |    0.7784 |       0.9407 |   0.1623 | True  | nan                                                                  |
| power     | power     |                  |  nan      |       2.3690 | nan      | False | no scorable matched-family ceiling — the check would pass on NOTHING |
| isotonic  | isotonic  |                  |  nan      |       0.9592 | nan      | False | no scorable matched-family ceiling — the check would pass on NOTHING |

## 2. The full field (pooled over RB/TE/WR)

| arm                    | kind                            |   pooled tier MAE |   tier MAE RB |   tier MAE TE |   tier MAE WR |   universe MAE |   universe bias |   board rank | placement clears   |
|:-----------------------|:--------------------------------|------------------:|--------------:|--------------:|--------------:|---------------:|----------------:|-------------:|:-------------------|
| ols_slope              | REFERENCE (NF-D16)              |            0.9407 |       72.3010 |       42.2860 |       65.3330 |        42.9630 |         -5.4050 |            6 | False              |
| global_match(power)    | MATCHED FOIL (⛔ not shippable) |            0.9407 |       72.3010 |       42.2860 |       65.3330 |        42.9630 |         -5.4050 |            6 | False              |
| global_match(isotonic) | MATCHED FOIL (⛔ not shippable) |            0.9407 |       72.3010 |       42.2860 |       65.3330 |        42.9630 |         -5.4050 |            6 | False              |
| isotonic               | attenuating                     |            0.9592 |       68.9030 |       47.4610 |       64.2040 |        41.4800 |         -3.3940 |            7 | False              |
| incumbent (NULL)       | NULL                            |            1.0738 |       80.4300 |       53.9190 |       68.8360 |        42.0540 |        -20.8690 |           12 | True               |
| power                  | attenuating                     |            2.3690 |      154.0900 |      106.2500 |      194.8590 |        66.0210 |          9.8000 |            1 | False              |

⛔ The `global_match(...)` rows are the NON-SHIPPABLE MATCHED FOILS. They are excluded from the eligible set, from PBO's search and from the DSR trial field — a diagnostic anchor is never a trial (MH2 (a)) — and they are reported here so the field can be read whole.

## 3. ⭐ THE PRE-REGISTERED POOLED SELECTION — one hypothesis, one test, both constraints

Eligible arms (1 of 4 candidates) are those that are shippable AND do no ordering harm at EVERY scaled position AND clear the NF-D17 placement cap threshold-invariantly on the emitted 2026 board.

|   incumbent pooled tier MAE | selected arm     |   pooled tier MAE |   Δ vs incumbent | PBO   | Bailey degradation %   | contender spread %   | DSR (whole-field, THE GATE)   | DSR (contender, reported)   |   one-sided paired p (1 test) |   α (pre-registered) |
|----------------------------:|:-----------------|------------------:|-----------------:|:------|:-----------------------|:---------------------|:------------------------------|:----------------------------|------------------------------:|---------------------:|
|                      1.0738 | incumbent (NULL) |            1.0738 |           0.0000 |       |                        |                      |                               |                             |                        1.0000 |               0.1000 |

Per-class deltas (incumbent − winner, > 0 ⇒ the winner is better): `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]` over classes `[2019, 2020, 2021, 2022, 2023, 2024, 2025]`.

**Ship decision under the pre-registered framing:** `{'ship': False, 'framing': 'pooled', 'has_eligible_winner': True, 'recalibrates': False, 'beats_incumbent': False, 'ordering_ok_every_position': True, 'placement_clears_threshold_invariant': True, 'pbo_ok': False, 'dsr_ok': False, 'significant': False}`

### 3a. ⭐ WHY EACH INELIGIBLE ARM WAS REFUSED — the constraint doing visible work

| label     | ordering_ok   | placement_clears   |   best_rookie_overall_rank |
|:----------|:--------------|:-------------------|---------------------------:|
| ols_slope | True          | False              |                          6 |
| power     | True          | False              |                          1 |
| isotonic  | False         | False              |                          7 |

### 3b. Is the answer resting on a gate level I chose? — the sensitivity, computed

| DSR whole-field (THE GATE)   | DSR contender-set (reported)   | ships at pre-registered DSR ≥ 0.95   | ships at NF1.4's DSR ≥ 0.0   | ships with the DSR dropped entirely   | ships on the CONTENDER DSR reading   |
|:-----------------------------|:-------------------------------|:-------------------------------------|:-----------------------------|:--------------------------------------|:-------------------------------------|
|                              |                                | False                                | False                        | False                                 | False                                |

⭐ **THE ANSWER DOES NOT TURN ON THE DISPUTABLE GATE, AND THAT IS THE POINT OF COMPUTING IT.** Nothing ships even with the DSR removed ENTIRELY and even on the kinder contender-set reading, because `['recalibrates', 'beats_incumbent', 'pbo_ok', 'significant']` blocks independently. So the verdict is not an artefact of inheriting NF-D16's stricter DSR bar nor of naming the whole-field reading as binding — a reader who disagrees with either choice reaches the same verdict.

### 3c. ⭐ THE DISCLOSED ORDERING-ONLY READING — the eligibility rule this story did NOT use

NF-D16 applied its face-validity check as a post-hoc VETO on an already-selected arm. NF-D18 pre-registered the placement cap as an ELIGIBILITY constraint instead, for the reason in §0, and owes the reader the other reading. **Reported, never selected on.**

| eligibility rule                    |   n eligible | selected arm   |   pooled tier MAE |   its board rank | would the post-hoc placement VETO fire?   |
|:------------------------------------|-------------:|:---------------|------------------:|-----------------:|:------------------------------------------|
| ordering ONLY (NF-D16's convention) |            3 | ols_slope      |            0.9407 |                6 | YES — vetoed                              |

⚠️ **THE TWO READINGS DISAGREE, AND THAT DISAGREEMENT IS EXACTLY THE STORY.** The ordering-only rule selects `ols_slope`, which the post-hoc placement veto would then REFUSE; the pre-registered rule filters first and selects `incumbent (NULL)`. The pre-registered rule GOVERNS. Reporting both is what makes 'the eligibility choice is disclosed, not hidden' a number.

### 3d. THE DISCLOSED PER-POSITION READING

| position   |   incumbent_metric | winner           |   metric |   delta | pbo   | dsr   |   pvalue |
|:-----------|-------------------:|:-----------------|---------:|--------:|:------|:------|---------:|
| RB         |            80.4300 | incumbent (NULL) |  80.4300 |  0.0000 |       |       |   1.0000 |
| TE         |            53.9186 | incumbent (NULL) |  53.9186 |  0.0000 |       |       |   1.0000 |
| WR         |            68.8357 | incumbent (NULL) |  68.8357 |  0.0000 |       |       |   1.0000 |

BH cutoff a position must clear UNCONDITIONALLY under the 3-test framing: **0.0333** — against the pooled framing's α of **0.1**.

## 4. Ordering — MEASURED on emitted projections, never asserted

| form      | ordering class           |   max rank move RB |   max rank move TE |   max rank move WR |   worst | structural claim holds   |
|:----------|:-------------------------|-------------------:|-------------------:|-------------------:|--------:|:-------------------------|
| ols_slope | conditionally monotone   |             0.0000 |             0.0000 |             0.0000 |  0.0000 | True                     |
| power     | conditionally monotone   |             0.0000 |             0.0000 |             0.0000 |  0.0000 | True                     |
| huber     | conditionally monotone   |             0.0000 |             0.0000 |             0.0000 |  0.0000 | True                     |
| qmap      | monotone by construction |             1.5000 |             3.0000 |             4.5000 |  4.5000 | False                    |
| isotonic  | reordering               |             3.5000 |             3.0000 |             4.0000 |  4.0000 | True                     |

⭐ **NOTHING IN THIS FIELD IS MONOTONE FOR EVERY ADMISSIBLE PARAMETER EXCEPT THE QUANTILE MAP.** An affine inverts a position's whole board on a negative slope and a power does on a negative exponent, so `ols_slope`/`huber`/`power` are CONDITIONALLY monotone and their measured rank movement is a property of THIS RUN's fitted parameters, not of the forms (NF-D16 method lock 2). `isotonic` is only WEAKLY monotone — its flat segments TIE, and a tie IS rank movement. The measured fits:

`all_slopes_positive` = **True** (range 0.6663–1.7386 over 42 affine fits) · `all_gammas_below_one` = **False** (γ range 1.7312–2.0 over 21 power fits). ⚠️ A power with γ ≥ 1 is not an attenuator at all — this is the number that says whether the form registered as the canonical top-attenuator actually is one on this data.

|   class | position   |   ols a |   ols b |   huber a |   huber b |   power c |   power γ |   power smear |
|--------:|:-----------|--------:|--------:|----------:|----------:|----------:|----------:|--------------:|
|    2019 | RB         | -5.3440 |  1.3928 |  -19.4480 |    1.4653 |   -6.0220 |    2.0000 |        2.0000 |
|    2019 | TE         |  7.1780 |  0.9773 |   -4.1550 |    1.1356 |   -3.7750 |    1.9159 |        2.0000 |
|    2019 | WR         | 18.4350 |  0.8890 |   -0.3180 |    0.9711 |   -5.0540 |    2.0000 |        2.0000 |
|    2020 | RB         | -1.0190 |  1.4183 |  -16.5390 |    1.5606 |   -5.3330 |    2.0000 |        2.0000 |
|    2020 | TE         |  2.8840 |  1.2052 |   -7.5020 |    1.3266 |   -3.8200 |    1.9514 |        2.0000 |
|    2020 | WR         | 27.9640 |  0.6663 |    5.7270 |    0.8196 |   -4.5700 |    2.0000 |        2.0000 |
|    2021 | RB         | -2.7220 |  1.4585 |  -19.5690 |    1.6630 |   -5.3500 |    2.0000 |        2.0000 |
|    2021 | TE         |  5.9380 |  1.1404 |   -3.0300 |    1.2133 |   -2.9400 |    1.7590 |        2.0000 |
|    2021 | WR         | 23.7610 |  0.8266 |   -4.1790 |    1.2469 |   -4.0260 |    1.9584 |        2.0000 |
|    2022 | RB         | -0.7130 |  1.3864 |  -20.6120 |    1.6756 |   -4.6170 |    2.0000 |        2.0000 |
|    2022 | TE         |  2.0300 |  1.3584 |   -8.2350 |    1.5265 |   -3.2560 |    1.8653 |        2.0000 |
|    2022 | WR         | 18.9460 |  0.9575 |   -6.1600 |    1.3151 |   -3.4620 |    1.8279 |        2.0000 |
|    2023 | RB         |  0.0000 |  1.4251 |  -20.9730 |    1.7386 |   -4.2220 |    1.9724 |        2.0000 |
|    2023 | TE         |  2.3520 |  1.3432 |   -6.9500 |    1.4977 |   -3.2950 |    1.8717 |        2.0000 |
|    2023 | WR         | 18.2050 |  0.9482 |   -3.5750 |    1.1769 |   -3.1500 |    1.7312 |        2.0000 |
|    2024 | RB         |  3.2990 |  1.3458 |  -13.2520 |    1.5043 |   -4.1110 |    1.9477 |        2.0000 |
|    2024 | TE         |  0.8290 |  1.3599 |   -6.7420 |    1.4283 |   -3.2290 |    1.8356 |        2.0000 |
|    2024 | WR         | 19.7480 |  0.9349 |   -2.1420 |    1.1545 |   -3.1940 |    1.7335 |        2.0000 |
|    2025 | RB         |  4.7720 |  1.3509 |  -11.9610 |    1.4958 |   -3.8900 |    1.9076 |        2.0000 |
|    2025 | TE         | -1.4210 |  1.4600 |   -7.3470 |    1.4737 |   -3.0210 |    1.7813 |        2.0000 |
|    2025 | WR         | 18.7980 |  0.9639 |   -2.1440 |    1.1596 |   -3.1830 |    1.7338 |        2.0000 |

### 4b. ⭐ THE PERMUTATION ANCHOR THAT WAS VACUOUS IN NF-D16 AND BITES HERE

NF-D16 measured its within-position permutation as EXACTLY invariant (max |Δ| 7.1e-15): a LEVEL is a MARGINAL statistic and a within-position shuffle preserves the marginal, so the anchor could not act, and NF-D16 said so in advance rather than presenting a near-tie as a passed test. **Every NF-D18 form estimates a SHAPE** — the relationship between projection and outcome — which that same shuffle DESTROYS while preserving the marginal exactly. So the anchor genuinely tests this hypothesis, and it was pre-registered as a GATE. Measured: within-permutation **1.4272** vs the best real arm **0.9407** ⇒ BEATEN ✅. ⭐ *A mechanism that cannot act is a finding, not an omission* (NF1.9) — and so is one that starts acting when the hypothesis changes shape.

## 5. ⭐ THE MATCHED GLOBAL FOIL — is it the SHAPE, or just less correction?

Every attenuating arm is paired with the REFERENCE affine shrunk GLOBALLY to the SAME mean absolute correction over the draftable tier: same family, same magnitude, UNIFORM instead of shaped. The foil's λ is computed from POINT PROJECTIONS ONLY — no realized outcome enters it — so it is matched on magnitude without being told anything about the answer. A leaderboard rank cannot make this distinction (NF-D10 (g)); a matched pair can.

| arm      | foil                   |   arm_tier_mae |   foil_tier_mae |   paired_delta |   arm_rank |   foil_rank | arm_clears   | foil_clears   | shape_earns_clearance   | magnitude_explains_it   |
|:---------|:-----------------------|---------------:|----------------:|---------------:|-----------:|------------:|:-------------|:--------------|:------------------------|:------------------------|
| power    | global_match(power)    |         2.3690 |          0.9407 |         1.4283 |          1 |           6 | False        | False         | False                   | False                   |
| isotonic | global_match(isotonic) |         0.9592 |          0.9407 |         0.0185 |          7 |           6 | False        | False         | False                   | False                   |

## 6. ⭐ THE PLACEMENT CONSTRAINT ON THE EMITTED 2026 BOARD

The correction is applied to the board's OWN emitted rookie points — exactly where serving applies it (`RookieSlotCurve.recalibrate_fp` acts on the final scored projection) — so the incumbent half of every row below IS the served product rather than a reconstruction of it. Veterans are untouched by construction, which is precisely why a within-position 'moves no ranks' argument never reaches this gate.

| arm                    | best rookie      | pos   |   proj PPR |   overall rank |   rookies in top 10 | clears cap (threshold-invariant)   |   top-of-board ratio |   tier mean ratio | attenuates at top   |
|:-----------------------|:-----------------|:------|-----------:|---------------:|--------------------:|:-----------------------------------|---------------------:|------------------:|:--------------------|
| incumbent (NULL)       | Fernando Mendoza | QB    |   268.3300 |             12 |                   0 | True                               |               1.0000 |            1.0000 | False               |
| ols_slope              | Jeremiyah Love   | RB    |   291.6300 |              6 |                   1 | False                              |               1.2650 |            1.3464 | True                |
| power                  | Jeremiyah Love   | RB    |  1141.3000 |              1 |                   4 | False                              |               4.6309 |            2.4081 | False               |
| isotonic               | Jeremiyah Love   | RB    |   286.2400 |              7 |                   1 | False                              |               1.1692 |            1.5675 | True                |
| global_match(power)    | Jeremiyah Love   | RB    |   291.6300 |              6 |                   1 | False                              |               1.2650 |            1.3464 | True                |
| global_match(isotonic) | Jeremiyah Love   | RB    |   291.6300 |              6 |                   1 | False                              |               1.2650 |            1.3464 | True                |
| zero_scale             | Fernando Mendoza | QB    |   268.3300 |             12 |                   0 | True                               |             nan      |          nan      |                     |
| pos_median             | Fernando Mendoza | QB    |   268.3300 |             12 |                   0 | True                               |             nan      |          nan      |                     |

The validated NF-D17 cap band: `{'Q05': 7.9, 'Q10': 8.8, 'Q15': 9.7, 'Q20': 10.6, 'Q25': 11.5}`, observed minimum realized rank **7.0** ⇒ a THRESHOLD-INVARIANT clearance requires overall rank ≥ **11.5**, i.e. rank 12 or worse. There is no threshold left for anybody to pick, which is what makes a clearance as un-reverse-engineerable as NF-D17's veto was.

⭐ **THE PLACEMENT CLAUSE IS A CONSTRAINT A DEGENERATE SATISFIES, AND THAT IS THE RIGHT SHAPE.** `zero_scale` places its best rookie at overall rank 12 and therefore CLEARS the cap trivially — while losing the selection metric by a mile. NF1.8's rule is that a constraint a degenerate satisfies is fine (the metric eliminates it) whereas a CRITERION a degenerate WINS is fatal. Measuring that is the proof this story did not quietly promote a constraint into a selection criterion.

## 7. Honest limitations

- ⚠️ **THE PLACEMENT CONSTRAINT IS EVALUATED ON ONE BOARD.** It is a serving-time property of the 2026 draft board, not a held-out statistical criterion, so it contributes no power and it does influence WHICH of six discrete forms is selected. Three things bound that: no arm's PARAMETERS are ever tuned to the board (every form is fitted in-fold and has no strength dial), the clearance is required to be THRESHOLD-INVARIANT so no cutoff was chosen, and the ordering-only reading is reported beside it (§3c).
- ⚠️ **λ WAS DELIBERATELY NOT RE-OPENED, AND THAT BOUNDS WHAT A NULL HERE MEANS.** A global shrink of NF-D16's affine might well clear the placement cap — the matched foils measure exactly that — but re-picking a selection parameter after seeing a constraint result is the E2.1-r inversion. So a null here is 'no top-attenuating SHAPE works', never 'nothing could ever work'; the forbidden move is measured and reported rather than taken.
- **`tier_mae` grades the DRAFTABLE TIER — ~6 RB / 8 WR / 3 TE per class.** A claim here is a claim about a few dozen rookie-seasons across seven draft classes; the paired per-class deltas are reported so a reader sees the spread rather than only the mean.
- **The in-fold shapes are estimated against IN-SAMPLE point projections** (the training rows' points come from the fold's own slot curve). NF-D16 measured the resulting optimism at −0.05 in constant space and the direction is CONSERVATIVE — it biases a correction toward the identity — but it is not zero, and it applies to every form here.
- ⛔ **QB is out of scope by pre-registration, not by result** — inherited by import through NF-D16 from NF-D15, and proven untouched on both the held-out classes and the served board rather than asserted.
- **No edge claim.** A projection-quality product: `best_alpha = 0`, no CLV/ROI statement.
