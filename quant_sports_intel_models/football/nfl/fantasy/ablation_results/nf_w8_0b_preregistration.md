# NF-W8-0b — pre-registration: the TAIL-COMPLETED cross-position ranking point

Registered 2026-08-19 (branch `nf-w8-0b`), **BEFORE any scoring run**. This document is committed
ahead of the smoke and the decisive run; nothing in §1–§9 may be re-read after a result lands
(E2.1-r). Post-run findings go in §12, appended — never edited into the registration.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger · research-only. Nothing
serves, nothing publishes, nothing retrains. This is NF-W8-0 §12.5(1) + §12.5(2), registered
forward as a fresh story.

---

## §1 What NF-W8-0 established, and what this story changes

NF-W8-0 measured a **real** cross-position level gap and attributed it: pooled identity bias
QB −0.470 · RB −0.254 · TE −0.151 · WR −0.109 PPR, with **QB|WR −0.359 (p=0.0016)** and
**QB|TE −0.319 (p=0.0021)** surviving BH(q=0.10). It then proved the gap is **NOT a calibration
defect** — every position's PIT is flat, `banks_untouched` held, and the §6 swap check showed the
artifact is a property of the **generator**, not the population: on the SAME rows the QB assembly
reads **0.371 PPR below** the direct-points construction, while direct-points at QB carries the
same small bias (−0.10) as the WR/TE generators.

§12.3d named the mechanism: **the consumer-visible ranking point is the MEAN OF THE 199-LEVEL
QUANTILE GRID, which is the midpoint-rule `E[Y]` with the outer 0.5% of probability mass
TRUNCATED** — and a generator with a heavier right tail loses more mean to that truncation.

**This story changes ONE thing: how the point is READ off the certified bank.** It does not touch
the generators, the folds, the recalibration field, the anchors, the gates, or any certified
distribution. It is NF-W8-0's harness driven through a different ranking-point reader.

⛔ **What this story is NOT.** It is not a re-certification of any position (NF-W7f's QB Option-B
caveat, NF-W7c's calibrated-default disclosure and every per-position certification scope are
inherited UNCHANGED), not a re-opening of per-position §0.5, and not a re-read of any NF-W8-0
gate. NF-W8-0's record stands exactly as decided; this runner is **refused at import** if its own
artifact paths would collide with the predecessor's.

---

## §2 The quadrature the incumbent point implies (arithmetic, fixed in advance)

`EVAL_LEVELS` is 199 uniform levels 0.005…0.995 with spacing `h = 0.005 = 1/200`. Reading level
`u_k` as the MIDPOINT of a probability bin of width `h`, the 199 bins tile
`[COVERED_LO, COVERED_HI] = [0.0025, 0.9975]`, so

```
covered_integral := ∫_0.0025^0.9975 Q(u) du  =  (1/200)·Σ_k Q(u_k)  =  COVERED_MASS · gridmean
```

with `COVERED_MASS = 199·h = 0.995`. The mass OUTSIDE that interval is `TAIL_MASS_PER_SIDE =
0.0025` per side — **exactly the "outer 0.5% tails truncated" NF-W8-0 §3 declares**.

⭐ **The `0.995` re-weight is LOAD-BEARING and is registered as such.** Without it the transform
carries a `+0.5%` MULTIPLICATIVE bias that scales with a position's own level, which would
MANUFACTURE a cross-position differential of exactly the kind family A measures. The correctness
anchor is exactness on a degenerate bank (below).

---

## §3 The transform — DETERMINISTIC, by registration

For `u > 0.995` the NF-MARGIN exponential mean-excess form (`MC.apply_level_map`'s exact
functional family) is

```
Q(u) = Q(0.995) + β_hi · ln( 0.005 / (1−u) )
```

whose closed-form contribution to `E[Y]` beyond the quadrature edge is

```
∫_0.9975^1 Q(u) du = s · ( Q(0.995) + β_hi·(ln 2 + 1) ),   s = 0.0025
```

mirrored below. `ln 2` is a consequence of the quadrature edge sitting exactly half a bin beyond
the last level — **not a free parameter**. The registered ranking point is therefore

