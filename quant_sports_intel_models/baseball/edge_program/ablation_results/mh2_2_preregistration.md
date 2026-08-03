# MH2.2 — pre-registration: the trajectory family, declared BEFORE it is scored

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": "leave-one-MLB-debut-cohort-out (n_cohorts)",
 "gates": null,
 "n_arms": 3,
 "n_folds": 11,
 "per_metric": null,
 "primary_contrast": null,
 "reason": "a pre-registration, cited by run_mh2_2.py as 'written before any arm was scored'; results land in mh2_2_trajectory_family(_pitchers).md.",
 "schema": 1,
 "source_artifact": null,
 "status": "exempt",
 "verdict": null
}
-->

_written **2026-08-03, before any MH2.2 arm was scored**. Every number in §1, §4 and §6 is a property of
the DESIGN or the SUBSTRATE, computable before a leaderboard exists to rationalise against.
`best_alpha = 0` — a Dynasty/board projection and a betting prior, never a market bet._

---

## 0. What this story is, and what it retires

E7.15-H3 recorded its trajectory arms as *"a REAL effect that FAILED DSR at 0.607 over the 7-arm field
and **CLEARS at 0.998** over the 2-arm trajectory family."* MH2 reproduced both figures exactly and
found the 2-arm field to be **POST-HOC**: H3's own pre-registration (`e7_15_h3_preregistration.md` §2)
names **three** trajectory arms — `T1_traj_ladder`, `T2_traj_raw`, `T3_tenure` — and the 0.998 is
computed over a field that silently drops `T3_tenure`, *the arm that lost*.

⛔ **Trimming a field after the fact is the second layer of the very selection bias DSR exists to
deflate. You get to pre-register a family; you do not get to discover one** (MH2 §(a)).

So MH2.2 is **not** "re-run it smaller and collect the win." It re-runs the trajectory mechanism as a
standalone §0.5 bake-off **with the family declared in advance**, and its deliverable is a formally
pre-registered verdict that closes the E7.15/E7.17 trajectory lineage. **The expected outcome is a
recorded NULL** (§7). Recording it is the point.

---

## 1. ⭐ The fold count is MAXED OUT, and that is a measured fact, not an assumption

MH2's headline lever — *"widen the window, buy folds, raise achievable DSR"* — was worth testing here
first, because on the MLB game model (MH2.1) the 3-fold ceiling turned out to be a **window choice**
rather than a data limit. **Here it is a data limit.** Measured on the live lakehouse before any
scoring:

| quantity | value | source |
|---|---:|---|
| MLB label mart `mart_batter_rolling_stats` season range | **2015 – 2026** | live lakehouse read |
| raw MLB pitch substrate `stg_batter_pitches` season range | **2015 – 2026** | live lakehouse read |
| distinct MLB debut cohorts in the pairs table | **12** (2015…2026) | `mle_graduated_pairs.parquet` |
| folds (a cohort is evaluable iff an earlier cohort exists) | **11** (2016…2026) | `run_h3` fold rule |

`debut_cohort` is `min(game_year)` over the MLB label mart, so **the fold count is bounded by the MLB
substrate's 2015 floor on BOTH sides** (batter and pitcher). E7.15-H3 already ran all 11. There is no
wider cohort set available today.

⇒ **the fold-count re-test trigger is CALENDAR-BOUND: +1 fold per MLB season, one per year.** Per MH2
rule (b) that makes it a *future note*, not a live re-test — and it must not be reported as though a
window widening could be done now.

## 2. The family, declared — and why `T3_tenure` STAYS

**The mechanism: a player's PATH through the minors, which the aggregated final-level box line erases.**
Two identical Double-A lines mean different things if one player arrived improving, and different things
again if one took three seasons to get there.

| arm | what it reads | why it is IN the family |
|---|---|---|
| `T1_traj_ladder` | ladder-adjusted rate change from the player's previous level | the mechanism's primary form — the change, made comparable across levels by H1's ladder |
| `T2_traj_raw` | the RAW previous-level change | **matched foil for the ladder's contribution** (NF-D15 g′); it confounds "the player improved" with "the level got harder", so if it ties `T1` the ladder adds nothing here |
| `T3_tenure` | years-at-level + levels-logged | the **same erasure argument, on the time axis** — the box line records *what* he hit, never *how long he took*. H3's own arm table justifies it in exactly those words. |

