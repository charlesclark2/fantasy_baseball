# E7.16 — the comp pool rebuilt on the point-in-time MLB Pipeline archive
### (+ E7.14, run as phase 2 of the same session on the same cached cohort)

**Status (2026-08-01):** **DONE.** E7.13's deferred verdict is RESOLVED for batters and recorded as
an honest per-side bound for pitchers. `best_alpha = 0`. **The 8/3 draft file is UNCHANGED** — and
that is the finding, not an omission (§6).

| | |
|---|---|
| Cohort builder | `betting_ml/scripts/prospect_board/build_pipeline_cohort.py` — **OPERATOR-RUN, ~3 min cold** (29 s warm-cache; the 4.6M-row MiLB `delta_scan` is the cost). S3/DuckDB, SF-free |
| E7.16 runner | `run_e7_16_pipeline_comps.py` |
| E7.14 runner | `run_e7_14_source_accuracy.py` |
| Engine + harness | `prospect_comps.py` + `comp_validation.py` — **reused, not rebuilt** |
| Artifacts | `ablation_results/e7_16_artifacts/` (gitignored; ~1 min to regenerate) |
| Tests | `test_e7_16_pipeline_comps.py` (28, fast-gate) |

---

## 1. The one-line result

**E7.13 said "the batter comp term is BLEND-ELIGIBLE but deliberately NOT WIRED — re-check 2029."
It is now checked.** On a cohort with no retained-board hindsight and a **strictly-matured** fold
plan, the batter comp term clears every pre-registered gate. The reason E7.13 withheld the ship is
discharged, three years early, and the thing it licenses is **what the board already displays**.

| | batters | pitchers |
|---|---|---|
| verdict | **BLEND_WIRE** (was `BLEND_ELIGIBLE_NOT_WIRED`) | **DISPLAY_ONLY** (unchanged) |
| best contender | `comp_gower_k25` | `comp_mahalanobis_k15` |
| CRPS vs the incumbent | **−8.31** (p < 0.0001) | −2.82 (p = 0.186) |
| PBO (contender set) | 0.00 | 0.00 |
| DSR (contender set) | **1.000** ✅ | 0.379 ✗ |
| PIT max decile dev | 0.036 ✅ | 0.038 ✅ |
| **fold plan** | **4 strictly-matured** | **4 strictly-matured** |

---

## 2. 🔢 The fold count — measured, not assumed (readiness lock 1)

The story hypothesised ~13 matured folds. **It is 4** (relaxed: 7), and the binding constraint is
**ours, not MLB's**:

| bound | reach | binding? |
|---|---|---|
| MLB Pipeline archive | 2010–2026 (17 seasons) | no |
| E7.1 MiLB game logs (the as-of features) | 2005–2026 (no 2020 — MiLB was cancelled) | no |
| Pipeline's published **Overall grade** | 2014+ (0% before) | nearly |
| Org lists 30 deep | 2015+ (Top 10 in 2011, Top 20 in 2012–14) | nearly |
| **`mart_{batter,pitcher}_rolling_stats` — the realized-MLB LABEL** | **2015+ (Statcast era)** | **YES** |

A 2014 board's 3-season window opens before the marts begin, so a real player would be scored as a
partial bust. Three independent bounds happen to agree at **2015**; the ceiling is the newest board
whose window has closed (**2022**). ⇒ **board seasons 2015–2022, 7,186 rows, 3,202 distinct
players**, and a strictly-matured plan (`train + horizon < query`) of **2019, 2020, 2021, 2022**.

**Four is the number that matters**, because CSCV needs ≥ 4 folds: PBO is computable on a
**strictly-matured** plan here for the first time. E7.13 had **one** matured fold and had to relax.

> ⚠️ **The 2020 discontinuity is real and is not patched.** MiLB was cancelled, so a 2021 board's
> as-of line is necessarily from 2019; and MLB 2020 was 60 games, so every window covering it is
> depressed. Both are what an evaluator actually faced and both are shared by every arm.

---

## 3. 🔍 The hindsight is gone, and the detector proves it can fire

E7.13's headline defect was that FanGraphs' retained board carries a `level` column which is a
near-perfect one-sided bust tell. `comp_validation.leakage_scan` makes that crosstab mechanical and
runs it over **every** as-of column of the new cohort.

