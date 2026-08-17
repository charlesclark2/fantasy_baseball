# NCAAF-P2.1 S1b — PRE-REGISTRATION: is the composite's margin over the block EARNED?

**Status: PRE-REGISTERED. Written and committed BEFORE any S1b arm was scored.**
_A FRESH §0.5 registration. The field, the primary contrast, the two return series, which one binds,
the anchors, the gates and the verdict rule are fixed HERE, in advance. Anything changed after the
first S1b score is laundering and is forbidden (E2.1-r). Amendments, if any, are dated entries at the
bottom, never edits to the body._

⚠️ **Not to be confused with `ncaaf_p2_1_s1b_registration.md`**, which is S1-serve's *representation
decision* record (what serves, and why, on mechanistic grounds). That document is DECIDED and this
run does not write to it. This document is the *evidential* registration its §6 asked for.

---

## 0. Why this story exists, and what is honestly at stake

S1 shipped `pace` and S1-serve wired the **2-column composite** `pace_axis` = {`pace_sum`,
`pace_diff`} into the served contract `strength_pace`, on the mechanistic argument that the 8-column
block spans a lower-dimensional space than 8 (the `seconds_per_play` ratio identity) so the six
per-side levels add ridge penalty without adding span. `ncaaf_game_mean_v2.json` is already fitted
with `pace_columns = ["pace_sum","pace_diff"]`.

S1-serve's own record (`ncaaf_p2_1_s1b_registration.md` §6) states the debt plainly:

> "If a later story wants to *claim* the +0.018, it needs its own fresh registration and run — this
> record explicitly does not license quoting it as an independently-earned lift."

**S1b is that run, and nothing more.** It is therefore a study of a *claim*, not of a wiring change.

### 0.1 Three disclosures that bound what S1b can possibly earn

These are stated up front because each one limits the verdict, and burying them would inflate it.

1. ⭐ **There is NO held-out season, and there cannot be one this cycle.** S1's folds are eval-years
   **2018…2025 — every completed FBS season in the cache**. The 2026 season opens 2026-08-29 and is
   unplayed. So S1b **cannot** produce a fold S1 did not see. The measurement substrate is shared
   with S1 in full.
2. ⭐ **The harness is deterministic, so S1b's CRPS numbers will be byte-identical to S1's.** Same
   cache, same folds, same learner/α/form, same seed 42, same 4,000 draws. Re-running the battery is
   a **REPRODUCTION check**, not a new measurement. S1b's freshness is entirely in the *gate design*
   (below), and the record must never imply otherwise.
3. ⭐ **The point estimate was seen during scoping, before this document was written.** While
   confirming the story was worth running, the author read the recorded S1 scores and computed the
   matched-pair deltas: **+0.0175 pooled, 6/8 folds, per-fold Sharpe 0.719, one-sided paired
   p = 0.041**. Nothing about `V`, PBO, DSR or the anchors was computed. The design below is fixed by
   S1-serve §2's mechanistic argument and by this story's brief — both of which pre-date the scoping
   read — **not** chosen to clear a bar. Disclosed rather than hidden, exactly as S1 disclosed that
   its per-fold Sharpe was already public from P2.1.

### 0.2 So what does S1b legitimately add?

One thing, and it is real: **S1 never gated this statistic.** S1 measured every arm against the
25-column `reference`, and recorded the block-vs-composite delta as an *attribution read* — its own
harness labels it "declared; reported, **never gated**". The composite-vs-block contrast has never
had a fold-consistency clause, a BH-FDR correction, a PBO, a DSR, or an anchor set applied to it.

S1b registers that contrast as the **primary**, with the block as the **matched foil** (NF-D10: a
matched pair is what separates a null from a tie and what makes a win *attributable*), and gates it.

---

## 1. Verified against the MODEL CODE, not this story's brief

P2.1's own lesson was that 6 of its spec premises were wrong on contact, so every premise is checked
against the running system first. **Two of this story's brief premises were wrong and are corrected
here** rather than silently absorbed.