🔒 **LOCK 1 — `T3_tenure` IS RETAINED, AND THE REASON IS THAT IT LOST.** It is the arm the post-hoc
2-arm reading dropped. Dropping an arm *because it lost* is not a field definition, it is a selection.
The only admissible ground for excluding it would be **mechanistic** — "tenure is not trajectory" —
and that argument fails on this substrate: `T1`/`T2` read the *rate* delta between consecutive levels
and `T3` reads the *time and level count* over the same traversal. Both are properties of the path;
neither is readable from the final-level line. They belong to one family.

⚠️ **A 2-arm "rate-change-only" family is a DIFFERENT, NARROWER HYPOTHESIS.** It is not forbidden — but
it must be declared **before** a run, and it must be reported as testing something narrower than "does
reading a player's trajectory help". This story registers the **3-arm** family. The 2-arm figure is
reported in the results only as the **retired post-hoc reading**, labelled as such (§6).

## 3. 🔒 LOCK 2 — the mechanism split, declared so the result cannot be mis-attributed

Two splits, both mandatory, both fixed before scoring:

1. **TRAJECTORY ≠ PLAYER-STRUCTURE.** H3's field mixed the trajectory arms with a *reweighting /
   random-intercept* family (`P1_dedup`, `P2_dedup_sqrt`, `P3_player_re`, `P4_re_dedup`). The pitcher
   side's single largest H3 lift — `k_pct` **+1.713%** — is `P4_re_dedup`, i.e. **player structure, not
   trajectory.** Carrying "H3's trajectory arms are a real effect" forward without splitting credits
   trajectory with another mechanism's result. **MH2.2 scores the trajectory family ONLY.** The
   player-structure family keeps H3's recorded verdict and is out of scope here.
2. **BATTER ≠ PITCHER.** These are reported as two separate verdicts and never pooled. The pre-run
   reading of H3's recorded lifts says they are not the same finding:

   | side | trajectory arms' recorded H3 behaviour |
   |---|---|
   | batter | POSITIVE on 3 of 4 metrics (`k_pct` +1.18%, `bb_pct` +1.40%, `iso` +1.42%), 9/11 folds |
   | pitcher | **NEGATIVE** on `k_pct` (−0.26%), `bb_pct` (−0.34%), `hr_rate` (−0.20%); positive only on `gb_pct` (+1.21%) |

   ⇒ **this is a BATTER lead, not a two-sided one**, and the report must say so.

## 4. 🔒 LOCK 3 — the honest bar, stated in advance: ~0.85, not ~1.00

Computed with `cv_power` from the recorded fold structure **before** re-scoring anything. `SR` is the
winner's per-fold skill Sharpe; `SR0 = √V·z(N)` is the 3-arm field's deflated benchmark; `bar SR` is
`dsr_required_sr` — the per-fold Sharpe an arm **must** post to reach DSR ≥ 0.95 in *this* field.

**Batter — the declared 3-arm family, 11 folds:**

| metric | best arm | SR | SR0 | **DSR** | bar SR | folds needed | verdict-shape expected |
|---|---|---:|---:|---:|---:|---:|---|
| `bb_pct` | `T2_traj_raw` | 1.006 | 0.657 | **0.849** | 1.385 | **35** | POWER_LIMITED |
| `iso` | `T1_traj_ladder` | 0.910 | 0.617 | **0.759** | 1.331 | **46** | POWER_LIMITED |
| `k_pct` | `T1_traj_ladder` | 0.424 | 0.155 | **0.748** | 0.742 | **42** | POWER_LIMITED |
| `woba` | `T2_traj_raw` | −0.157 | 0.004 | 0.285 | 0.563 | — (SR<0) | GENUINE_ABSENCE |

**Pitcher — the declared 3-arm family:**

| metric | best arm | SR | SR0 | **DSR** | folds needed | verdict-shape expected |
|---|---|---:|---:|---:|---:|---|
| `gb_pct` | `T1_traj_ladder` | 0.422 | 0.366 | **0.564** | 946 | POWER_LIMITED (barely reachable) |
| `k_pct` | `T1_traj_ladder` | −0.157 | 0.155 | 0.120 | — | GENUINE_ABSENCE |
| `bb_pct` | `T1_traj_ladder` | −0.082 | 0.231 | 0.137 | — | GENUINE_ABSENCE |
| `hr_rate` | `T2_traj_raw` | 0.018 | 0.442 | 0.089 | — | DSR_UNREACHABLE (SR < SR0) |
| `xwoba_against` | — | — | — | — | — | **INACTIVE** (§5) |

