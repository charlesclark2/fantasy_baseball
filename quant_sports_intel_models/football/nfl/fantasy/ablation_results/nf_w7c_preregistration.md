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
- **ANCHORS:** `permuted_direct`; and **per-form** oracle + matched-n controls for every arm and
  foil. ⭐ Per-FORM is load-bearing: the joint forms NEST one another (Σ=I ⊂ one-factor ⊂ full), so
  a single field-wide ceiling would veto a legitimately-better nested form as a false metric
  inversion (NF-D16 (g‴)).

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
