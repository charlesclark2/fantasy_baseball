# E7.15 H1 — pre-registration: the within-player level-translation ladder

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": null,
 "gates": null,
 "n_arms": null,
 "n_folds": null,
 "per_metric": null,
 "primary_contrast": null,
 "reason": "a pre-registration ('written before any arm was scored', per run_e7_15_h1.py's own citation) \u2014 the results land in e7_15_h1_level_ladder.md, covered above.",
 "schema": 1,
 "source_artifact": null,
 "status": "exempt",
 "verdict": null
}
-->


_written 2026-08-01, **BEFORE any arm was scored**. The transition census in §2 is the only measured
content here; it was produced by `run_e7_15_h1.py --transitions-only`, which computes no MAE and fits no
model. `best_alpha = 0` — a Dynasty/board projection and a betting prior, never a market bet._

---

## 1. The claim, and why it is not another re-expression of the box score

E7.12 closed six slices with one direction: **everything that WON is about who is in the sample and how
precisely each label is measured; everything about WHAT THE PLAYER DID nulled** (park, age, tool grades —
four independent slices, same answer). A disattenuation check refuted the comfortable reading that we had
hit the label-noise ceiling: E7.3 sits at OOS correlation 0.64 / 0.49 (batter K% / BB%) against a
label-reliability ceiling of 0.93 / 0.83. There is real headroom. The nulls are therefore genuine
**information failures** — park, age and grades are all re-expressions of the same minor-league line — and
round 2 has to add information that is not already in a player's own box score.

H1's information source is the **within-player minor→minor transition**. E7.3 learns
`MLB_rate ~ f(minor_rate, level, league, age)` from graduates only. But the level-to-level part of that map
needs no MLB label at all: a player who posted a .330 wOBA at High-A and .310 at Double-A is a direct
observation of the High-A → Double-A translation. There are 2,102 of those against 432 labelled High-A
rows, and **65% of them belong to players who never reached MLB** — precisely the un-promoted population
the E8.0 board is served on, and precisely the population a graduates-only fit structurally cannot see.

So: estimate every rung EXCEPT the last from within-player transitions, express every row at a common
reference level (Triple-A), and let the existing pooled learner do the final AAA→MLB step on labelled
graduates. This multiplies n for the lower rungs, confines the promotion-selection problem (E7.12 slice 2)
to the final rung, and is new information rather than a restatement.

---

## 2. ⭐ The transition census — the premise, measured first (readiness lock 2)

The n-multiplication IS the hypothesis, so the counts come before any leaderboard exists to rationalise
against. A rung that is thin is a **per-rung null**, not a failure of the idea, and that distinction has to
be available in advance.

### Batters (`mle_graduated_pairs.parquet`, 20,561 rows / 9,804 players, season floor 2015)

| rung | usable transitions | never-MLB source | labelled rows at that source level today | multiplier |
|:--|--:|--:|--:|--:|
| Single-A → High-A | **2,204** | 1,727 (78.4%) | 306 | **7.2×** |
| High-A → Double-A | **2,102** | 1,361 (64.7%) | 432 | **4.9×** |
| Double-A → Triple-A | **1,314** | 577 (43.9%) | 563 | **2.3×** |
| Single-A → Triple-A *(one-step)* | 695 | 314 (45.2%) | 306 | 2.3× |
| High-A → Triple-A *(one-step)* | 982 | 439 (44.7%) | 432 | 2.3× |
| Single-A → Double-A *(one-step)* | 1,494 | 977 (65.4%) | — | — |
| **Triple-A → MLB** *(the final rung — unchanged, still label-bound)* | **461** | — | 461 | 1.0× |

5,945 of 9,804 batters carry ≥2 level rows. Every count above already enforces both gates: ≥150 PA on
**both** sides of the pair, and the destination stint starting no earlier than the source stint (a rehab
demotion is not a promotion translation).

### Pitchers (`mle_graduated_pairs_pitchers.parquet`, 23,949 rows / 11,209 players)

| rung | usable transitions | never-MLB source | labelled rows at that source level today | multiplier |
|:--|--:|--:|--:|--:|
| Single-A → High-A | **2,207** | 1,691 (76.6%) | 356 | **6.2×** |
| High-A → Double-A | **2,172** | 1,399 (64.4%) | 524 | **4.1×** |
| Double-A → Triple-A | **1,367** | 714 (52.2%) | 664 | **2.1×** |
| Single-A → Triple-A *(one-step)* | 680 | 350 (51.5%) | 356 | 1.9× |
| High-A → Triple-A *(one-step)* | 983 | 493 (50.2%) | 524 | 1.9× |
| **Triple-A → MLB** *(final rung)* | **491** | — | 491 | 1.0× |

