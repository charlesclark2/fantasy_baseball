# NCAAF-VAL3 — cold-start μ_total correction (weeks 1–3, in-fold selected)

**Verdict: `INCUMBENT_STANDS`, recorded state `DEFLATION_REFUSED_PBO`.** The correction is real,
large, attributable and clears every ship clause and every per-arm gate — and the pre-registered
**PBO** gate refuses it, because a field of four near-identical correction FORMS makes a
selection-stability statistic answer *"which form"* when the decision was *"whether to correct."*

`best_alpha = 0`, unchanged. Eval-only: **no serving write, no registry edit, no refit of a served
artifact, no bet.** Market-blind — the estimator reads `mu_total − y_total` and is *mechanically
prevented* from reading a market column; the one market-facing number below is descriptive and
never a clause. **No edge claim is made anywhere.**

Machine-rendered tables: [`ncaaf_val3_cold_start_readout.md`](./ncaaf_val3_cold_start_readout.md).
Every figure below: [`ncaaf_val3_cold_start_mu.json`](./ncaaf_val3_cold_start_mu.json).
Pre-registration (written before a single arm was scored):
[`ncaaf_val3_preregistration.md`](./ncaaf_val3_preregistration.md).

---

## 1. Step 0 first — the levels are re-quoted on current data, and VAL2 reproduces

The CLV-repair PM decision (§6a-2) left that repair on the 2026-07-22 vintage and made "re-quote on
current data" VAL3's first step. Executed in the card's order — cache backed up, odds join
smoke-tested alone, `--assemble --matrix-source s3`, **S1-serve re-run BEFORE VAL1**, VAL1's §2a pin
re-anchored **from the parent's output**, then VAL1 and VAL2 re-run.

| | 2026-07-22 (recorded) | **2026-08-22 (this study)** |
|---|---|---|
| closes | 4,182 | **4,187** |
| VAL2 verdict | `HAND_TO_VAL3_SCOPED`, `wk1-3` | **identical** |
| `wk1-3` μ−y (clustered) | +2.322 [+0.88, +3.76] | **+2.311 [+0.89, +3.74]**, 6/6 seasons |
| cold-start contrast Δ | +2.118 [+0.42, +3.81] | **+2.101 [+0.39, +3.81]**, t +3.16 |
| `wk4-6` μ−y | −0.626 | **−0.626** |
| by week (μ−y) wk1 / 2 / 3 | +4.83 / +2.88 / +0.28 | **+4.77 / +2.88 / +0.28** |
| VAL1 verdict | `ALL_BUCKETS_NULL` | **identical** (0 of 6 cells clear) |
| VAL1 `wk1-3` model→over / over hit | — | **0.608 / 0.463** |

Three things about step 0 that are worth carrying forward:

- ⚠️ **`--form` is load-bearing on the S1-serve re-run.** `stage_finalize` defaults to the P1.4
  REFERENCE form (`gaussian`), **not** the served `strength_posterior`. The first re-run omitted it
  and would have re-anchored VAL1's pin onto the wrong model — caught only because the banner prints
  the resolved form. Anyone re-anchoring that pin must pass
  `--contract strength_pace --form strength_posterior`.
- ⭐ **`--calib-out` is what makes the re-anchor safe.** It writes the calibration doc to an explicit
  path and **no served artifact**, so S1-serve's own decided record is not rewritten (NF-W7f).
- ⭐ **VAL1's pin HALTed exactly as designed, and the HALT was the instruction.** It failed on the
  POPULATION legs (4,187 vs 4,182 closes) — precisely the separation its docstring promises between
  *"the population moved"* and *"the read changed"*.

⭐ **A worktree makes the cache-clobber hazard structural rather than procedural.** The card flags
that a failed odds join still writes `has_close = False` over the only working cache. In this
worktree `_PROJECT_ROOT` resolves to the worktree, so `--assemble` wrote a worktree-local cache and
**could not reach the main checkout's copy at all**. The `/tmp` backup was taken anyway; it was
never needed.

---

