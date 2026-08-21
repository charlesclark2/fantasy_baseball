# NF-W8-0e — pre-registration: the QB | `passing_yards` CELL, zero-mass × conditional-level (the 2×2)

Registered 2026-08-20 (branch `nf-w8-0e`), **BEFORE any scoring run**. Committed ahead of the path
proof and the decisive run; nothing in §1–§11 may be re-read after a result lands (E2.1-r).
Post-run findings go in §13, appended — never edited into the registration.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger · research-only. Nothing
serves, nothing publishes, nothing retrains, and **this story writes NO optimizer input and NO
served per-stat cell** (§11). NF-W8-0b's shipped input and the NF-W6c/W6d served substrate stand
untouched.

Registered forward by **NF-W8-0c §12.6(1)**: *"The substrate (the strongest lead). §12.1 localises
93% of the model channel to QB | `passing_yards`'s conditional level — a per-stat NF-W6d cell, the
same layer NF-W7d/NF-W7f found binding at QB. A fix there is a **marginal-layer** fix carrying a
per-stat re-certification cost, not an assembly-layer patch."*

---

## §1 What the predecessors established (PINS — recorded figures, never re-derived here)

| fact | figure | source |
|---|---|---|
| the assembled QB ranking point reads BELOW realized | **−0.4237 PPR** (row-pooled, tail-completed) | NF-W8-0c §12.1 |
| the identity splits it: READ +0.0039 · MODEL **−0.4276** | availability −0.0182 / conditional **−0.4094** | NF-W8-0c family A |
| ONE leg carries it | `passing_yards` **−0.3975** of −0.4276 = **93%**; its own split is availability −0.0097 / conditional **−0.3878** | NF-W8-0c family A |
| `passing_yards` is the only leg above the 0.05 PPR materiality floor | next largest `passing_tds` **+0.0274** | NF-W8-0c family A |
| the same cell, from the CALIBRATION side | served cell predicted `P(0)` **0.2983** vs realized **0.5563** | NF-W7f |
| the `zm_floor` re-splice moves that cell to | **0.5461** (gap after **+0.0102**) | NF-W7f |
| the assembled QB is the ONLY PIT-clearing QB distribution on record | `zm_floor` max-decile-dev **0.0281**, clears the 0.05 bar **8/8**; `direct_points` clears it **0/8** (0.0959) | NF-W7f |
| the surviving cross-position contrasts under the served QB point | QB\|WR **−0.3621** (MDE 0.2036) · QB\|TE **−0.3106** (MDE 0.1903) | NF-W8-0b / NF-W8-0c |
| the TAIL lever is closed deterministically | bounded at **0.0193 PPR** — ~19× short | NF-W8-0b §12.1, re-closed by NF-W8-0c §12.2 |
| two mechanism halves that each move a metric are **NOT additive** | measured 2×2, ratios 0.43–0.59 on the split channel | NF-W7e |
| a bundled null is not a verdict on either half | the availability SPLIT pays 4/4 while the played-rows Σ costs 4/4, inside a net null | NF-W7d |

⛔ **NF-W8-0, NF-W8-0b, NF-W8-0c, NF-W8-0d, NF-W7f are DECIDED.** They are not re-run, re-derived
or re-read by this story; their per-fold figures enter only as REPRODUCTION PINS (§9), and this
story is refused at import if it would write any of their artifact paths.

### §1.1 The tension this story exists to resolve, stated before it is measured

Two unrelated instruments named the same cell from opposite sides. From the LEVEL side (NF-W8-0c)
the cell's conditional (played-and-positive) level is too LOW. From the CALIBRATION side (NF-W7f)
the cell under-prices its own zero atom, and raising that atom LOWERS the marginal mean. The two
corrections plausibly push the cell's level in OPPOSITE directions.

That is not a contradiction — the conditional shortfall is large enough to swamp an under-weighted
atom — but **NF-W7e proved that fixing one and then the other is the single most likely way to burn
two stories and land back here.** So the two mechanisms are registered JOINTLY and the 2×2 is
measured, and **the INTERACTION is the read**, never the two marginals.

---

## §2 Layer, and why it does not inherit the `dsr_ok` wall

This story operates at the **MARGINAL / per-stat (NF-W6d) layer** — one 199-level cell bank,
`QB | passing_yards` — not at the cross-position assembly layer. NF-W8-0c's and NF-W8-0d's
`DSR_UNREACHABLE` reading is a property of **that** field (4 assembly-layer re-level arms scored on
a paired assembled-level statistic); it is not inherited, because this is a different field, a
different statistic and a different declared family. ⛔ Equally, this story does **not** get to
claim the reverse: NF-W8-0d's LOCKSTEP invariant (a shared proportional variance lever cannot flip
the sign of `SR − SR0`) applies to ANY common-random-number field, including this one, so if
`dsr_ok` fails here the lockstep reading is computed and reported rather than a "lower-variance
design" trigger being published (NF-W8-0d §1, R2).

---

## §3 The pinned inputs (nothing here is selected in this story)

- **Fold axis** — NF-W7c's, verbatim: 8 expanding-window half-season folds 2022H1…2025H2 on the
  W6d matrix; gate league `full_ppr`; target for the assembled read `league_fantasy_points`; draws
  `FA.ASSEMBLY_DRAWS = 4000`; seeds inherited (`SA._SEED` + `AVAIL_STREAM_OFFSET`) so the
  reproduction pins can hit at 1e-9.
- **The incumbent CELL** — the SERVED `QB|passing_yards` bank, built by the serving dispatch
  `stat_distribution_serving_d.serve_banks` through the map read from the NF-W6d records (form
  `lgbm_quantile_tail`, source `nf_w6b`). ⛔ Not re-fitted, not re-selected, not re-typed here.
- **The incumbent ASSEMBLY** — `run_nf_w8_0_cross_position.build_position_banks`, the predecessors'
  ONE code path, driven through NF-W8-0b's DECIDED point reader `fp_tail_point.tail_completed_point`.
  QB's consumed generator is `zm_floor` (Option B); RB `direct_points`; WR `mixall_learned`; TE
  `single_copula` — `fp_cross_position.CONSUMED_GENERATOR_OF`, imported.
