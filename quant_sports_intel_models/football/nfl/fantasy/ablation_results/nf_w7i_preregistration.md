# NF-W7i — Pre-registration: the RB DIRECT-POINTS improvement ceiling (an oracle-first MEASUREMENT)

**Committed BEFORE the full 8-fold run** (the §0.5 discipline). Every constant named here lives in
`direct_points_ceiling.py` and the runner READS it (NF-D16). `best_alpha = 0` · **deploy-held** ·
research-only, no changelog entry, promotes nothing.

## 0. Framing — what this story is, and the three things it is NOT

NF-W7h settled RB's architecture question: **assembly-from-parts genuinely LOSES at RB.** The
direct-points foil beat the assembly winner by **0.0263 CRPS** even AFTER the marginal-layer
zero-mass recalibration — the QB→RB flip did not happen, and the cross-position sign split
survives marginal recalibration. RB's remaining value therefore lives in the **direct-points
form**, and NF-W6 exists precisely to SIZE that headroom before a bake-off is funded.

- ⛔ **NOT a bake-off.** No arm is selected, tuned, or promoted. The output is a CEILING and a band.
- ⛔ **NOT an RB-assembly successor.** No "more draws" arm is funded: assembly loses at RB, and
  NF-W7h measured its DSR as variance-bound and unreachable at any n (the only sub-field that moved
  it deleted the winning arm).
- ⛔ **NO season/fold re-test trigger is published for RB**, in any outcome. A ceiling below the
  band is a MEASUREMENT of the form's headroom, not a power shortfall; a "come back with more
  seasons" trigger would be the actively-misleading direction NF-D18 / MH2 (g″) forbid. The runner
  hard-codes `retest_trigger = None`.

Either outcome advances RB toward NF-W8-readiness **in the correct form**: a large ceiling licenses
a successor bake-off; a small one is a COMPLETE result at a fraction of a bake-off's cost, and
NF-W8 takes the direct-points RB as-is.

## 1. ⭐ The premise correction, measured before anything was designed

The story card motivates the work with NF-W7h's recorded `oracle__foil_direct_points` = **1.4933**
against the honest arm's 2.4692 — an apparent ~39.5% ceiling. **That figure is not a ceiling, and
this story must not inherit it.**

`run_nf_w7h_rb_marginal.py:360` builds it as `KW.fit_direct_points(te_p, te_p, ...)` — nine
200-estimator LGBM quantile learners **fit on the test block and predicted on the same rows**.
Every row sees its own label. The NF-W6 pre-registration names exactly this construction in
advance: *"A ROW-level peek is a zero-CRPS degenerate, not a ceiling."* Reproduced here on fold
`2025H2`: in-sample **1.4663** vs the honest arm **2.4347**.

This was **harmless in NF-W7h** — that record only ever asked the arm to beat it
(`FOILS_WITH_ORACLE`), and it gated nothing — but it cannot carry the ceiling claim that is this
story's entire object. ⇒ every peek here is **CROSS-FIT at K=3** (`EM.crossfit_ids`, which itself
REFUSES K<2 with "a 1-fold cross-fit is an in-sample fit and the oracle would memorize rows").

## 2. ⭐ The measurement problem, and the bracket that solves it

A **block-only** cross-fit peek — NF-W6's literal construction — is **capacity-starved on this
cell**. RB test blocks are 1,025–1,126 rows; cross-fit at K=3 leaves the peek ~700 rows to fit a
nine-knot 200-estimator quantile bank, against an honest arm trained on 13k–20k rows. Measured on
fold `2025H2`: the block-only peek scores **2.6180 — WORSE than the arm's 2.4347** (a NEGATIVE
ceiling), and it loses to its own matched-n control (2.5483).

That is exactly the failure NF-W7h's own §2 predicts ("a Σ peeked on a small block LOSES more to
sample size than the peek gains — which is how a per-form floor goes INACTIVE") and NF-W6d gives
the rule for reading it: **an oracle that ties or loses to its own matched-n control is INACTIVE —
uninformative, never a NO** (NF-D20: count whether the mechanism could ACT before crediting a pass
*or* a refusal). Reporting −7.53% as "RB has no headroom" would be that error.

So the ceiling is **bracketed** by peeks that differ in how much regime knowledge they carry at
FULL capacity, and the weight sweep is the bridge between the brackets.

## 3. The declared oracle forms (five; NF-D16 (g‴) — one ceiling per FORM, never one for the field)

Each form is a **(peek, matched-n control) PAIR**. `ORACLE_FORMS` in `direct_points_ceiling.py`.

| form | the peek | its matched-n control |
|---|---|---|
| `direct_blockonly` | the incumbent form re-fit WITHIN the block, cross-fit (NF-W6 literal) | the same form on the most recent train window sized `len(test)·(K−1)/K` |
| `direct_augmented` | train ∪ the block's own rows at weight `LAMBDA_AUGMENTED = 1`, cross-fit | the IDENTICAL construction with the peeked block replaced by an equally-sized, equally-weighted slice of the most recent TRAIN rows |
| `direct_upweighted` | the same at `LAMBDA_DIAG = 5` — the starvation BRIDGE, a declared diagnostic | as above, at the same weight |
| `recal_block` | the ARM's own honest conditional location re-dressed in the BLOCK's realised residual law, cross-fit | the same location in the matched recent-train window's residual law |
| `climatology_block` | the block's unconditional marginal (n-insensitive) | the matched window's marginal |

