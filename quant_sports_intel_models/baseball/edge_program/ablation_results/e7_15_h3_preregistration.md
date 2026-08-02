# E7.15 H3 — pre-registration: the PLAYER is the unit, not the row

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": null,
 "gates": null,
 "n_arms": null,
 "n_folds": null,
 "per_metric": null,
 "primary_contrast": null,
 "reason": "same as h1: a pre-registration, cited by run_e7_15_h3.py as 'written before any arm was scored'; results land in e7_15_h3_player_structure(_pitchers).md.",
 "schema": 1,
 "source_artifact": null,
 "status": "exempt",
 "verdict": null
}
-->


_written **2026-08-01, before any arm was scored**. Every number in §1 and §2 is a property of the
substrate, measured before a leaderboard existed to rationalise against (the H1 readiness lock-2
discipline). `best_alpha = 0` — a Dynasty/board projection and a betting prior, never a market bet._

---

## 1. The premise, measured first

`build_graduated_pairs` emits **one row per (player_id, level)**, and every one of a player's rows
carries the **same** MLB label — its own docstring calls that "a stated limitation". So the training
matrix is pseudo-replicated, and the fit currently treats a player's four level-rows as four
independent observations of the minor→MLB map.

| | batter | pitcher |
|---|---:|---:|
| labelled rows | 2,171 | 3,031 |
| distinct players | **736** | **1,048** |
| replication | **2.95×** | **2.89×** |
| rows/player histogram (1 / 2 / 3 / 4) | 125 / 96 / 206 / 309 | 166 / 199 / 265 / 418 |
| share of fitted weight from the top 42% of players | **56.9%** | **57.3%** |
| rows on a player who can pool at all (≥2 rows) | **94.2%** | **94.5%** |
| debut cohorts (= CV folds) | 12 | 12 |

⭐ **The effective sample size is 736 players, not 2,171 rows**, and the over-weighting is *unequal*:
measured on the live substrate the normalised observation weight runs **p05 0.74 → p95 2.95 — a 4.0×
spread in influence** between an otherwise-identical one-level and four-level player.

⚠️ **THIS IS AN EFFICIENCY QUESTION, NOT A LEAKAGE BUG, AND THE DISTINCTION IS LOAD-BEARING.** The folds
are MLB debut cohorts and `debut_cohort` is a per-PLAYER join, so **all of a player's rows share one
fold and no player straddles the train/test boundary**. Nothing here is leaking. What is at stake is
only whose line the coefficients are fitted to. A report that framed this as leakage would be wrong.

### Per-mechanism coverage — can each arm act at all?

Measured before scoring, so a null is attributable to the mechanism rather than to coverage:

| mechanism | batter | pitcher |
|---|---:|---:|
| de-pseudo-replication weight (rows whose weight moves) | 100.0% | 100.0% |
| player random intercept (rows whose player can pool) | 94.2% | 94.5% |
| trajectory delta (rows with a real previous level) | 66.1% | 65.4% |
| level tenure (rows that repeated a level) | 34.9% | 36.0% |

All four clear the `MIN_PCT_ROWS_MOVED = 1%` activity bar by a wide margin. **A null from H3 will be a
null about the mechanism, not about power to apply it.**

---

## 2. The arms

Foil is the **shipped E7.12-slice-1 configuration per metric** (learner, prior scale, park/level-env
context and `weight_col` all held fixed) — the same foil H1 and H2 used, so the three slices are
mutually comparable.

| arm | mechanism | why it is in the field |
|---|---|---|
| `L0_foil` | ⭐ the shipped configuration | the direct-learned foil (§0.5) |
| `P1_dedup` | weight ← base ÷ n_rows(player) | full de-pseudo-replication: every PLAYER carries equal weight |
| `P2_dedup_sqrt` | weight ← base ÷ √n_rows(player) | **matched partner to P1** — "1/n over-corrects" is a separate hypothesis from "1/n is right", and a field carrying only one cannot tell them apart |
| `P3_player_re` | penalized per-player intercept | the textbook fix for pseudo-replication |
| `P4_re_dedup` | P3 + P1 | do the two compose, or is one redundant given the other? |
| `T1_traj_ladder` | ladder-adjusted change from the previous level | **genuinely new information** — two identical final lines mean different things if one player arrived improving |
| `T2_traj_raw` | the RAW previous-level change | **matched foil for the ladder's contribution here** |
| `T3_tenure` | years-at-level + levels-logged | repeating a level is a scouting-legible negative signal the aggregated box line erases |

⭐ **`P1`/`P2` MULTIPLY the arm's own foil weight, they do not replace it.** The shipped pitcher configs
for `bb_pct`/`hr_rate` already carry `w:mlb_pa`; a bare `1/n` would change two things at once and the
arm would be unattributable. On a side whose foil is unweighted the base is 1.0 and it reduces to the
plain `1/n`.