**Zero columns flagged.** And — the half that makes it mean anything — the same detector is scored
on E7.8's cohort in the same pass as a **POSITIVE CONTROL** and **fires**: `level`'s largest
one-sided bin is 883 rows (16.8%) at a **0.000** debut rate, while the negative control `fv` comes
back clean at AUC 0.7005. A scan that has never fired on a known positive is not evidence
(NF1.7 (a)); `LeakageControlError` is a hard stop if it ever stops firing.

The primary tell is deliberately the **one-sided block, not the AUC** — an honest grade and a
contaminated status column are only 0.10 of AUC apart on live data (0.701 vs 0.800), far too narrow
to gate on. What separates them is structure: a real predictor is *graded*, a post-hoc column
produces a large **pure** block.

Two design choices do the actual work of removing the hindsight:

* **age is recomputed from `birth_date` against the board date.** MLB's archived page returns the
  player's CURRENT age (Buxton comes back 32 on the 2015 board, where he was 21). Every such field
  is `_current`-suffixed in the table and **this cohort reads none of them** — pinned by a test that
  greps the assembly SQL.
* **the grade is the season's own scouting report.** `mlb_pipeline._select_bio` takes the report
  titled `season`, else the newest **not after** it. Verified across the whole archive: **zero** rows
  carry a bio from after their season, and a violation raises rather than scoring.

---

## 4. ⭐ The position asymmetry reproduces a THIRD time — and it is now visible in one table

E7.8 found FV **substitutes** for our read on hitters and **complements** it on arms. E7.13
recovered it independently. E7.16 recovers it a third time, on a different pool, and this run makes
the mechanism explicit — look at what the FV-bucket **blend** does to each side:

| paired ΔCRPS (negative = the arm is better) | batters | pitchers |
|---|---|---|
| `blend_comp_fv` vs the incumbent `fv_bucket` | −6.75 *** | **−2.73** (p = 0.0045) |
| `blend_comp_fv` vs the **pure comp** distribution | **+1.50** (p = 0.053 — the blend is WORSE) | **−3.94** *** (the blend is BETTER) |

**On batters, mixing the scouts' grade back in makes the comp read worse. On pitchers, it is the
only thing that makes it beat the grade at all.** Same asymmetry, third independent measurement, now
with a directly attributable mechanism rather than a rank.

The matched-foil attribution agrees with E7.13's on both sides — similarity is the largest single
channel (batters −21.46, pitchers −15.66 vs the random-neighbour placebo), and the component block
alone is worse than random neighbours on both.

**All four two-sided anchors passed on both sides**: nothing beat the peeking oracle; `all_zero`
(the nihilist that wins MAE) and `marginal` both lost; the matched placebo lost.

---

## 5. 🚨 A defect found in E7.13's ORDERING harness — and what it corrects

The ordering study scored `comp_only` against `board_proxy` **on different populations**.
`rank_ic` drops non-finite rows; `comp_only` is finite only where the engine produced comps (64–69%
of the pool) while `board_proxy` is finite nearly everywhere. **And the comped subpopulation is
intrinsically easier to order, because having comps means having a minor-league record.** This is
the CRPS half's own `usable`-intersection rule — *a comparison over different row sets is not a
comparison* — which the ordering half was missing.

Measured on the strictly-matured folds:

| | as published | on matched support | how much was the population |
|---|---|---|---|
| `comp_only` − `board_proxy`, batters | +0.1073 | **+0.0330** | **69%** |
| `comp_only` − `board_proxy`, pitchers | +0.0991 | **+0.0513** | 48% |

`board_proxy` alone scores **+0.4385** over the full population and **+0.5186** on the matched rows —
i.e. most of the "win" was the rows. (Restricting only on `comp_only`'s own support, which isolates
the effect most sharply, leaves batters at **+0.0138** — 87% population.)

