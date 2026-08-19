# NF-W8-0 — pre-registration: the cross-position comparability layer + the QB consumption decision

Registered 2026-08-19 (branch `nf-w80`), **BEFORE any scoring run**. This document is committed
ahead of the smoke and the decisive run; nothing in §1–§8 may be re-read after a result lands
(E2.1-r). Post-run findings go in §12, appended — never edited into the registration.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · research-only. This story produces the
INPUT to the eventual weekly optimizer; nothing serves, nothing publishes, nothing retrains.

---

## §1 ⭐⭐ THE QB CONSUMPTION DECISION — OPTION B, REGISTERED FORWARD

**Decision (PM, 2026-08-19, registered here before any NF-W8-0 scoring): NF-W8 consumes the
RECALIBRATED QB — NF-W7f's `zm_floor` arm — as its QB generator.**

**What Option B asserts.** `dsr_ok` is a **SHIPPING gate**, not a **CONSUMPTION bar** for a
projection consumer. The fantasy vertical gates consumption on (a) CALIBRATION and (b) the
product metric — not on betting-posture deflation. NF-W7f's DSR failure deflated a *search*
(which of 4 zero-mass targets wins) in a story whose search was never the problem: the recorded
flip mass is 100% on `zm_floor`, PBO 0.0, and both closure stories (NF-W7j, NF-W7k) measured the
DSR shortfall as a property of the *design's per-fold variance*, not of arm-selection instability.

**Why `zm_floor`, on the record (all figures are prior stories' committed records — nothing here
is re-scored):**
- It is the ONLY QB construction on record that clears the calibration bar: assembled PIT
  max-decile-dev **0.0281** vs the 0.05 bar, clearing on **8/8 folds** where the incumbent
  (`mixall_learned`) clears **0/8** (NF-W7f).
- It is the best-scoring QB construction on record: **+0.0184 CRPS** vs the matched foil
  (CI95 [0.0032, 0.0336], p=0.0121, PBO 0.0) and **+0.0189** vs the direct-points foil — the
  NF-W7c "assembly loses at QB" verdict is overturned once the marginal zero mass is fixed
  (NF-W7f §12, program finding).
- Every alternative consumption is strictly worse on BOTH axes: `mixall_learned` fails the PIT
  bar (0.0648); `single_copula` fails it (0.0646); direct-points loses CRPS (+0.0189) and its
  ceiling story never certified a QB distribution.
- Every remedy to the dsr_ok shortfall is now MEASURED CLOSED: NF-W7j — DSR_UNREACHABLE, field
  size is no lever, `field_remedy_admissible: None`; NF-W7k — the draw-count lever is a **325×
  shortfall** (σ_MC is 0.31% of per-fold variance vs the ≥99.8% a clearing ceiling needs),
  `MC_LEVER_EXHAUSTED`. Refusing consumption pending dsr_ok is refusing it forever on a bar whose
  levers are exhausted — which would be a *decision* wearing a *gate's* clothing.

**⚠️ THE WEAKER-FOOTING CAVEAT (part of the registration — it travels with every consumer).**
QB is the ONLY position that did not pass the full certification gate WR (DSR 0.9852) and TE
(0.9822) cleared and RB was registered against. What dsr_ok's failure leaves un-certified is the
*deflation-adjusted selection* among the four zm arms — i.e. the residual risk is that `zm_floor`'s
margin over its own family is partly selection noise. The risk retained is **arm-selection
uncertainty within the zm family**, NOT calibration (8/8-fold PIT is a per-fold measurement, not a
selection) and NOT the sign of the improvement over the served incumbent (p=0.0121 vs the matched
foil). Every NF-W8 output that carries QB rows inherits this caveat: the QB generator is
"calibrated + best-on-record, consumed under Option B; not certification-equivalent to WR/TE/RB."

**⛔ What this registration is NOT.** It is NOT a re-certification of QB — the ship bar stands,
un-relaxed, exactly as NF-W7j/W7k left it (E2.1-r: the bar is never re-read after the result).
It is NOT precedent that consumption bars are generally lower than ship bars — it is a
POSITION-SPECIFIC decision on a measured, deterministically-closed refusal, registered forward
before this story scored anything. A future position in the same posture registers its own
decision; it does not cite this one as automatic.

