# NF-D20 — PRE-REGISTRATION (committed BEFORE the run)

**Story:** in-fold GLOBAL-SHRINK selection of NF-D16's ratified rookie-point recalibration, under a
PER-FOLD whole-board placement constraint. The only legitimate publish path NF-D18 left open.

**Committed:** this document and `rookie_shrink_selection.py` are committed in their own commit,
before `run_nf_d20_infold_shrink.py` exists and before any λ has been swept. The module is the SINGLE
OWNER of every constant; this document exists so the registration has a git timestamp that precedes
the result rather than only a docstring that could have been edited alongside it.

---

## ⛔ The one thing this story may not do

NF-D18 measured that the placement cap admits a global shrink of NF-D16's affine up to a specific λ,
**read off the 2026 board with the answer already in view**, and refused to take it. Pre-registering
that number now would be reverse-engineering wearing a pre-registration's clothes (the E2.1-r
inversion in a successor's badge).

⇒ **No arm in this story is fitted, tuned, filtered or selected on the 2026 board, and no rule may
default to or prefer NF-D18's frontier value.** Every λ is a deterministic function of held-out draft
classes and the merged veteran+rookie boards of PRIOR seasons only. The 2026 board is read exactly
once, at the end, as NF1.4's ordinary serving-time face-validity check applied to an arm whose λ was
already fixed without it.

## The family, and why the field is RULES rather than λ values

A field of fixed λ values would make λ a knob and the winner a re-pick of NF-D16's selected shrink.
A field of RULES makes each arm a deterministic function of in-fold data: no human chooses a λ at any
point.