```
point_tc = 0.995 · gridmean  +  ∫_0^0.0025 Q  +  ∫_0.9975^1 Q
```

**The scale is read off the CERTIFIED BANK'S OWN tail spacing:**

```
β_hi = ( Q(0.995) − Q(0.975) ) / ln( 0.025 / 0.005 )      (mirrored for β_lo)
```

⛔ **THE SCALE MAY NOT BE FITTED.** `MC.fit_tail_betas` (mean excess on realized `y`) and
`M3.fit_eq_tail` (empirical exceedance quantiles) are **estimators** and are forbidden here, for
two independent reasons registered now: (a) NF-W8-0 §12.3a measured a **non-stationarity floor** —
the cross-position range of prior-vs-fold `y`-level drift is **0.511 PPR against a 0.4888
artifact**, which is why every registered recal arm captured only ~20% of the peeking oracle's
ceiling; a transform that reads outcomes re-imports precisely that floor. (b) NF-MARGIN2 measured
the **fitted** exponential mean-excess **UNDER-EXTENDING at QB/WR** (`CONSTRAINT_REFUSED` there),
i.e. the estimator is known-biased-low at exactly the position under test. A pure function of the
bank has no moving target and no inherited bias: identical bank ⇒ identical point, on every fold
and in every era.

**Anchor levels (design constants, fixed by PRIOR stories, not by this one):** `0.975` is
`WP.Q_LEVELS[-1]`, the SERVED 39-level grid's end and the level `MC.apply_level_map` already
treats as "where the tail begins"; `0.995` is the eval grid's end. This is the **widest in-grid
tail span available**, so the implied scale is the most stable one the bank can supply. The
narrower alternatives (`inner_hi ∈ {0.95, 0.99}`) are scored as a **REPORT-ONLY sensitivity** and
⛔ never selected — the record states the transform's spread across them so the anchor's influence
is BOUNDED and VISIBLE rather than argued to be small.

**SYMMETRY, registered** (`TAIL_FORM = exponential_mean_excess_symmetric`)**:** the same
machinery is applied to BOTH tails. The weekly fantasy target
is zero-heavy but **not bounded below** (an INT/fumble line scores negative), so there is no
support argument for treating the sides differently — and an asymmetry that happened to favour
the position family A indicted would be indistinguishable from tuning (E2.1-r). On a zero-atom row
the bottom anchors are equal, `β_lo` is 0, and the left extension degenerates to the flat clamp on
its own; the record reports `flat_lo_share` and the per-side magnitudes rather than asserting it.
`β ≥ 0` always (the bank is sorted) ⇒ the extension is monotone by construction — asserted, not
assumed.

**The correctness anchors (an ORACLE FLOOR the transform must MEET, checked every run):**
`point_tc` returns `c` EXACTLY for a degenerate bank at `c`, `0.5` exactly for the uniform
quantile function, and `E[Y]` to <1e-3 for `Exp(1)`; on right-skewed shapes it must move
**strictly toward** the truth. ⭐ And the mechanism itself is guarded: a SYMMETRIC bank loses
~nothing to the truncated grid mean while a right-skewed bank of the SAME mean loses an order of
magnitude more — a guard that could not separate those two would not be testing this story.

---

## §4 The measurement — family A, re-run on the new point

Verbatim NF-W8-0 §3, with `point := point_tc`:

- per (fold, position) OOF `bias_p(f) = mean(point − y)`, pooled `Σerr/Σn` (NF1.8: pool over rows;
  both conventions reported);
- the family is the **6 pairwise position contrasts** `bias_p(f) − bias_q(f)`, **paired by fold**
  (8 folds), two-sided t, **BH-FDR q=0.10**. `gap_detected := any pair survives BH`;
- the **MDE at 80% power** is computed per pair and stated in PPR — a null is "**no artifact
  larger than X PPR**", never "no artifact" (MH2.6);
- the incumbent GRID-MEAN bias is recorded BESIDE the tail-completed one, per position, so the
  two reads of the same certified banks are auditable against each other rather than asserted.