**🚩 SECOND-READER FLAG (governance).** NF-W7j already flagged "whether NF-W8 may use a lower
CONSUMPTION bar than the ship bar" for a second reader. This registration is the affirmative
answer for QB and inherits that flag: **a governance second reader is requested on §1 before any
NF-W8 successor treats the 4-position input as settled.** The flag is recorded in the story
record's `second_reader` field and stays open until a reader signs it.

**Enforcement.** `fp_cross_position.CONSUMED_GENERATOR_OF["QB"] == "qb_zm_floor"` is a guarded
constant; the QB bank construction is NF-W7f's `zm_floor`, by identity (same machinery, same seed,
same Σ estimator, same π̂ estimator), and must reproduce NF-W7f's recorded per-fold CRPS exactly
(`generator_reproduces` — a failed or absent reproduction is a failed clause, never a pass,
NF1.7 (a)).

---

## §2 The consumed-generator map (pins — nothing here is selected in this story)

| pos | consumed generator | construction (by identity) | reproduction pin (per-fold CRPS) |
|---|---|---|---|
| QB | `qb_zm_floor` | NF-W7f `zm_floor`: `zero_targets("zm_floor")` → `resplice_zero_mass` → clamp → mixture over Σ_all, π̂=`mix_learned` | `nf_w7f_qb_marginal.json` arm `zm_floor` @ QB |
| RB | `rb_direct` | `KW.fit_direct_points` (9-knot LGBM quantile → dense grid + exponential tails) | `nf_w7e_split_allrows.json` arm `foil_direct_points` @ RB |
| WR | `wr_mixall` | NF-W7e `mixall_learned`: mixture over Σ_all, π̂=`mix_learned` | `nf_w7e_split_allrows.json` arm `mixall_learned` @ WR |
| TE | `te_single_copula` | NF-W7c `joint_rank` (= `single_copula`): one Gaussian copula, Σ on all rows | `nf_w7c_fp_assembly.json` arm `joint_rank` @ TE |

Basis: TE certified (NF-W7c, DSR 0.9822) · WR certified (NF-W7e, DSR 0.9852) · RB direct-points
near-ceiling take-as-is (NF-W7i: ceiling 0.136%, CI wholly below the 2% band — no bake-off
licensed) · QB per §1. ⛔ Per-position §0.5 is NOT re-opened here: the generators are PINNED
inputs, and a reproduction failure at any position REFUSES that position's folds rather than
re-fitting anything.

Swap alternatives (for the §6 verification ONLY — never consumed): QB/WR/TE → `direct_points`;
RB → `single_copula`. Each is the strongest other-family construction those positions' records
already scored on these folds.

Fold axis: NF-W7c's, verbatim — 8 expanding-window half-season folds 2022H1…2025H2 on the W6d
matrix; gate league `full_ppr`; target `league_fantasy_points`; draws 4000; seed inherited
(`SA._SEED` + `AVAIL_STREAM_OFFSET`) so the reproduction pins can hit at 1e-9.

---

## §3 The measurement — the LEVEL GAP between generators

**The ranking point.** `point := the mean of the 199-level quantile grid` (uniform levels
0.005…0.995 ⇒ the grid mean is the midpoint-rule E[Y] with the outer 0.5% tails truncated). This
IS the point the optimizer input carries, so the artifact being measured/corrected is exactly the
consumer-visible quantity — tail-truncation bias is part of the generator artifact, not a
nuisance to be argued away. (A generator with heavier tails loses more mean to truncation; that
differential is precisely a code-of-origin level artifact.)

**The statistic.** Per (fold, position), OOF on the test block:
`bias_p(f) = mean(point − y)`. Pooled per position as Σ(point−y)/Σn over folds (NF1.8: pool over
rows, never a mean of fold means — both conventions reported).

**Is the gap real? — the pre-registered test.** The cross-position claim is about DIFFERENCES of
biases, so the family is the **6 pairwise position contrasts** `bias_p(f) − bias_q(f)`, paired by
fold (8 folds), BH-FDR q=0.10 over the 6 pairs. `gap_detected := any pair survives BH`.
The MDE at 80% power is computed from each pair's paired SE and stated in PPR — a null here is
"no artifact larger than X PPR", never "no artifact" (MH2.6).

