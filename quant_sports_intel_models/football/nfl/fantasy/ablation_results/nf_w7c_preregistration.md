# NF-W7c pre-registration — arbitrary-league re-scoring assembly: per-stat distributions → one per-player fantasy-point distribution

**Committed BEFORE any full-run scoring** (the §0.5 discipline). Everything below lives as
constants in `fp_assembly.py` / `joint_draw.py`; the runner `run_nf_w7c_fp_assembly.py` READS them
(NF-D16). A smoke run (1 fold, short train window, 300 draws, artifacts suffixed `_smoke`) may be
used to prove the code path — no verdict, and **no constant may change in response to a smoke
score after this file is committed**.

⚖️ Edge-independent projection product — `best_alpha = 0`, **deploy-held**, NF-G0 challenger.
Research-only: no changelog entry. Every emitted string is a calibrated RANGE, never an edge /
ROI / win-rate claim.

## 0. The thesis under test (not assumed)

NF-W6d completed the per-STAT substrate: 52 (position, stat) cells, one calibrated quantile bank
each. What the optimizer and the "what might this player do this week" surface need is a
per-PLAYER fantasy-POINT distribution **under a specific league's scoring** — which is an
ASSEMBLY: draw a player's 13 scored stats jointly, score each draw under the league's own rules,
read the point distribution off the draws.

The joint half is the whole difficulty, and the program has already MEASURED both halves of it.
NF-W7 assembled DST from independently-drawn component banks, won its score contest, and was
`CONSTRAINT_REFUSED` by the coverage(80) floor — the declared independence simplification firing.
NF-W7b then added a Gaussian-copula draw over the same frozen marginals and found that fixing the
dependence was a **free CRPS win** (+0.0273 vs the refused independent arm), not a
coverage-for-score trade.

⇒ **Independence here is a measured, refused simplification — never a benign default.** The thesis:
a joint draw over the 13 legs, whose Σ is estimated on RAW OUTCOME RANKS, produces a calibrated
league fantasy-point distribution that beats a matched independent draw on the proper score AND on
coverage. A null is a legitimate published outcome, naming exactly which dependence structures
were tried and how they fell short.

## 1. Binding constraints

- ⛔ **The per-stat marginals are NOT refit or re-selected.** The assembly consumes the NF-W6d
  SERVED MAP through the SERVING DISPATCH (`SDSD.serve_banks`), so it can never consume a marginal
  the served substrate would not. This story adds ONLY the dependence structure and the re-scoring.
- ⛔ **There is no fourth scorer.** Fantasy points come from `ScoringRules.points_for` — the same
  authority `fantasy_engine`, the browser TS port and the Lambda scorer all resolve to — assembled
  into a per-position weight vector and dotted with the draw. `test_nf_w7c_fp_assembly.py` proves
  the linear form equals `fantasy_engine.scoring.score_players` EXACTLY on real published payload
  rows, for every shipped preset. **The NF-EPIC 1 merge-gate parity test is therefore untouched and
  still covers every scoring rule; NF-W7c pays no parity tax because it REUSES the policy rather
  than restating it.**
- ⛔ **The coverage(80) floor is `kdst_weekly`'s verbatim** (0.80, blocking beyond 3 binomial SE) —
  it may not move in either direction (NF-D18 / E2.1-r / NF1.8), and the over-correlated degenerate
  is SCORED against it to prove it was not promoted into a selection criterion.
- **Frames, folds, PIT gate**: the NF-W6d matrix builder + the NF-W1 8-fold axis (2022H1…2025H2,
  purge 2) + the fail-closed per-week PIT gate, all reused unchanged. NF-W0 constraints (leak-clean
  PIT frame, ⛔ no `fillna(0)`, provenance-checkable features, no markets/weather) are inherited
  through the reused frame builder.
- **Σ is always estimated on TRAIN**, never on the slate being scored; oracle and matched-n
  contexts are the only exceptions and are labelled as such.

## 2. The declared gate league (one — the field is not multiplied by format)

`full_ppr` gates. It is the substrate's own convention (`SD.PPR_WEIGHTS`) and the modal real
league. `standard` / `half_ppr` / `te_premium` are re-scored **REPORT-ONLY**, which demonstrates
league-generality without buying a multiplicity penalty for it. ⛔ The gate league may not be
re-chosen after seeing a score.

## 3. The declared real-arm family (4 arms — a structure/magnitude grid on the dependence axis)

