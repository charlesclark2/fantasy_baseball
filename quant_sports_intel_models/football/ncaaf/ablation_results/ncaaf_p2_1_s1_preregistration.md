# NCAAF-P2.1 S1 — PRE-REGISTRATION: `pace` under a lower-variance GATE design

**Status: PRE-REGISTERED. Written and committed BEFORE any S1 arm was scored.**
_This is a FRESH §0.5 registration (the successor P2.1 §9.6 earned), not a re-read of P2.1's folds.
Everything below — the field, the two return series, which one binds, the anchors, the gates and the
verdict rule — is fixed HERE, in advance. Anything changed after the first S1 score is laundering and
is forbidden (E2.1-r). Amendments, if any, are dated entries at the bottom, never edits to the body._

---

## 0. Why this story exists, stated honestly

NCAAF-P2.1 (`REFERENCE_STANDS`, 22 configs × 8 folds × 8,325 games) found ONE real structural
effect: **`pace`** — +0.0620 CRPS, positive in **8/8** folds, p = 0.0020 (BH cutoff 0.003125),
PBO 0.023, eligible, not a nested-form tie. It failed the pre-registered DSR gate (0.0409) and was
classified `DSR_UNREACHABLE` — and P2.1 §9.6 recorded WHY, as a **design** finding, not an
evidential one: P2.1 pre-registered ONE return series and used it for both PBO and DSR. CSCV/PBO
wants MANY buckets, so each fold was sliced into quarters (8 × 4 = 32 buckets); DSR wants LOW-NOISE
INDEPENDENT observations, and slicing a fold into quarters adds within-fold noise without adding
independent information. Same effect, same folds:

```
pace, per-FOLD improvement Sharpe    1.492   (8 obs)     ← recorded in P2.1 §9.6, public
pace, per-BUCKET improvement Sharpe  0.532   (32 obs)    ← the P2.1 gate series
```

⚠️ **Disclosure, because it bears on how much S1 can be said to "discover":** the per-fold Sharpe
above is already on the record from P2.1. P2.1 deliberately did NOT quote a per-fold DSR (that would
have been re-reading a pre-registered gate on the better-looking series). S1's contribution is
therefore not a surprise number; it is (a) a gate whose series is pre-registered FORWARD and binds,
(b) a COHERENTLY declared field whose cross-trial dispersion `V` is unknown until the run, (c) a
reproduction of the effect under a committed contract, and (d) the anchors + null classification
that turn "it looks better on the other series" into a verdict a reader can trust. Per the program
rule (MH2 (a); NF-W6b-C / MARGIN2→3 / W7→W7b precedents): **a DSR failure over a design like P2.1's
is a hypothesis about the RETURN SERIES / FIELD, not a verdict on the effect — the remedy is a fresh
registration with the series and family declared up front, never a re-read and never a post-hoc
trim (MH2.2).**

⛔ **What S1 does NOT do:** it does not re-open the pace FEATURE (no new columns), it does not touch
the folds, the learner, α, the form, the seed or the draw count, and it does not change the
calibration constraint. Change ONE thing — the gate's series design — and declare the field.

---

## 1. Verified against the MODEL CODE, not the P2.1 spec (P2.1's own lesson — 6 of its premises were wrong on contact)