**Fold axis, generators, gate league, target, draws and seed: NF-W8-0's, verbatim** — QB
`zm_floor` (Option B, §1 of the predecessor's registration, caveat and open second-reader flag
inherited), RB `direct_points`, WR `mixall_learned`, TE `single_copula`, each BY IDENTITY of its
certifying story's code path. **`generator_reproduces` is a hard clause in every state:** each
consumed generator's per-fold CRPS must match its record pin at **1e-9**; an absent or
smoke-flagged record is "the control DID NOT RUN" — a failed clause, never a pass (NF1.7 (a)).
⛔ Scores are stored at FULL PRECISION: a `round(…, 6)` caps every pin at ~5e-7 and returns the
run UNDEFINED while reproducing perfectly (the NF-W8-0 smoke bug, re-armed as a RED-proof break).

**Family B (the recalibration contest) runs UNCHANGED on the new point** — same declared field
`{identity, level_add, level_affine}`, same four anchors (`zero_point` · `position_mean_point` ·
`level_add_permuted` · `level_add_oracle`), same clauses, same `declared_field_size=2`. It is
REPORTED; ⛔ **it is not this story's gate** (§5).

---

## §5 The swap-clause MATERIALITY FLOOR (NF-W8-0 §12.5(2))

NF-W8-0's §6 activity rule (`|pooled shift| > 2×SE`) has **no materiality floor**, so it refused
the story's winner on WR/TE shifts of **0.037 / 0.095 PPR** — precisely estimated (SE 0.011/0.013)
but an **order of magnitude below family A's own detection floor** — while QB, the position family
A indicted, collapsed decisively (0.371 → 0.074, p<1e-4). That is the NF-W6 "demonstrable ≠
material" lesson on a clause of the predecessor's own design. The registered successor rule:

```
active := |pooled shift| > 2×SE   AND   |pooled shift| ≥ SWAP_MATERIALITY_FLOOR
```

**The floor is a DESIGN quantity, not a tuned one:** it is family A's own resolution on the SAME
run — the **MEDIAN of the 6 pairwise MDEs at 80% power** (`median_pairwise_mde_ppr`). An MDE is a
function of the design's noise, never of the effect (MH2.6), so this states the rule the story
already lives by: **a swap shift smaller than what family A can detect cannot be the artifact
family A indicted.**

**Disclosed so the choice cannot hide:** on NF-W8-0's RECORDED shifts the MIN (0.1732), MEDIAN
(0.1955) and MAX (0.3277) pairwise MDE yield the **IDENTICAL activity set** (QB active; RB/WR/TE
inactive) — the summary statistic is **not outcome-determining** there. The record reports all
three on this run's own numbers (`materiality_floor.sensitivity_band`) either way.

**Two properties, both guarded:** the floor is an AND with the precision rule, so it can only
ever **REMOVE** activity, never add it (anything else would be a NEW way to refuse, not a
materiality filter); and a floor that could not be FORMED is `None` and **RAISES** — ⛔ never
silently floor-0, which would restore the predecessor's no-floor rule under this story's name
(NF1.7 (a)).

**The path-proof clause** (registered 2026-08-19, still BEFORE any scoring run — amended into §5
while the story was pre-run, and the commit history is the audit trail). A run with **fewer than
4 evaluable folds is UNDEFINED BY CONSTRUCTION** (§6.4) and reaches no verdict — that is exactly
the `--smoke` path proof, where family A has one observation per position and every pairwise MDE
is therefore `None`, so the floor cannot be formed. Raising there would defeat the path proof;
falling back to floor-0 or `None` would restore the predecessor's rule. **The registered
resolution is an INFINITE floor**, which deactivates every position ⇒ `INACTIVE_EVERYWHERE` ⇒ the
clause neither passes nor refuses, recorded as `unformable_on_a_path_proof`. ⛔ The relaxation is
gated on `verdict_reachable` and may **never** reach a run that can decide — that case still
RAISES. Both halves are RED-proven.

---

## §6 The verdict rule + the ONE definition of `cross_rankable` (fixed in advance)