## 2. The correction works, and it is large

8 purged folds (2018–2025), 6,024 OOS games, **1,051 cold-start rows**. Every arm moves `μ_total`
only; per-game σ and `μ_margin` are byte-identical across arms (clauses C6/C7).

| arm | role | δ̄ (pts) | CRPS wk1-3 | gain vs foil | folds won | DSR | p | clauses |
|---|---|---|---|---|---|---|---|---|
| `none` (foil) | foil | 0.000 | 9.4642 | — | — | — | — | — |
| **`bucket_shift`** | candidate | 1.517 | **9.3793** | **+0.0848** | **8/8** | **0.998** | **0.0047** | ✅ |
| `linear_decay` | candidate | 1.526 | 9.3822 | +0.0820 | 7/8 | 0.953 | 0.0194 | ✅ |
| `per_week_shift` | candidate | 1.555 | 9.3908 | +0.0734 | 6/8 | 0.703 | 0.0712 | ✅ |
| `shrunk_bucket` | candidate | 0.997 | 9.3918 | +0.0723 | 8/8 | 0.999 | 0.0065 | ✅ |
| `pooled_level` | ⛔ lose | 0.239 | 9.4497 | +0.0145 | 6/8 | 0.949 | 0.0118 | ✅ |
| `week_blind` | ⛔ lose | 0.239 | 9.4497 | +0.0145 | 6/8 | 0.949 | 0.0118 | ✅ |
| `over_scale` | ⛔ lose | 3.034 | 9.3723 | +0.0918 | 6/8 | 0.826 | 0.0463 | ❌ C8 |

**The AC's two halves, both met by the leader.**

| | foil | `bucket_shift` |
|---|---|---|
| cold-start bias | **+2.074 pts** | **+0.557** (73 % removed) |
| cold-start CRPS | 9.4642 | **9.3793** (+0.90 %) |
| cold-start PIT max-decile-dev | 0.0653 | **0.0613** |
| cold-start `calib_80` | 0.8270 | 0.8302 |
| pooled bias | +0.362 | **+0.102** |
| **pooled PIT max-decile-dev** | 0.0261 | **0.0269** |
| pooled `calib_80` | 0.8080 | 0.8086 |

The aggregate PIT is **not degraded**: +0.0008 against the pre-registered +0.0020 tolerance. Stated
plainly rather than rounded away — it did not *improve* either; what improves is the aggregate BIAS
(+0.362 → +0.102) and everything on the cell the mechanism touches.

**Attribution, read as paired deltas rather than as a rank (NF-D10 / NF-D15 g′).**

| channel | pair | cell | mean gain | folds + | p |
|---|---|---|---|---|---|
| **MAGNITUDE** | `bucket_shift − week_blind` | wk1-3 | **+0.0704** | 7/8 | **0.0051** |
| SCOPING | `week_blind − pooled_level` | pooled | +0.0000 | 3/8 | 0.4928 |

The win is **attributable to the week-informed magnitude**: holding the scoping fixed and replacing
the cold-start constant with the pooled one costs 83 % of the gain.

⚠️ **The scoping channel reads +0.0000, and that is `INACTIVE`, not "scoping is inert."** The
pooled in-fold magnitude is only **0.239 pts**, so spreading it over weeks 4+ instead of confining
it to weeks 1–3 has almost nothing to express — the contrast could not ACT (NF-D20: count whether
the mechanism could move the constrained quantity before reading its result). What DOES bear on the
scoping question is the leaderboard's own shape: `pooled_level` recovers **+0.0145** of the
available **+0.0848**, i.e. a pooled level correction leaves 83 % of the cold-start error in place —
VAL2's ⛔ survives contact, and the reason is that a pooled estimator is diluted by the `wk4-6` cell
VAL2 measured at **−0.626**.

⭐ **A structural fact about this design, stated because it is arithmetic and not a discovery:**
`pooled_level` and `week_blind` apply the same δ to the same cold-start rows, so on the PRIMARY
(cold-cell) metric they are **identical by construction** — the primary metric is structurally BLIND
to the scoping channel. That is why the two channels are read on different cells.

