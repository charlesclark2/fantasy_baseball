# NCAAF-P2.1 S1b — read-out: the composite's margin is **NOT** independently earned

_Decided 2026-08-17 · `MARGIN_NOT_EARNED` · `best_alpha = 0` · no change to the served artifact_

**Pre-registration:** [`ncaaf_p2_1_s1b_preregistration.md`](./ncaaf_p2_1_s1b_preregistration.md)
(committed before the first score) · **Dossier:**
[`ncaaf_p2_1_s1b_composite.md`](./ncaaf_p2_1_s1b_composite.md) · **Harness:**
`models/p2_1_s1b_composite.py`

---

## 1. What this story actually was, after the card met the running system

Two of the brief's premises were **already true** and one was **false**; all three are corrected in
the pre-registration §1 rather than absorbed silently (P2.1's own "verify against the model code"
lesson).

| brief said | reality |
|---|---|
| "wire the composite in / refit the mean coefficient table" | **already done** by S1-serve (PR #895). `SERVED_PACE_COLS == ("pace_sum","pace_diff")`; `ncaaf_game_mean_v2.json` carries `contract: strength_pace`, 27 columns, `pace_columns: ["pace_sum","pace_diff"]`. |
| "the coefficient table is gitignored" | **false — it is tracked** and reviewable in the diff. |
| "score the composite vs the reproduced 8-col incumbent" | ✅ this was the real, un-done work. |

So S1b shipped **no wiring change**. It is a study of a **claim** — the one
[`ncaaf_p2_1_s1b_registration.md`](./ncaaf_p2_1_s1b_registration.md) §6 explicitly left open:

> "If a later story wants to *claim* the +0.018, it needs its own fresh registration and run."

**Answer: the claim does not clear.** The representation continues to serve on its mechanistic
argument; the margin is not independently quotable.

## 2. What S1b could and could not establish — stated before the result

* ⚠️ **No held-out season exists.** S1's folds are eval-years **2018…2025 — every completed FBS
  season**; 2026 is unplayed. S1b shares S1's substrate in full and cannot replicate on unseen data.
* ⚠️ **The harness is deterministic**, so S1b's CRPS is byte-identical to S1's — gate R verified
  this at **max |Δ| = 0.0**. Re-running the battery is a *reproduction*, not a new measurement.
* ✅ **What is genuinely new:** S1 measured every arm against the 25-column `reference` and recorded
  the block-vs-composite delta as an attribution read its own harness labels *"declared; reported,
  **never gated**"*. S1b registers that delta as the **primary contrast** and gates it. A
  fold-consistency clause, BH-FDR, PBO, DSR and an anchor set had never been applied to this
  statistic.

## 3. The result

Matched pair, `crps(pace 8-col block) − crps(arm)` per fold; > 0 ⇔ the arm beats the block.

| arm | Δ vs block | fold wins | p (1-sided) | BH | eligible | margin-PIT | SR/fold | state |
|---|---|---|---|---|---|---|---|---|
| `pace_axis` ⭐ (serves) | **+0.0184** | 6/8 | 0.0407 | ❌ | ✅ | 4/8 (need ≥4) | 0.719 | `POWER_LIMITED` |
| `pace_total_axis` | +0.0170 | 5/8 | 0.0578 | ❌ | ✅ | 5/8 | 0.635 | `POWER_LIMITED` |
| `pace` (FOIL) | — | — | — | — | ✅ | 5/8 | — | matched incumbent |

| gate | value | bar | |
|---|---|---|---|
| anchors (7 checks, incl. the no-pace degenerate) | all hold | — | ✅ |
| **R** — reproduction of S1 | max abs dev **0.0** | < 1e-4 | ✅ |
| eligible · not a tie · Δ>0 · fold clause (6 of 8) | all hold | — | ✅ |
| **BH-FDR** | p 0.0407 vs required **0.025** | α = 0.05 | ❌ |
| **PBO** | **0.331** | < 0.2 | ❌ |
| DSR (per-fold, declared field, degenerate-excluded) | **0.9687** | ≥ 0.95 | ✅ |

**Two gates fail, and they fail for different reasons.** The sign holds everywhere, so the
pre-registered `REVERT_TO_BLOCK` trigger did **not** fire.

### 3.1 Reading the PBO failure — a TIE, not an unstable pick

NF1.8 requires three things reported beside PBO, because a rank statistic alone cannot separate
*"my pick is unstable"* from *"the candidates are tied"* — and here those readings imply opposite
things for a representation that already serves.

* **Contender spread — 0.0184 CRPS = 0.099 % of the foil.** The three representations are separated
  by a tenth of a percent (`pace_axis` 18.4387 · `pace_total_axis` 18.4401 · `pace` 18.4570).
* **Per-fold flip distribution — `pace_axis` 4, `pace_total_axis` 2, `pace` 2** of 8.
* **Median OOS rank of the in-sample best — 3 of 3** (in this instrument higher = better, `ω =
  rank/(N+1)`): the in-sample winner typically lands **first** out-of-sample, the opposite of a
  fragile selection.

⭐ And PBO is a **coarse** statistic on a 3-config field: ω can only be 0.25 / 0.50 / 0.75, and a
*middle* finish already counts as an overfit event. Among three arms separated by 0.099 %, finishing
second is close to a coin flip, so PBO > 0.2 here is near-structural.

⇒ This is E2.1-r's **tie reading**: *"no representation robustly beats the others, so which one wins
is noise."* That is a null about the *ordering*, not a warning that the served composite is risky.

### 3.2 Reading the BH-FDR failure — the shortfall, in the unit that binds

`pace_axis` ranked 1st of 2 registered arms, so its BH step is `α·1/2 = 0.025`; it observed
**p = 0.0407**, a gap of **+0.0157**. ⛔ The shortfall is **not** a fold count, and a larger field
would make it *worse* (a bigger `m` raises the bar for rank 1). What would close it is a larger or
less noisy effect — which no additional season can be assumed to deliver, because the effect size is
what it is.

### 3.3 Where the contrast can act

The block and the composite differ **only** in the six per-side level columns; on NULL-pace rows
both impute to the train mean and contribute **exactly 0** to the delta. Active on **91.4 %** of eval
rows (5,507/6,024) — so the pooled delta is diluted by ~9 % of rows (NF-D20; reported, never used to
rescale the metric).

### 3.4 A caveat on the served representation, recorded plainly

`pace_axis` is margin-PIT flat in **4/8** folds against a threshold of ≥4 — it passes **exactly at
the boundary**, and is **one fold worse than the block** (5/8). ⛔ The constraint is inherited
verbatim and was **not** tightened (NF1.8: a floor is never a target; tightening it after seeing a
result is the E2.1-r inversion). This is a real, if small, mark against the composite that the CRPS
ordering does not show.

## 4. Two defects found while building — both the "same gate, two ways" class (MH2)

Neither was in the data; both were in how a gate was computed, and both would have put a **false
statement in the record**.

1. ⭐ **`classify_null` defaulted to Gaussian higher moments while the binding `deflated_sharpe`
   estimates them from the series.** The fold-delta series is platykurtic (skew +0.51, kurt 1.99),
   and the two disagree by **three folds**: the DSR gate needs 7 folds under the measured moments
   (8 available ⇒ passes) but 10 under Gaussian ones. Left alone, the record would have published a
   **"+1 more season"** re-test trigger for a gate that had **already passed** — precisely the
   actively-misleading trigger MH2/NF-D18 forbid. The measured moments are now passed explicitly.
   *(Disclosed the other way too: the DSR pass rests partly on 8-point moment estimates, which are
   themselves noisy and here favourable.)*
2. ⭐ **With BH rejecting every arm, the cutoff degenerates to 0.0 and the instrument rendered
   `"+-8 folds (⇒ 0 total) for certifiability"`.** A negative fold requirement is a **mis-render of
   a state**, not a re-test instruction — the MH2.7 `n_arms=1`-renders-as-a-fold-shortage family on
   a second code path. Corrected locally; the raw string is preserved verbatim in the JSON
   (`retest_trigger_raw_from_instrument`) so the defect stays auditable.

⏭️ **Carded, not done here:** the fix belongs in `cv_power` itself — this is now the *N*-th
downstream hand-correction of that renderer, and MH2.7's own lesson is that a defect corrected N
times downstream is a defect in the **instrument**. It was not changed here because `cv_power` is a
**shared** instrument pinned by cross-vertical guards (MLB / fantasy / prospect), and MH2.7 records
that changing it requires grepping those guards — out of scope for a §0.5 read-out.

## 5. Classifying the null, and what it does NOT license

Both arms classify **`POWER_LIMITED`** — the effect is positive, every gate is reachable, and the
design cannot resolve it.

⛔ **The re-test trigger is a future note, not a live re-test.** The fold count is **calendar-bound**:
2018…2025 is every completed FBS season, so a ninth fold requires the 2026 season to be *played*
(opener 2026-08-29). No window widening and no field change can add one now.

⛔ **"A smaller field" is not a remedy.** `field_remedy_admissible` is not asserted, the declared
field is already the mechanistically closed set of 2, and trimming it post-hoc would re-commit the
exact selection bias DSR exists to deflate (MH2.2). `pace_total_axis` was retained precisely so the
field could not be accused of a trim.

⛔ **This is not a `GENUINE_ABSENCE`.** The composite does beat the block on average, in 6 of 8
folds, with the sign holding. What failed is the *certification*, not the direction.

## 6. What this means for the served artifact — nothing changes, and why that is not a dodge

The pre-registration fixed the effect of every verdict **before** the run, including a
`REVERT_TO_BLOCK` trigger on a sign flip, so the study could genuinely fail against the served state.
It did not fire.

`MARGIN_NOT_EARNED` ⇒ **no change**. The composite continues to serve on S1-serve §2's *mechanistic*
argument — the `seconds_per_play` ratio identity means the 8-column block spans a lower-dimensional
space than 8, so the six per-side levels add ridge penalty without adding span. That argument is
independent of this margin and is untouched by the result. What changes is the **record**: the
+0.018 is now *measured* to be non-quotable rather than merely *undeclared*, and §6's debt is
discharged with a negative answer.

Both representations remain certified members of S1's field; the choice between them is, on this
evidence, a **tie broken on mechanism**.

## 7. If a successor wants to settle it

The honest options, in order of strength:

1. **Wait for played seasons.** The trigger is calendar-bound; 2026 adds one fold. ⛔ But note §3.2:
   the *binding* failure is BH-FDR, whose shortfall is an effect-size gap, not a fold count — so a
   ninth fold is necessary, not obviously sufficient. Do not promise otherwise.
2. **A lower-variance design** (more rows per fold, or a sharper metric than pooled CRPS) attacks the
   actual constraint — `classify_null` names this explicitly, and it does not require waiting.
3. ⛔ **Not** a re-cut of this field, a widened tie band, a third return series, or a re-read on the
   better-looking statistic. All four are forbidden by the pre-registration §3's stated refusal.

## 8. Honest framing

`best_alpha = 0`. S1b changes no bet, no edge claim and no framing. It concerns which of two
already-certified column sets carries a calibration term in a market-blind mean model. The edge bar
(model-side ATS/OU > 0.5238 breakeven **and** > placebo) is unchanged and unclaimed.

---

_Guards: `betting_ml/tests/test_ncaaf_p2_1_s1b_composite.py` (33 tests), every clause proved to go
RED on deliberately-broken source by `betting_ml/tests/ncaaf_p2_1_s1b_red_proof.py` (24/24 breaks
caught — one vacuous guard was found and fixed by that proof: a fixture that could only ever reach
the missing-arm branch of gate R, never the missing-file branch)._
