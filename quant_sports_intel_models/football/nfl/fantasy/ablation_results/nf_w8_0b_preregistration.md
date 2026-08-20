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