---

## 3. What refused it: PBO — and the null does NOT rest on the gate choice

`bucket_shift` passes C1–C8, beats the foil, wins 8/8 folds (the calibrated clause asks 6),
clears DSR 0.998 ≥ 0.95 and clears BH (p 0.0047 vs cutoff 0.0357). It fails on one gate:

**PBO 0.5300, gate < 0.20.**

NF-D15 (g″) says a null must be shown not to rest on the analyst's gate choice, so the same
statistic was recomputed over three populations. ⛔ The pre-registered one **binds**; the others are
labelled diagnostics and none of them was adopted (MH2.2 / E2.1-r).

| population | arms | PBO | binds |
|---|---|---|---|
| **pre-registered** (foil + all 7 scored arms) | 8 | **0.5300** | ✅ |
| eligible set only (foil + the 4 selectable candidates) | 5 | **0.7010** | diagnostic |
| the two-arm decision (foil vs `bucket_shift`) | 2 | **0.0000** | diagnostic |

⭐ **This is the finding, and it is the opposite of the tempting one.** The obvious hypothesis is
that PBO 0.53 is inflated by the three pre-registered INELIGIBLE arms out-ranking the candidates —
CLAUDE.md's own note even says PBO belongs over the eligible set. **Measured: the eligible-set PBO
is WORSE (0.701), not better.** Trimming the field does not rescue this null; only collapsing to the
two-arm question does, and there PBO is 0.0000 because there is no search left to overfit.

**Why, precisely.** The four candidates land within **0.0125 CRPS of one another — 0.13 % of the
foil** — while the fold-level flip distribution scatters (`per_week_shift` 3, `over_scale` 3,
`bucket_shift` 1, `linear_decay` 1, everything else 0). That is NF1.8's **tied-field** signature
read exactly as recorded: mass sitting on arms a fraction of a percent apart is a TIE. So PBO is
reporting something TRUE — *which of four near-identical correction forms is best is a coin flip* —
and reporting it against a decision that was never about choosing between forms.

⚠️ **And note the whole-field spread is 0.0774 CRPS, 6× the candidate spread.** Reading the spread
over the full field would say "wide spread + high PBO ⇒ genuine overfitting"; that number is
measuring the pre-registered nulls, not the contest (NF1.8, verbatim). Both are reported.

**The gate is not being second-guessed.** It was pre-registered, it was evaluated, it failed, and
nothing ships. What the sensitivity establishes is the *mechanism* of the refusal, which is what the
successor needs.

⭐ **An instrument gap, recorded rather than worked around.** `cv_power.classify_null` takes **no
PBO argument at all** — it can express PBO-UNDEFINED (too few folds, or a single contrast) but not
PBO-**EVALUATED-AND-FAILED** — so its own state (`POWER_LIMITED`, on its honest
"insufficient recorded statistics" default) structurally cannot see the gate that bound here. Its
state is preserved verbatim in the artifact and is **not** the verdict; the recorded state is
`DEFLATION_REFUSED_PBO` with `binding_half = "deflation"`. This vertical has hand-corrected that
classifier several times (NF-W2 → NF-D18 → NF-W3 → NF-W4 → MH2.7); this is the next one, and by
MH2.7's own rule — *a defect corrected N times downstream is a defect in the instrument* — it
belongs in `cv_power`, not in another local workaround.

⛔ **No fold or season re-test trigger is published.** No fold count moves a pre-registered gate
POPULATION, so a "come back with more seasons" trigger would be the actively-misleading direction
(NF-D18). The admissible remedy is a **forward-registered** narrower coherent family.

⚠️ **A pre-registration gap, recorded as such.** This study registered a materiality band in POINTS
(inherited from VAL2) but not a practically-meaningful CRPS effect in SD units, which is why
`classify_null` correctly declines to certify the null as powered rather than returning
`TRUSTWORTHY_DEAD`. ⛔ Supplying one now would be re-deriving a bar from the answer (E2.1-r).