**⚖️ This CONFIRMS what E7.13 wired and corrects only what it didn't.** The blend arms
(`board_plus_comp_w*`) fall back to the board's score where a comp is absent, so they were always
defined on the same rows as the incumbent and were never affected. On matched support the blend's
edge over the incumbent **grows** (`w30`: batters +0.0368 → **+0.0507**; pitchers +0.0280 →
**+0.0514**), and the winner flips from
`comp_only` to the blend on **every** type × form. E7.13 §6.2 read `comp_only`'s relaxed-fold win as
an *era artifact* refuted by its single zero-overlap fold; it now has a **second, measurable**
explanation — the population — and both point the same way. `comp_only` was measured, reported, and
deliberately not wired; the fix is applied to E7.13's runner and its artifacts are regenerated.

### The ordering result on the deep folds

| | batters | pitchers |
|---|---|---|
| best contender | `board_plus_comp_w40` / `w30` | `board_plus_comp_w40` / `w30` |
| ΔIC vs the board's own formula | +0.0548 / +0.0353 | +0.0564 / +0.0470 |
| folds improved | 4/4 | 4/4 |
| PBO | 0.00 | 0.167 / 0.00 |

**Positive in 16 of 16 fold × type × form combinations on strictly-matured folds** — versus E7.13's
+0.0101/+0.0192 on its single clean fold. `w30` and `w40` differ by ≤ 0.004 IC on every cell, which
is a tie: **the shipped `COMP_RANK_WEIGHT = 0.30` is confirmed and is not re-picked inside its own
tie band** (the E2.1-r rule).

---

## 6. 🎯 What this changes on the board: nothing — and why that is the result

The batter verdict is **BLEND_WIRE**, so the natural next question is what to wire. The answer is
that the thing it licenses is **already what ships**:

* the winning batter arm is the **pure `comp_gower_k25` distribution** — the band the board already
  displays — and mixing it with the FV bucket makes it *worse* (§4). There is nothing to add;
* the E8.0 board emits **no blended point projection** at all (`comp_fp_median`, `comp_band_*` are
  the comp distribution itself), so a projection-blend term has **no consumer today**;
* the ORDERING term is already wired at `COMP_RANK_WEIGHT = 0.30`, and §5 confirms that exact weight
  on deep clean folds.

⇒ **The 8/3 draft file `e7_13_prospect_board_comps.xlsx` stands unchanged**, per readiness lock 3 —
what changed is its *warrant*: the batter comp band moves from "display, unvalidated, re-check 2029"
to **certified on a hindsight-free, strictly-matured, deflated backtest**.

**⏭️ E8.1 still owns the `board_assembly.attach_scores` footgun fix.** E7.16 deliberately did NOT
take that edit: the wiring it would install is the ordering term that already ships, the refactor
needs the comp pool inside the E8.0 runner (which today reads neither the pool nor E7.3's pair
files), and doing it two days before the draft on the exact file the operator drafts from is the
risk lock 3 exists to prevent. **No double-edit hazard — E8.1's edit is untouched.**

---

## 7. The pitcher null, made attributable

`DISPLAY_ONLY` stands, and the story asked that a miss be recorded as a real per-side null rather
than a failure. Two things make it attributable rather than a shrug:

* **the binding constraint is NOT DSR alone.** With the DSR gate removed the pitcher side *still*
  fails, on BH-FDR. Saying "it just missed DSR at 0.379" would be wrong;
* **the selection was resolved inside a 0.081% gap.** `comp_mahalanobis_k15` (114.28) beat
  `blend_comp_fv` (114.37) by 0.08 CRPS, and the flip distribution spreads over three arms
  ({blend 3, mahalanobis 2, k25 1} of 6) — a genuine tie (NF1.8). The arm that lost that coin flip
  is the one whose paired test against the incumbent lands at **p = 0.0045 and survives FDR**. That
  is reported and the pre-registered min-CRPS pick is **not revisited**: re-picking on a p-value
  seen after the fact is the E2.1-r inversion facing the other way.

⇒ **the pitcher comp term is a tie at the top of a field the study cannot separate at 4 folds — not
an absent effect.** Re-runs mechanically: each new board season whose window closes adds one fold
(5 in 2023-label terms → 2026 board matures 2029).

---

## 8. E7.14 — which SOURCE orders realized value best? (phase 2, same session, same cohort)

Run on the identical cached cohort with the identical harness, per the PM sequencing decision.
E7.11's own `build_consensus` computes the consensus arm, so "the consensus" here is byte-identically
the object the 8/3 board ships. **Cohort reported before scoring: 3,667 rows, 1,790 players, seasons
2018–2022** (the FanGraphs archive is the binding overlap).