| # | claim to verify | verified (code + assembled cache, 8,325 games) | consequence |
|---|---|---|---|
| **S1-V1** | pace enters ONLY through the registered block | ✅ The shipped reference contract is the 25 `home_strength*`/`away_strength*` cols + `strength_margin_diff` (`reference_columns`, prefix-resolved). **No pace column is in it.** P1.2's pre-registered `COVARIATES` (`team_strength.py`) are talent / returning production / roster continuity / portal / coaching / prior_strength — **no pace covariate**, so the strength ratings do not carry pace as a design term. | pace is a genuine ADD, and the paired read is valid. |
| **S1-V2** | pace is not already ABSORBED by the strength ratings | ✅ On the assembled frame ρ(`home_strength_offense`, `home_off_plays_per_game`) = **0.25**, ρ(`home_strength_offense`, `home_seconds_per_play`) = **−0.13**, ρ(`home_strength_margin`, `home_off_plays_per_game`) = 0.13. Weak — the P1.2 points model rates points-per-game (efficiency × possessions), so it carries a faint pace echo at the TEAM level; it does not carry the GAME-level combined tempo. | the ΔCRPS P2.1 measured is the increment over that echo; recorded, not assumed. |
| **S1-V3** | where the mechanism acts | The block's marginal association is on the **TOTAL axis**: ρ(`pace_sum`, `label_total_points`) = **−0.237** (slow + slow ⇒ fewer possessions ⇒ fewer points), ρ(`pace_diff`, `label_home_margin`) = 0.06. Consistent with the P2.1 H9 registration ("as a SUM on the total axis, where pace should act"). | the representation set below is built around the axis, and the attribution reads ask exactly this. |
| **S1-V4** | the columns are what they say | `home_seconds_per_play` = `possession_seconds_per_game / off_plays_per_game` in dbt (`feature_ncaaf_pregame_matrix.sql` L220/L312) — the ratio identity holds EXACTLY on the cache (max dev 0.0). Median 26.2 s/play, 69 plays/game — the right magnitude for FBS (P2.1's punt-yardage lesson: check the median against the known number). `pace_sum`/`pace_diff` are exact linear combinations of the two `seconds_per_play` levels. | the 8-column block spans a lower-dimensional space than 8; under ridge + standardization the composites change the penalty geometry, not the span. This is WHY the representation set is informative rather than redundant. |
| **S1-V5** | is pace TARGET-ENCODED anywhere (P2.1's per-team-HFA collapse was an in-fold target-encoding artifact) | ✅ **No.** The block is RAW: season-to-date, strictly-prior-week aggregates from `rollup_ncaaf_team_week_asof`, plus two row-level linear composites. No in-fold builder, no fit on any label. | out-of-fold encoding is N/A; nothing to nest. |
| **S1-V6** | where the block is INERT (NF-D20 active-rows) | Season-to-date ⇒ **week-1 rows are 100 % NULL** (461 games, 5.5 %; week 2: 35.7 % NULL; week ≥3: ~3 %). NULLs are TRAIN-mean imputed ⇒ the block contributes NOTHING on week-1 rows. | (a) the pooled effect is measured over ~94 % active rows; (b) a PRE-SEASON board (P1.5's product) is untouched by pace by construction — pace is an IN-SEASON effect. |
| **S1-V7** | fold / harness reuse | S1 calls the P2.1 harness's `build_folds` (`PurgedWalkForwardSplit(min_train_seasons=3)` → 8 season-forward date-purged folds 2018…2025), `score_arm_fold` (ridge α=10, `strength_posterior`, seed 42, 4,000 draws, inner-holdout dispersion) unchanged. The only harness edit is a `blocks=` injection point so S1's registry can be scored by the same function. | `pace`'s per-fold CRPS must REPRODUCE P2.1's recorded figures (§4 check R). |

---

## 2. The declared field — coherent, mechanistic, declared here (MH2 (a): "you get to PRE-REGISTER a family; you do NOT get to DISCOVER one")

The field is the pace FEATURE and its representation set. Every arm is `reference ∪ block`, all else
byte-identical (NF-D10 matched pairs). **All three are strict subsets of the P2.1 H9 columns — no
new column enters.**

| id | arm | block (added to the 25-col reference) | role |
|---|---|---|---|
| **S1-A** | `pace` | the P2.1 H9 block VERBATIM: `{home,away}_seconds_per_play`, `{home,away}_off_plays_per_game`, `{home,away}_possession_seconds_per_game`, `pace_sum`, `pace_diff` (8 cols) | ⭐ **PRIMARY — the only arm that can ship.** It is the arm P2.1 found; S1 re-registers IT. |
| **S1-B** | `pace_axis` | the two game-level composites only: `pace_sum` (total axis) + `pace_diff` (margin axis) (2 cols) | representation: "the game-level tempo composites carry the effect; the per-side levels add nothing" |
| **S1-C** | `pace_total_axis` | `pace_sum` only (1 col) | representation: "the effect is the possessions channel on the TOTAL axis, with no margin-axis content" |

**Declared field size = 3 real arms.** `n_trials` for DSR = reference + 3 real arms + 4 anchors =
**8**. `V` (cross-trial Sharpe dispersion) is measured over the **3 real arms only** (DSR-CONV +
MH2.1(a), declared forward exactly as in P2.1 §1.6; the degenerate-excluded figure binds).

⛔ **The ship candidate is FIXED as `pace` (S1-A).** S1-B and S1-C are members of the field (they
count in `n_trials`, in `V`, and in BH-FDR) and are ATTRIBUTION reads. If S1-A fails and a sibling
clears, that is reported as a successor hypothesis, never shipped from this run — "pick the best of
three" is the search this document exists to bound.

**Attribution reads (declared, tie band 1e-3, reported not gated):**
* `pace` vs `pace_axis` — do the six per-side LEVELS add beyond the two composites?
* `pace_axis` vs `pace_total_axis` — is there any MARGIN-axis content, or is it all possessions on
  the total?

**Anchors — the same four generic anchors as P2.1 §1.7, scored every run** (`hfa_global` is H1b's
foil and is not part of S1): `oracle_peek` (ORACLE FLOOR — nothing may beat it; a breach ⇒ the metric
is inverted), `permute` (must LOSE), `zero_width` (must LOSE **and** FAIL the coverage floor),
`max_width` (must **SATISFY** the coverage floor **and** LOSE). An anchor that fails to fit RAISES
(NF1.7 (a)).

---

## 3. THE TWO RETURN SERIES — declared separately, and which one binds

This is the one thing S1 changes, so it is stated with its rationale and its refusal.

| statistic | return series | why THIS series | binds? |
|---|---|---|---|
| **PBO** (`pbo_cscv`) | **per-BUCKET**: each fold's eval games split into 4 contiguous quarters (≥40 games each) → 8 × 4 = **32 buckets** — IDENTICAL to P2.1 | CSCV needs many buckets to form its S/2 in-sample / out-of-sample combinations; a bucket count of 8 is degenerate for it. Computed over the ELIGIBLE real-arm set + the reference (anchors excluded — not promotion candidates). | ✅ gate < 0.2 |
| **DSR** (`deflated_sharpe`) | **per-FOLD**: `reference − arm` pooled CRPS on each of the **8** season-forward folds | The fold IS the independent unit of this design (season-forward, date-purged); the four quarters of one fold share the same trained model, the same season and the same regime — they are not four independent observations of the improvement, and treating them as such adds pure within-fold noise to the series' sd while the mean stays put. DSR asks "is the TRUE Sharpe of this improvement above the expected max under N trials?" — the answer wants the lowest-noise independent series, and that is the fold. `n_obs = 8` enters through `√(n_obs − 1)`; the series' skew/kurtosis are estimated from 8 points and enter DSR's denominator as AFML §14 specifies. | ✅ **BINDING — gate ≥ 0.95, degenerate-excluded** |
| DSR on the per-BUCKET series | the 32-bucket series above | **REPORTED, NOT GATED** — it is P2.1's gate series, shown beside the per-fold figure so the series choice is AUDITABLE (the story AC: "report BOTH per-bucket and per-fold Sharpe"). | ❌ reported only |

⛔ **Refusal, stated forward:** if the per-fold DSR fails, S1 will NOT then try half-folds, seasons
pooled by pairs, a trimmed-mean series, or any third series. One series was declared for each
statistic; that is the whole design change.

**DSR `n_trials` — three figures, one binding (NF-D14 two-figure convention):**

| figure | N | V over | status |
|---|---|---|---|
| **S1 declared field, degenerate-excluded** | 8 | the 3 real arms | ⭐ **BINDING** |
| S1 whole field | 8 | 3 real arms + 4 anchors | reported (expected to be arithmetically inflated by the oracle, as P2.1 measured 279×) |
| lineage-inclusive | 8 + 22 = 30 (S1's field plus the P2.1 field in which `pace` was FOUND) | the 3 real arms | reported — disclosure that S1's primary is P2.1's survivor; per the successor precedent the fresh registration's own field binds, but a reader should see whether the verdict depends on that |

---

## 4. Gates — fixed in advance, verdict rule stated

**Run-validity checks (a failure ⇒ the run is NOT INTERPRETABLE; no verdict is stated):**
* **A** — all six anchor checks (as P2.1): oracle floor holds; permute / zero_width / max_width all
  lose CRPS to the reference; zero_width FAILS the coverage floor; max_width SATISFIES it.
* **R** — **REPRODUCTION**: `pace`'s per-fold CRPS (all 8 folds) and the reference's must match
  P2.1's recorded `ncaaf_p2_1_battery_scores.json` to within 1e-4 (byte-identical harness ⇒
  byte-identical scores). A mismatch means the design DRIFTED and this is not S1; stop and find out
  why. This check is what makes "the 8/8 sign structure holds" a REPRODUCTION statement rather than
  a coincidence.

**Arm-level gates on the PRIMARY (`pace`) — all pre-registered constants inherited from P2.1:**
1. **eligible** — the calibration CONSTRAINT: `calib_80 ≥ 0.78` on margin AND total (pooled over
   folds) AND margin PIT flat in ≥ half the folds. Never tightened; never a target (NF1.8).
2. **not a nested-form tie** — |ΔCRPS| ≥ 1e-3.
3. **ΔCRPS > 0** (reference − arm; CRPS lower-is-better).
4. **BH-FDR pass** at α = 0.05 over the 3 registered real arms (one-sided paired t on the 8 per-fold
   deltas).
5. **fold-consistency** — `cv_power.fold_consistency_clause(8)` (calibrated: 6 of 8 wins, false-fire
   ≤ 0.20). Reported beside it: the raw fold-win count, and whether P2.1's **8/8** reproduces
   (it must, by check R).

**Run-level gates:**
6. **PBO < 0.2** on the per-bucket series over the eligible real set + reference.
7. **DSR ≥ 0.95** on the per-FOLD improvement series of the PRIMARY, `n_trials = 8`, `V` over the
   3 real arms (degenerate-excluded — binding).

**Verdict rule:**
* **`SHIP`** iff A ∧ R ∧ (1–5 on `pace`) ∧ 6 ∧ 7.
* Otherwise **`REFERENCE_STANDS`**, and `pace` is classified with
  `cv_power.classify_null(n_arms=3, declared_field_size=3, degenerates_excluded_from_v=True,
  observed_sr=<per-FOLD Sharpe>, var_trials_sr=<V over the 3 real arms>, …)`; the report reads the
  MACHINE flag `field_remedy_admissible`, never the prose (MH2.7). `DSR_UNREACHABLE` ⇒ no re-test
  trigger; `POWER_LIMITED` ⇒ the shortfall stated in folds/seasons; a calibration-constraint refusal
  ⇒ `CONSTRAINT_REFUSED` (NF-D18), no trigger.
* The two siblings are ALWAYS classified too (they are field members) — reported, never promoted.

**Reported beside the verdict, always:** per-fold Sharpe AND per-bucket Sharpe for every real arm;
per-fold DSR (binding) AND per-bucket DSR (P2.1's series) for the primary; the three-N table of §3;
`V` clean vs whole-field; the two attribution reads; the vs-close leg (`best_alpha = 0` — a
calibration ship is product value, never an edge claim; the edge bar is unchanged from P2.1 §1.10 and
P2.1 measured `pace` at ATS 0.5045 / O/U 0.5126, both under the 0.5238 breakeven).

---

## 5. What a SHIP means operationally — recorded now so the closeout cannot inflate it

* The served P1.4 artifact (`ncaaf_game_distribution_v1.json`) carries DISPERSION parameters and a
  contract NAME; it carries **no mean model** — P1.5's season sim rebuilds μ analytically from the
  P1.2 strengths (`season_simulation.py`, "not an independent pace axis"). NCAAF is **not yet
  serving** a product surface (`production_model_state.md`: no store / API / frontend row).
* A `pace` ship therefore means: (i) the P1.4 reference contract becomes `strength_only ∪ pace` for
  any STANDALONE game distribution / in-season board; (ii) a re-finalize of the dispersion (σ₀, k)
  under that contract; (iii) the P1.5 mean map gains a pace term for the IN-SEASON (`--as-of-week`)
  board — the pre-season board is untouched by construction (S1-V6: week-1 pace is NULL ⇒ inert).
* `best_alpha = 0` is unaffected either way.

---

## 6. Data + cost hygiene

The identical P2.1 cache (`betting_ml/data/cache/ncaaf_p2_1_battery.parquet`; re-assembled by
`--assemble`, 29 s, Snowflake-free, DuckDB over S3): 8,325 completed games 2015–2025, 4,187 CLV
closes joined — the same counts P2.1 recorded. ONE parquet, read by every arm × fold.

Battery cost: 8 configs × 8 folds ≈ 1 min on the laptop (P2.1's 22 configs took ~2.5 min).

---

_Pre-registered 2026-08-15, before the first S1 arm was scored. Amendments (if any) appear below this
line, dated, never as edits to the body._