---

## 4. Anchors — and one leaderboard reading that the paired test refutes

**Every peek is per-FORM and every peek has its own matched-n control.** A single field-wide bucket
ceiling would have vetoed `per_week_shift` and `linear_decay` — both of which CONTAIN the bucket
constant as a special case — as metric inversions (NF-D16 g‴). The C8 clause was under-built on the
first cut and the smoke run exposed it before the full run.

| arm | form | own-form peek | its matched-n | peek gain | pair | C8 |
|---|---|---|---|---|---|---|
| `bucket_shift` | bucket | 9.3464 | 9.4154 | +0.0689 | ACTIVE | FLOORED |
| `per_week_shift` | per_week | 9.2117 | 9.4692 | +0.2575 | ACTIVE | FLOORED |
| `linear_decay` | linear | 9.2845 | 9.4361 | +0.1516 | ACTIVE | FLOORED |
| `shrunk_bucket` | shrunk | 9.3762 | 9.4218 | +0.0456 | ACTIVE | FLOORED |
| `pooled_level` | pooled_all | 9.4449 | 9.4154 | −0.0295 | **INACTIVE** | INACTIVE |
| `week_blind` | pooled_cold | 9.4449 | 9.4154 | −0.0295 | **INACTIVE** | INACTIVE |
| `over_scale` | over2 | 9.4177 | 9.5265 | +0.1088 | ACTIVE | **BEATEN** |

The two pooled foils' anchor pairs are `INACTIVE` — their peek does not beat its own matched-n
control, so their floors are uninformative and are recorded as such: never a pass, never a fail
(NF-W6d / NF-D20).

**`over_scale` tops the leaderboard, and it is a TIE, not a refuted magnitude.** A pre-registered
lose-by-construction arm finishing first is NF-D20's refuted-magnitude signature, and the honest
move is to read the PAIRED delta rather than the rank (NF1.8: a rank statistic cannot tell a tie
from a win). Paired per fold:

> `over_scale − bucket_shift` = **+0.0070 CRPS, 5/8 folds, two-sided p = 0.779** — indistinguishable.

⇒ ⛔ **do not record "the estimator under-corrects by ~2×".** The leaderboard would have said
exactly that. What the leaderboard did earn is `over_scale`'s **C8 failure**: it is the only arm
that beats its own-form peek, i.e. doubling a *downward-biased* in-fold estimate lands closer to the
truth than doubling the *eval fold's own* mean. That is an accident of a deliberately mis-scaled
form, not skill — and it is left FAILING and decomposed rather than re-labelled (NF-D20 (1)).
`over_scale` was ineligible by ROLE in any case, so nothing turns on it.

**The under-correction that IS measured** is the residual: **+2.074 → +0.557 pts**, i.e. the
correction removes 73 % of the cold-start bias on a metric minimised at zero bias. Its cause is
visible per fold:

| fold | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|
| the fold's own cold-start error | +0.72 | +1.46 | +1.80 | +1.70 | +0.67 | +2.90 | **+4.09** | **+3.25** |
| the in-fold δ it was given | +1.88 | +1.29 | +1.35 | +1.38 | +1.46 | +1.30 | +1.57 | +1.91 |

⭐ **The in-fold estimator is nearly a CONSTANT for a quantity that moves by ±1.2 pts a year.**
Its sd across folds is **0.249** against the target's **1.227** (5×), and their correlation is
**0.105** — it gets the average level roughly right (1.517 vs 2.074) and tracks essentially none of
the year-to-year variation. That is what a backward-looking mean does to a **non-stationary** level:
VAL2 measured that level drifting −0.06 → +2.14 by season, and the same non-stationarity that made
NF-TR2's full-history level constant over-correct makes this one under-correct. **It is a property
of the ESTIMATOR, not of the mechanism**, and it is the sharpest lead this study produces.

---

## 5. Instrument controls