| # | claim | verified | consequence |
|---|---|---|---|
| **S1b-V1** | "wire the composite in / refit the mean table" | ❌ **ALREADY DONE.** `bakeoff_ncaaf_game.SERVED_PACE_COLS == ("pace_sum","pace_diff")`; `ncaaf_game_mean_v2.json` carries `contract: strength_pace`, 27 columns, `pace_columns: ["pace_sum","pace_diff"]`, `fit_at 2026-08-17`. | S1b ships **no wiring change**. Its deliverable is a verdict on a claim. |
| **S1b-V2** | "the coefficient table is gitignored" | ❌ **FALSE — it is TRACKED** (`git check-ignore` → not ignored), and is reviewable in the PR diff. | the closeout lists it as a tracked artifact, not an excluded one. |
| **S1b-V3** | a held-out season exists | ❌ **No.** fold eval-years = 2018…2025 = all played seasons. | §0.1(1); no independent replication is available this cycle. |
| **S1b-V4** | the ratio identity that motivates the composite | ✅ inherited from S1-V4, re-verified on the re-assembled cache by the harness's reproduction check. `pace_sum`/`pace_diff` are exact linear combinations of the two `seconds_per_play` levels. | the family below is the representation set, mechanistically closed. |
| **S1b-V5** | where the CONTRAST can act (NF-D20: count the folds/rows the mechanism can move) | The block and the composite differ **only** in the six per-side levels. On rows where pace is NULL (week-1: 100 % NULL, 5.5 % of games) BOTH arms impute to the train mean ⇒ identical μ ⇒ the contrast contributes **exactly 0**. The harness measures and reports the active-row share. | a pooled delta is diluted by inactive rows; reported, never used to rescale the metric. |
| **S1b-V6** | the calibration constraint's status on the primary | ⚠️ `pace_axis` is margin-PIT-flat in **4/8** folds against a threshold of `max(1, int(0.5·8)) = 4` — it passes **exactly at the boundary**, and is one fold WORSE than the block (5/8). | ⛔ the constraint is inherited **verbatim** and is NOT tightened (NF1.8: a floor is never a target and never tightened above nominal). The boundary status is reported prominently as a caveat. |

---

## 2. The declared field — coherent, mechanistically closed, declared here

MH2 (a): *you get to PRE-REGISTER a family; you do NOT get to DISCOVER one.* MH2.2: *a post-hoc trim
re-commits the selection bias DSR exists to deflate.*

The family is the **pace representation set**, re-parameterised around the block as the foil. It is
the same closed set S1 declared — nothing is dropped, and nothing is added:

| id | arm | block added to the 25-col reference | role |
|---|---|---|---|
| **FOIL** | `pace` | the P2.1 H9 block VERBATIM (8 cols) | ⭐ the **matched incumbent foil** — every contrast is measured against it. The S1-PROMOTED arm. |
| **S1b-A** | `pace_axis` | `pace_sum` + `pace_diff` (2 cols) | ⭐ **PRIMARY — the only arm whose margin can be claimed.** The arm that already serves. |
| **S1b-B** | `pace_total_axis` | `pace_sum` only (1 col) | sibling representation: is there any margin-axis content at all? |

**Declared field size = 2 real arms** (`declared_field_size=2` is passed to `cv_power.classify_null`,
which then REFUSES to prescribe a field below it — MH2.7 — and the report reads the machine flag
`field_remedy_admissible`, never the prose).

⚠️ **Why a 2-arm field is DECLARED and not DISCOVERED, stated before the run.** A small field lowers
`SR0`, so "I shrank the field until DSR cleared" is the obvious suspicion and it deserves a direct
answer. The pace representation set has exactly three members because the block has exactly three
mechanistically distinct parameterisations (all 8 columns / the two composites / the total axis
alone). S1b makes one of them the foil, which leaves two. **No arm was removed because it lost** —
`pace_total_axis` is retained even though it is expected to tie, precisely so the field is not
trimmed. The lineage-inclusive `n_trials` is reported beside the binding one so a reader can see
whether the verdict depends on the narrow count.

**`n_trials` (DSR multiplicity) — three figures, one binding (NF-D14 two-figure convention):**