> ⚠️ **The asymmetry that decides what this can conclude.** FanGraphs' board is RETAINED (E7.13
> measured a leak on it) **and** its snapshot is stamped `-07-01` against MLB Pipeline's `-02-01`,
> so the FanGraphs rank has seen five more months of the same season. **Both inequalities favour
> FanGraphs ⇒ a FanGraphs win would be uninterpretable; a Pipeline win or a tie is conservative.**

**Three questions, three different answers.**

| question | answer |
|---|---|
| Which source's **rank** orders better? | **NULL.** Pipeline − FanGraphs = **+0.0040** against a minimum detectable gap of **0.0245**, 3/5 folds, sign-inconsistent. Cannot distinguish. |
| Does the **consensus** beat the best single source? | **NOT EARNED.** +0.0043, positive in **2 of 5** folds. E7.11's refusal to claim "averaging is more accurate" stands. |
| Does the point-in-time **grade** beat the ranks? | **REAL BUT NOT CERTIFIABLE HERE.** `pipeline_grade` is the best arm overall (+0.3772) and beats FanGraphs' FV in **5/5** folds — but see below. |

⇒ **E7.11's EQUAL WEIGHT is CONFIRMED as the honest default and the shipped 8/3 board needs no
re-export.** Equal weight is kept because it is the honest default, **not** because it was shown to
be better — the distinction the story asked for.

### 8.1 🚨 The gate is unattainable at 5 folds, and that is a computed finding

With a fold sign test the smallest attainable p-value over 5 folds is **2/2⁵ = 0.0625**, while BH's
rank-1 cutoff over the 5-test family is **0.01**. **No effect of any magnitude could pass.** DSR is
likewise **UNCOMPUTABLE** (it needs ≥ 8 observations and the observation is the FOLD, not the row) —
reported as uncomputable, never as a nan a reader's eye slides past.

So "we tested it, nothing there" would be **false** for the grade result. Stated in the unit that
grows (NF1.8): it needs **8 overlapping board seasons and has 5**, and the overlap grows one per
year. The rank head-to-head is a *different* kind of no — its gap is a fifth of the detectable one
and does not hold its sign, which is a genuine null at any gate.

### 8.2 ⭐ The hindsight-free E7.8 replication

| | FanGraphs FV rank-IC | MLB Pipeline grade rank-IC | Δ |
|---|---|---|---|
| pooled | +0.3371 | **+0.3772** | +0.0401 (5/5 folds) |
| batters | +0.3903 | **+0.4376** | +0.0473 |
| pitchers | +0.3109 | **+0.3426** | +0.0317 |

**E7.8's FV finding does not rest on retained-board hindsight.** A genuinely point-in-time 20-80
grade orders realized dynasty value *at least as well* as the retained FV — from a source holding
**neither** structural advantage. Had hindsight been carrying E7.8's result, the retained grade would
have been the stronger one. It is not. (Read as a direction, not a certified margin — §8.1.)

---

## 9. Known limitations, stated

* **4 folds is few.** PBO is computable and DSR is meaningful at 734/663 person-clusters, but the
  fold count is the ceiling on the ordering inference and it is the number to grow.
* The cohort is **MLB Pipeline's universe** — the top 100 plus 30 org top-30s, ~898 players a season.
  A player neither list ranked is absent, which is a different (narrower, more selected) population
  than FanGraphs' deeper board. The two studies' absolute levels are therefore not comparable; the
  deltas within each are.
* **Matched support costs rows.** 56–62% of the ordering cohort has every arm defined (vs 80–88% on
  E7.13's pool), because Pipeline's org lists reach further into just-drafted and international
  players with no full-season record. That is the honest denominator, but it is a smaller one.
* The target remains 3-season dynasty fantasy points — it under-serves a player whose value is speed
  or defence, the same gap `board_assembly`'s `speed_flag` exists to surface.
* `pipeline_grade_overall` is parsed from **prose**, not a field (`mlb_pipeline.py` §"tool grades are
  prose"). Coverage is 91.5% across 2015–2022 and dips to 0.69–0.75 in 2020–21; a miss is a `None`,
  never a 0.