- **The scored CRPS is a closed form, not a sample.** The served predictive *is* a heteroscedastic
  Gaussian, so `σ·[z(2Φ(z)−1) + 2φ(z) − 1/√π]` is its exact CRPS. Every figure above is
  deterministic to 1e-12, which removes the Monte-Carlo-variance question NF-W7k needed a whole
  story to close, rather than bounding it.
- **Cross-checked against the ensemble identity the rest of the vertical uses**, at TWO draw counts:
  max |gap| **0.02125 at 5,000 draws → 0.01234 at 20,000** (0.13 % of the CRPS). ⭐ The
  **convergence** is the evidence, not the single gap: a fixed residual gap would be a real
  disagreement; a gap shrinking ~1/√n is the sampler's own error.
- **Two-sided metric check** (guarded, not asserted): the closed-form CRPS is minimised at the true
  conditional mean and rises for a shift in *either* direction, so a pessimism arm cannot win it
  (NF-D11); a correct Gaussian's analytic PIT is flat to <0.01 and its `calib_80` lands on nominal.
- **Fold-consistency** uses the calibrated clause: 6 of 8 wins required at a 0.1445 false-fire rate
  (the legacy 60 % rule would have asked 5 at 0.3633 — H8's point that `≥60 %` is a different gate
  at every fold count).
- **`V` is measured over the real arms only** — a diagnostic anchor must never set the gate's own
  bar (MH2.1 a). The FULL-FIELD `V` (0.05878) **binds**, as declared forward; the DSR-CONV variant
  (0.09080, designed losers excluded) is reported and does not. ⛔ Declaring the generous reading
  non-binding *before* the run is what forecloses the NF-W7h failure in which a post-hoc re-read of
  `V` deletes the arm under test — and here the instrument itself prescribed exactly that re-read,
  which the pre-registration declines.

---

## 6. The AC's headline — the wk1-3 over-tilt

⚠️ **DESCRIPTIVE.** The only market-touching number in the study, on the 715 close-carrying
cold-start rows. It is not a clause, not a selection criterion and not an edge claim; the estimator
is *mechanically* prevented from reading it (C4 raises on any market column reaching the estimator
frame, and the column list is a contract, not a denylist). Over actually hit **0.456** on these rows.

| arm | model → over | mean μ − close (pts) |
|---|---|---|
| `none` (served today) | **0.613** | **+1.357** |
| `bucket_shift` | **0.502** | −0.157 |
| `linear_decay` | 0.497 | −0.162 |
| `per_week_shift` | 0.509 | −0.160 |
| `shrunk_bucket` | 0.519 | +0.147 |
| `pooled_level` / `week_blind` | 0.608 | +1.244 |
| `over_scale` | 0.410 | −1.672 |

The correction does what VAL1/VAL2's lead said it should: the served model's cold-start over-tilt
goes from **0.613 to 0.502** — from a 61/39 lean to a coin flip — on the one bucket where the over
hit only 0.456. ⛔ **This is not an edge finding.** VAL1's `ALL_BUCKETS_NULL` stands and is
unaffected: removing a directional lean is a statement about our own calibration, and `best_alpha`
remains 0.

---

## 7. Verdict, and what a successor would have to do

**`INCUMBENT_STANDS` / `DEFLATION_REFUSED_PBO`.** Nothing ships. The served model is unchanged.

**What is established and survives the null:**

1. The cold-start over-correction is **real, large and repairable in-fold**: +2.074 → +0.557 pts of
   bias, +0.0848 CRPS on the cell, **8/8 folds**, DSR 0.998, p 0.0047, every ship clause clear, and
   aggregate PIT within its tolerance.
2. It is **attributable to the week-informed magnitude** (+0.0704, 7/8, p 0.0051) by a matched foil,
   not merely observed.
3. VAL2's ⛔ on a pooled level correction **survives contact**: the pooled estimator recovers 17 % of
   the available gain.
4. The binding limitation is the **ESTIMATOR, not the mechanism**: a backward-looking in-fold mean is
   a near-constant (sd 0.249) for a target that moves ±1.227 a year, ρ = 0.105.