The shared derive layer returns NF-W8-0's four-state comparability verdict computed on the
tail-completed point; NF-W8-0b names it:

1. **`TAIL_COMPLETION_CLOSES_THE_GAP`** — `gap_detected` is False. The DETERMINISTIC point closes
   the gap **with no recalibration layer**. ⇒ **`cross_rankable: true`** — raw-point
   cross-position surfaces and a superflex board are unblocked **at the stated MDE**.
2. **`TAIL_COMPLETED_LEVEL_ARTIFACT_REMOVED`** — the gap survives the completion but a registered
   arm is admissible on top of it. ⇒ **`cross_rankable: false`**, `cross_rankable_with_layer:
   true`. This is a **weaker, different claim**: a fitted layer re-imports §12.3a's
   non-stationarity floor, which is exactly what this story exists to step around.
3. **`TAIL_COMPLETED_GAP_PERSISTS`** — the gap survives and no arm is admissible. ⇒ both false;
   the input ships as `identity` on the tail-completed point with the residual per-position gap
   DISCLOSED (`level_gap_disclosure`); classified per the vertical's rule (a refusal resting on
   anchor/constraint clauses is `CONSTRAINT_REFUSED` with **no data trigger** — NF-D18; one
   resting only on statistical clauses goes to `classify_null`, recorded verbatim with
   `binding_half` named).
4. **`UNDEFINED`** — a reproduction pin failed, a position was skipped, or family A could not
   evaluate: the harness did not run; never read as any verdict (NF1.7 (a)).

⭐ **`cross_rankable` has exactly ONE definition, fixed here: `state == TAIL_COMPLETION_CLOSES_THE_GAP`.**
The weaker reading is reported under its own name so the two can never be confused.

**`banks_untouched` is an IDENTITY, not a hope.** This story moves the RANKING POINT ONLY; the
certified bank passes through UNTOUCHED, asserted byte-identical per fold at write time. A writer
that shifts a quantile (the NF-TR2 `apply_to_band` mistake) **demotes the ship** — RED-proven.

---

## §7 The deliverable

The 4-position VOR-ranked optimizer input under the shipped arm, written to
`artifacts/nf_w8_0b_input/` (gitignored parquet, one file per fold), schema inherited verbatim
from NF-W8-0 §7 — with `point_raw` now carrying the **tail-completed** point, since that is this
story's registered ranking point. The tail-completion magnitude is reported **per position in the
record** (`tail_completion_by_position`), where a measurement belongs; ⛔ a per-row disclosure
column is NOT added here — that would be an undeclared schema change, and a successor registers it
if a consumer needs it.

**Promote blockers:** NF-W8-0's in full, verbatim, plus (a) the tail completion re-certifies NO
position, and (b) `cross_rankable: true` licenses the raw-point surfaces at the stated MDE only —
it is not a claim about a rank-dependent (within-position non-uniform) generator artifact, which
stays out of scope for a successor's registration.

---

## §8 Runtime plan (the >2-min rule)

- **In-session:** SYNTHETIC verification only (no lake, no W6d dispatch) — the transform's
  correctness anchors, the floor, the verdict mapping, the full derive layer end-to-end on
  fabricated fold rows, and the RED proof.
- **OPERATOR (laptop):** `--smoke` (1 fold, 300 draws, artifact `_smoke` — path proof, no
  verdict: reproduction pins cannot hit at smoke draws), then the decisive run (8 folds × 4000
  draws, ~50 min; dominated by the W6d marginal dispatch). The per-fold bank cache is NF-W7e's
  (`artifacts/nf_w7e_bank_cache/`), shared by identity, so a machine that ran NF-W8-0 pays only
  draws + LGBM fits. `--rewrite-report` re-derives every verdict from stored rows at zero refit.

---

## §9 Limitations (registered now, so they cannot become post-hoc rescues)

- The transform corrects the **outer 0.5% of mass only**. A generator artifact inside the covered
  region (a mis-shaped body, a rank-dependent distortion) is **out of scope** — a successor's
  fresh registration.