- **The zero-mass transform** — `fp_qb_marginal_calibration.resplice_zero_mass` and
  `fp_qb_marginal_calibration.zero_targets("zm_floor", …)`, imported BY IDENTITY. ⛔ No second
  implementation of the re-splice exists in this story (NF-C0e wrong-key class); the module is
  guard-tested to hold pointers, not copies.
- **The cell reducer** — `efficiency_marginals.score_bank`, the ONE reducer (refuses a non-finite
  predictive — NF-W3 (b)). Cell PIT is `kdst_weekly.randomized_pit_from_bank` →
  `fp_availability_mixture.pit_detail`, the same statistic NF-W7c/W7e/W7f gate on.
- **Gate constants — every one INHERITED BY REFERENCE, un-relaxed (E2.1-r):** assembled PIT bar
  `FA.PIT_MAX_DECILE_DEV = 0.05` · `WP.PBO_MAX` · `WP.DSR_MIN = 0.95` · `WP.FDR_Q = 0.10` ·
  `WP.COVERAGE_FLOOR` / `WP.COVERAGE_BLOCK_SE` · `XP.BH_Q = 0.10` · `XP.ALPHA = 0.05` ·
  `XP.MIN_PRIOR_ROWS = 50` · `SDC.TIE_EPS_CRPS = 1e-4` · reproduction tolerance **1e-9**.
- **NF-W7c's, NF-W7f's and NF-W8-0b's promote blockers, and the QB Option-B caveat, are INHERITED
  IN FULL.** This story re-certifies nothing.

---

## §4 The two mechanisms (defined before either is scored)

Both act on ONE leg (`passing_yards`, `FA.LEGS` index 1, a CONTINUOUS leg whose draw-path zero
threshold is exactly 0.0) of the (n, 13, 199) served bank tensor. Every other leg is a **byte-exact
no-op**, and that is a MEASURED clause (§7 `other_legs_untouched`), never an assumption.