⭐ **STATED PLAINLY, BEFORE THE RUN: nothing clears.** The best figure in the whole family is batter
`bb_pct` at **0.849** against a 0.95 gate. The re-test trigger for it is **tens of extra folds ⇒ one
per MLB season.** That is not "on the doorstep"; it is a calendar-bound future note.

> 📌 **ADDENDUM, added after the run — a correction to this section's DERIVED columns, left visible
> rather than quietly applied.** The `bar SR` and `folds needed` columns above were computed with
> `dsr_required_sr` / `folds_to_clear_dsr` under **normal moments** (skew 0, kurtosis 3), while the DSR
> gate itself uses the winner's **empirical** moments. That is precisely the "same moments everywhere,
> or nowhere" trap `cv_power` warns about twice — hit here, in this document, and worth recording as an
> instance rather than editing away. **Nothing that this story concludes moves:** every DSR value above
> came from `deflated_sharpe` (already empirical) and reproduced exactly, all four batter and five
> pitcher verdicts stand, and **all nine pre-registered null states were confirmed**. Only the derived
> bar and fold counts shift — e.g. batter `bb_pct` needs **27** folds rather than 35, `iso` **56** rather
> than 46, `k_pct` **62** rather than 42, pitcher `gb_pct` **1,039** rather than 946. The authoritative
> figures are the ones in `mh2_2_trajectory_family(_pitchers).md` §3, which thread the empirical
> moments. The direction of the finding is unchanged and, on three of four, worse.

**The fold-consistency clause.** MH2/H8's calibrated clause is used here (`n_folds=11`): it requires
**8 of 11** fold wins at α=0.20 (null false-fire 0.113) against the legacy `≥60%` bar's 7 wins (null
false-fire 0.274). It is **weakly stricter**, so it can only prevent a false ADD. On the recorded
data `T1`/`T2` post 9/11, so it re-decides nothing — stated in advance so that is a *check*, not a
discovery.

## 5. 🔒 LOCK 4 — `xwoba_against` is INACTIVE, declared up front

`xwoba_against`'s minor-league feature is a **Triple-A-only Statcast summary**, so a player has at most
one level carrying it and the trajectory delta has **zero within-player transitions to act on**. H3
recorded `T1_traj_ladder` and `T2_traj_raw` at **exactly 0.000% lift** on this metric — the signature of
an arm that is byte-identical to the foil.

It is therefore classified **INACTIVE** (`cv_power.NULL_STATES`): a statement about the POPULATION's
scope, not about the effect. **There is no defect to hunt and no fold count that fixes it**, and the
remedy is a different population. It is excluded from the pitcher-side BH-FDR family for the same
reason — a metric no arm can move is not a hypothesis that was tested.

## 6. 🔒 LOCK 5 — anchors, and the one that is deliberately NOT carried

| anchor | kind | must hold | why it is here |
|---|---|---|---|
| `A_traj_shuffled` | refute (defends `T1_traj_ladder`) | must **LOSE** | the ordering carries real information, rather than "any dispersed extra regressor helps" |
| `A_weight_identity` | noop | **byte no-op**, max abs MAE gap `< 1e-9` | the harness did not change anything it did not declare |
| `A_degenerate_mean` | block | must **LOSE** | MAE is not inverted on this cohort (NF-D11 degenerate ceiling) |

⛔ **`A_re_shuffled` IS DELIBERATELY EXCLUDED, ON MECHANISTIC GROUNDS — and this is the one exclusion
in the story.** It is a matched foil for the **player random intercept** (`P3_player_re`), permuting the
row→player assignment with the group-size multiset preserved. `P3_player_re` **is not in this field**
(lock 2 removed the player-structure family), so the anchor has **no defender**. Carrying an anchor
whose defender is absent would be an anchor that can neither pass nor fail meaningfully — the NF1.7 (a)
vacuous-anchor shape, and the NF-D16 (g‴) mis-scoping shape besides. It is dropped because its
*mechanism* left the field, never because of anything it scored.