| arm | Σ̂ estimator | the hypothesis |
|---|---|---|
| `joint_rank` ⭐ PRIMARY | Spearman rank correlation of **RAW outcomes** → `2·sin(π·ρs/6)`, per position, train-only | the co-movement is real and is best read off the outcomes themselves |
| `joint_factor` | nearest ONE-FACTOR structure of that Σ̂ | a single shared latent (game script / pace / opponent), each leg loading with a free sign |
| `joint_pit` | randomized-PIT latent z-scores under the frozen W6d marginals | the residual scale — **registered as a REAL arm so the raw-rank choice is EARNED on this population, not inherited from NF-W7b's finding** |
| `joint_double` | raw-rank Σ̂ off-diagonals ×2, PSD-repaired | the attenuation/magnitude probe (NF-D20): a REAL arm, so an under-correcting estimator cannot hide behind an anchor's ineligibility |

⭐ **Why raw ranks are the pre-registered primary.** NF-W7b's `joint_double` beat the residual-PIT
estimator, confirming that randomized-PIT z-scores systematically UNDER-estimate dependence on
zero-heavy discrete margins. The 13 legs here are far MORE zero-heavy than DST's. But a measured
finding carried forward as an assumption is how a result becomes folklore, so `joint_pit` is in the
field as a contest, not a foregone conclusion.

## 4. Foils, degenerates and anchors — all SCORED, never reasoned about

- **FOILS (eligible; `beats_foil` is a gate clause):**
  - `assembled_indep` — ⭐ **the matched INDEPENDENT draw**, the card's binding requirement. It is
    a FOIL and not an anchor precisely so that beating it can REFUSE the story. It shares the base
    normals with every arm (common random numbers), and at Σ=I the copula draw is
    BYTE-IDENTICAL to it — so the comparison is dependence and nothing else.
  - `foil_direct_points` — a learner pointed straight at league points. Without it, "the assembly
    wins" would only ever be measured against itself.
- **DEGENERATES (registered to LOSE):** `nihilist_zero`, `zero_width`, `max_width`,
  `assembled_comonotone`. The comonotone arm is the over-correlated ceiling: it will trivially
  SATISFY the coverage floor, and it must still lose the metric (NF1.8 — a constraint a degenerate
  satisfies is fine; a criterion a degenerate wins is fatal).

  ⚠️ **SMOKE AMENDMENT (2026-08-16, BEFORE any full run / any decision).** `zero_width` was first
  located at the train MEDIAN. The path-proof smoke measured it at **6.1409 on the QB fold —
  byte-identical to `nihilist_zero`** — because QB league points have a train median of 0, so a
  median-located point mass IS the all-zero bank. Both still lose by a wide margin, so no verdict
  was affected; but two anchors collapsing into one is a silent loss of evidence — the sharpness
  degenerate stops being a distinct test (the NF-D11/D14 conditional-median lesson, appearing in
  the anchor set). It is now located at the train MEAN: still a point mass (maximally sharp, which
  is its entire purpose) but positive on a zero-heavy target, so the two degenerates test
  different things again. Recorded here rather than silently changed.