⭐ **NO NEW PROJECTOR CLASS.** `PartialPoolProjector`'s slice-5 `bucket_col`/`bucket_intercept` machinery
*is* a generic grouped random intercept, so `P3` reuses it. A subclass would have re-opened the
documented E7.12-S5 landmine: `clone_projector` is `isinstance`-dispatched and returns a **plain**
`PartialPoolProjector`, so a subclass's extra config would be silently dropped on every expanding-window
refit and the arm would score **as the foil under its own name** — the same silent-inert-arm class as
the H2 anchor defect. Pinned by a test.

---

## 3. ⭐ A PRE-REGISTERED DIRECTIONAL PRIOR: we expect P3/P4 to LOSE, and we say so now

Because the label is **constant within a player**, a player intercept can absorb *all* between-player
variation in `y`, leaving the fixed effects identified only by **within-player** variation — i.e. it
silently converts the estimator into a within-player one, whose identifying variation is exactly the
level-transition variation **H1 already measured and found null**. At predict time a held-out player has
no column (its intercept is 0), so the prediction comes from fixed effects fitted on within-player
contrasts alone, discarding the between-player information the incumbent actually runs on.

**So P3/P4 are registered as a DECOMPOSITION — how much of the incumbent's skill is between- vs
within-player — not as hopefuls.** A loss is an informative measurement of where the model's skill
lives. A *win* would overturn the reading above and would be the more interesting outcome. Stating the
expected direction before the run is what makes either result a finding rather than a rationalisation.

---

## 4. Anchors — what must hold, and what each one is defending against

| trap | anchor | must hold |
|---|---|---|
| the harness silently changed something | `A_weight_identity` | **byte no-op** — MAE gap EXACTLY 0 vs the foil |
| a random intercept is just extra regularization, nothing to do with "players" | `A_re_shuffled` | must **not beat** `P3` |
| the trajectory ordering carries no real information | `A_traj_shuffled` | must **LOSE** |
| MAE is inverted on this cohort | `A_degenerate_mean` | must **LOSE** |

⭐ **`A_re_shuffled` is the sharpest test in the slice.** It permutes the row→player assignment while
**preserving the group-size multiset exactly** (the same 125 singletons / 96 pairs / 206 triples / 309
quads), so the shuffled block has the same width and the same shrinkage geometry as the real one and
the *only* thing that differs is whether the grouping is the truth. A "shuffled" foil with different
group sizes would be testing block width instead (NF1.7 (b): a foil must be matched in family *and*
resolution).

🕳️ **`pct_rows_moved` IS MEASURED IN EACH MECHANISM'S OWN UNITS — a direct consequence of the H2 defect.**
H1 and H2 both rewrote `minor_<metric>`, so "did the arm act" was a feature diff. **H3's weighting and
random-effect arms move no feature value at all**, so a feature-diff activity check would report 0% for
every one of them and the new `must_move` guard would block the entire slice for the wrong reason.
Weight arms therefore report the share of rows whose normalised weight moved; the RE arm reports the
share of rows whose player can pool (plus the fitted block width); trajectory arms report non-imputed
delta coverage. **The H2 lesson generalises to: prove the mechanism acted, in the mechanism's own
units — an inert-anchor guard is only as good as its activity metric.**

---

## 5. Gate (pre-registered, unchanged from H1/H2 so the three are comparable)

An arm ships only if **all** of:

1. strict OOS improvement vs the foil in **≥60% of folds**;
2. **>1%** of rows moved, in the mechanism's own units;
3. **every anchor holds** — a missing anchor BLOCKS (NF1.7 (a)) and so does an **inert** one (H2);
4. **PBO(eligible) < 0.20** *and* **DSR(eligible) ≥ 0.95**, with the whole-field reading reported beside
   the contender-set reading (NF-D14) and a high PBO over a *tied* field read as the null, not as
   overfitting (E2.1-r), classified by contender spread rather than left to the reader;
5. **BH-FDR at α=0.10** over the side's metric family — a gate, not a footnote;
6. for a **board** metric, a non-negative **LOW-propensity-tercile** lift on **moved rows only** (H5,
   with the E7.15-H1 correction: the tercile's level mix is published beside it, because the low tercile
   is the one *richest* in Triple-A rows and an all-rows read dilutes exactly the end the gate is about).

**If nothing clears:** the null is stated **in the unit that grows** (folds ARE debut cohorts — one per
MLB season), separating a *genuine absence* (the best arm loses on average; no sample size rescues a
negative point estimate) from *underpowered* (positive but short of the bar, with the number of extra
cohorts needed). And the null is re-decided with the deflation gates removed, so the record can say
whether it rests on our own gate choice (NF-D15 g″).

---

## 6. Leakage posture

* Row counts, level tenure and the player grouping are MiLB-side facts carrying no MLB label.
* The trajectory delta uses the **H1 ladder**, fitted per fold with **`exclude_players` = the held-out
  cohort's players** — the leave-one-player-out posture H1 established, so no map applied to a player
  was fitted using that player's own later-level line.
* Every arm is asserted to score the **identical labelled population** each fold; an arm that changed
  the population would not be an ablation and raises rather than scores.