🪤 **Per NF1.7 (a), an anchor that did not RUN or that MOVED NOTHING has not passed.** All three anchors
are asserted **present** and **active** (`pct_rows_moved > 1%` in the mechanism's own units) before any
verdict is read; `A_degenerate_mean` is exempt from the activity check because a degenerate *projector*
legitimately transforms no feature.

⚠️ **AND A DIAGNOSTIC ANCHOR IS NEVER A TRIAL (MH2.1 (a)).** The DSR trial field is the **3 selectable
trajectory arms only**. The foil and all three anchors are excluded from `n_trials` and from the
cross-trial dispersion `V` — an anchor that is far from the winner by construction would otherwise
inflate `V` and set the gate's own bar. This is asserted mechanically, not assumed.

## 7. The expected outcome, written down before the run

**A recorded NULL.** Specifically: no metric on either side clears the composite gate; batter
`bb_pct`/`iso`/`k_pct` classify **POWER_LIMITED** with a calendar-bound trigger; batter `woba` and
pitcher `k_pct`/`bb_pct` classify **GENUINE_ABSENCE** (a negative point estimate that no `n` rescues);
pitcher `hr_rate` classifies **DSR_UNREACHABLE**; pitcher `xwoba_against` is **INACTIVE**.

Stating this in advance is what makes the run a confirmation rather than a rationalisation — and it is
also the honest answer to "why run it at all": **to convert a post-hoc 0.998 into a pre-registered
0.849, so the lineage cannot keep citing the former.**

⚠️ **A WIN WOULD BE THE MORE INTERESTING RESULT** and would overturn §4. The bar for it is stated above
in per-fold Sharpe, not in p-decimals, precisely so it can be checked rather than argued.

## 8. ⭐ The substrate measurement — where a reachable lever actually lives

MH2 rule (b) requires the trigger be stated **and** classified as reachable-now or not. The fold *count*
is calendar-bound (§1). The fold **resolution** is not.

`build_graduated_pairs` was built with a **`--season-floor 2015`** on the MiLB side — a build-time
choice, not a data limit: **the MiLB lakehouse holds `season=2005` … `season=2026`.** That floor
left-truncates the minor-league history of exactly the players in the earliest folds, and the
trajectory mechanism — which needs a *previous level* to act on — is the mechanism most exposed to it:

| debut cohort (fold) | batter rows/player | **% rows with a trajectory** | pitcher % |
|---|---:|---:|---:|
| 2015 *(train-only)* | 1.17 | **14.4** | 24.3 |
| 2016 | 1.98 | **49.6** | 54.5 |
| 2017 | 2.89 | **65.4** | 64.5 |
| 2018 | 3.30 | 69.7 | 71.0 |
| 2019 → 2026 | 3.6 – 3.8 | **72 – 74** (steady state) | 68 – 73 |

Measured on the live lakehouse: for the **118 players** of the 2016+2017 debut cohorts, the MiLB tables
hold **23,719 regular-season pre-2015 games across 96 of them** (10,058 in 2014 alone) that the 2015
floor discards.

⇒ **2 of the 11 folds test the mechanism at materially reduced resolution, and the deficit is an
artifact of a build flag rather than a property of the mechanism.** This is the mirror of MH2.1 (c)
("part of a window-widening's added power is COSMETIC") — here, part of the *existing* fold set is.

**This is the one lever that is REACHABLE TODAY**, and it is the remedy `classify_null` names for a
dispersion-limited null ("a lower-variance design — more rows per fold"), not the calendar-bound one.

🔒 **BUT IT IS OUT OF SCOPE FOR MH2.2, AND MUST NOT BE OVERSOLD.** Rebuilding the pairs table on a wider
MiLB floor changes the **substrate**, which (a) breaks comparability with every E7.15/E7.12 result and
with the shipped E7.12-S1 foil configurations that were *selected* on the 2015-floored substrate, and
(b) is a heavy operator rebuild. It is therefore recorded as a **named successor**, with its
measurement, not attempted here. **Nothing in this story claims the wider substrate would clear the
gate** — the shortfall is large (`bb_pct` needs SR 1.385 against 1.006) and whether more resolution
closes it is unknown and unmeasured.

## 9. Leakage posture — unchanged from H3, restated because it still binds

* Folds are MLB debut cohorts and `debut_cohort` is a per-PLAYER join, so all of a player's rows share
  one fold and no player straddles the train/test boundary. **This was never a leakage question.**
* The trajectory delta uses H1's ladder fitted per fold with `exclude_players` = the held-out cohort's
  players, so no map applied to a player was fitted using that player's own later-level line.
* Every arm is asserted to score the **identical labelled population** each fold; an arm that changed
  the population would not be an ablation and raises rather than scores.
* **Reproduction anchor (new here):** MH2.2 re-fits the shared arms and asserts its per-fold MAE
  **reproduces E7.15-H3's recorded matrix**. A re-scored field is only a legitimate re-reading of the
  same evidence if the evidence is byte-identical; if it is not, the deflation comparison is between
  two different runs and the whole argument collapses.