- **ANCHORS:** `permuted_direct`; and **per-form** oracle + matched-n controls for every real arm,
  plus an own-form oracle for `foil_direct_points`. ⭐ Per-FORM is load-bearing: the joint forms
  NEST one another (Σ=I ⊂ one-factor ⊂ full), so a single field-wide ceiling would veto a
  legitimately-better nested form as a false metric inversion (NF-D16 (g‴)).
  ⛔ `assembled_indep` deliberately carries **NO** oracle: it estimates nothing, so a peek has
  nothing to improve and its "oracle" would be byte-identical to the arm itself. An anchor that
  cannot differ from what it anchors is décor, and scoring it as "respected" would be a pass on
  nothing (NF1.7 (a) / NF1.9's "a mechanism that cannot act is a finding").

  ⚠️⚠️ **SMOKE AMENDMENT 2 — THE ORACLE FLOOR IS NOW THREE-STATE (2026-08-16, BEFORE any full run
  / any decision; the amendment is disclosed as SMOKE-INFORMED).**

  The path-proof smoke measured **every** dependence oracle at or BELOW its own arm on the QB
  fold — `joint_rank` +0.0002, `joint_factor` +0.0007, `joint_double` +0.0048, `joint_pit`
  +0.0095, all in the ARM's favour — so the two-state clause
  (`arm > oracle OR oracle < matched_n`) returned **False for all four arms** and would have
  refused the story at every position regardless of how well the dependence performed.

  **MECHANISM, measured not asserted.** This story's oracle peeks at Σ and nothing else, because
  an oracle that also refit the marginals would be a DIFFERENT FAMILY (NF1.7 (b)). So it estimates
  a 13×13 correlation on the ~701-row TEST block while its own arm estimates the same matrix on
  ~12,622 TRAIN rows. **The peek's information gain is swamped by an ~18× sample-size loss, so the
  "ceiling" lands BELOW the quantity it is meant to bound.** A peeking oracle is a floor only when
  the peek's gain exceeds its sample-size loss — NF1.7 (b) facing the direction this story hit.
  This is the NF-W6d finding verbatim ("a per-form oracle floor that TIES its matched control is
  INACTIVE, not a refusal — an inactive anchor is UNINFORMATIVE (NF-D20), never a fail"), whose
  own record cards the fix as belonging in the SHARED gate **because it recurs**. This is the
  recurrence.

  **THE AMENDED RULE.** `RESPECTED` — the peek beat its own arm or the matched-n control.
  `VIOLATED` — it beat neither AND the arm's win over it is BOTH significant (α = 0.05, the level
  this story's permutation clause already uses) AND **material**, defined as at least one tenth of
  the CRPS that arm CLAIMS over the independent foil. `INACTIVE` — it beat neither and the
  inversion is a tie. INACTIVE blocks nothing, is **never** scored as a pass (`respected is None`),
  and is NAMED on the verdict (`positions_with_unevaluated_oracle_ceiling`) so a ship cannot
  silently claim a protection it never had.

  **WHY MATERIALITY AND NOT SIGNIFICANCE ALONE.** A paired test over folds calls an arbitrarily
  TINY but CONSISTENT gap significant — a constant-offset series has zero paired variance, so
  p → 0 on a 2e-4 difference nobody could act on. That is NF-W6's "the ceiling bands must refuse a
  ceiling that is statistically DEMONSTRABLE but IMMATERIAL". The first cut of this amendment used
  significance alone and was caught by its own fixture.

  ⛔ **THE CLAUSE REMAINS FALSIFIABLE, AND IT ALREADY DISCRIMINATES ON THE REAL NUMBERS.** Under
  the amended rule the three raw-scale arms read INACTIVE, but **`joint_pit` reads VIOLATED** — it
  loses 0.0095 to its own ceiling while claiming only 0.061, i.e. ~15% of its claimed effect. The
  amendment was NOT tuned until everything passed; the attenuated arm is still called out, and
  `joint_pit` failing this way is consistent with NF-W7b's finding that residual-PIT estimates are
  attenuated on zero-heavy discrete margins. A guard that could not fail would be the vacuous-guard
  class this repo keeps re-learning (NF1.7 (a) / INC-38 / NF-D17).

  **AUDITABILITY.** The UNAMENDED verdict is recorded beside the amended one
  (`oracle_floors_respected_PRE_AMENDMENT`, and `pre_amendment_respected` per arm), the per-fold
  contrasts are stored, and the whole verdict layer is re-derivable at zero refit cost
  (`--rewrite-report`). The amended clause BINDS; the pre-amendment figure is reported so a reader
  can reverse the decision (NF-D14 — report both, pre-register which binds).

  ⚠️ **THE MATERIALITY FRACTION IS A DESIGN CHOICE MADE BEFORE THE 8-FOLD EVIDENCE EXISTS, AND
  IT IS SMOKE-INFORMED.** One fold cannot say whether an inversion is CONSISTENT — the smoke's
  significance is an artefact of replicating a single mean. Only the full run's per-fold series can
  settle `joint_pit`, and it will do so under the rule fixed here, not one chosen afterwards.

  ⭐ **ACTIVITY POSITIVE CONTROL.** `foil_direct_points`' own oracle peeks at EVERYTHING and
  measured **2.6128 → 1.7592** on the same smoke. It runs through the IDENTICAL evaluator and must
  read RESPECTED — which is what proves "inactive" is a measured property of the Σ channel rather
  than a blanket excuse (NF1.8's two-sided degenerate discipline).

## 5. Pre-declared arm-movability (a statistic the arm cannot move is décor — NF-MARGIN2 / NF-D20)

- **Analytic half:** `sd(Σ wᵢXᵢ) = √((w∘σ)ᵀ Σ (w∘σ))` is strictly increasing in every off-diagonal
  with a positive weight product, so the dependence knob provably moves the assembled sum's
  dispersion and hence its central-interval coverage — before a single draw. Recorded per fold.
- **Measured half:** the gate carries three DEPENDENCE clauses —
  `independence_under_disperses` (the harness must SEE the defect it claims to fix),
  `dependence_moves_coverage` (the knob's full range moves the gated statistic), and
  `beats_indep_on_coverage` (correlation earns its place on coverage too).

## 6. Gate (all clauses must pass; declared here, composed in code)

`crps_q199` vs the best foil ∧ the calibrated fold-consistency clause (`cv_power`) ∧ PBO < 0.2
over the 6-config eligible field ∧ DSR ≥ 0.95 over the 4-arm declared family (anchors and
degenerates never enter V — MH2.1 (a) / DSR-CONV, pre-registered FORWARD) ∧ BH-FDR at q=0.10 over
the four position hypotheses ∧ **coverage(80) floor** ∧ **randomized-PIT decile flatness ≤ 0.05**
∧ degenerates lose ∧ permutation behaves ∧ per-form oracle floors respected at matched n ∧ the
three dependence clauses.

⭐ E2.1-r: on these atom-bearing discrete legs, coverage is a **FLOOR** and PIT flatness is the
calibration **TARGET** — never the other way round.

`cv_power.classify_null(declared_field_size=4)` classifies any null, read through
`field_remedy_admissible` (MH2.7) so the instrument REFUSES to prescribe a field smaller than the
pre-registered one. A null resting solely on the coverage floor is `CONSTRAINT_REFUSED` with **no
data trigger** (NF-D18) — more folds shrink the SE and make the refusal MORE certain.

## 7. Labelling (NF-W6d's promote blocker, honoured at the assembled level)

An assembled distribution surfaces the sources of the legs it is actually BUILT from — **the legs
the league PRICES**, because a leg weighted 0 contributes identically 0 to every draw and cannot
influence the answer. A Phase-C DEFAULT among priced legs sets `source = partial_default` (or
`default`) and emits a `calibration_warning`; a default on an unpriced leg does not (a warning
about something that cannot matter is the alert-fatigue direction E11.30 names). **Both directions
are guarded.**

⚠️ Measured against the real 52-cell map, **every position labels `partial_default`** — because a
position's MINOR CHANNELS (a receiver's passing yards) are Phase-C defaults and standard leagues
price them. So `default_contribution_share` additionally MEASURES the share of absolute expected
point contribution that rests on a default. ⛔ **No materiality threshold is applied here.** Choosing
one now, having seen which legs it would silence, is the E2.1-r inversion; any display rule is
pre-registered FORWARD by the consuming story.

## 8. The coverage gap that must never be silent

The substrate covers 13 stats. A league may price terms outside it — a per-completion bonus, the
NF-C0e long-touchdown bonuses (`SKILL_UNMODELED_KEYS`). Scoring those as 0 would UNDER-state
fantasy points with no signal anywhere. `assert_assembly_is_priceable` **REFUSES by default**;
`allow_unpriced=True` still returns the gap so a caller must carry it onto the row. K/DST terms are
partitioned off separately — structurally another position's line, not a gap in this substrate —
and the three buckets are asserted to PARTITION the profile, so a new scorable term cannot land
nowhere and be silently zeroed.

## 9. What a null would mean

- **Beaten by `assembled_indep`** ⇒ the legs do not co-move enough at this granularity to pay for
  a dependence structure; independence is then a MEASURED simplification for the skill-position
  assembly (a real, publishable finding, and the opposite of NF-W7b's DST result).
- **Coverage-floor-only refusal** ⇒ `CONSTRAINT_REFUSED`; the registered structures UNDER-correct.
  Remedy is a BETTER estimator/shape under a FRESH registration (the NF-MARGIN3 / NF-W6b-C
  successor pattern — e.g. an atom-aware or vine copula that models the zero/positive mixture
  explicitly), or a PM decision. ⛔ Never a post-hoc floor change, never "more seasons".
- **DSR failure** ⇒ read for its MECHANISM (observed SR vs the field's SR0, and which trial arm
  inflates V) BEFORE filing POWER_LIMITED (NF-W6b-C: "≈0 more folds" is a misleading trigger when
  the mechanism is field dispersion).

## 10. Deploy hold

Nothing here promotes, publishes or retrains. The serving path (`certified_arms` / `serve_fp_frame`)
is FAIL-CLOSED on the record: an absent / smoke / wrong-story / NULL-verdict record is REFUSED, so
a challenger cannot serve itself into existence. `PROMOTE_BLOCKERS` are carried onto the artifact
and into the report.

---

## 11. POST-RUN FINDINGS (added AFTER the decisive run — 2026-08-16)

⛔ **Nothing in this section changes a gate, a threshold, an arm, or a verdict.** The run's result
stands exactly as the pre-registration and its two smoke amendments defined it. This records what
the completed record explains, and what it hands the next story.

### 11.1 The QB PIT-flatness refusal is an AVAILABILITY defect, not a copula defect

QB is the only position failing the pre-registered PIT bar (winner 0.0888; even the best-calibrated
representation in the field reaches only 0.0563 against a 0.05 bar), so **no arm in the declared
field could have passed it** — a refusal structural to the field, not a selection accident. For
scale: a *perfectly* calibrated model at these sample sizes (n ≈ 690) posts a median max-decile
deviation of **0.0201** and exceeds 0.05 essentially never (4,000-draw simulation).

⭐ **Every representation fails, including `foil_direct_points`, which contains no copula at all**
(0.0959 — the WORST in the field). So the defect belongs to the target, not to the assembly.

The mechanism, measured on the W6d matrix (84,553 rows): **QB's fitted correlation is mostly "did he
play", not "how did he play".**

| pos | all-zero rows | ρ̄ all rows | ρ̄ played-only | ratio | PIT (`joint_rank`) |
|---|---|---|---|---|---|
| QB | 53.9% | 0.239 | 0.127 | **1.88×** | 0.065 ✗ |
| RB | 35.2% | 0.189 | 0.143 | 1.32× | 0.025 ✓ |
| WR | 32.9% | 0.126 | 0.102 | 1.23× | 0.017 ✓ |
| TE | 42.4% | 0.127 | 0.111 | 1.14× | 0.020 ✓ |

⭐ **The RATIO orders the failure; the SIZE of the zero atom does not.** RB carries the largest
joint-zero excess over independence (17.6× vs QB's 11.0×) and passes comfortably. What breaks
calibration is the distance between the MARGINAL dependence and the CONDITIONAL-ON-PLAYING
dependence — one Gaussian copula is being asked to carry a binary availability factor and a
within-game co-movement at once, and it fits a compromise between them. A Gaussian copula also has
**zero tail dependence by construction**, so at ρ̂ ≈ 0.24 it cannot reproduce a 53.9% joint-zero
atom at all.

That single mechanism explains the whole QB table: `assembled_comonotone` has the BEST PIT (0.0563)
because perfect dependence is a crude availability factor — every leg goes to zero together — and
the WORST CRPS (2.6954) because it destroys the within-game structure. `joint_double` compensates
the attenuation enough to win CRPS while doubling noise and signs indiscriminately, so its
calibration degrades. **CRPS and PIT rank almost inversely at QB and nowhere else.**

**SUCCESSOR (not run here):** an explicit availability mixture — Bernoulli(plays) × a
conditional-on-playing joint draw — with Σ estimated on played rows only. ⚠️ **NF-W4 already tested
an availability mixture and returned a null ×4**, so this is not a free win; NF-W4's target was
per-stat availability, and no prior story measured the ASSEMBLED total's joint-zero atom, which is
the specific claim here. A legitimate successor registers a fresh coherent family (MH2 (a)) —
⛔ never a re-run of this field.

### 11.2 Instrumentation gap: a calibration statistic that discards its own direction

The record stores only `max_decile_dev` — not the decile vector, not WHICH decile is off — and the
PITs themselves are not stored, so the direction of miscalibration is **not recoverable without
another run**. §11.1's mechanism was inferred from the arm ORDERING plus the raw matrix, not from
the PIT shape. Storing ten floats per label per fold would have answered it directly. Any successor
touching calibration should carry the decile vector.

### 11.3 The assembly's value is POSITION-DEPENDENT — an architectural finding

`foil_direct_points` (a learner pointed straight at league points) BEATS the assembly at QB
(−0.0025) and RB (−0.0589) and LOSES at WR (+0.0173) and TE (+0.0257). The sign split falls exactly
at the availability-ratio boundary in §11.1 (RB 1.32 / WR 1.23), which suggests the same
availability contamination that breaks calibration also decides where assembling from parts is
worth doing. ⚠️ **SUGGESTIVE ONLY at n = 4 positions** — QB and RB swap order on margin, so this is
a hypothesis for a successor to register, not a finding of this story.

### 11.4 What the nulls do and do not say

⭐ `classify_null` names the FOIL, not the HYPOTHESIS. QB/RB's `GENUINE_ABSENCE` answers "does
assembling from per-stat parts beat modelling the total directly?" — **NOT** "does cross-stat
dependence help?". On the story's own mechanism all three dependence clauses pass at **all four**
positions, and the assembly beats independent draws by +0.0565 to +0.1051 CRPS while lifting
coverage from 0.738–0.797 to 0.813–0.886. Reading these nulls as "dependence is dead at QB/RB"
inverts the result. (Sixth hand-correction of this classifier's phrasing in the vertical — the
carded instrument fix inherits this shape.)