**Scale read (reported, feeds the affine arm).** Per position, the OLS slope of y on point over
the OOF rows — slope 1 = scale-correct; a slope ≠ 1 distorts VOR spread multiplicatively and is
the affine arm's motivation.

**Why the level matters even though classic VOR subtracts a per-position replacement:** a
per-position additive bias cancels in `point − replacement` *within* a position, but (a) the FLEX
allocation compares RAW points ACROSS positions when assigning flex starts (so replacement ranks
themselves move with a level artifact), (b) the merged board interleaves VOR magnitudes across
positions, and (c) any raw-point read (start/sit at FLEX, lineup totals) is distorted directly.
The §6 synthetic guard demonstrates channel (a) mechanically.

---

## §4 The declared recalibration field (⛔ never trimmed or grown after a score — MH2/MH2.2)

**Estimator discipline.** Every recal parameter is fit on **PRIOR FOLDS' OOF rows only** — for
fold k, the (point, y) pairs from test blocks 1…k−1, which lie strictly earlier in time (the fold
axis is expanding-window chronological). Nothing is fit in-sample (NF-MARGIN1: in-sample recal
fitting is optimistically flat) and nothing peeks at the eval fold. **Fold 1 (2022H1) has no
prior OOF ⇒ recal = identity there by construction**; the recal contest runs on the 7 evaluable
folds (2022H2…2025H2), disclosed. A (position, generator) cell with < `MIN_PRIOR_ROWS = 50` prior
OOF rows keeps identity for that fold, flagged — never silently defaulted.

**Real arms (2):**
- `level_add` — per-(position, generator) additive δ = −mean(prior OOF error), all prior folds.
- `level_affine` — per-(position, generator) OLS `y = a + b·point` on prior OOF rows.
  ⛔ Admissibility: if ANY fitted slope b ≤ 0 at any (position, evaluable fold), the arm is
  INELIGIBLE outright (NF-D16/NF-TR2b: a negative slope inverts a board; a b > 0 affine is
  order-preserving within position, asserted per fold, never assumed).

**Incumbent/null:** `identity` — consume the generator points as-is.

**Anchors (scored, never trials — excluded from the PBO/DSR field, MH2.1 (a)):**
- `zero_point` — every point 0 (the nihilist). Must lose RMSE at every position (NF-D11: the
  degenerate is scored every run, never reasoned about).
- `position_mean_point` — every row = its POSITION's prior-OOF mean of y (a per-position
  climatology constant). It DESTROYS all within-position skill while trivially achieving ~0
  cross-position bias range — the NF1.8 two-sided anchor: it must LOSE the point metric (RMSE)
  decisively at every position, proving the comparability constraint was never promoted into a
  selection criterion (a criterion this degenerate wins is fatal, NF-D18).
- `level_add_permuted` — the fitted δ vector cyclically shifted across positions
  (QB→RB→WR→TE→QB), deterministic. It preserves the population of corrections and destroys their
  per-position assignment: it must NOT beat the real arm on the gap statistic.
- `level_add_oracle` — δ fit on the TEST fold itself (the peeking level correction; zeroes test
  bias by construction). Its RMSE improvement is the CEILING of the level channel; the real arm's
  captured fraction is reported (NF-D16 (e)). Never a trial.

**Trailing-window sensitivity (REPORT-ONLY, ⛔ never selected):** δ from the trailing 3 prior
folds beside the all-prior δ. If the full-history fit fails a gate in a way the trailing read
would not, that is a SUCCESSOR's fresh registration (the NF-TR2→TR2b pattern), not a re-pick.

**Point metric: RMSE** (squared error selects the MEAN — the quantity under repair). ⛔ NOT MAE:
the all-rows weekly target is zero-heavy (QB realized all-zero rate 0.516) and MAE optimizes the
conditional median ⇒ the NF-D11 inversion class. The degenerate ceiling (`zero_point`) is scored
against exactly this risk every run.