**Z — the zero-mass recalibration (NF-W7f's mechanism, leg-scoped).**
`t_row = max(leg_zero_mass(bank), 1 − π̂_row)` for `passing_yards`, and `t = leg_zero_mass(bank)`
(a no-op by the RAISE-ONLY rule) on all twelve other legs; then `QM.resplice_zero_mass`. π̂ is
NF-W7d's learned estimator `QM.PI_ESTIMATOR`, fitted on TRAIN. The transform re-weights the atom
and leaves the conditional-on-positive law EXACTLY unchanged; its three identities
(`zero_mass_hits_target`, `positive_law_preserved`, `matched_foil_identity`) are re-measured here,
not inherited on trust.

**C — the conditional-level correction (this story's mechanism).**
Acting on the SAME leg's conditional-on-positive quantile function
`Q_cond(c) = Q(p̂ + (1 − p̂)·c)` — read through `QM.conditional_quantiles`, the PUBLIC reader, so
the correction never consults a transform's internals — in one of two DECLARED forms:

- `shift` (the pre-registered PRIMARY form): `Q_cond ↦ max(Q_cond + δ, 0)`;
- `scale` (the declared alternative form): `Q_cond ↦ max(κ · Q_cond, 0)`.

Levels at or below the bank's own measured atom are LEFT AT THEIR ORIGINAL VALUES — the identical
rule `resplice_zero_mass` documents and the identical reason (flattening a sub-threshold knot
changes the interpolation ramp into the first positive knot and flips draws 1 → 0). The result is
re-sorted so the bank stays monotone.

**Order.** Z is applied FIRST, then C. ⭐ The two are expected to COMMUTE on the bank up to grid
resolution (Z preserves the conditional law exactly; C moves only positive knots, so it cannot move
a continuous leg's atom) — that is registered as a MEASURED diagnostic
(`z_and_c_commute_on_the_bank`, tolerance 1e-9 in the drawn total), stated FORWARD so a near-tie is
not presented as a passed test (NF-D16 sibling (1)). ⛔ Commuting on the OBJECT does not make the
mechanisms additive on the METRIC — CRPS is not linear in the bank, and the fitted magnitude of C
genuinely depends on whether Z is on (§4.1). That is exactly the question.

### §4.1 Fitting — PRIOR folds' OOF rows only, and refitted INSIDE each 2×2 cell

Every parameter is fitted on the pooled OOF sums of STRICTLY PRIOR folds (`XP.MIN_PRIOR_ROWS = 50`
floor; below it the arm is IDENTITY and RECORDED, never silently defaulted — NF1.7 (a)). Fold 1 is
therefore identity for every arm BY REGISTRATION, which is why the path proof runs two folds.

⭐ **δ and κ are refitted separately in the Z-on and Z-off columns**, each against the bank that
column actually produces. This is deliberate and is the substantive non-additivity the story is
about: raising the atom lowers the marginal mean, so the conditional correction a Z-on cell needs
is not the one a Z-off cell needs. A single δ carried across the columns would measure the
ordering, not the mechanisms.

Estimators (moment matching, the NF-W8-0c `fit_arm_params` pattern at the cell layer):

- `δ = ȳ⁺_prior − m̄_cond_prior` where `ȳ⁺_prior` is the realized mean over PRIOR-fold rows with
  `y > 0` and `m̄_cond_prior` is the mean over ALL prior-fold rows of that row's model conditional
  grid mean under the SAME Z setting;
- `κ = ȳ⁺_prior / m̄_cond_prior`, INELIGIBLE outside the band `[QB.MIN_SCALE, QB.MAX_SCALE]` =
  [0.5, 2.0] and INELIGIBLE outright at `κ ≤ 0` (a negative scale inverts the leg — NF-D16).

---

## §5 The declared field (⛔ never trimmed or grown after a score — MH2/MH2.2)

The field is the 2 × 3 grid `{Z: off, on} × {C: none, shift, scale}`. The (off, none) cell is the
INCUMBENT. **Five real arms; `declared_field_size = 5`**, committed here before any score.

| arm | Z | C | role |
|---|---|---|---|
| `identity` | off | none | the SERVED cell — incumbent and binding foil |
| `zm_only` | **on** | none | NF-W7f's mechanism alone, leg-scoped |
| `cond_shift` | off | shift | NF-W8-0c's mechanism alone, PRIMARY form |
| `joint_shift` | **on** | shift | ⭐ the 2×2's fourth cell — the story's primary arm |
| `cond_scale` | off | scale | the declared alternative form |
| `joint_scale` | **on** | scale | the alternative form's joint cell |

The family is COHERENT by construction: every arm is a recalibration of ONE cell's quantile bank
driven by TRAIN-side moments — no learner, no refit, no new feature, and no far-out arm to inflate
the cross-trial dispersion (the MH2.5 / NF-W6b-C `V`-inflation mechanism, avoided by DESIGN rather
than by a post-hoc trim). Trials = the 5 real arms; the PBO eligible set = incumbent + 5.

⛔ **`leg_scale` is NOT re-registered.** NF-W8-0c records it carrying 77% of the flip mass and the
smallest pooled bias, and NF-W8-0c §12.6(3) leaves its form open to a fresh registration — but it
re-levels EVERY certified per-stat marginal to buy an assembled level, and it does not address the
cell this story is about. It is out of scope here by declaration, not by result.

### §5.1 Anchors — SCORED every run, NEVER trials (excluded from `V` and from the PBO field)

| anchor | what it is | registered to |
|---|---|---|
| `oracle_<arm>` (one per FORM — NF-D16 (g‴)) | the SAME form with its parameter fitted on the TEST fold (Z's oracle uses the test fold's own realized zero rate) | WIN — a floor its arm must not beat |
| `matched_n_<arm>` (one per FORM — NF1.9 (f)) | the SAME form fitted on the most recent TRAIN rows sized to the peek's effective n (= the test block) | bracket the oracle at matched capacity |
| `over_joint_shift` | `δ × QB.OVER_SCALE = 2` | **LOSE** — a magnitude hypothesis, SCORED not reasoned about (NF-D20 / NF-D14 (g′)) |
| `reverse_joint_shift` | `δ × (−1)` — the correction applied backwards | **LOSE** — brackets the magnitude from the OTHER side, so the metric is shown to respond to DIRECTION and not only to size |
| `permuted_shift` | δ fitted on prior-fold rows whose realized labels are permuted within fold | ⭐ **an EXPECTED EXACT TIE, declared FORWARD** — see §5.2 |
| `climatology_bank` | prior-fold realized `passing_yards` empirical quantiles, row-blind | LOSE |
| `nihilist_zero`, `zero_width`, `max_width` | `EM.anchor_nihilist` / `anchor_zero_width` / `anchor_max_width`, by identity | LOSE (two-sided sharpness — NF1.7 (d) (3)) |

### §5.2 ⭐ The permutation anchor is registered as INACTIVE, in advance

δ and κ are POOLED SCALARS. Permuting realized labels within a fold leaves every pooled moment
unchanged, so `permuted_shift` is **byte-identical to its arm by construction**. Registering it as
a passed test would be exactly the NF-D16 sibling defect ("a PERMUTATION anchor is near-vacuous
against a LEVEL/marginal hypothesis — register it as an expected TIE in advance and prove it, don't
present the near-tie as a passed test"). So:

- it is SCORED every run and its tie is ASSERTED (`permutation_is_inactive`, gap ≤ 1e-9);
- ⛔ it **does not enter** the `permutation_behaves` gate clause, because a mechanism that cannot
  act cannot supply evidence (NF-D20). The discriminating anchors here are the two-sided magnitude
  bracket, the degenerates and the per-form oracle floors.

---

## §6 The 2×2 read (the story's primary deliverable — NF-W7e)

On the cell's `crps_q199`, per fold, on the SAME rows (paired):

```
Δ_Z     = CRPS(identity)   − CRPS(zm_only)
Δ_C     = CRPS(identity)   − CRPS(cond_shift)
Δ_joint = CRPS(identity)   − CRPS(joint_shift)
interaction = Δ_joint − (Δ_Z + Δ_C)
```

The same square is computed on the cell's LEVEL (marginal grid-mean minus realized mean) and,
separately, on the `scale` column. Each quantity gets a paired CI95 over folds
(`GE.paired_ci95`) and a one-sided paired p.

**Interaction state (fixed in advance):**

- `ADDITIVE` — the interaction CI95 covers 0;
- `SUB_ADDITIVE` — CI95 wholly below 0 (the halves overlap: together they buy less than the sum);
- `SUPER_ADDITIVE` — CI95 wholly above 0;
- `UNDEFINED` — fewer than 2 evaluable folds, or any cell of the square unevaluable.

⛔ The 2×2 is a MEASUREMENT and gates nothing on its own. The selection is §7's.

---

## §7 Selection and the clause battery (fixed in advance)

**Ranked on** the cell's `crps_q199`, mean over folds, among the 5 real arms. **PIT flatness gates,
never ranks** (NF-W7c: a degenerate posted the best PIT and the worst CRPS — a criterion a
degenerate wins is fatal, NF1.8). Binding foil = `identity` (the served cell).

| # | clause | measured |
|---|---|---|
| 1 | `beats_foil` | mean paired Δ vs `identity` > 0 |
| 2 | `not_a_foil_tie` | mean Δ > `TIE_EPS_CRPS` (1e-4) — a nested form collapsing onto its foil is a TIE, never a win (Batter-Props Ph2) |
| 3 | `fold_consistency` | `cv_power.fold_consistency_clause(n_folds)` — the calibrated count, not a bare 60% |
| 4 | `pbo_ok` | PBO < `WP.PBO_MAX` over the ELIGIBLE set |
| 5 | `dsr_ok` | DSR ≥ `WP.DSR_MIN` = 0.95, `V` measured over the 5 real arms (no degenerate is ever a trial — MH2.1 (a)) |
| 6 | `fdr_ok` | BH at `WP.FDR_Q` over the two declared C-form contrasts (shift, scale) |
| 7 | `coverage_floor_ok` | the cell's coverage(80) shortfall vs `WP.COVERAGE_FLOOR` within `COVERAGE_BLOCK_SE` binomial SE — a FLOOR, never a target (NF1.8) |
| 8 | `cell_pit_not_degraded` | the winner's cell max-decile-dev ≤ the INCUMBENT cell's. ⭐ A NO-HARM clause against the served cell, **not** an imported bar: NF-W6d's 0.03 was registered for Phase-C DEFAULTS, and importing it as a gate here would be inventing a bar this cell was never held to (E2.1-r). The 0.03 figure is REPORTED beside it as disclosure. |
| 9 | ⭐ `assembled_pit_preserved` | the ASSEMBLED QB distribution under the winner clears `FA.PIT_MAX_DECILE_DEV = 0.05` on **every evaluable fold** — the same 8/8 basis NF-W7f's `zm_floor` clears it on. *The assembly is the only PIT-clearing QB distribution on record; a cell fix that breaks its calibration is DISQUALIFIED.* |
| 10 | ⭐ `assembled_crps_no_harm` | mean paired assembled-QB `crps_q199` delta (incumbent − winner) ≥ 0 |
| 11 | `degenerates_lose` | `nihilist_zero`, `zero_width`, `max_width`, `climatology_bank` all lose the cell CRPS |
| 12 | `magnitude_anchors_lose` | BOTH `over_joint_shift` and `reverse_joint_shift` lose to the winner |
| 13 | `winner_own_form_floor` | the winner's OWN form's peeking oracle beats that form's matched-n control (NF-D16 (g‴) / NF1.9 (f)). ⚠️ A TIE here is INACTIVE, not a refusal (NF-W6d) — an inactive pair is recorded as such and cannot supply a pass either. |
| 14 | `transform_identities_hold` | `zero_mass_hits_target` · `positive_law_preserved` · `matched_foil_identity` · `other_legs_untouched` · `atom_unmoved_by_C` |
| 15 | `incumbent_reproduces` | §9 |

Clause classes for the null: **statistical** = 1, 3, 4, 5, 6. **constraint** = 7, 9, 10.
**anchor/registration** = 2, 8, 11, 12, 13, 14, 15. A null resting only on constraint/anchor
clauses classifies `CONSTRAINT_REFUSED` and publishes **no** fold/season trigger (NF-D18). A
statistical null goes to `cv_power.classify_null(declared_field_size=5, degenerates_excluded_from_v=True)`
and the machine flag `field_remedy_admissible` is read, never the prose (guide §0.5.4 rules 5/5b).
If `dsr_ok` fails, the NF-W8-0d LOCKSTEP check (`sign(SR − SR0)` under proportional shrinkage) is
computed and reported so a void "lower-variance design" trigger is never published (NF-W8-0d R2).

---

## §8 Family D — the DOWNSTREAM verification (the point of the story)

Under the §7 winner's corrected cell, the FULL cross-position read is re-run through
`XP.pairwise_gap_tests` — one implementation (E9.61), the same statistic NF-W8-0/0b/0c used — on
the per-fold biases of the four consumed generators' ranking points. Reported for `identity` and
for the winner:

- the six pairwise contrasts, their BH-FDR verdicts and their per-pair MDEs;
- `gap_detected`, and specifically whether **QB|WR and QB|TE fall below their MDEs**;
- the QB level bias itself, row-pooled, and the §12.1 mechanism decomposition recomputed so the
  cell's own contribution can be read after the fix.

⛔ Family D's bar is INHERITED (`XP.BH_Q`, the MDE construction) and is not re-derived. It is a
VERIFICATION, not a second selection: no arm is chosen on it.

### §8.1 ⭐ A structural fact that must be MEASURED here, not assumed

The QB generator the cross-position read consumes is `zm_floor`, which **already applies the
zero-mass re-splice to all thirteen legs** — so the assembled incumbent already carries Z on
`passing_yards` (that is why NF-W8-0c's decomposition found the conditional level short by 0.3878
PPR *after* the atom correction). Under the RAISE-ONLY rule the re-splice is idempotent, so at the
ASSEMBLED layer the Z column is predicted to be a structural NO-OP and the assembled propagation is
predicted to depend on C alone.

That prediction is registered FORWARD and **measured**, not asserted: `assembly_z_column_inactive`
reports the per-fold assembled CRPS/point gap between `identity` and `zm_only` (predicted 0.0) and
between `cond_shift` and `joint_shift` (predicted 0.0). ⭐ Whichever way it reads, the ACTIVE-fold
count is reported beside every assembled comparison, because an inactive arm is UNINFORMATIVE and
never a pass (NF-D20).

---

## §9 Reproduction pins (hard clauses, all states; tolerance 1e-9, ⛔ no `round(…, 6)`)

| pin | reproduces |
|---|---|
| `incumbent_cell_is_the_served_cell` | the `identity` cell bank is byte-identical to `SDSD.serve_banks`' `QB|passing_yards` |
| `qb_assembly_matches_w7f` | the re-derived assembled QB incumbent's per-fold CRPS **and** PIT vs the NF-W7f record's `zm_floor` |
| `non_qb_bias_matches_w8_0b` | every position's per-fold identity bias on the tail-completed point vs the NF-W8-0b record |
| `w8_0c_leg_contribution` | the recomputed `passing_yards` leg contribution / conditional part vs NF-W8-0c's −0.3975 / −0.3878 |
| `resplice_is_the_certified_transform` | `fp_qb_passing_cell` holds POINTERS at `QM.resplice_zero_mass` / `QM.zero_targets` / `QM.conditional_quantiles`, not copies (guard, by identity) |

A pin that CANNOT be compared (an absent or smoke predecessor record) reports `reproduces: False`
with a note — a control that did not run is never a pass (NF1.7 (a)).

---

## §10 Runtime plan (the >2-min rule)

The decisive run is the 8-fold × 4-position build (NF-W8-0c measured 3109 s on the same axis), so
it is an **OPERATOR** run on the LAPTOP. In-session: a `--smoke` path proof on the last TWO folds
at 300 draws (two, not one — every arm is identity on the first fold BY REGISTRATION §4.1, so a
one-fold proof exercises no arm), plus a pure-module unit battery and a RED proof.
⚠️ Per-fold marginal banks are cached under `artifacts/nf_w7e_bank_cache/` — **gitignored, and
therefore ABSENT in a fresh worktree** (the NF-INFRA1 class): a first run in a new checkout pays the
full marginal fit. The decisive run must be launched from a checkout that also holds
`artifacts/nf_w6d_stat_matrix_<key>.parquet`, or it rebuilds the matrix from the lake.

---

## §11 What this story ships (registered now, so it cannot grow after a result)

**Nothing.** No served cell, no optimizer input, no registry edit, no publish, no deploy. In
particular: a §7 SHIP verdict is a statement that a corrected cell EXISTS and is certified on this
axis — it is **not** a re-serve of `QB|passing_yards`. Re-serving a NF-W6d cell is a separate,
deliberate step (it changes the certified substrate every assembled position reads) and it is a
SUCCESSOR's registration, never a side effect of this run. `cross_rankable` stays whatever
NF-W8-0c left it (`false`) unless family D says otherwise AND governance acts — this story records,
it does not flip a consumption flag.

---

## §12 Limitations (registered now, so they cannot become post-hoc rescues)

1. **One cell.** The other twelve legs are untouched by declaration. `passing_tds` (+0.0274) and
   every other leg sit below the 0.05 PPR materiality floor; a residual after this fix is a
   successor's question, not a rescue for this one.
2. **A LEVEL correction only.** Both forms move a level (additively or by a uniform scale). A
   rank-dependent, covariate-dependent or shape-dependent cell artifact is out of scope and stays a
   successor's fresh registration.
3. **The correction is ROW-BLIND** (a pooled scalar per fold). That is why §5.2's permutation
   anchor is inactive, and it bounds what a win can claim: the cell's LEVEL is corrected, not its
   per-player resolution.
4. **A cell fix carries a per-stat RE-CERTIFICATION cost.** `QB|passing_yards` is a certified
   NF-W6b SHIP cell; anything that changes it changes what every QB assembly reads. This story
   MEASURES the cell's own CRPS/PIT/coverage so that cost is priced, but it does not pay it.
5. **`cond_scale` / `joint_scale` re-level a certified marginal multiplicatively**; their measured
   marginal drift is disclosed with the result, and an admissible win under the scale form trades a
   per-stat certification scope for an assembled level.
6. **The gate league is `full_ppr`.** `passing_yards` is priced at +0.04 there; a league pricing it
   differently scales every PPR figure in this record and is not separately certified.
7. **Family D is a verification on 8 folds** with MDEs of ~0.19–0.20 PPR. "Below the MDE" means
   "no artifact larger than X", never "no artifact" (MH2.6).
8. **NF-W8-0d's answer (b) stands.** If `dsr_ok` fails here, that is a fact about THIS field, and
   the admissible remedy is a fresh coherent registration — ⛔ never a post-hoc trim of the five
   declared arms (MH2.2), and ⛔ never a re-read of NF-W8-0c's refusal.

---

## §12A BUILD-TIME AMENDMENTS (appended BEFORE any scoring run; §1–§12 untouched)

Three implementation decisions that §5.1 and §7 left under-specified. Each is committed here
**before the path proof and before any score**, and each moves in the direction that makes the gate
HARDER or the control MORE honest — never easier (E2.1-r).

**A1 — the matched-n control is the MOST RECENT PRIOR FOLD, not a train slice.** §5.1 wrote "the
most recent TRAIN rows sized to the peek's effective n". Two reasons that is the wrong sample and
this is the right one:

- the peek fits its scalar on the TEST block's rows, which are OUT-OF-SAMPLE for the marginal fit;
  TRAIN rows are IN-SAMPLE for it, so a train slice is capacity-MISmatched in the other direction
  and would flatter the control (the NF1.7 (b) "same-family AND same-sample" lesson);
- the most recent prior fold is one half-season (~685 rows) against a test block of ~687 — matched
  n to within ~0.3%, honestly out-of-sample, and it costs ZERO additional marginal fitting because
  its ledger already exists (a train slice would need a second `serve_banks` pass per fold and
  roughly double the decisive run).

⚠️ For fold 2 the most recent prior fold IS the whole prior set, so the control and the arm coincide
there by construction; that is recorded per fold, never averaged over silently.

**A2 — `fdr_ok` is BH over ALL FIVE real arms' contrasts, not two.** §7 clause 6 wrote "the two
declared C-form contrasts". Charging the multiplicity at the size of the field the selection
actually ran (5) rather than at 2 is what the §0.5 discipline requires ("count every config toward
PBO/DSR"), and it is STRICTLY STRICTER — it can only prevent a false ADD, never permit one. The
winner must be BH-rejected at `WP.FDR_Q` within that family of five.

**A3 — the `zm_only` peeking oracle's target.** `zm_only` has no fitted scalar of its own (its
target is NF-W7f's certified `zm_floor` rule), so "fit the parameter on the test fold" needs a
definition. Its ONE estimated input is **π̂**, so the same-form peek replaces π̂ with the TEST fold's
REALIZED activity indicator (`q_i = 1 − active_i`) inside that certified rule — the oracle differs
from its arm in exactly that estimate and in nothing else (NF-D16 (g‴): a peek must be the arm's
OWN form). ⛔ A first draft peeked the realized MARGINAL zero rate instead; that target is
ROW-BLIND, i.e. a DIFFERENT form, and the path proof showed it losing its own arm outright — a
false `ACTIVE_AND_VIOLATED` produced by the anchor's construction rather than by the arm. Its
control is the certified train-side π̂ rule (= the arm). The control is data-ADVANTAGED (full train
vs the test block), which is the CONSERVATIVE direction for an oracle floor: a peek that still wins
clears it a fortiori.

**A6 — the model side of δ/κ is PROBABILITY-WEIGHTED.** §4.1 wrote "the mean over ALL prior-fold
rows of that row's model conditional grid mean". That is the wrong population: the realized side
averages over the rows that WERE positive — disproportionately starters — while an unweighted mean
of per-row model conditional means carries every backup's much lower conditional law at full
weight. The two are then not the same quantity, and the difference is a SELECTION effect, not a
level defect. The model's own `E[Y | Y > 0]` is by definition
`Σ_i P̂_i(Y>0)·m_i / Σ_i P̂_i(Y>0)` with `P̂_i(Y>0) = 1 − p̂_i`, so that is what the ledger stores and
the fit divides. ⭐ MEASURED, not reasoned: the path proof's unweighted estimator over-shot the
cell's marginal level by ~3.5× and drove every C arm's assembled bias from −0.41 PPR to **+0.57**.
The unweighted reading is carried BESIDE the weighted one so the choice is auditable.

**A7 — an INACTIVE own-form oracle pair does NOT refuse.** §7 clause 13 already records NF-W6d's
refinement in prose ("a TIE here is INACTIVE, not a refusal"), but the first implementation returned
`passes: False` for it, which IS a refusal. NF-W6d killed three shippable arms on exactly that
reading. Corrected: `ACTIVE_AND_RESPECTED` and `INACTIVE` pass the clause; `ACTIVE_AND_VIOLATED`
(the floor is genuinely broken) and `UNDEFINED` (an absent read) both fail CLOSED. ⛔ An INACTIVE
pair is not a clean pass either — the verdict NAMES it, so the record says the floor could not act
rather than that it held.

**A4 — the estimator's MODEL side is the TAIL-COMPLETED conditional mean, not the grid mean.**
§4.1 wrote "that row's model conditional grid mean". NF-W8-0b DECIDED that a 199-level grid mean is
not `E[Y]` — it integrates 0.995 of the mass and drops the outer 0.5% — and the −0.3878 PPR
conditional channel this story is correcting is stated by NF-W8-0c **on the tail-completed point**.
An estimator built on the truncated grid mean would therefore target a slightly DIFFERENT quantity
than the one the record localised, and on a right-skewed yardage law it would under-state the model
side and inflate δ. So the model side is `fp_tail_point.tail_completed_point` applied to the
conditional quantile array — NF-W8-0b's decided reader, deterministic, already in this lineage.
⭐ BOTH readings are carried in the ledger and reported, so the choice is auditable rather than
asserted.

**A5 — δ is expected to be very nearly Z-INVARIANT, and that is a property of the transform, not a
failure of A1/§4.1.** `resplice_zero_mass` preserves the conditional-on-positive law EXACTLY, so a
CONDITIONAL-mean-matching correction sees almost the same model side in both Z columns (they differ
only by the grid's own resolution). Registered here so the near-equality is read as the construction
working, not as a fitting bug. ⭐ It does NOT make the mechanisms additive on the metric: with Z off
the atom is ~0.30 against a realized ~0.556, so a conditional-mean match leaves the MARGINAL level
badly over-stated, while with Z on the same δ lands it. **That coupling — the same parameter buying
a correct marginal level only when the atom is right — is precisely the interaction §6 measures**,
and it is why §5 registers the 2×2 rather than two sequential stories.

---

**A8 — the downstream cross-position read is computed under EVERY real arm, REPORT-ONLY.** §8
registered it "for `identity` and for the winner". Computing it for all six costs nothing (it is
pure arithmetic on already-stored per-fold biases) and it is the whole point of the story, so a
`CELL_NOT_CORRECTED` verdict still RECORDS what the downstream read would have said under each
candidate rather than leaving the question blank. ⛔ It is emphatically NOT a second selection:
`cell_verdict` reads the closure of the §7 winner and nothing else, and the report says so on the
table — promoting an arm that lost the registered contest because its downstream row looks better
would be the E2.1-r inversion in its most literal form.

---

## §12B PATH-PROOF OBSERVATIONS (2 folds, 300 draws — ⛔ NOT a result)

Recorded so §12A's amendments are auditable against what actually produced them, and so the
decisive run's operator knows which ❌s are structural. **Nothing here is a finding**: two folds at
300 draws, with every C arm identity on fold 1 BY REGISTRATION (§4.1), leaves exactly one usable
fold — so `beats_foil`, `fold_consistency`, `pbo_ok`, `dsr_ok` and `fdr_ok` are structurally
unreachable, and the reproduction pins compare against records built at 4000 draws and therefore
CANNOT hit. The 2×2's state is correctly `UNDEFINED` at n=2.

What the path proof DID establish, all of it about the harness rather than the question:

1. ⭐ **§8.1's prediction is confirmed, measured.** `identity` and `zm_only` produce a
   BYTE-IDENTICAL assembled QB bank — `0/2` active folds, max
   CRPS gap `0.0`. The consumed `zm_floor` generator already re-splices all
   thirteen legs and the re-splice is idempotent under the RAISE-ONLY rule, so at the ASSEMBLED
   layer the Z column is a structural no-op and the propagation depends on C alone.
2. ⭐ **The A6 defect was visible and is fixed.** Under the unweighted estimator every C arm drove
   the assembled QB bias from −0.41 PPR to **+0.57** — a ~3.5× over-correction produced by a
   SELECTION effect, not a level defect. Under the weighted estimator the same arms move the cell's
   own `passing_yards` channel from `-0.2832` PPR
   (`identity`) to `+0.0310` (`joint_shift`) and
   `+0.0072` (`joint_scale`), while `cond_shift` — the same
   correction with the atom left wrong — OVERSHOOTS to `+0.3840`.
3. **The registered coupling is visible in the direction §5/§12A A5 predicted.** On the one usable
   fold the primary square reads Δ_Z `-0.06487`, Δ_C
   `-7.37933`, Δ_joint `-0.67748` on the cell's CRPS —
   the joint arm costs a small fraction of what the conditional correction costs ALONE. ⛔ At one
   fold this is an anecdote with no interval; it is recorded as the shape the decisive run will
   either reproduce or refute, never as the finding.
4. **A3′ was found by its own anchor losing.** The first `oracle_zm_only` peeked the realized
   MARGINAL zero rate — row-BLIND, i.e. a different FORM — and lost its own arm outright, which the
   floor would have read as `ACTIVE_AND_VIOLATED`: a refusal manufactured by the anchor's
   construction rather than by the arm.
5. **Runtime.** 2 folds × 4 positions ≈ 65-85 s/fold on a WARM marginal-bank cache; ≈ 420 s/fold
   COLD. The decisive 8-fold run is therefore an OPERATOR run (§10).

---

---

## §13 POST-RUN FINDINGS (appended after the decisive run; §1–§12 untouched)

_Decisive run 2026-08-21T04:06:30Z · 8 folds × 4 positions · 4000 draws · 3182.1 s · artifacts
`nf_w8_0e_qb_passing_cell.{json,md}`. §1–§12 are the registration and are UNCHANGED; everything
below is a reading of stored per-fold scores._

### 13.1 Verdict

**`CELL_NOT_CORRECTED` · `cross_rankable: false`.** The CRPS-ranked winner is `zm_only`
(Δ `crps_q199` **−0.15482**, CI95 [−0.46137, +0.15174], 3/8 folds, p 0.8643) and it fails six of
the fifteen registered clauses — `beats_foil`, `not_a_foil_tie`, `fold_consistency`, `dsr_ok`,
`fdr_ok`, `cell_pit_not_degraded`. **The served `QB|passing_yards` cell STANDS and the NF-W8-0c
reading is unchanged.** Nothing is promoted, nothing is re-served, `best_alpha = 0`.

`cv_power.classify_null(declared_field_size=5, degenerates_excluded_from_v=True)` returns
**`GENUINE_ABSENCE`** with **`retest_trigger: null`** — the best arm loses ON AVERAGE, and the
NF-W8-0d lockstep reading is attached and **CLOSED**: `SR = −0.4222 ≤ SR0 = 0.9173`, so a shared
proportional variance lever maps `SR − SR0 ↦ (SR − SR0)/c` with its sign invariant. No row, fold or
draw count clears it ⇒ **no data trigger is published** (NF-D18), and the instrument's stock
"lower-variance design" remedy is VOID here rather than merely unmet.

### 13.2 ⭐ The interaction, and the mechanism behind it — the reason this was ONE story

The primary square is **SUPER_ADDITIVE**, and not marginally:

| quantity (CRPS, shift form) | mean | CI95 | folds won |
|---|---|---|---|
| Δ_Z (zero-mass alone) | −0.15482 | [−0.46137, +0.15174] | 3/8 |
| Δ_C (conditional level alone) | **−13.23693** | [−17.87689, −8.59698] | 0/8 |
| Δ_joint (both) | **−0.97468** | [−1.53138, −0.41798] | 0/8 |
| interaction | **+12.41707** | [+8.02400, +16.81013] | — |
| joint ÷ sum-of-halves | **0.0728** | — | — |

The conditional-level correction applied ALONE costs **13.6×** what it costs applied WITH the
zero-mass fix. The fitted parameters name the mechanism exactly, and only the 2×2 could produce
them — δ is refitted per Z column (§4.1), so the square carries both:

| Z column | model conditional mean (prior OOF) | realized positive-side mean | fitted δ | fitted κ |
|---|---|---|---|---|
| **Z ON** (atom re-spliced to ≈0.52) | 172.1 – 189.1 | 205.9 – 218.1 | **29.0 – 34.4** | 1.153 – 1.167 |
| **Z OFF** (atom left at ≈0.31) | 135.5 – 141.1 | 205.9 – 218.1 | **73.5 – 77.1** | 1.542 – 1.546 |

With the atom left wrong, ≈21 points of probability mass that belongs at zero sit inside the
"conditional" region and drag the model's conditional mean down ≈35 yards, so the δ needed to match
the realized positive-side mean is **≈2.4× too large** — and it is then applied to every
above-atom level, including the mass that should have been zero. That is the whole interaction.
**A sequential story would have measured Δ_C = −13.24 first and concluded the conditional-level
correction is catastrophic and must be abandoned — the wrong conclusion, off a correct number.**
This is the NF-W7e finding reproduced with an independent mechanism and a measured cause.

### 13.3 What the correction DOES do — and what it costs

Registered as REPORT-ONLY context (§12A A8); the §7 verdict reads none of it.

| arm | cell CRPS | cell PIT | cell level bias (yds) | pred P(0) | assembled CRPS | assembled PIT | assembled bias (PPR) |
|---|---|---|---|---|---|---|---|
| `identity` (served) | **30.699** | 0.0569 | −1.51 | 0.3100 | 2.56449 | 0.0281 | **−0.4233** |
| `zm_only` | 30.854 | 0.0643 | −11.06 | 0.5235 | 2.56449 | 0.0281 | −0.4233 |
| `cond_shift` | 43.936 | 0.0826 | +43.63 | 0.3083 | 2.62382 | 0.0377 | +0.8253 |
| `joint_shift` | 31.674 | **0.0389** | +3.52 | 0.4955 | **2.56401** | 0.0255 | **+0.1179** |
| `joint_scale` | 32.151 | 0.0434 | +2.97 | 0.4960 | 2.56521 | **0.0239** | **+0.0971** |

Realized cell `P(0)` pooled **0.5497** (NF-W7f recorded 0.5563 against a served 0.2983).

Three measured facts, each stated as a fact and none of them a selection:

1. **The diagnosis is CONFIRMED at the cell.** Even with the atom corrected, the model's conditional
   mean runs **≈33 yards low** against the realized positive-side mean, every fold. That is
   NF-W8-0c's conditional-level defect observed directly in the cell it localised it to.
2. **The joint arms close the downstream gap.** Assembled QB level bias moves from
   **−0.4233, CI95 [−0.6033, −0.2433] — excluding zero** — to **+0.1179, CI95 [−0.0727, +0.3084]**
   (`joint_shift`) and **+0.0971, CI95 [−0.1031, +0.2973]** (`joint_scale`), both **containing
   zero**. Family D agrees independently: under both joint arms `gap_detected` is **False**, QB|WR
   and QB|TE fall **below their MDEs**, and **nothing is BH-rejected**. The conditional-only arms
   **overshoot decisively** (+0.83 / +1.15 PPR, CIs excluding zero) — the coupling again.
3. **The cell-CRPS cost does NOT propagate.** `joint_shift` loses **0.975 CRPS at the cell**
   (0/8 folds, CI excluding zero) while the assembled QB total is a **statistical tie**:
   identity − `joint_shift` = **+0.00048**, CI95 [−0.01154, +0.01251], joint better in 5/8 folds.
   Assembled PIT is a favourable tie (+0.00265, CI95 [−0.00430, +0.00959]) and every arm clears the
   0.05 bar on 8/8 folds, so the registered `assembled_pit_preserved` and `assembled_crps_no_harm`
   constraints both HOLD.

⛔ **These three do not add up to "the gate was wrong."** The registered primary is the CELL's
`crps_q199` (§5, §7) because this is a per-stat cell story, the cost on it is decisive rather than
noisy, and **re-reading this field on a different primary now — after seeing CRPS refuse — is
precisely the E2.1-r inversion.** The verdict stands as registered. What the three facts do is
name a successor (§13.6) rather than reopen this one.

### 13.4 Why this is GENUINE_ABSENCE and not an underpowered null

The classifier's verdict is corroborated by a series it does not read: **the CRPS deficit WIDENS as
the fit gets better informed.** Per fold, identity − `joint_shift`: 2022H1 **+0.000** (structurally
ineligible — no prior OOF rows, identity by construction, §4.1), then −0.553, −0.436, −0.701,
−1.884, −1.032, −1.671, **−1.520**, against `n_prior` rising 674 → 4,784. More seasons make δ more
stable and the arm *worse*, not better. Stated in the unit that grows: **there is no fold count,
row count or draw count that turns this positive** — the direction is affirmatively
counter-indicated, not merely unsupported. Combined with the closed lockstep, **no re-test trigger
is published in any form.**

### 13.5 The anchors — every one earned its place

- **`identity_vs_zm_only`: 0/8 active folds, max abs CRPS gap `0.000000000`.** The §8.1 prediction,
  registered BEFORE the run, is CONFIRMED at 8 folds: the consumed `zm_floor` generator already
  re-splices all thirteen legs idempotently, so the Z column is a **structural no-op at the
  assembled layer** and downstream propagation depends on C alone. The Z×C coupling of §13.2 lives
  entirely at the CELL layer. An inactive arm is UNINFORMATIVE, never a pass (NF-D20) — which is
  why it is measured and labelled rather than quietly counted as agreement.
- **Two-sided magnitude bracket, both LOSE:** `over_joint_shift` (×2) 34.812 and
  `reverse_joint_shift` (×−1) 32.743 vs `joint_shift` 31.674. Unlike NF-D20, the registered-to-lose
  magnitudes actually lose, so the fitted magnitude is not an under-correction hiding behind an
  inadmissible anchor. On CRPS the ordering is monotone toward **zero** correction
  (identity 30.699 < `zm_only` 30.854 < ×1 31.674 < ×−1 32.743 < ×2 34.812): the cell's CRPS optimum
  is **no conditional correction at all**, while the level channel wants ≈+33 yards. The two are
  opposed with no interior optimum on the registered metric — the cleanest statement of the null.
- **`permutation_is_inactive` ✅.** `permuted_shift` scores **byte-identical** to `joint_shift`
  (31.67391 both) — the tie was registered in advance (§5.2) as the expected result of permuting a
  row-blind pooled scalar, and it is reported as a confirmed INACTIVE anchor, never as a passed test
  (NF-D16 sibling defect).
- **Per-form oracle floors split the field, and the split is informative.** `cond_shift` and
  `cond_scale` are **`ACTIVE_AND_VIOLATED`** — each BEATS its own peeking oracle (gaps −1.627 and
  −1.725), which per NF-W6d refuses those forms on an anchor independently of the statistics. Both
  joint arms are `ACTIVE_AND_RESPECTED`, but by **+0.079 / +0.087 CRPS ≈ 0.25%** — narrow enough
  that a future reader should treat them as near-ties rather than comfortable clearances.
- **All four degenerates lose** (`nihilist_zero` 91.94, `zero_width` 40.53, `max_width` 40.19,
  `climatology_bank` 57.11) and `coverage_80` = 0.8086 (n 5,485, SE 0.0054) clears its floor as a
  CONSTRAINT — `max_width` satisfies that floor and is eliminated by the metric, which is the shape
  NF1.8 requires.
- **PBO 0.0000** with 88.6% of the in-sample flip mass on `identity` — the field is not a tie the
  rank statistic is mis-reading; the incumbent genuinely wins the CRPS contest.
- Every reproduction pin holds at **1e-9 or exact**: `qb_assembly_matches_w7f` (max abs CRPS gap
  0.0, PIT gap 0.0), `non_qb_bias_matches_w8_0b` (0.0 at all four positions),
  `w8_0c_leg_contribution` (recorded −0.3975331334769923 vs recomputed −0.3975331334769923,
  gap 0.0), `incumbent_cell_is_the_served_cell`.

### 13.6 What a successor may — and may NOT — do

**MAY:** register FORWARD, as a fresh coherent family, the question §13.3 raises and this story did
not ask: whether a correction selected on the ASSEMBLED quantity (level closure under a cell-CRPS
no-harm CONSTRAINT) clears its own battery. §13.3(3) shows the assembled tie is real, so such a
registration is **not a foregone pass** — it would have to survive its own anchors, its own
degenerates and its own DSR field, and the cell-CRPS cost it must constrain is measured and
decisive, not noise. A ROW-DEPENDENT (covariate-conditioned) correction is the other admissible
successor: §13.4's widening deficit is the signature of a **row-blind pooled scalar buying
calibration at the cost of per-row accuracy**, which is exactly the limitation §12 registered in
advance.

**MAY NOT:** re-read THIS field on a different primary, trim these five declared arms post hoc
(MH2.2), promote a family-D row (§12A A8 — the table is report-only and the guard pins it),
re-classify `zm_only`'s refusal, or carry "the joint arms close the QB gap" forward as a shipped
result. `cond_scale`/`joint_scale` additionally re-level a CERTIFIED per-stat marginal
multiplicatively; their measured marginal drift is disclosed and an admissible scale win would
trade per-stat certification scope for an assembled level.

### 13.7 Corrections and limitations discovered in the run

1. **Fold 2022H1 is structurally ineligible for every fitted arm** (no prior OOF rows; identity by
   construction, §4.1). Family A therefore reports 8 folds of which **7 are evaluable** for the
   fitted arms, and `joint_shift`'s "0/8 folds won" is really 0 of 7 evaluable plus one exact tie.
   Recorded rather than trimmed — dropping it would be a post-hoc population change.
2. `assembled_crps_delta` is reported as `0.0` because it is computed for the **winner**
   (`zm_only`), whose assembled effect is the §8.1 structural no-op. It is not a statement about
   the joint arms; their assembled deltas are in §13.3(3).
3. **`share_clipped_at_zero` = 0.0 on every eligible fold** — the `max(·,0)` floor never bound, so
   the shift form's zero-floor guard is present and INACTIVE here. Recorded as inactive, not as a
   passed test.
4. The gate league is `full_ppr` (`passing_yards` at +0.04); every PPR figure above scales with a
   league that prices it differently, and no other league is certified by this run.