| arm | what it is |
|---|---|
| `incumbent (NULL)` | λ ≡ 0 — the rookie point AS SERVED TODAY (NF-D16's flip is off). It can win. |
| `infold_all_boards` | in-fold-metric-optimal λ among those admissible (C2) on **every** prior season's merged board |
| `infold_last_board` | same, but admissibility required only on the **most recent** prior board |
| `unconstrained (λ=1)` | NF-D16's ratified affine at full strength — the REFERENCE, carried SHIPPABLE so the constraint has something to REFUSE |
| `blind_half (λ=0.5)` | ⛔ MATCHED FOIL, non-shippable — a constant shrink with **no board information at all** (the blind midpoint of the registered interval). Separates "the in-fold board evidence earned the selection" from "any mid-strength shrink would have done." Excluded from the eligible set, from PBO's search and from the DSR trial field (MH2 (a)). |

## λ grid — inherited by import

`LAMBDA_GRID = (0.0,) + rookie_point_recalibration.SHRINK_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)`.

This is **NF-D16's own pre-registered shrink grid**, written before any constraint result existed and
scored end-to-end by the story that ratified the correction. Inheriting it is what stops the grid from
becoming a place to hide a choice. The finer 0.05 grid is computed as a **disclosed sensitivity only**.

## Constraints — both binding on ELIGIBILITY

**C1 · do no ordering harm** — NF1.4's `ORDERING_DO_NO_HARM = 0.02` on within-position rank
correlation, **per position**, never a pooled mean. Inherited verbatim by import.

**C2 · the per-fold placement constraint** — on a merged board `S`, a shrink λ is ADMISSIBLE iff

```
rank_λ(S)  ≥  min( STRICT_CAP , rank_incumbent(S) )
```

`STRICT_CAP` is NF-D17's THRESHOLD-INVARIANT cap — the strictest of the entire Q05–Q25 band **and**
reality's observed minimum realized rank, i.e. the same terms on which the VETO held. Delegated to
`season_projection.rookie_placement_breach` through NF-D18's `placement_clearance`. **No new
threshold and no new reference are introduced**, because clearing only at a cap one would pick after
seeing the result is the E2.1-r inversion facing the other way.

⚠️ **Why the second term is there, disclosed in advance.** The incumbent's own emitted boards do not
all clear the cap — the served 2021 board places its top rookie at overall rank 10, inside the band.
That is a property of the SHIPPED PRODUCT, measured before any candidate in this field was scored.
Without the second term the constraint would refuse **every** λ on such a board including λ = 0, i.e.
it would refuse the null itself, and a constraint that refuses everything has examined nothing
(NF1.7 (a)). The clause as written governs the CHANGE: never place the top rookie better than the
validated cap admits, and never make a pre-existing breach WORSE. It reduces to the plain NF-D17 cap
on every board the incumbent already clears. **The strict reading (bare cap, no second term) is
computed and reported as a sensitivity; it is never selected on.**

⚠️ **C2 is evaluated OUT-OF-SAMPLE.** An arm is eligible only if the λ its rule chose from data
strictly BEFORE each held-out fold ALSO satisfies C2 on that fold's OWN board — the board the rule
never saw. That is the question that decides a publish: *does an in-fold-selected shrink still clear
the cap on the NEXT board?*

## Metric · framing · deflation — inherited, not re-chosen

- **metric** — NF1.4's `tier_mae`, imported. Grading the fourth change to ONE product on a new metric
  is metric-shopping.
- **framing** — POOLED, inherited from NF-D16 through NF-D18. The ship unit is one change to
  `project_rookies` at RB/TE/WR together or not at all. The per-position reading is a DISCLOSURE.
- **deflation** — whole-field DSR ≥ 0.95 **binds**; PBO < 0.2; α = 0.10 single-hypothesis. All three
  inherited BY IMPORT from `rookie_point_recalibration` so the bar cannot drift between the story that
  ratified the correction and the story trying to publish it. Sensitivities at DSR ≥ 0 and with the
  DSR removed are reported.

## Anchors — two-sided, and the degenerate does double duty

`oracle_perplayer` (floor) · `oracle_ols` (peeking ceiling at MATCHED FAMILY — every arm is a λ-blend
of a per-position affine with the identity, which is itself a per-position affine, so this field is
ONE family and one ceiling is correct) · `permuted_across` (must lose) · `permuted_within`
(**pre-registered to be BEATEN**: NF-D16 measured it vacuous for a pure LEVEL and NF-D18 measured it
biting for a SHAPE; NF-D16's ratified winner carries a SLOPE, so it acts here) · `zero_scale`
(degenerate — must LOSE the metric while SATISFYING C2 trivially, which is what proves the placement
clause is a CONSTRAINT and not a promoted CRITERION) · `pos_median` (MAE-collapse tell) · `over_scale`
(λ = 2 — **must lose the metric AND breach C2**, so the constraint is measured having teeth rather
than merely being described as strict).

## Empty-evidence default

The merged boards begin at 2019, so the first held-out class has no prior board and its rules have no
constraint evidence. `EMPTY_EVIDENCE_LAMBDA = 0.0`: with nothing to verify against, a rule applies NO
correction — a check that did not run is not a check that passed (NF1.7 (a)).

## What ships, and what does not

**SHIP** iff an in-fold-selected shrink (a) beats the incumbent on `tier_mae` under the pooled
framing, (b) does no ordering harm at every scaled position, (c) satisfies C2 **out of sample on every
held-out fold's own board**, (d) clears PBO/DSR/α, and (e) passes NF1.4's serving-time face-validity
check on the 2026 board with its λ already fixed. Then NF-D16 publishes AT THAT SHRINK.

**ELSE** a FINAL recorded null closing NF-D16 unpublished — classified `CONSTRAINT_REFUSED` (NF-D18's
8th null state) wherever the deterministic board rank rather than the metric is what refused the arm.
⛔ Never a "+N draft classes" re-test trigger for a deterministic constraint: no number of additional
seasons can move a board rank.

> ⚖️ Edge-independent, `best_alpha = 0`. QB excluded by pre-registration (inherited through NF-D16
> from NF-D14), proven untouched on emitted projections rather than asserted. The rookie INTERVAL's
> WIDTH model is untouched; a shipped shrink moves the band's CENTRE, so a ship requires
> `run_interval_revalidation` re-run with every coverage floor re-confirmed.