**Matched-n sizing is the corrected one (NF-W6b-C, `matched_window`): `len(test)·(K−1)/K`, not a
full block-size window.** A K-fold cross-fit peek trains on (K−1)/K of the block, so a full-size
control hands it ~1.5× the peek's rows — same-family but NOT same-sample (NF1.7 (b)), which is
precisely what made NF-W6b-C's kNN/hurdle pairs read as false near-ties.

⭐ **The augmented control is the load-bearing idea of this story.** Replacing the peeked block with
recent TRAIN rows of the same size and weight means the pair differs in exactly one thing: whether
the extra rows are the **future** (peek) or the **recent past** (honest). Without it, a λ=1
augmented peek cannot be distinguished from plain **recency weighting** — the two would look
identical. This is what makes "the gap is FORM" vs "the gap needs INFORMATION" an attribution
rather than an assertion.

## 4. The weight sweep — declared, with its numbers, BEFORE the full run

Measured on the 1-fold smoke (`2025H2`, arm 2.4347, train 20,601 rows, block 1,082):

| λ | block share of fit weight | oracle | ceiling |
|---|---|---|---|
| 1 | 3.4% | 2.4216 | **+0.54%** |
| 5 | 14.9% | 2.4314 | +0.13% |
| 20 | 41.2% | 2.5595 | −5.13% |
| 60 | 67.7% | 235.5915 | −9576.60% (numerically degenerate — a blown tail fit) |

Two things follow, both declared here rather than discovered later:

1. **`LAMBDA_AUGMENTED = 1` is the CEILING-MAXIMISING setting.** The declared bias therefore
   favours BUILD and cannot manufacture the NO this gate is most likely to return.
2. **The ceiling is MONOTONE DECREASING in the block's weight**, and the block-only peek is the
   λ→∞ limit. That monotonicity is what PROVES the block-only peek's negative ceiling is **sample
   starvation** rather than an absence of headroom. λ=5 is carried as a declared form for exactly
   this bridge, not as a ceiling candidate.

λ=60 is **not** a declared form: a peek that blows up numerically must never be scored as a ceiling.
`assert_finite_predictive` cannot see it (the bank is finite, merely absurd) — the **activity
clause** is what excludes such a peek, since an oracle worse than its own matched-n control is
INACTIVE and never enters the headline max.

## 5. Metric, folds, anchors

- **Primary: `crps_q199`** — the dense 199-level grid, imported (`FA.EVAL_LEVELS`). The native
  39-level grid is structurally blind to beyond-grid tail work (NF-MARGIN2), and the incumbent form
  carries an exponential mean-excess tail.
- ⛔ **Never MAE.** RB's realised all-zero rate is 0.3359 (NF-W7h): a zero-heavy target has its
  conditional median at the floor, exactly where MAE pays for pessimism (NF-D11/D14).
- **Folds: the 8 NF-W1 folds** (2022H1…2025H2, expanding window, purge = 2 weeks), the axis
  verbatim. Position **RB**, league **`full_ppr`** — INHERITED through W7c/W7d/W7e/W7h (E2.1-r).
- **Degenerate anchors, scored every run, never reasoned about (NF-D14):** `nihilist_zero`,
  `zero_width`, `max_width`. On a zero-heavy target the nihilist LOSING is the metric-soundness
  proof — an all-zero arm winning would mean the metric is inverted.