- The exponential form is a MODEL of the beyond-grid tail. It is exact for an exponential tail,
  near-exact for the gamma/lognormal shapes weekly fantasy points resemble, and its anchor
  sensitivity is reported; it is **not** claimed to be the true tail.
- A residual gap **below** the stated MDE survives at every position and cancels in within-position
  VOR, but not in FLEX allocation — the `level_gap_disclosure` column exists for exactly this, and
  NF-W8-0 §12.3b's structural shield (a uniform QB level shift cancels EXACTLY in VOR, and QB is
  not FLEX-eligible in the gate league) is a property of the GATE LEAGUE, **lost in superflex**.
- Family B is REPORTED, not this story's gate; a `LEVEL_ARTIFACT_REMOVED` outcome is recorded as
  the weaker claim it is (§6.2) and does not license the raw-point surfaces.

---

## §12 POST-RUN FINDINGS (appended 2026-08-19 after the decisive 8-fold run; §1–§9 untouched)

Decisive run: operator laptop, 8 folds × 4000 draws, 3,874.6 s. Record:
`nf_w8_0b_tail_point.{json,md}` (re-derived once via `--rewrite-report` for a display-rounding
fix — verdict, every gap, every pin and every clause byte-identical).

### §12.0 Headline — VERDICT `TAIL_COMPLETED_GAP_PERSISTS` · `cross_rankable: false`

**The tail-truncation mechanism is REAL, MEASURED, and roughly 20× TOO SMALL to be the cause of
the QB cross-position gap.** All four reproduction pins hit at **0.0 over 8 folds** — the consumed
generators are byte-identical to their certified records, so the `point_reader` architecture
delivered what it was built for. `banks_untouched` True, max quantile drift 0.0, shipped arm
`identity`.

### §12.1 The measurement (family A on the tail-completed point)

| pos | grid-mean bias | tail-completed bias | completion Δ | hi-tail recovered |
|---|---|---|---|---|
| QB | −0.4695 | −0.4237 | **+0.0462** | +0.0816 |
| RB | −0.2532 | −0.2206 | +0.0331 | +0.0598 |
| WR | −0.1110 | −0.0591 | **+0.0498** | +0.0773 |
| TE | −0.1509 | −0.1127 | +0.0383 | +0.0557 |

`gap_detected` **True**: QB|WR **−0.3621** (p=0.0016, MDE 0.2036) and QB|TE **−0.3106**
(p=0.0026, MDE 0.1903) still survive BH(q=0.10); no other pair does. Against NF-W8-0's grid-mean
reads the pairs moved by **−0.0036** and **+0.0080** — i.e. QB|WR got marginally WORSE.

⭐ **The change to any pair is EXACTLY the difference of the two positions' ROW-POOLED completion
deltas** (QB +0.0458 · RB +0.0326 · WR +0.0519 · TE +0.0382 — verified to 1e-17), **so the whole
mechanism is bounded by their SPREAD: 0.0193 PPR.** Every one of the six pairs moved by ≤0.0193,
as that identity requires (largest: RB|WR, exactly 0.0193). Against a 0.36 PPR artifact needing to
fall under a ~0.20 PPR MDE, the lever is **~19× short**.