**Reading.** The premise holds on both sides and no rung is thin — every one clears the pre-registered
`MIN_RUNG_N = 60` floor by more than an order of magnitude. H1 is therefore a real test, not an
underpowered one, and a null from it will be a null about the mechanism rather than about sample size.

### ⚠️ One metric is structurally inert, and that is a finding, not an omission

`xwoba_against` (pitcher) has **zero** transitions: its minor feature is the E7.2 AAA-Statcast summary,
which exists only at Triple-A, so there is no lower-level line to translate from. The ladder cannot act on
it. Per NF1.9, that is reported as "the mechanism cannot act" and the arm is marked INACTIVE and made
unselectable — it is never reported as "the ladder is a clean null here."

**H6 is honoured by this census.** The pitcher side is furthest from its reliability ceiling
(disattenuated 0.41–0.47 vs batters' 0.59–0.69) and its rung multipliers are comparable, so it is run as a
first-class side rather than as a replication footnote.

---

## 3. The pre-registered arm set — a bake-off, not a ladder (readiness lock 1)

§0.5 forbids testing one architecture and calling its miss a null. Four **formulations** are registered
against a direct-learned foil, with the learner and its `weight_col` held fixed at each metric's shipped
values (E7.9: 54–77% of a bake-off leader's apparent margin can be the learner swap, not the mechanism).

| arm | kind | formulation |
|:--|:--|:--|
| `L0_foil` | **foil** | ⭐ the configuration LIVE on the board today — the shipped E7.12-slice-1 `ContextSpec` per metric, **no ladder**. The matched pair. |
| `L1_chain_ols` | ladder | composed adjacent-rung OLS maps (A → A+ → AA → AAA) |
| `L2_chain_paweighted` | ladder | the same chain, rung regressions weighted by the pair's harmonic-mean line length. **L1's matched pair** — the weighting's contribution is attributable, not bundled. |
| `L3_direct_to_ref` | ladder | ⭐ one-step (level → Triple-A) maps from the players who actually made that jump — avoids the chain's threefold attenuation compounding |
| `L4_ladder_delta` | ladder | ⭐ **NESTS THE FOIL** — the raw line is kept and the ladder DELTA enters as an unpenalized fixed regressor, so a win is unambiguously "the ladder adds information beyond the raw line" (foil = coefficient 0) |
| `L1p_chain_purged` | sensitivity | L1 with every transition that had not FINISHED before the held-out cohort purged (see §5) |

The foils per metric, pinned as literals from the slice-1 reports so the harness cannot silently compare a
change against a re-derivation of itself:

| side | metric | foil `ContextSpec` |
|:--|:--|:--|
| batter | woba | `levelenv` |
| batter | k_pct | `park:exposure+levelenv+rel:0.5k` |
| batter | bb_pct | `park:exposure+levelenv+rel:2k` |
| batter | iso | `park:exposure+levelenv+rel:2k` |
| pitcher | bb_pct | `park:exposure+levelenv+rel:1k+w:mlb_pa` |
| pitcher | hr_rate | `park:exposure+levelenv+rel:1k+w:mlb_pa` |
| pitcher | k_pct / gb_pct / xwoba_against | `baseline` (slice 1p DROPPED these — the bare incumbent IS what ships) |

---

## 4. 🪤 What would make this lie, and the anchor that catches each

| trap | anchor | must hold |
|:--|:--|:--|
| the ladder CODE PATH itself perturbs the fit, so every margin is confounded with plumbing | `A_ladder_identity` (rung maps forced to `0 + 1·x`) | a **byte** no-op vs `L0_foil` |
| it is really a per-LEVEL re-centring — which the E7.3 level intercepts already own — not per-player content | `A_ladder_meanshift` (per-rung **additive** shift, slope pinned to 1) | must **LOSE** (NF-D15 g′) |
| the two marginals do the work and the within-player link is decorative | `A_ladder_shuffled` (destination rates permuted within rung; both marginals intact) | must **LOSE** |
| MAE is inverted on this cohort so a nihilist wins | `A_degenerate_mean` (predict the population mean) | must **LOSE** (NF-D11 / NF-D14) |
| the selection metric is inverted outright | ORACLE FLOOR | no candidate may score MAE < 0 |

**A MISSING anchor BLOCKS the metric.** An anchor that did not run is not an anchor that passed
(NF1.7 (a)); the runner enumerates the required four and refuses to ship without all of them.

**Two pre-registered predictions about the anchors**, stated now so they cannot be written to fit the
result. (a) `A_ladder_shuffled`'s fitted rung slopes must collapse toward 0 — verified on synthetic data;
if they do not, the permutation is not doing what it claims. (b) The chain's composed Single-A → Triple-A
slope will be **materially smaller** than the one-step `direct` estimate, because composing three
attenuated regressions attenuates three times while one step attenuates once. On the live batter ISO
substrate the measured gap is **0.182 (chain) vs 0.463 (direct)** — a 2.5× over-shrink. That is exactly
why `L3_direct_to_ref` is in the field, and if the chain arms lose while the direct arm wins, this is the
stated reason, not a post-hoc one.

---

## 5. 🔒 Leakage, in two layers (readiness lock 4)

1. **Leave-the-held-out-player-out — ALWAYS ON.** Every transition belonging to a player in the evaluation
   fold is dropped before the rung maps are fitted, so no map applied to a player was estimated using that
   player's own later-level line. This is slice 1's leave-one-player-out park posture, one mechanism over,
   and it is the specific leakage the readiness pass named.
2. **Calendar purge — a REGISTERED SENSITIVITY, not an argument.** Slice 1's rule is that a MiLB-only
   transform touches no MLB label and can therefore be estimated over the whole substrate; the ladder is
   the same class. Rather than assert that, `L1p_chain_purged` additionally drops any transition that had
   not finished before the held-out debut cohort, and is scored beside `L1_chain_ols`. If the two agree,
   the question is settled by measurement. ⚠️ It costs real power on the early folds — the substrate starts
   in 2015, so the 2017 fold sees only transitions completed through 2016 — and the per-fold transition
   counts are reported rather than hidden.

**Survivorship is confined, not removed.** H1 pushes the promotion-selection problem into the final
AAA→MLB rung; that rung still carries it. Every number remains conditional on the graduated population,
and §6's per-tercile table is the honest read of who benefits.

---

## 6. The gate

An **ADD** requires all of:

1. a strict out-of-sample MAE improvement over `L0_foil`,
2. in **≥60%** of held-out debut cohorts,
3. the ladder actually MOVED **>1%** of rows (a mechanism that cannot act is not a null),
4. every anchor in §4 holds,
5. **PBO(eligible) < 0.20** — computed over the ELIGIBLE set, the search the selection actually ran, never
   over a field containing its own anchors (NF1.8/NF-D14); the whole-field figure is reported beside it,
6. **DSR(eligible) ≥ 0.95**, with the whole-field DSR reported beside it and the **eligible-set figure
   pre-registered to bind** (if both clear, nothing turns on the choice — the NF-D14 clean shape),
7. **Benjamini-Hochberg** over the per-side metric family at α = 0.10 — a gate, not a footnote (the
   slice-1 defect, not repeated),
8. for a **board metric**, a non-negative lift in the **lowest promotion-propensity tercile**.

Deflation is reported as four numbers, not one: PBO alone cannot separate "my pick is unstable" from "my
pick is tied" (NF1.8), so the flip distribution, Bailey's out-of-sample degradation and the contender
spread are all published.

### H5 — the per-propensity-tercile read, and why it can veto a board metric

Every arm is also scored inside promotion-propensity terciles from E7.12 slice 2's hazard, fit on seasons
strictly before the held-out cohort so the strata cannot be a function of the test fold's own promotions.
The board serves un-promoted prospects; slice 2 measured its winner helping the low tercile +0.54% against
+0.07% at the high end. **A board metric whose winner is negative in the lowest tercile is downgraded to
reported-but-not-shipped** — it improves the players we do not serve. A cosmetic metric (batter `woba`;
pitcher `hr_rate` / `xwoba_against`) has this stated rather than enforced, because a move there cannot
change a draft ranking.

### Reading a null honestly (readiness lock 5 — the MH2 caveat)

The ≥60%-fold clause is the known weak instrument: a placebo cleared it 9/11 in E7.12 S5/S6 and it
false-fires 49.7% of the time at 3 folds. **H1's deflation therefore does not lean on fold count alone** —
PBO, DSR and BH-FDR all bind independently. If H1 nulls, the margin is stated **in the unit that grows**
(rungs, seasons, transition rows), never in p-decimals (NF-D15 g″), and the characterisation of that
clause's false-fire rate is MH2's job, not this story's (H8, already carded there).

---

## 7. 🔒 Estimand preservation and the downstream contract (locks 3 and 6)

**The estimand does not change.** The ladder changes how the level translation is *learned*; the model
still predicts the same realized MLB rate from the same labelled population, and `emit_projections` still
writes `mle_<metric>` meaning "projected MLB rate", clipped to the same `PLAUSIBLE_RANGE`. The E8.0 board
and the E7.5b betting prior therefore stay comparable. This is asserted per fold, not assumed: an arm that
changed `has_target` would be scored on different players and the runner raises. (Contrast **H4**, which
explicitly changes the estimand to a regressed true-talent target and must pay a board-comparability cost
for it.)

**If an arm ships, re-emission is not the last step.**

* A **BATTER** arm ⇒ E7.5b's batter head-to-head gate (`mle_prior.head_to_head`) must be **re-run** before
  the served run_diff / pre-lineup rookie prior moves. Re-emitting the MLE does not auto-update it; that
  path reads a separately-recalibrated parquet. The gate exists — this is a one-line re-run.
* A **PITCHER** arm (especially anything moving `gb_pct`) ⇒ the pitcher head-to-head gate **does not
  exist**. Building it is in scope for that ship, not a re-run, and the standing warning against an
  ungated pitcher recalibration remains in force until it does.

---

## 8. The ordered follow-on agenda (registered, not run here)

| # | hypothesis | status |
|:--|:--|:--|
| **H2** | opponent / competition-quality adjustment — `build_park_context.py` **asserts** "opponent mix averages out over 3 seasons" and never tested it; reuse the NCAAF opponent-strength machinery | **NEXT.** ⚠️ scope-gate first: confirm opponent identity is actually present in the MiLB game logs, or the story is an ingest story wearing a modelling costume |
| **H3** | within-player trajectory / delta features + a player random effect — 60% of players have multiple level rows treated as independent; the design has **no player block**. "How his line changed as he climbed" ≈ what scouts mean by "made an adjustment" | registered; cheap. ⭐ **H1 builds the substrate H3 needs** — `build_transitions` is the trajectory frame |
| **H4** | predict a REGRESSED / true-talent target instead of a raw realized rate (14–40% of label variance is sampling noise) | registered. ⚠️ **changes the estimand** ⇒ inherits a board-comparability cost H1 explicitly does not pay; must state it |
| **H5** | per-propensity-tercile scoring, targeting the LOW tercile | ✅ **already implemented and enforced here** — it is an eval convention, not a separate story, and applies to H2–H4 verbatim |
| **H6** | prioritise the PITCHER side (furthest from its ceiling) | ✅ **honoured** — the pitcher side is a first-class run, not a replication footnote |
| **H7** | "add the new tracking metric" (bat speed etc.) | ⛔ **DECLINED, with reason.** `sc_avg_bat_speed_mph` covers **0.0%** of labelled rows — not one graduate can be scored today. The wall is a property of the DATA SOURCE, not our ingest, and the both-sides-of-the-expanding-window requirement means it stays that way for ~3 years. 🩹 whoever re-opens it: passing `sc_*` through `extra_cols` alone silently mean-imputes ~88% of rows (`_design` discards `_Scaler`'s missing flag) — use `_with_missing_indicators` |
| **H8** | the E7.12 harness defects (fold-count clause) | ✅ **routed to MH2**, which already owns it in its readiness block — MH2 must deliver the FIX, not only the diagnosis |

---

## 9. Code + reproduction

* `betting_ml/scripts/milb_mle/level_ladder.py` — the ladder mechanism (pure; no IO, no bake-off)
* `betting_ml/scripts/milb_mle/run_e7_15_h1.py` — the §0.5 harness, reusing E7.12 slice 1's deflation /
  anchors / FDR and slice 2's propensity strata rather than forking them
* `betting_ml/tests/test_e7_15_level_ladder.py` — 48 fast-gate guards. Two were verified to **FAIL on the
  pre-fix source** rather than passing vacuously: the identity-anchor byte no-op (the first implementation
  clipped unconditionally, so identity moved 0.1% of the live substrate) and the temporal-order filter
  (without it a rehab demotion is scored as a promotion translation).
