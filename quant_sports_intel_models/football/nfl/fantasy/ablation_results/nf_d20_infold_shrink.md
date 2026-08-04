# NF-D20 — IN-FOLD GLOBAL-SHRINK selection of NF-D16's rookie-point recalibration under a PER-FOLD whole-board placement constraint

**Generated:** 2026-08-04T07:16:14.267795+00:00 · **held-out draft classes:** 2019–2025 (7) · **merged boards read:** 2019–2026 · **arms:** 4 candidates + 1 matched foil + 7 anchors · **held-out rookie-seasons (RB/TE/WR):** 472 · **framing:** PRE-REGISTERED `pooled` · **DSR reading:** PRE-REGISTERED `whole_field`

## ⭐ VERDICT — 🟡 RECORDED NULL — no in-fold-selected shrink clears every pre-registered gate; NF-D16 stays ratified-but-unpublished

**The pre-registered pooled test selects `incumbent (NULL)`**, moving the pooled draftable-tier MAE **1.0738 → 1.0738** (Δ 0.0) over 7 held-out draft classes, with PBO None, whole-field DSR None (the pre-registered gate, ≥ 0.95) and a one-sided paired p of 1.0 against α = 0.1. **The BINDING failures are `['recalibrates', 'beats_incumbent']`** — `['pbo_ok', 'dsr_ok', 'significant']` are reported as failed only because they are **UNDEFINED**: with the incumbent the single eligible arm there is no search to deflate and no non-zero delta to score, and a statistic that was not COMPUTABLE must never be read as a mechanism that lost (MH2's UNDEFINED-vs-failed rule).

⭐ **AND THE REASON THE INCUMBENT IS THE ONLY ELIGIBLE ARM IS THE WHOLE RESULT.** Every recalibrating arm BEATS the incumbent on the selection metric — the in-fold rules by 0.1293 pooled tier MAE at best — and every one of them is removed by the PER-FOLD placement constraint evaluated OUT OF SAMPLE. Nothing here lost on accuracy; the arms were refused by a deterministic board rank (§9).

⚠️⭐⭐ **THE MATCHED FOIL REFUTES THIS STORY'S MECHANISM IN THE SHARPEST WAY AVAILABLE — AND THIS IS THE MOST IMPORTANT LINE IN THE REPORT.** The BLIND constant shrink — a λ fixed at the midpoint of the registered interval with NO board information whatsoever — satisfies the per-fold placement constraint OUT OF SAMPLE on **every** held-out board, while **not one** of the in-fold selection rules does. So the in-fold machinery this story was built to test is not merely failing to help: it is actively WORSE at respecting the constraint than knowing nothing, because reading prior boards licenses it to raise λ on the seasons where the constraint happens to be inactive and it is then caught by the next season that is not. ⛔ **AND THAT IS NOT A LICENCE TO SHIP THE BLIND CONSTANT.** The foil is NON-SHIPPABLE by pre-registration precisely so this reading cannot become a back door: 'λ = 0.5 works' is a statement one can only make with the constraint results already in view, which is the same laundering NF-D18 refused for its own frontier value. The counterfactual is computed in §6a and selected on by nothing.

⇒ **RECORDED NULL ON THE PRE-REGISTERED QUESTION, AND IT CLOSES THE *IN-FOLD SELECTION* PATH RATHER THAN NF-D16 ITSELF.** The harness NF-D18 named as the only legitimate remaining publish route has now been built — the merged veteran+rookie board rebuilt per held-out season, the constraint enforced OUT OF SAMPLE — and it does not produce a shippable shrink under the gates NF-D16 itself pre-registered. NF-D16 stays RATIFIED-BUT-UNPUBLISHED, the shipped rookie point STANDS, the interval is untouched, and the QB exclusion was never re-opened. ⚠️ **What this null does NOT say is 'nothing could ever work', and §6a is where a reader must go before treating it that way:** a shrink that never consults a board survives every constraint this story could throw at it, so what failed is the SELECTION MACHINERY, not the shrink family — and the reason it failed is diagnosable (§2b: the constraint's activity is a draft-class accident, so prior boards cannot teach a rule what the next one will refuse). The remaining routes are a PM decision or a board-free shrink ESTIMATOR, both spelled out in §6a; neither is 'more draft classes'.

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. ⛔ **QB is EXCLUDED by pre-registration and PROVEN untouched** (max |Δ| over every arm, every held-out class and every board: **0.000000000** PPR). 🔒 The rookie INTERVAL's WIDTH model is untouched.

## 0. What was pre-registered, and when

Everything that could otherwise have been chosen after seeing a result is a CONSTANT in `rookie_shrink_selection.py`, **committed in its own commit before this runner existed**. This report READS those constants rather than restating them, so 'what was pre-registered' has exactly one owner.

| decision               | value                                                                                           | why (written BEFORE the run)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
|:-----------------------|:------------------------------------------------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| family                 | global λ-shrink of NF-D16's ratified per-position affine                                        | NF-D18 measured that the binding problem is the SHAPE, not the constraint — a plain global shrink of the ratified affine is the mechanism its null named. The field is SELECTION RULES rather than λ values, so no human chooses a number.                                                                                                                                                                                                                                                                                                                                                                    |
| λ grid                 | [0.0, 0.25, 0.5, 0.75, 1.0]                                                                     | NF-D16's OWN pre-registered `SHRINK_GRID`, imported, plus λ = 0 (which reproduces the incumbent exactly). Inheriting it is what stops the grid from becoming a place to hide a choice.                                                                                                                                                                                                                                                                                                                                                                                                                        |
| arms                   | incumbent (NULL), infold_all_boards, infold_last_board, unconstrained (λ=1), blind_half (λ=0.5) | the incumbent NULL + two in-fold rules differing only in how they aggregate board evidence + NF-D16's ratified affine at full strength as the REFERENCE (shippable, so the constraint has something to REFUSE) + a non-shippable blind constant as the MATCHED FOIL.                                                                                                                                                                                                                                                                                                                                          |
| constraint C1          | do-no-ordering-harm ≤ 0.02                                                                      | NF1.4's own constant, inherited verbatim, checked PER POSITION and never as a pooled mean.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| constraint C2          | rank_λ ≥ min(NF-D17 threshold-invariant cap, rank_incumbent), PER FOLD, evaluated OUT-OF-SAMPLE | the validated clause imported rather than re-derived; the incumbent term exists because the shipped product itself breaches on some boards and a constraint that refuses the NULL has examined nothing. Held-out because an in-sample constraint check is circular.                                                                                                                                                                                                                                                                                                                                           |
| constraints bind on    | ELIGIBILITY (not a post-hoc veto)                                                               | The PER-FOLD placement constraint acts on ELIGIBILITY and is evaluated OUT-OF-SAMPLE: an arm is eligible only if the λ its rule chose from data strictly BEFORE each held-out fold also satisfies C2 on that fold's OWN board — the board the rule never saw. As a post-hoc veto the story would be vacuous (the least-shrunk arm wins the tier metric by construction and is precisely the arm the cap refuses), and as an IN-SAMPLE filter it would be circular. Only the held-out reading asks the question that decides a publish: does an in-fold-selected shrink still clear the cap on the NEXT board? |
| framing                | pooled                                                                                          | INHERITED FROM NF-D16 THROUGH NF-D18 VERBATIM, and inheriting rather than re-deciding is itself the point: this is the FOURTH pre-registered change asked of ONE product, and a framing re-chosen per story is a framing chosen for its answer. The ship UNIT is one change to `project_rookies` that applies at RB/TE/WR together or not at all, so the hypothesis is ONE claim and gets ONE test. The per-position reading is computed as a DISCLOSURE and does not gate.                                                                                                                                   |
| DSR reading that BINDS | whole_field                                                                                     | Inherited from NF-D16 through NF-D18. Naming which reading binds in advance is what stops it becoming a choice made after seeing which is kinder.                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| DSR level / PBO / α    | 0.95 / 0.2 / 0.1                                                                                | All three INHERITED FROM NF-D16 BY IMPORT, so the bar cannot drift between the story that ratified the correction and the story trying to publish it.                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| selection metric       | tier_mae                                                                                        | NF1.4's draftable-tier MAE, INHERITED. Grading the fourth change to ONE product on a new metric is metric-shopping.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| empty-evidence default | λ = 0                                                                                           | the boards begin at 2019, so the first held-out class has no prior board. With nothing to verify against, a rule applies NO correction — a check that did not run is not a check that passed (NF1.7 (a)).                                                                                                                                                                                                                                                                                                                                                                                                     |

🚩 **THE PROVENANCE CLAUSE.** λ is NEVER a knob in this story. Every candidate is a deterministic RULE whose λ is computed from held-out draft classes and prior-season merged boards alone; the grid itself is NF-D16's own pre-registered SHRINK_GRID, imported. ⛔ NF-D18's frontier value (read off the 2026 board with the answer in view) is not referenced, defaulted to, or reachable by any rule here, and no arm is fitted, filtered or selected on the 2026 board.

## 1. The metric, the two constraints, and the anchor set

**Primary metric — `tier_mae`, NF1.4's, INHERITED RATHER THAN CHOSEN.** The draftable-tier MAE on a tier FIXED by the incumbent's own projection (NF1.1's fixed-anchor rule, so no arm can buy a friendlier subset), pooled scale-free over RB/TE/WR for the pooled test and reported per position in raw PPR beside it.

### The anchors, scored on THIS run

| anchor             | what it is                                                                                                                        |   pooled tier MAE |   tier MAE RB |   tier MAE TE |   tier MAE WR |   universe MAE |
|:-------------------|:----------------------------------------------------------------------------------------------------------------------------------|------------------:|--------------:|--------------:|--------------:|---------------:|
| oracle_perplayer   | ORACLE FLOOR, full resolution (peeks per player). Nothing may beat it.                                                            |            0.0000 |        0.0000 |        0.0000 |        0.0000 |         0.0040 |
| oracle_ols         | PEEKING CEILING at MATCHED FAMILY — the per-position affine fitted on the HELD-OUT class. No arm may beat it.                     |            0.7784 |       59.4690 |       32.2690 |       58.2040 |        38.9960 |
| permuted_across    | reference fitted on outcomes shuffled ACROSS positions. Must LOSE.                                                                |            1.3359 |      100.1190 |       62.1100 |       94.1910 |        56.7490 |
| permuted_within    | shuffled WITHIN position — the marginal preserved, the projection↔outcome relationship destroyed. ⭐ PRE-REGISTERED TO BE BEATEN. |            1.4251 |       95.5270 |       77.2240 |       93.0070 |        55.9860 |
| zero_scale         | DEGENERATE — project nothing. Must LOSE the metric; SATISFIES C2 (see §2a).                                                       |            2.0477 |      139.7000 |      105.3140 |      140.3610 |        62.2900 |
| pos_median         | DEGENERATE — NF1.4's MAE-collapse tell. Wins an INVERTED metric; must LOSE.                                                       |            1.6691 |      110.8560 |       86.5930 |      115.2810 |        54.0390 |
| over_scale         | DEGENERATE on the OTHER side — λ = 2, twice the ratified correction. Must LOSE the metric AND BREACH C2.                          |            0.8861 |       71.7010 |       36.2140 |       63.7340 |        47.0740 |
| → INCUMBENT (NULL) | the rookie point as SERVED TODAY                                                                                                  |            1.0738 |       80.4300 |       53.9190 |       68.8360 |        42.0540 |

- ❌ **the pre-registered `degenerates_lose` gate** (all three of `zero_scale`, `pos_median`, `over_scale` must lose the metric) — §1a decomposes it rather than leaving one flag to stand for three different claims
- ✅ …of which the two TRUE degenerates (`zero_scale` 2.0477, `pos_median` 1.6691) lose to the best real arm (0.9445) — the metric is not paying for pessimism
- ❌ …and `over_scale` (λ = 2) DOES NOT — it scores 0.8861, BEATING every real arm. ⭐ A PRE-REGISTERED EXPECTATION REFUTED BY MEASUREMENT, decomposed in §1a
- ✅ the truth beats the ACROSS-position permutation
- ✅ ⭐ the truth beats the WITHIN-position permutation — the affine's SLOPE is real information, and this is the anchor that was provably VACUOUS in NF-D16 (a level is a marginal statistic) and BIT in NF-D18
- ✅ the full-resolution oracle floor holds
- ✅ every arm respects the matched-family peeking ceiling
- ✅ ⭐ `zero_scale` SATISFIES C2 on every board while losing the metric — the proof the placement clause is a CONSTRAINT and was not quietly promoted into a selection CRITERION (NF1.8)
- ✅ ⭐ `over_scale` (λ = 2) BREACHES C2 — the constraint is measured having TEETH rather than described as strict
- ✅ QB is untouched on real emitted projections, not merely by assertion
- ✅ every merged board read is WALK-FORWARD (`base_season == season − 1`, rookie leg present) — checked, not assumed

**The STORY-LEVEL verdict gate** (these are VETOES: a failing anchor means no number computed in this run may be shipped — it can never make one shippable):

| ship   | pooled_gate_passes   | degenerates_lose   | permutation_across_beaten   | permutation_within_beaten   | oracle_respected   | family_ceiling_respected   | over_scale_breaches_the_constraint   | degenerate_satisfies_the_constraint   | boards_are_walk_forward   | qb_untouched   |
|:-------|:---------------------|:-------------------|:----------------------------|:----------------------------|:-------------------|:---------------------------|:-------------------------------------|:--------------------------------------|:--------------------------|:---------------|
| False  | False                | False              | True                        | True                        | True               | True                       | True                                 | True                                  | True                      | True           |

### 1a. ⭐ THE `over_scale` ANCHOR — a pre-registered expectation, MEASURED

⚠️⭐⭐ **A PRE-REGISTERED ANCHOR FAILED, AND IT IS REPORTED AS A FAILURE RATHER THAN RE-LABELLED INTO A PASS.** `over_scale` (λ = 2, twice the ratified correction) was registered as a degenerate that MUST lose the metric. It scored **0.8861** and BEAT every real arm in the field, including NF-D16's ratified correction at λ = 1 (0.9407). The pre-registered `degenerates_lose` gate therefore reads **False**, and it is left reading False: moving a gate after seeing which way it fell is the E2.1-r inversion, and this one costs nothing to leave standing because the verdict is a NULL either way — a failed anchor can only ever block a ship, never manufacture one.

⭐ **WHAT IT ACTUALLY MEANS, AND WHY IT STRENGTHENS THE NULL RATHER THAN UNDERMINING IT.** This is NOT the metric-inversion signature the anchor exists to catch: an inverted metric is one a DO-NOTHING arm wins, and both do-nothing degenerates lose here by a mile (2.0477 and 1.6691 against 0.9445). What λ = 2 wins is MORE OF THE VERY THING THE CORRECTION DOES, which says the in-fold affine UNDER-corrects out of sample — the pooled tier MAE is still falling as λ leaves the registered interval (1.0738 → 1.0321 → 0.9949 → 0.9653 → 0.9407 → 0.8861 at λ = 2). So the metric's optimum lies BEYOND the correction the constraint already refuses, while the constraint's admissible ceiling sits at or below the middle of the interval. **The two objectives are opposed along the magnitude axis with no interior optimum**, which is a considerably stronger statement of this null than NF-D18's frontier could make — and it is a statement the run only got to make because the anchor was scored and READ rather than reasoned about in advance (NF-D14 (g′)).

⚠️ The honest cost of leaving the gate as written: `degenerates_lose` now bundles a genuine metric-sanity check with a refuted magnitude hypothesis, so a future reader must not treat a False here as evidence the measurement is untrustworthy. That is precisely why it is decomposed into three lines above instead of surfacing as one flag.

### The ONE matched-family peeking ceiling — and why one is correct here

⭐ **NF-D16 (g‴) SAYS ONE CEILING PER *FORM* WHEN THE FORMS NEST; IT DOES NOT SAY 'MORE CEILINGS ARE ALWAYS BETTER'.** Every arm in this field is `point + λ·(a + b·point − point)` = `λa + (1 + λ(b − 1))·point`, i.e. a per-position AFFINE for every λ. The field is therefore ONE family, `oracle_ols` is its matched-family peeking ceiling, and no arm may beat it.

| arm                 | form      | ceiling_anchor   |   ceiling |   arm_metric |   margin | ok   |
|:--------------------|:----------|:-----------------|----------:|-------------:|---------:|:-----|
| infold_all_boards   | ols_slope | oracle_ols       |    0.7784 |       0.9665 |   0.1881 | True |
| infold_last_board   | ols_slope | oracle_ols       |    0.7784 |       0.9490 |   0.1706 | True |
| unconstrained (λ=1) | ols_slope | oracle_ols       |    0.7784 |       0.9445 |   0.1661 | True |

## 2. ⭐ THE PER-SEASON MERGED BOARDS — the cost NF-D18 named, and its provenance checked

Each board is the product as it would have been SERVED that summer: veterans from season `Y − 1`'s realized data, the incoming rookie class priced by a slot curve fitted on classes `≤ Y − 1`, and NF-D16's recalibration OFF. The λ = 0 row of every curve below IS that served board rather than a reconstruction of it.

|   season |   base_season | walk-forward   |   rows |   rookies |   incumbent best-rookie rank | incumbent clears the cap   | admits λ (pre-registered C2)   | admits λ (STRICT cap — sensitivity)   | role                    |
|---------:|--------------:|:---------------|-------:|----------:|-----------------------------:|:---------------------------|:-------------------------------|:--------------------------------------|:------------------------|
|     2019 |          2018 | True           |    716 |        80 |                           22 | True                       | [0.0, 0.25, 0.5, 0.75, 1.0]    | [0.0, 0.25, 0.5, 0.75, 1.0]           | held-out evidence       |
|     2020 |          2019 | True           |    745 |        77 |                           15 | True                       | [0.0, 0.25, 0.5, 0.75, 1.0]    | [0.0, 0.25, 0.5, 0.75, 1.0]           | held-out evidence       |
|     2021 |          2020 | True           |    758 |        75 |                           10 | False                      | [0.0, 0.25, 0.5, 0.75, 1.0]    | []                                    | held-out evidence       |
|     2022 |          2021 | True           |    783 |        79 |                           31 | True                       | [0.0, 0.25, 0.5, 0.75, 1.0]    | [0.0, 0.25, 0.5, 0.75, 1.0]           | held-out evidence       |
|     2023 |          2022 | True           |    764 |        80 |                           19 | True                       | [0.0, 0.25, 0.5]               | [0.0, 0.25, 0.5]                      | held-out evidence       |
|     2024 |          2023 | True           |    734 |        77 |                           17 | True                       | [0.0, 0.25, 0.5, 0.75, 1.0]    | [0.0, 0.25, 0.5, 0.75, 1.0]           | held-out evidence       |
|     2025 |          2024 | True           |    786 |        85 |                           14 | True                       | [0.0, 0.25, 0.5]               | [0.0, 0.25, 0.5]                      | held-out evidence       |
|     2026 |          2025 | True           |    784 |        81 |                           12 | True                       | [0.0, 0.25, 0.5, 0.75]         | [0.0, 0.25, 0.5, 0.75]                | SERVING (read once, §8) |

⚠️⭐ **THE SHIPPED PRODUCT ITSELF BREACHES THE CAP ON 1 OF 7 HELD-OUT BOARDS ([2021]), AND THAT IS WHY C2 IS WRITTEN AS A NO-DEGRADATION CLAUSE.** It was measured before any candidate in this field was scored and is disclosed rather than worked around: on such a board a bare-cap constraint would refuse EVERY λ including λ = 0 — i.e. it would refuse the NULL — and a constraint that refuses everything has examined nothing (NF1.7 (a)). The pre-registered clause `rank_λ ≥ min(cap, rank_incumbent)` reduces to the plain NF-D17 cap on every board the incumbent already clears and forbids making a pre-existing breach worse. The STRICT column is the bare-cap sensitivity; it is reported, never selected on.

### 2a. The λ → best-rookie-overall-rank curve, per board

|   season |   λ=0 |   λ=0.25 |   λ=0.5 |   λ=0.75 |   λ=1 |
|---------:|------:|---------:|--------:|---------:|------:|
|     2019 |    22 |       22 |      22 |       22 |    22 |
|     2020 |    15 |       15 |      15 |       15 |    15 |
|     2021 |    10 |       10 |      10 |       10 |    10 |
|     2022 |    31 |       28 |      28 |       25 |    25 |
|     2023 |    19 |       19 |      14 |        8 |     6 |
|     2024 |    17 |       17 |      17 |       17 |    17 |
|     2025 |    14 |       14 |      14 |       11 |     7 |
|     2026 |    12 |       12 |      12 |       12 |     6 |

The validated NF-D17 cap band: `{'Q05': 7.9, 'Q10': 8.8, 'Q15': 9.7, 'Q20': 10.6, 'Q25': 11.5}`, observed minimum realized rank **7.0** ⇒ a THRESHOLD-INVARIANT clearance requires overall rank ≥ **11.5**, i.e. rank 12 or worse. There is no threshold left for anybody to pick, which is what makes a clearance as un-reverse-engineerable as NF-D17's veto was.

⭐ **MONOTONICITY, MEASURED RATHER THAN ASSUMED.** The pooled tier MAE is MONOTONE DECREASING in λ (argmin at λ = 1.0), and the served board's best-rookie rank is MONOTONE non-increasing in λ. Where the metric is monotone the rule's `argmin over the admissible set` coincides with 'the largest admissible λ' and has a one-line description; the argmin is registered anyway because correctness must not depend on a property that is a measurement (NF-D16 method lock 2).

### 2b. ⭐ ON HOW MANY BOARDS CAN THE CONSTRAINT EVEN ACT? — measured

The recalibration touches RB/TE/WR only, so on a board whose best rookie is a QB the best-rookie rank cannot move until a corrected RB/WR/TE overtakes him. Where the rank is identical at every λ the constraint is **INACTIVE** on that board, and its 'admits everything' describes the mechanism's reach rather than a permissive constraint (NF1.9: a mechanism that cannot act is a finding, not an omission). This is what makes 'the rules raised λ and were then caught' legible instead of surprising.

|   season | top rookie (λ=0)   | pos   |   rank at λ=0 |   rank at λ=1 | rank moves with λ   | constraint can act   |
|---------:|:-------------------|:------|--------------:|--------------:|:--------------------|:---------------------|
|     2019 | Kyler Murray       | QB    |            22 |            22 | False               | False                |
|     2020 | Joe Burrow         | QB    |            15 |            15 | False               | False                |
|     2021 | Trevor Lawrence    | QB    |            10 |            10 | False               | False                |
|     2022 | Drake London       | WR    |            31 |            25 | True                | True                 |
|     2023 | Bryce Young        | QB    |            19 |             6 | True                | True                 |
|     2024 | Caleb Williams     | QB    |            17 |            17 | False               | False                |
|     2025 | Cam Ward           | QB    |            14 |             7 | True                | True                 |
|     2026 | Fernando Mendoza   | QB    |            12 |             6 | True                | True                 |

⇒ the constraint is ACTIVE on **3 of 7** held-out boards (and on the 2026 serving board). ⭐⭐ **THIS IS THE MECHANISM BEHIND THIS STORY'S NULL, AND IT IS THE MOST TRANSFERABLE THING IN IT.** A board's constraint activity is decided by whether its best rookie is a QB — and QB is the one position the recalibration may not touch. So on most boards the correction cannot move the best-rookie rank AT ALL, every λ 'is admissible', and a rule reading prior boards learns that λ = 1 was fine. It then meets a class whose best rookie is a corrected RB or WR and is caught immediately. **The per-fold placement constraint is not learnable from prior boards, because its ACTIVITY is a draft-class accident rather than a stable property** — which is exactly why the in-fold rules fail where a blind constant that never raises λ survives (§6).

## 3. ⭐ THE IN-FOLD SELECTION — what each rule chose, and from what

For held-out class `Y` a rule may read the merged boards of seasons `< Y` and the held-out scores of classes `< Y`, and nothing else. No human chooses a λ at any point.

| arm                 | shippable   |   λ(2019) |   λ(2020) |   λ(2021) |   λ(2022) |   λ(2023) |   λ(2024) |   λ(2025) | C2 holds out on every fold   |   pooled tier MAE |
|:--------------------|:------------|----------:|----------:|----------:|----------:|----------:|----------:|----------:|:-----------------------------|------------------:|
| incumbent (NULL)    | True        |    0.0000 |    0.0000 |    0.0000 |    0.0000 |    0.0000 |    0.0000 |    0.0000 | True                         |            1.0738 |
| infold_all_boards   | True        |    0.0000 |    1.0000 |    1.0000 |    1.0000 |    1.0000 |    0.5000 |    0.5000 | False                        |            0.9665 |
| infold_last_board   | True        |    0.0000 |    1.0000 |    1.0000 |    1.0000 |    1.0000 |    0.5000 |    1.0000 | False                        |            0.9490 |
| unconstrained (λ=1) | True        |    0.0000 |    1.0000 |    1.0000 |    1.0000 |    1.0000 |    1.0000 |    1.0000 | False                        |            0.9445 |
| blind_half (λ=0.5)  | False       |    0.5000 |    0.5000 |    0.5000 |    0.5000 |    0.5000 |    0.5000 |    0.5000 | True                         |            0.9949 |

⭐ **EVERY λ ABOVE IS A COMPUTED VALUE, NOT A CHOSEN ONE.** `infold_all_boards` selected λ ∈ [0.0, 0.5, 1.0] across the seven held-out classes (evidence mode `all`); `infold_last_board` selected λ ∈ [0.0, 0.5, 1.0] across the seven held-out classes (evidence mode `last`); `unconstrained (λ=1)` selected λ ∈ [0.0, 1.0] across the seven held-out classes (evidence mode `none`).

⭐ **AND THE STRICT-C2 SENSITIVITY (bare cap, no incumbent term — reported, never selected on):** `infold_all_boards` → λ ∈ [0.0, 1.0]; `infold_last_board` → λ ∈ [0.0, 0.5, 1.0]; `unconstrained (λ=1)` → λ ∈ [0.0, 1.0].

## 4. The full field (pooled over RB/TE/WR)

| arm                 | kind                            |   pooled tier MAE |   tier MAE RB |   tier MAE TE |   tier MAE WR |   universe MAE |   universe bias | C2 holds out   |
|:--------------------|:--------------------------------|------------------:|--------------:|--------------:|--------------:|---------------:|----------------:|:---------------|
| unconstrained (λ=1) | REFERENCE (NF-D16 @ λ=1)        |            0.9445 |       73.6330 |       42.1290 |       65.3100 |        42.8660 |         -7.1740 | False          |
| infold_last_board   | in-fold rule                    |            0.9490 |       72.8790 |       42.9800 |       65.6490 |        42.5750 |         -8.2560 | False          |
| infold_all_boards   | in-fold rule                    |            0.9665 |       72.5740 |       45.7210 |       65.7070 |        42.5030 |         -9.6270 | False          |
| blind_half (λ=0.5)  | MATCHED FOIL (⛔ not shippable) |            0.9949 |       73.8760 |       48.1000 |       66.6760 |        41.9560 |        -13.1370 | True           |
| incumbent (NULL)    | NULL                            |            1.0738 |       80.4300 |       53.9190 |       68.8360 |        42.0540 |        -20.8690 | True           |

⛔ The `blind_half` row is the NON-SHIPPABLE MATCHED FOIL. It is excluded from the eligible set, from PBO's search and from the DSR trial field — a diagnostic anchor is never a trial (MH2 (a)) — and is reported here so the field can be read whole.

## 5. ⭐ THE PRE-REGISTERED POOLED SELECTION — one hypothesis, one test, both constraints

|   incumbent pooled tier MAE | selected arm     |   pooled tier MAE |   Δ vs incumbent | PBO   | Bailey degradation %   | contender spread %   | DSR (whole-field, THE GATE)   | DSR (contender, reported)   |   one-sided paired p (1 test) |   α (pre-registered) |
|----------------------------:|:-----------------|------------------:|-----------------:|:------|:-----------------------|:---------------------|:------------------------------|:----------------------------|------------------------------:|---------------------:|
|                      1.0738 | incumbent (NULL) |            1.0738 |           0.0000 |       |                        |                      |                               |                             |                        1.0000 |               0.1000 |

Per-class deltas (incumbent − winner, > 0 ⇒ the winner is better): `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]` over classes `[2019, 2020, 2021, 2022, 2023, 2024, 2025]`.

**Ship decision under the pre-registered framing:** `{'ship': False, 'framing': 'pooled', 'has_eligible_winner': True, 'recalibrates': False, 'beats_incumbent': False, 'ordering_ok_every_position': True, 'per_fold_placement_holds_out': True, 'serving_placement_ok': True, 'pbo_ok': False, 'dsr_ok': False, 'significant': False}`

### 5a. ⭐ WHY EACH INELIGIBLE ARM WAS REFUSED — the constraint doing visible work

| label               | ordering_ok   | placement_holds_out   | failing_folds   |
|:--------------------|:--------------|:----------------------|:----------------|
| infold_all_boards   | True          | False                 | [2023]          |
| infold_last_board   | True          | False                 | [2023, 2025]    |
| unconstrained (λ=1) | True          | False                 | [2023, 2025]    |

### 5b. Is the answer resting on a gate level I chose? — the sensitivity, computed

| DSR whole-field (THE GATE)   | DSR contender-set (reported)   | ships at pre-registered DSR ≥ 0.95   | ships at NF1.4's DSR ≥ 0.0   | ships with the DSR dropped entirely   | ships on the CONTENDER DSR reading   |
|:-----------------------------|:-------------------------------|:-------------------------------------|:-----------------------------|:--------------------------------------|:-------------------------------------|
|                              |                                | False                                | False                        | False                                 | False                                |

⭐ **THE ANSWER DOES NOT TURN ON THE DISPUTABLE GATE, AND THAT IS THE POINT OF COMPUTING IT.** Nothing ships even with the DSR removed ENTIRELY and even on the kinder contender-set reading, because `['recalibrates', 'beats_incumbent', 'pbo_ok', 'significant']` blocks independently. So the verdict is not an artefact of inheriting NF-D16's stricter DSR bar nor of naming the whole-field reading as binding.

**And the λ-GRID sensitivity the pre-registration promised — is the verdict an artefact of a coarse grid?** Every board's admissible set and every rule's λ recomputed on the 21-point 0.05 grid. ⛔ Reported, never selected on.

| arm                 | λ chosen (fine grid)   | C2 holds out on every fold   |   pooled tier MAE | beats incumbent   |
|:--------------------|:-----------------------|:-----------------------------|------------------:|:------------------|
| infold_all_boards   | [0.0, 0.6, 1.0]        | False                        |            0.9619 | True              |
| infold_last_board   | [0.0, 0.6, 1.0]        | False                        |            0.9481 | True              |
| unconstrained (λ=1) | [0.0, 1.0]             | False                        |            0.9445 | True              |

### 5c. THE DISCLOSED ORDERING-ONLY READING — the eligibility rule this story did NOT use

| eligibility rule                                      |   n eligible | selected arm        |   pooled tier MAE |
|:------------------------------------------------------|-------------:|:--------------------|------------------:|
| PRE-REGISTERED (ordering + per-fold C2 out-of-sample) |            1 | incumbent (NULL)    |            1.0738 |
| ordering ONLY (NF-D16's convention)                   |            4 | unconstrained (λ=1) |            0.9445 |

⚠️ **THE TWO READINGS DISAGREE, AND THE DISAGREEMENT IS THE CONSTRAINT DOING ITS JOB.** The ordering-only rule selects `unconstrained (λ=1)`; the pre-registered rule filters on the out-of-sample per-fold placement constraint first and selects `incumbent (NULL)`. The pre-registered rule GOVERNS. Reporting both is what makes 'the eligibility choice is disclosed, not hidden' a number.

### 5d. THE DISCLOSED PER-POSITION READING

| position   |   incumbent_metric | winner           |   metric |   delta | pbo   | dsr   |   pvalue |
|:-----------|-------------------:|:-----------------|---------:|--------:|:------|:------|---------:|
| RB         |            80.4300 | incumbent (NULL) |  80.4300 |  0.0000 |       |       |   1.0000 |
| TE         |            53.9186 | incumbent (NULL) |  53.9186 |  0.0000 |       |       |   1.0000 |
| WR         |            68.8357 | incumbent (NULL) |  68.8357 |  0.0000 |       |       |   1.0000 |

BH cutoff a position must clear UNCONDITIONALLY under the 3-test framing: **0.0333** — against the pooled framing's α of **0.1**.

## 6. ⭐ THE MATCHED FOIL — did the BOARD EVIDENCE earn it, or would any shrink have done?

| arm                 | foil               |   arm_tier_mae |   foil_tier_mae |   paired_delta | arm_holds_out   | foil_holds_out   | evidence_earns_clearance   | any_shrink_would_do   |
|:--------------------|:-------------------|---------------:|----------------:|---------------:|:----------------|:-----------------|:---------------------------|:----------------------|
| infold_all_boards   | blind_half (λ=0.5) |         0.9665 |          0.9949 |        -0.0283 | False           | True             | False                      | False                 |
| infold_last_board   | blind_half (λ=0.5) |         0.9490 |          0.9949 |        -0.0458 | False           | True             | False                      | False                 |
| unconstrained (λ=1) | blind_half (λ=0.5) |         0.9445 |          0.9949 |        -0.0504 | False           | True             | False                      | False                 |

⚠️⭐⭐ **THE MATCHED FOIL REFUTES THIS STORY'S MECHANISM IN THE SHARPEST WAY AVAILABLE — AND THIS IS THE MOST IMPORTANT LINE IN THE REPORT.** The BLIND constant shrink — a λ fixed at the midpoint of the registered interval with NO board information whatsoever — satisfies the per-fold placement constraint OUT OF SAMPLE on **every** held-out board, while **not one** of the in-fold selection rules does. So the in-fold machinery this story was built to test is not merely failing to help: it is actively WORSE at respecting the constraint than knowing nothing, because reading prior boards licenses it to raise λ on the seasons where the constraint happens to be inactive and it is then caught by the next season that is not. ⛔ **AND THAT IS NOT A LICENCE TO SHIP THE BLIND CONSTANT.** The foil is NON-SHIPPABLE by pre-registration precisely so this reading cannot become a back door: 'λ = 0.5 works' is a statement one can only make with the constraint results already in view, which is the same laundering NF-D18 refused for its own frontier value. The counterfactual is computed in §6a and selected on by nothing.

### 6a. ⛔ THE COUNTERFACTUAL — what if the blind constant had been registered SHIPPABLE?

Computed because the honest reading of this null depends on it, and **selected on by nothing**. ⛔ It is NOT a recommendation: 'λ = 0.5 survives' is a sentence one can only write with the constraint results already in view, and a successor pre-registering it on the strength of this table would be laundering a known number through a pre-registration — the identical move NF-D18 refused to make with its own frontier value, and the one this story exists to avoid making with a different constant.

| selected           |   serving λ |   2026 rank at that λ | clears the 2026 cap   |   metric |   incumbent_metric |   delta |    pbo |    dsr |   pvalue | would_have_shipped   | blocking   |
|:-------------------|------------:|----------------------:|:----------------------|---------:|-------------------:|--------:|-------:|-------:|---------:|:---------------------|:-----------|
| blind_half (λ=0.5) |      0.5000 |                    12 | True                  |   0.9949 |             1.0738 | -0.0789 | 0.0000 | 0.9999 |   0.0055 | True                 | []         |

⚠️⭐⭐ **THE REGISTRATION CHOICE — FOIL RATHER THAN CANDIDATE — DECIDED THIS VERDICT, AND SAYING SO IS NOT OPTIONAL.** Had the blind constant been registered SHIPPABLE it would have been selected and it would have SHIPPED: Δ -0.0789 pooled tier MAE, PBO 0.0, whole-field DSR 0.9999, p 0.0055, C2 satisfied out of sample on every held-out board, and overall rank 12 on the 2026 board. This programme's rule is that a null must prove it does not rest on the author's own design choice (MH2 (g″)) — and here it DOES rest on one. What it does NOT rest on is a gate LEVEL: §5b shows nothing ships even with the DSR removed entirely.

⛔ **AND THE CHOICE WAS STILL THE RIGHT ONE, WHICH IS WHY IT IS NOT BEING REVISITED.** The brief this story answers asks whether an IN-FOLD-SELECTED shrink can be published; a fixed constant is not one, and it was registered as the attribution control for exactly that reason, in writing, before the run. Re-classifying it now that its result is known would be the E2.1-r inversion in the most literal form available.

⭐ **WHAT A LEGITIMATE SUCCESSOR WOULD HAVE TO LOOK LIKE (and what it may NOT be).** ⛔ It may not pre-register λ = 0.5, for the same reason NF-D18 could not pre-register its own frontier value — the number is now known and was read off these results. The honest options are: **(i) a PM DECISION** to publish a fixed conservative shrink, accepting openly that the constant was chosen by judgement rather than by any held-out criterion (this story's numbers are then the evidence base, not the selection); **(ii) a SHRINK ESTIMATOR that contains no board information at all** — e.g. empirical-Bayes shrinkage of the fitted per-position slopes toward 1 with its strength set by the fold-to-fold VARIANCE of those slopes — which is legitimately pre-registrable because it is an ESTIMATOR rather than a number, and which must be registered with its own gates before it is run; or **(iii) accept this null and close NF-D16 unpublished.** ⚠️ Option (ii) is a real path and it is also the one most at risk of becoming a search for an estimator that lands near a number we now know, so it should be registered with that hazard named.

## 7. Ordering — MEASURED on emitted projections, never asserted

|      λ | max_rank_move_by_pos              |   worst_rank_move |   min_effective_slope | all_effective_slopes_positive   |
|-------:|:----------------------------------|------------------:|----------------------:|:--------------------------------|
| 0.0000 | {'RB': 0.0, 'TE': 0.0, 'WR': 0.0} |            0.0000 |                1.0000 | True                            |
| 0.2500 | {'RB': 0.0, 'TE': 0.0, 'WR': 0.0} |            0.0000 |                0.9166 | True                            |
| 0.5000 | {'RB': 0.0, 'TE': 0.0, 'WR': 0.0} |            0.0000 |                0.8331 | True                            |
| 0.7500 | {'RB': 0.0, 'TE': 0.0, 'WR': 0.0} |            0.0000 |                0.7497 | True                            |
| 1.0000 | {'RB': 0.0, 'TE': 0.0, 'WR': 0.0} |            0.0000 |                0.6663 | True                            |

`all_slopes_positive` = **True** (range 0.6663–1.46 over 21 affine fits). A λ-blend has effective slope `1 + λ(b − 1)`, so positive fitted slopes make every λ in the grid within-position monotone — measured above, not assumed.

|   class | position   |       a |      b |
|--------:|:-----------|--------:|-------:|
|    2019 | RB         | -5.3440 | 1.3928 |
|    2019 | TE         |  7.1780 | 0.9773 |
|    2019 | WR         | 18.4350 | 0.8890 |
|    2020 | RB         | -1.0190 | 1.4183 |
|    2020 | TE         |  2.8840 | 1.2052 |
|    2020 | WR         | 27.9640 | 0.6663 |
|    2021 | RB         | -2.7220 | 1.4585 |
|    2021 | TE         |  5.9380 | 1.1404 |
|    2021 | WR         | 23.7610 | 0.8266 |
|    2022 | RB         | -0.7130 | 1.3864 |
|    2022 | TE         |  2.0300 | 1.3584 |
|    2022 | WR         | 18.9460 | 0.9575 |
|    2023 | RB         |  0.0000 | 1.4251 |
|    2023 | TE         |  2.3520 | 1.3432 |
|    2023 | WR         | 18.2050 | 0.9482 |
|    2024 | RB         |  3.2990 | 1.3458 |
|    2024 | TE         |  0.8290 | 1.3599 |
|    2024 | WR         | 19.7480 | 0.9349 |
|    2025 | RB         |  4.7720 | 1.3509 |
|    2025 | TE         | -1.4210 | 1.4600 |
|    2025 | WR         | 18.7980 | 0.9639 |

## 8. ⭐ THE SERVING CHECK — the 2026 board, read ONCE, with λ already fixed

⭐ **λ FOR SERVING WAS FIXED BEFORE THIS BOARD WAS READ.** The winning rule (`incumbent (NULL)`) applied to ALL seven held-out boards selects **λ = 0.0**; only then is the 2026 board read, and only to run NF1.4's ordinary serving-time face-validity check on that already-fixed arm. This clause can only REFUSE a publish — it can never choose between arms — which is the one role in which reading the served board cannot contaminate a selection.

|      λ | best rookie      | pos   |   proj PPR |   overall rank |   rookies in top 10 | clears the cap (threshold-invariant)   | SELECTED   |   pooled tier MAE (held-out) |
|-------:|:-----------------|:------|-----------:|---------------:|--------------------:|:---------------------------------------|:-----------|-----------------------------:|
| 0.0000 | Fernando Mendoza | QB    |   268.3300 |             12 |                   0 | True                                   | True       |                       1.0738 |
| 0.2500 | Fernando Mendoza | QB    |   268.3300 |             12 |                   0 | True                                   | False      |                       1.0321 |
| 0.5000 | Fernando Mendoza | QB    |   268.3300 |             12 |                   0 | True                                   | False      |                       0.9949 |
| 0.7500 | Jeremiyah Love   | RB    |   270.8300 |             12 |                   0 | True                                   | False      |                       0.9653 |
| 1.0000 | Jeremiyah Love   | RB    |   291.6300 |              6 |                   1 | False                                  | False      |                       0.9407 |

## 9. Which kind of null (or ship) is this?

| state              | taxonomy_would_say   | taxonomy_fits   | why                                                                                                                                                                                                                                                                                                                      | best_recalibrating_arm   |   best_recalibrating_metric |   incumbent_metric | beats_incumbent_on_accuracy   |   fold_wins |   n_folds |   observed_sr | remedy                                                                                                                       |
|:-------------------|:---------------------|:----------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-------------------------|----------------------------:|-------------------:|:------------------------------|------------:|----------:|--------------:|:-----------------------------------------------------------------------------------------------------------------------------|
| CONSTRAINT_REFUSED | POWER_LIMITED        | False           | the seven states classify STATISTICAL nulls; every recalibrating arm here BEAT the incumbent on the metric and was removed by a DETERMINISTIC constraint (a board rank against a fixed cap) with no sampling error to accumulate, so 'POWER_LIMITED' would emit a re-test trigger that more draft classes cannot satisfy | unconstrained (λ=1)      |                      0.9445 |             1.0738 | True                          |           6 |         7 |        1.3973 | a different MECHANISM, or a PM decision to revisit the constraint — never more draft classes, which cannot move a board rank |

⚠️⭐ **RECORDED AS `CONSTRAINT_REFUSED`.** `cv_power.classify_null` returns **`POWER_LIMITED`**. the seven states classify STATISTICAL nulls; every recalibrating arm here BEAT the incumbent on the metric and was removed by a DETERMINISTIC constraint (a board rank against a fixed cap) with no sampling error to accumulate, so 'POWER_LIMITED' would emit a re-test trigger that more draft classes cannot satisfy

⇒ **remedy: a different MECHANISM, or a PM decision to revisit the constraint — never more draft classes, which cannot move a board rank**.

## 10. Honest limitations

- ⚠️⭐ **THE VERDICT RESTS ON A REGISTRATION CHOICE OF THIS STORY'S OWN — DISCLOSED IN §6a, NOT BURIED.** The blind constant shrink was registered as a NON-SHIPPABLE matched foil before the run, and had it been registered as a candidate it would have been selected and would have shipped. The choice was faithful to the brief (a fixed constant is not an IN-FOLD-SELECTED shrink) and re-classifying it now would be the E2.1-r inversion — but a reader is entitled to know that the eligibility of one arm, and not a gate LEVEL, is what separates this null from a ship. §5b shows the gate levels decide nothing.
- ⚠️⭐ **THE CONSTRAINT IS INACTIVE ON MOST BOARDS, WHICH BOUNDS WHAT 'C2 HELD OUT' MEANS EITHER WAY.** On 4 of the 8 boards read here the best rookie is a QB — the one position the recalibration may not touch — so no λ can move the rank and C2 admits everything vacuously (§2b). An arm's constraint record is therefore built from far fewer genuinely informative boards than the fold count suggests, in BOTH directions: the blind constant's clean sheet is as thin as the rules' failures are.
- ⚠️ **A PRE-REGISTERED ANCHOR (`over_scale`) FAILED AND THE GATE IS LEFT READING FALSE** (§1a). It is not the metric-inversion signature the anchor exists to catch — both do-nothing degenerates lose comfortably — but the bundled `degenerates_lose` flag now mixes a metric-sanity check with a refuted magnitude hypothesis, and a future reader must not read its False as 'the measurement is untrustworthy'.
- ⚠️ **THE PLACEMENT CAP'S REFERENCE DISTRIBUTION IS NOT WALK-FORWARD, AND IT IS INHERITED RATHER THAN RE-DERIVED.** NF-D17's `REALIZED_BEST_ROOKIE_OVERALL_RANK` spans 2019–2025, so the cap applied to the 2019 board was estimated partly from seasons after it. Re-deriving a per-fold cap would mean re-specifying the very validated clause this story must clear — the E2.1-r inversion facing the other way — so the clause is imported verbatim. The bound on the cost: the cap is a CONSTANT, identical for every arm and every fold, so it cannot favour one arm over another; it can only shift the whole field's admissible set together.
- ⚠️ **THE FIRST HELD-OUT CLASS HAS NO BOARD EVIDENCE AT ALL.** The merged boards begin at 2019, so every rule falls back to the registered empty-evidence default (λ = 0) on that class and contributes a delta of exactly 0. That is a real power cost of one fold in seven, registered in advance rather than discovered. It is reachable — earlier boards can be emitted with `--backtest-from` further back — but it is a DATA-availability limit on the metric, and it is stated separately from the constraint result so the two are never confused.
- ⚠️ **THE PER-FOLD CONSTRAINT IS EVALUATED ON ONE BOARD PER FOLD.** A board is a serving-time artifact, not a held-out statistical criterion, so C2 contributes no power — it can only remove arms. What bounds that: no arm's PARAMETERS are ever tuned to any board (the affine is fitted in-fold on rookie outcomes, and only the discrete λ is chosen), the clearance is required to be THRESHOLD-INVARIANT so no cutoff was picked, C2 is enforced OUT-OF-SAMPLE, and the ordering-only reading is reported beside it (§5c).
- ⚠️ **THE `min(cap, rank_incumbent)` TERM IS A REAL LOOSENING ON THE BOARDS WHERE IT BINDS, AND IT IS DISCLOSED RATHER THAN BURIED.** It was written into the pre-registration because the shipped product breaches the cap on some historical boards and a constraint that refuses the NULL has examined nothing — but on those boards it does admit λ values a bare cap would not. Both readings are computed (§2, §3) and the pre-registered one governs.
- **`tier_mae` grades the DRAFTABLE TIER — ~6 RB / 8 WR / 3 TE per class.** A claim here is a claim about a few dozen rookie-seasons across seven draft classes; the paired per-class deltas are reported so a reader sees the spread rather than only the mean.
- **The in-fold affine is estimated against IN-SAMPLE point projections** (the training rows' points come from the fold's own slot curve). NF-D16 measured the resulting optimism at −0.05 in constant space and the direction is CONSERVATIVE — it biases a correction toward the identity — but it is not zero, and it applies to every λ here.
- ⛔ **QB is out of scope by pre-registration, not by result** — inherited by import through NF-D16 from NF-D15/NF-D14, and proven untouched on both the held-out classes and every board rather than asserted.
- **No edge claim.** A projection-quality product: `best_alpha = 0`, no CLV/ROI statement.