| figure | N | `V` over | status |
|---|---|---|---|
| **S1b declared field, degenerate-excluded** | foil + 2 real + 4 anchors = **7** | the 2 real arms | ⭐ **BINDING** |
| S1b whole field | 7 | 2 real arms + 4 anchors | reported (expected arithmetically inflated by the oracle) |
| lineage-inclusive | 7 + 8 (S1) + 22 (P2.1) = **37** | the 2 real arms | reported — S1b's primary is a member of S1's field, which is a member of P2.1's. The fresh registration's own field binds (the successor precedent), but the reader sees whether that choice carries the verdict. |

**Anchors — the four generic anchors, inherited verbatim, scored every run:** `oracle_peek` (ORACLE
FLOOR — nothing may beat it; a breach ⇒ the metric is inverted), `permute` (must LOSE), `zero_width`
(must LOSE **and** FAIL the coverage floor), `max_width` (must **SATISFY** the coverage floor **and**
LOSE — NF1.8's proof that the floor is a constraint, not a criterion a degenerate wins). An anchor
that fails to fit RAISES rather than returning `None` (NF1.7 (a): a check that did not run is never a
pass).

⭐ **Plus ONE anchor specific to this contrast, declared here:** `reference` (the 25-col, **no-pace**
contract) is the **degenerate representation** for the S1b contrast and **must LOSE to the foil**. It
orients the matched pair two-sidedly: if a contract carrying *no pace at all* were to beat the block,
the contrast's sign convention is inverted and the run is not interpretable.

---

## 3. THE TWO RETURN SERIES — declared separately, and which one binds

S1's post-verdict 2×2 established that **field COHERENCE moves `V`, and the series choice is
secondary** — so both are declared, and neither is re-read after the fact.

The primary contrast is the **matched pair**, not the vs-reference delta:

> `delta_fold = crps(pace) − crps(pace_axis)` on each fold  (> 0 ⇔ the composite is better)

| statistic | return series | why THIS series | binds? |
|---|---|---|---|
| **PBO** (`pbo_cscv`) | **per-BUCKET**: each fold's eval games in 4 contiguous quarters → 8 × 4 = **32 buckets**, matched-pair | CSCV needs many buckets to form its in/out-of-sample combinations; 8 is degenerate for it. Computed over the eligible real arms + the foil. | ✅ gate < 0.2 |
| **DSR** (`deflated_sharpe`) | **per-FOLD**: the 8 matched-pair deltas above | the fold is the independent unit of a season-forward, date-purged design; four quarters of one fold share a trained model, a season and a regime, so they add within-fold noise without adding information. `n_obs = 8` enters through `√(n_obs − 1)`. | ✅ **BINDING — gate ≥ 0.95, degenerate-excluded** |
| DSR on the per-BUCKET series | the 32-bucket matched-pair series | **REPORTED, NOT GATED** — shown beside the binding figure so the series choice is auditable. | ❌ reported only |

⛔ **Refusal, stated forward:** if the per-fold DSR fails, S1b will NOT then try half-folds, pooled
season pairs, a trimmed-mean series, a widened tie band, or any third series. One series per
statistic; that is the whole design.

---

## 4. Gates — fixed in advance

**Run-validity (a failure ⇒ `NOT_INTERPRETABLE`; no verdict is stated):**
* **A** — the six generic anchor checks, plus the S1b-specific check that `reference` LOSES to the foil.
* **R** — **REPRODUCTION**: the per-fold CRPS of `reference`, `pace`, `pace_axis` and
  `pace_total_axis` must match S1's recorded `ncaaf_p2_1_s1_pace_scores.json` to within **1e-4**.
  A mismatch means the harness drifted and this is not S1b. This check is what converts §0.1(2) from
  an admission into a *verified* statement.

**Arm-level gates on the PRIMARY (`pace_axis` vs the `pace` foil) — constants inherited, never edited:**
1. **eligible** — the calibration CONSTRAINT verbatim: `calib_80 ≥ 0.78` on margin AND total, AND
   margin PIT flat in ≥ half the folds. ⛔ never tightened (S1b-V6 notes the primary sits exactly at
   the boundary; that is reported, not remedied by moving the bar).
2. **not a nested-form tie** — |Δ| ≥ 1e-3. ⭐ **Load-bearing here in a way it was not in S1:** the
   composite is a strict SUBSET of the block's columns, so under a ridge that drove the six level
   coefficients to ~0 the two arms would collapse onto each other. A near-zero margin is a TIE, and a
   tie is refused as a win (the MLB Batter Props Ph2 nested-form rule).
3. **Δ > 0** — the composite must actually beat the block.
4. **BH-FDR** at α = 0.05 over the 2 registered real arms (one-sided paired t on the 8 per-fold deltas).
5. **fold-consistency** — `cv_power.fold_consistency_clause(8)` (calibrated; false-fire ≤ 0.20).

**Run-level:**
6. **PBO < 0.2** on the per-bucket matched-pair series.
7. **DSR ≥ 0.95** on the per-FOLD matched-pair series, `n_trials = 7`, `V` over the 2 real arms.

**PIT is a GATE, never a rank** (clause 1). Total-PIT flatness is measured and reported but decides
nothing — the shipped reference itself fails it, and gating on a clause the incumbent fails is the
MH2.1(b) inversion. Total shape is NCAAF-P2.5's scope.

---

## 5. Verdict rule — and, stated forward, what each verdict does to the SERVED artifact

This matters more than usual, because **the composite already serves**. A verdict that quietly meant
"whatever happens, keep serving it" would be unfalsifiable, so the revert trigger is fixed here.

| verdict | condition | effect on `ncaaf_game_mean_v2.json` / `SERVED_PACE_COLS` |
|---|---|---|
| **`MARGIN_EARNED`** | A ∧ R ∧ (1–5 on the primary) ∧ 6 ∧ 7 | **No change** (it already serves) — but the +0.018 becomes independently quotable, and `s1b_registration.md` §6's debt is discharged. |
| **`MARGIN_NOT_EARNED`** | A ∧ R hold; the sign holds (Δ > 0) but a gate fails | **No change.** The served representation continues to stand on S1-serve §2's *mechanistic* argument, which is independent of this margin. The record states the margin is **NOT** independently claimable — i.e. exactly the status quo of `s1b_registration.md` §6, now measured rather than asserted. The failing gate is classified by the instrument. |
| ⭐ **`REVERT_TO_BLOCK`** | A ∧ R hold **and** the matched-pair sign FLIPS (Δ < −1e-3, the block beats the composite) | **Revert** `SERVED_PACE_COLS` to the 8-column block (the arm S1 actually PROMOTED) and refit the mean table. Recorded here so the study can genuinely fail against the served state. |
| **`NOT_INTERPRETABLE`** | A or R fails | no verdict; find out why. |

⛔ **A `MARGIN_NOT_EARNED` is not a licence to re-run.** Per the instrument: `DSR_UNREACHABLE` ⇒ **no
re-test trigger** (n enters only through `√(n−1)`, so it scales a positive gap and cannot create one;
"more seasons" would be actively misleading — NF-D18/MH2). `POWER_LIMITED` ⇒ the shortfall is stated
in the unit that grows (folds/seasons), and — because §0.1(1) proves the fold count is **calendar-
bound**, not a window choice — that trigger is a future note, not a live re-test. A calibration
refusal ⇒ `CONSTRAINT_REFUSED`, no trigger.

**Reported beside the verdict, always:** the per-fold and per-bucket Sharpe for both real arms; the
binding and reported DSRs; the three-N table; `V` clean vs whole-field; the active-row share for the
contrast (S1b-V5); the margin-PIT boundary status (S1b-V6); and `best_alpha = 0`.

---

## 6. What is NOT re-litigated

`best_alpha = 0`. S1b changes no bet, no edge claim and no framing. Whatever it finds concerns which
of two already-certified column sets carries a calibration term in a market-blind mean model. The
vs-close leg is unchanged and both sides sit under the −110 breakeven.

## 7. Data + cost hygiene

The identical P2.1 cache (`betting_ml/data/cache/ncaaf_p2_1_battery.parquet`, re-assembled by
`--assemble` in 24 s, Snowflake-free, DuckDB over S3): 8,325 completed games 2015–2025, 4,187 CLV
closes. ONE parquet, read by every arm × fold. Battery cost ≈ 1 min on the laptop (7 configs × 8
folds), so this is a smoke-scale run, not an operator handoff.

---

_Pre-registered 2026-08-17, before the first S1b arm was scored. Amendments (if any) appear below
this line, dated, never as edits to the body._