⚠️ **The pooling convention is load-bearing, and this story's own bound guard caught it.** Stated
from the per-fold `bank_detail` means — a MEAN OF FOLD MEANS — the deltas read
+0.0462/+0.0331/+0.0498/+0.0383 and imply a bound of **0.0167**, which is simply WRONG: RB|WR
moves 0.0193 and would breach it. Pooled over ROWS the identity is exact. The record now carries
BOTH (`completion_delta_pooled` beside `tail_completion_by_position`) precisely because they
differ enough to change a headline (NF1.8, on this story's own conclusion).

### §12.2 ⭐ §12.3d's HYPOTHESIS IS REFUTED, with a decomposition

NF-W8-0 §12.3d proposed (explicitly "untested here") that the QB gap is tail-mass differential
between the assembled and 9-knot representations under the same grid read. On the certified banks,
scoring both generators on the IDENTICAL rows:

| pos | consumed vs swap | level gap | tail-channel share |
|---|---|---|---|
| **QB** | `zm_floor` vs `direct_points` | **−0.3505** | **+0.0173 = 4.9%** |
| RB | `direct_points` vs `single_copula` | −0.0443 | −0.0242 = 54.5% |
| WR | `mixall_learned` vs `direct_points` | −0.0426 | +0.0111 = 26.0% |
| TE | `single_copula` vs `direct_points` | +0.1060 | +0.0128 = 12.0% |

**~95% of the QB generator gap lives in the BODY of the distribution, not in the truncated
tails** — a level difference present across the quantile function, which no tail completion can
reach. Per pair: the tail channel is **1.2%** of QB|WR and **8.1%** of QB|TE.

⚠️ The mechanism is NOT inert — at RB it explains 54.5% of that (much smaller) gap, and QB does
carry the heaviest right tail (hi-tail +0.0816, the largest). It is real; it is simply not what
drives QB.

**Why the direction confirms but the magnitude does not.** The incumbent grid mean carries TWO
opposite errors: it drops the outer tails (understating, most for a heavy tail) AND it weights the
covered mass by 200/199 (overstating by 0.5% of the position's own LEVEL). QB has both the
heaviest tail (+0.0816) and the highest level (re-weight −0.0354), so the two nearly cancel and
QB's net completion (+0.0462) lands BELOW WR's (+0.0498). ⇒ **the truncated grid mean is closer to
`E[Y]` than it "should" be, by an accident of offsetting errors** — and the offset is
position-dependent in a way that shrinks rather than creates the cross-position differential.

### §12.3 ⭐ THE ONE THING THAT SHIPPED — the swap materiality floor is VALIDATED

The §12.5(2) successor works exactly as registered. Floor **0.197 PPR** (`median_pairwise_mde_ppr`;
band {0.1733, 0.197, 0.3288}):

- **QB** — pooled shift −0.3576, precise ✓ **and material ✓ ⇒ ACTIVE**, collapsing 0.3576 → 0.0763
  (p = 3.4e-07) ⇒ **PASSES**;
- **RB / WR / TE** — pooled 0.0566 / 0.0263 / 0.1059, precise ✓ but **material ✗ ⇒ INACTIVE**.

`swap_clause` goes **FAIL → PASS**. The floor did NOT weaken the clause: the position family A
indicted is still active, still tested, and passes decisively; only the immaterial refusals
§12.3c named are removed. This is the NF-W6 "demonstrable ≠ material" lesson landing as working
code.

### §12.4 ⭐ THE CLASSIFICATION CHANGED — and a reader must not mis-scope its trigger

With `swap_clause` (an ANCHOR clause) now passing, the winner `level_affine` fails only
STATISTICAL clauses — `reduces_gap` (p=0.0522 vs the 0.05 bar; the bar stays, E2.1-r) and
`dsr_ok` (0.9193 vs 0.95). So the classification moves from NF-W8-0's **`CONSTRAINT_REFUSED`,
binding_half=anchor, NO data trigger** to **`POWER_LIMITED`** with a published trigger
("+2 folds for the DSR gate; field size is not a lever").

⚠️⚠️ **THAT TRIGGER DESCRIBES FAMILY B ONLY, AND MUST NOT BE READ AS FAMILY A'S STATUS.** Family B
asks "can a FITTED layer repair the residual?" — a genuinely power-limited question. Family A —
this story's actual gate — asks "does the DETERMINISTIC point close the gap?", and its answer is
**arithmetically bounded, not underpowered**: the completion delta is a deterministic function of
each certified bank, its cross-position spread is 0.0167 PPR, and **no fold count can make that
spread larger**. More seasons would estimate the same bound more precisely and change nothing.
Publishing "+2 folds" beside family A's null would be the NF-D18 misleading-trigger class; family
A's null is closer in kind to a measured absence.

### §12.5 The findings that outlive the story

- **(a) A quantile-grid MEAN is a truncated `E[Y]` whose bias scales with right-tail heaviness**,
  so two calibrated generators of the same quantity produce different "means" by how heavy a tail
  their code emits. Real, measured (+0.033 to +0.050 PPR here), and now correctable
  deterministically — but at this magnitude it is a **rounding-scale** effect, not a
  cross-position artifact. Other repo sites reading `bank.mean(axis=1)` as `E[Y]`
  (`stat_distribution_serving.encode_bank`, `fp_assembly`, `opportunity_allocation.pit_frame`,
  `run_nf_w3._point_and_sd`) inherit the same property and are unaudited.
- **(b) ⭐ The re-weight is not optional and its omission would have MANUFACTURED a result.**
  Dropping the 199/200 correction inflates every point by 0.5% of its own level — largest at QB —
  which would have "closed" much of the QB gap while being arithmetically wrong (a degenerate bank
  would return 1.005·c). The guard that catches it is exactness on a degenerate bank. A successor
  tempted to "just add the tails" is being offered a fabricated win.
- **(c) The non-stationarity floor is unchanged by the point read.** `position_mean_point` scores
  **0.511** on the tail-completed point, identical to NF-W8-0's grid-mean 0.511 — as it must,
  being a property of prior-vs-fold `y`-level drift, not of how the point is read. The real arms
  again capture ~20% of the peeking oracle's ceiling (0.4901 → 0.3906 against 0.0).
- **(d) The smoke predicted the decisive result to within 0.005 PPR per pair.** A 1-fold,
  300-draw path proof bounded the mechanism at ≤0.012 PPR (observed 0.0167) and put the tail
  channel at 1.6% of the QB swap gap (observed 4.9%). Where a mechanism's magnitude is a
  DETERMINISTIC function of the bank, a path proof can forecast the verdict cheaply — the draw
  count biases the completion delta by only ~10% at 300 draws and ~0% by 4000 (measured). ⛔ It
  cannot replace the run: the pins do not hit at smoke draws, so the banks are not certified.

- **(e) ⭐ A BOUND IS ONLY AS GOOD AS ITS POOLING CONVENTION, AND PROSE CANNOT CATCH THAT.** This
  story's headline is an identity ("a pair moves by exactly the difference of its two positions'
  completion deltas"), and it was first written from the per-fold `bank_detail` means — giving a
  bound of 0.0167 that RB|WR (0.0193) breaches. Nothing about the sentence looked wrong; the
  error was one convention deep (NF1.8). It was caught by a guard that asserts the IDENTITY on
  the committed record rather than restating the claim — the residual is 1e-17 pooled over rows
  and ~2.6e-3 as a mean of fold means. ⇒ when a conclusion rests on an arithmetic identity,
  ASSERT the identity against the artifact; a bound quoted from a differently-pooled summary of
  the same quantity is a different number wearing the same name.

### §12.6 Successors (forward registrations only — nothing here was selected)

1. **The QB gap lives in the BODY of the assembled distribution.** §12.2 localises ~95% of the
   −0.3505 PPR `zm_floor`-vs-`direct_points` gap to a level difference across the quantile
   function. A successor registers a BODY-level comparison (which quantile ranges carry the gap,
   and whether it is a mixture-weight or a per-leg-scale effect) — ⛔ NOT another read of the
   tails, which are now measured closed.
2. **The `reduces_gap` bar and the fitted-layer route are power-limited (§12.4)** — a family-B
   successor is a genuine +2-fold / lower-variance question, and is a DIFFERENT question from
   whether the hybrid is cross-rankable deterministically.
3. **NF-W8-0 §12.5(3) remains OPEN**: the PM decision on bounded VOR-space consumption under the
   disclosed gap, with NF-W8-0 §12.3b's structural shield (a uniform QB level shift cancels
   exactly in VOR; QB is not FLEX-eligible in the gate league) intact and superflex still excluded.

### §12.7 What ships from this record

The 4-position input parquets under `identity` **on the tail-completed point**, `cross_rankable:
false`, per-row `level_gap_disclosure`, the Option-B caveat on every QB row, and every promote
blocker in force. Raw-point cross-position surfaces and superflex stay BLOCKED. 🚩 NF-W8-0's §1
second-reader flag remains OPEN.