- **Permutation anchor:** `permuted_direct` — the incumbent form on labels shuffled WITHIN a global
  week (the target's LEVEL preserved, its per-row assignment destroyed). It must LOSE.
- One reducer for every construction; it REFUSES non-finite predictives (NF-W3 (b)) and the field
  REFUSES if any declared label produced no predictive (NF1.7 (a)).

## 6. The decision rule (pre-registered; fails closed)

`ceiling_pct` = 100 · (honest incumbent − best **ACTIVE** form's oracle) / honest incumbent, paired
over the 8 folds.

- ⭐ **ACTIVITY IS READ BEFORE MAGNITUDE.** A form whose peek does not BEAT its own matched-n
  control could not ACT; its ceiling is UNINFORMATIVE and is excluded from the headline max. **If
  NO form is active the verdict is `UNEVALUABLE`** — a statement about the instrument at this block
  size, explicitly NOT a finding that RB has no headroom (NF1.7 (a) / NF-W6d).
- `stat_ok` = CI95 excludes zero (lo > 0) ∧ `cv_power.fold_consistency_clause(8)` ∧ **BH binding at
  q = 0.10 over the five declared FORMS** — the headline is a MAX over that family, so the
  multiplicity the selection actually spends is the family (MH2 (a)).
- **Bands on `ceiling_pct`** (the NF-W5/NF-W6 bands, IMPORTED as `EM.CEILING_BANDS`):
  **< 2% → NO · 2–5% → MARGINAL (PM decision; nothing built in-session) · ≥ 5% → YES.**
  Not `stat_ok` → NO regardless of magnitude. Unevaluable pct/CI → NO (fails closed).
- ⭐ **The bands must refuse a ceiling that is statistically DEMONSTRABLE but IMMATERIAL** —
  NF-W6's "demonstrable ≠ material", whose four TD-NO cells were real at 0.07–0.38% and correctly
  refused. A tiny-but-significant ceiling is a NO.
- **PBO: UNDEFINED** — the ceiling is a pre-registered anchor contrast, not a searched field (the
  NF-W5/NF-W6 ceiling rule). **DSR does not arise**: no arm is selected.
- `cv_power.classify_null` is invoked with **`declared_field_size = 5`** and the machine flag
  **`field_remedy_admissible`** is read, never the prose (MH2.7).

**Declared bias direction (the NF-W5/NF-W6 rule): every choice favours a BUILD** — the ceiling is a
MAX over forms (upward-biased selection on the oracle side), the peek sees the future, and the
headline λ is the sweep's most generous value. **So a NO is CONSERVATIVE.**

## 7. Instrument validation (before the full run is trusted)

- **Positive control (NF-W6 §6 / MH2.1 (d)):** in `--smoke` the block's realised points are scaled
  ×1.3 and the `direct_augmented` ceiling re-measured. A blind instrument **REFUSES the smoke**
  with an `AssertionError` rather than reporting a ceiling it cannot see.

  ### ⚠️ SMOKE AMENDMENT (2026-08-17, BEFORE the full run — the NF-W6b-C precedent)

  **The clause as originally pre-registered — "the RELATIVE ceiling moves ≥ 2 percentage points" —
  FAILED at 0.821, and it is RETAINED, SCORED and REPORTED AS FAILING.** A pre-registered anchor
  that fails is left failing and DECOMPOSED, never re-labelled or deleted (NF-D20). What follows is
  the decomposition, from the evidence the refusal now writes to disk:

  | form | absolute peek advantage, base → shifted | growth | relative move |
  |---|---|---|---|
  | `direct_augmented` (gated) | 0.01102 → 0.04306 | **×3.9** | +0.821 |
  | `direct_upweighted` | 0.00103 → 0.05825 | **×56** | +1.681 |
  | `direct_blockonly` | −0.20535 → −0.05157 | — | +6.909 |

  The incumbent's CRPS goes **2.4346 → 3.3805 (×1.388)** under the shift. A MULTIPLICATIVE shift
  moves the target's scale, so it inflates BOTH the numerator and the **denominator** of a relative
  ceiling — reading instrument SENSITIVITY on that ratio understates it **by construction**. ⇒ the
  failure is a defect in the CONTROL'S OWN STATISTIC (the E2.1-r class: a gate read on a
  mis-specified statistic), **not** blindness in the instrument, which demonstrably responded
  (×3.9 and ×56).

  **The amended clause reads the quantity the peek actually moves, and is two-sided:** the gated
  form's **ABSOLUTE** advantage must grow **≥ 2×** AND the ceiling must move in the **POSITIVE**
  direction (a genuine regime difference must WIDEN a ceiling, never narrow it). The ×2 factor is a
  DESIGN quantity — the weakest non-trivial multiplicative response an instrument can be asked for
  — not a value tuned to pass.

  ⛔ **The bar was not lowered**: the amendment changes the STATISTIC the clause reads, both
  readings stay on the record, and it touches **only instrument validation** — the story's DECISION
  rule (bands, `stat_ok`, BH) is untouched.

  ⭐ The diagnosis also supplies an internal-consistency signal a blind instrument cannot produce
  (NF-D16 (g‴)): the form that is MORE sensitive to an artificial regime shift (`direct_upweighted`,
  ×56) reports a **SMALLER** ceiling on real data (0.042% vs 0.453%). Sensitivity and measured
  headroom move in opposite directions, which is what a genuinely small ceiling looks like.
- Guards RED-prove on deliberately broken source (mutation asserted to LAND, the asserted token
  asserted GONE, the mutation anchor asserted UNIQUE, `BaseException` caught around any inner
  `pytest.raises`): the cross-fit K refusal, the effective-n matched sizing, the activity-before-
  magnitude rule, the bands, the thin-bank refusal, the `retest_trigger = None` scope guard, and
  the declared-field completeness refusal — one isolating fixture per clause (NF-D17: a fixture
  that trips a second clause proves neither).

## 8. What this story cannot ship

Deploy-held: promotes nothing, publishes nothing, retrains nothing, writes no registry / S3 /
serving surface. The only outputs are the `ablation_results/` artifacts and the catalog record.
If the gate returns YES or MARGINAL, the licensed successor is a per-form §0.5 bake-off under a
**FRESH registration** — ⛔ nothing from this stage's oracle field may be promoted into that field
post-hoc (MH2.2: you may pre-register a family, you may not discover one).