**The successor, and why it is a fresh registration rather than a re-read.** The refusal came from a
gate measuring a tie among four forms of one mechanism. The repo has converted that shape four times
(MARGIN2→MARGIN3, W7→W7b, NF-W6b-C, NCAAF-P2.1-S1) and each time by **pre-registering a coherent,
narrower family forward** — never by re-cutting a field already scored (MH2.2). Here that means a
**single** pre-registered contrast, which is not a loophole but a documented state:
`classify_null`'s `n_arms < 2` branch says in terms that a single pre-registered contrast has **no
search to overfit**, so CSCV/PBO is *inapplicable rather than unmet*, and the deflation requirement
is satisfied by the DESIGN. The remaining gates (the paired contrast, its fold consistency, DSR)
already clear at 8/8 and 0.998.

⚠️ **But that is a hypothesis about the FIELD, and NF-W7f is the counterexample that says to measure
it rather than assume it.** The diagnostic is on the record: the two-arm PBO is **0.0000**. Which
form to register is likewise a decision the evidence constrains but does not make — `bucket_shift`
(1 parameter, 8/8 folds, best CRPS) and `linear_decay` (2 parameters, 7/8, +0.0820) are 0.13 % apart
and the flip distribution cannot separate them; ⛔ picking the leader *now* and calling it
pre-registered would be laundering (E2.1-r). The mechanistic argument favours the simpler form:
VAL2 measured the by-week decay as +4.77 / +2.88 / +0.28, which a 1-parameter constant over three
weeks already approximates, and the extra parameters bought nothing here.

⭐ **And the successor's real target is the estimator, not the form.** §4's per-fold table says a
backward-looking mean is a near-constant against a rising level, so the candidate that would
actually pay is a **recency-weighted or drift-aware in-fold estimator** — which is a *different*
mechanism, must be registered forward, and inherits every constraint here (in-fold selection, the
frozen σ, the aggregate-PIT clause, and the market-blindness of the estimator). ⛔ It must NOT be
reached by scaling this study's δ upward: `over_scale` measured that as a **tie** (p = 0.779), and
fitting a multiplier now with the answer in view is the inadmissible-λ shape VAL2 §9 explicitly
warned VAL3 about.

**PM decisions this study raises** (neither taken here):

1. **Should a single pre-registered contrast be carded as NCAAF-VAL3b?** The mechanism is measured,
   the constraint is understood, and the estimator lead is specific. It is a small story.
2. **`cv_power.classify_null` cannot express PBO-EVALUATED-AND-FAILED.** Every caller that hits it
   must hand-record the binding gate, as this one does. By MH2.7's own rule that belongs in the
   instrument. ⚠️ It is a SHARED instrument — the MLB and prospect verticals pin its output — so it
   is a deliberate cross-vertical change under the test-merge discipline, not a drive-by.

## Files

- `models/ncaaf_val3_cold_start_mu.py` — the harness (eval-only; no served artifact is written).
- `models/ncaaf_val3_red_proof.py` — 34 deliberate breaks, **34/34 RED**. ⭐ It found **four vacuous
  guards** on its first run: a HALT asserted as a substring (so `if False:` left every string a text
  scan looks for while HALTing on nothing — the CLV-repair lesson, one story on); two ship-rule
  clauses scanned over the whole of `stage_decide`, where every needle also appears in the reported
  dicts; and a binding-`V` clause matching a substring that survives swapping `V_binding` for
  `V_convention`. All four are fixed.
- `betting_ml/tests/test_ncaaf_val3_cold_start_mu.py` — 50 fast-gate guards.
- `ablation_results/ncaaf_val3_preregistration.md` · `…_cold_start_readout.md` (machine-rendered) ·
  `…_cold_start_mu.json` · `…_cold_start_scores.json` · `…_s1_serve_reanchor.json` (the parent run
  the reproduction pin is anchored on).

Runtime **17 s** end-to-end on the laptop; step 0 (`--assemble` + S1-serve + VAL1 + VAL2) a further
~80 s. No operator run required to reproduce any of it.