**PIT / calibration preservation — an IDENTITY, not a hope.** The layer moves the RANKING POINT
ONLY; the bank (the certified distribution) passes through UNTOUCHED, asserted byte-identical
per fold (`banks_untouched`). Each position's certified PIT is therefore preserved by
construction — and the point-vs-bank-mean offset (= the applied correction) is DISCLOSED per row
in the output schema, so a consumer reading the bank's own grid mean instead of the recalibrated
point knows exactly what gap it re-introduces (NF-TR2: point-only, band-fixed).

---

## §5 Gates + the decision rule (fixed in advance)

**Family structure, stated:** family A = the 6 pairwise bias contrasts (§3, BH q=0.10);
family B = the recal contest (ONE gated comparison: best real arm vs `identity`), declared field
size 2 (`declared_field_size=2` passed to `classify_null`; `field_remedy_admissible` read, not
the prose — MH2.7).

**The verdict rule (`comparability_verdict`), four states:**

1. **`COMPARABLE_AS_IS`** — `gap_detected` is False. The four generators sit on a common scale at
   the stated MDE; `identity` ships as the layer; the recal arms are REPORTED (never consumed);
   the §6 swap check runs as certification evidence. The record states the MDE in PPR — this is
   "no artifact larger than X", never "no artifact".
2. **`LEVEL_ARTIFACT_REMOVED`** — `gap_detected` is True AND the winning real arm passes ALL of:
   (a) reduces the per-fold cross-position bias RANGE vs identity (paired, one-sided p < 0.05);
   (b) beats `level_add_permuted` on the same statistic;
   (c) do-no-harm: RMSE not significantly degraded vs identity at ANY position (one-sided
       α=0.05 per position — a significant degradation at any position refuses the arm);
   (d) `degenerates_lose` (both degenerates lose RMSE to the arm at every position);
   (e) `banks_untouched` (the PIT-preservation identity holds);
   (f) the §6 swap clause (below) on its ACTIVE positions;
   (g) deflation over the eligible field (NF18.deflate subset = {identity, level_add,
       level_affine}; trial field = the 2 real arms) with the NF1.8 tied-field discipline
       PRE-REGISTERED, because the two real arms are near-clones BY CONSTRUCTION whenever the
       true artifact is additive (slope ≈ 1 makes affine ≈ add): `pbo_ok := PBO < 0.2 OR
       os_gap_pct ≤ 1.0` — Bailey's performance degradation asks the decision-relevant question
       ("did picking it COST anything?"), and a high PBO whose flip mass sits on two arms that
       score the same is a TIE, not overfitting (NF1.8). Both figures + the flip distribution
       are reported either way. DSR ≥ 0.95 on the winner-vs-identity range deltas;
   (h) BH-FDR within family B is trivial (one comparison) — reported for form.
   Arm selection between `level_add` and `level_affine`: the smaller pooled cross-position bias
   range; tie (within 1 SE) → the simpler (`level_add`). Registered before any score.
3. **`LEVEL_GAP_DETECTED_UNREPAIRED`** — `gap_detected` is True and NO real arm is admissible
   under 2(a)–(g). The finding stands: **the hybrid is not cross-rankable as-is.** The input
   ships as `identity` with the measured per-position gap DISCLOSED in the schema
   (`level_gap_disclosure`), flagged not-cross-rankable; classification follows the vertical's
   rule — a refusal resting on anchors/constraints is `CONSTRAINT_REFUSED` (no data trigger,
   NF-D18); one resting on a reachable statistical gate is classified by `classify_null`
   (recorded verbatim, hand-corrected only per the documented instrument gaps, with
   `binding_half` named — the NF-W7f mixed-failure rule).
4. **`UNDEFINED`** — a reproduction pin failed, fewer than 4 evaluable folds, or a position was
   skipped: the harness did not run; never read as any verdict (NF1.7 (a)).

**`generator_reproduces` (hard clause, all states):** each consumed generator's per-fold CRPS
must match its §2 record pin (tolerance 1e-9, `SA.incumbent_reproduction`). An absent record or a
smoke-flagged record is "the control DID NOT RUN" — a failed clause, never a pass.

---

## §6 The generator-swap verification (the matched check the story card asks for)

Same players, generator swapped: per (evaluable fold, position p), both the consumed and the
alternative generator score the IDENTICAL test rows. Define:

- `swap_level_shift(p, f) = mean(point_consumed − point_alt)` — the LEVEL component of the swap.
- The board decomposition (per global week within the fold, merged 4-position VOR board via the
  gate-league config): displacement(consumed vs alt) = TOTAL swap movement;
  displacement(consumed vs mean-matched alt — the alt's points shifted by the observed mean
  difference) = the ORDERING component (genuine model disagreement, not a comparability
  artifact); their difference in movement = the LEVEL-driven component. All three reported,
  before and after the layer (each generator recalibrated with ITS OWN prior-OOF δ).

**The clause (`swap_level_component_collapses`), with the NF-D20 activity rule:** a position is
ACTIVE for this clause iff its pre-layer |pooled swap_level_shift| exceeds 2× its paired SE — on
an INACTIVE position the two generators already agree on level and the clause has nothing to act
on (an inactive fold/position is UNINFORMATIVE, never a pass). On ACTIVE positions the shipped
layer must reduce |pooled swap_level_shift| (paired per fold, one-sided p < 0.05). If NO position
is active, the clause is `INACTIVE_EVERYWHERE` — reported as such (it then *corroborates*
`COMPARABLE_AS_IS` but cannot certify a repair).

---

## §7 The deliverable — the 4-position, VOR-ranked optimizer input

Written by the decisive run to `artifacts/nf_w8_0_input/` (gitignored parquet, one file per
fold) + schema and per-fold board summaries in the record. Columns:
`season, week, gw, gsis_id, position, generator, point_raw, point_recal, recal_arm,
point_vs_bank_offset, p10, p50, p90, replacement_points, vor, overall_rank, positional_rank,
level_gap_disclosure (per-position pooled bias under identity), qb_option_b (bool, True on QB
rows), calibration_warning (inherited from NF-W7c: the assembled row carries NF-W6d calibrated
DEFAULTS among priced legs)`.
Weekly replacement/VOR via `fantasy_engine.vor.compute_replacement_levels`/`build_board` on the
gate-league config (12-team full-PPR, 1QB/2RB/2WR/1TE/1FLEX), per global week.

**Promote blockers (inherited + new):** NF-W7c's blockers in full (calibrated-default disclosure;
SKILL_UNMODELED_KEYS coverage gaps; per-position certification scope) · the §1 QB caveat on every
QB row · K/DST are OUT OF SCOPE (the input is declared 4-position; the NF-W7 K/DST weekly models
are separately certified and join in a successor) · deploy-held, NF-G0 challenger — consumed by
nothing until governance promotes.

---

## §8 Runtime plan (the >2-min rule)

- In-session: SYNTHETIC verification only (no lake, no W6d dispatch) — the full
  runner path on synthetic banks, all guards, the RED proof.
- OPERATOR (laptop): `--smoke` (1 fold, few draws, artifact `_smoke` — path proof, no verdict),
  then the decisive run (8 folds × 4000 draws; dominated by the W6d marginal dispatch,
  ~370–600 s/fold cold — the per-fold bank cache is shared with NF-W7e's
  (`artifacts/nf_w7e_bank_cache/`, same key scheme, shape/cell-refused on mismatch), so a warm
  machine pays only draws + LGBM fits). `--rewrite-report` re-derives every verdict from stored
  fold results at zero refit cost.

## §9 Limitations (registered now, so they cannot become post-hoc rescues)

- The layer corrects LEVEL (and, via the affine arm, uniform SCALE). A rank-dependent
  (within-position non-uniform) generator artifact is out of scope — a successor's fresh
  registration.
- The prior-fold OOF estimator mixes eras (NF-TR2b's non-stationarity risk); the trailing-3
  sensitivity is reported, and a trailing successor is the named remedy if the full-history fit
  is what fails.
- The swap alternatives are verification instruments, not certified generators; nothing from §6
  is consumable.
- `gap_detected` at 8 folds resolves pairwise gaps down to roughly the stated MDE only; a smaller
  real artifact survives at every position equally and cancels in within-position VOR, but not in
  FLEX allocation — the disclosure column exists for exactly this.
