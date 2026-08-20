# NF-W8-0c — pre-registration: the QB BODY-level comparison (assembled `zm_floor` vs `direct_points`)

Registered 2026-08-19 (branch `nf-w8-0c`), **BEFORE any scoring run**. This document is committed
ahead of the path proof and the decisive run; nothing in §1–§10 may be re-read after a result
lands (E2.1-r). Post-run findings go in §12, appended — never edited into the registration.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger · research-only. Nothing
serves, nothing publishes, nothing retrains, and **this story writes NO optimizer input** —
NF-W8-0b's shipped input stands untouched (§9).

Registered forward by **NF-W8-0b §12.6(1)**: *"The QB gap lives in the BODY of the assembled
distribution … a successor registers a BODY-level comparison (which quantile ranges carry the
gap, and whether it is a mixture-weight or a per-leg-scale effect) — ⛔ NOT another read of the
tails, which are now measured closed."*

---

## §1 What the predecessors established (PINS — recorded figures, never re-derived here)

| fact | figure | source |
|---|---|---|
| the assembled QB ranking point reads BELOW realized | **−0.4237 PPR** (tail-completed, row-pooled) | NF-W8-0b §12.1 |
| the surviving cross-position contrasts | QB\|WR **−0.3621** (MDE 0.2036) · QB\|TE **−0.3106** (MDE 0.1903) | NF-W8-0b §12.1 |
| on the SAME rows, assembly vs `direct_points` at QB | **−0.3505 PPR**, of which the TAIL channel is **+0.0173 = 4.9%** | NF-W8-0b §12.2 |
| ⇒ ~95% of the QB generator gap is in the distribution BODY | — | NF-W8-0b §12.2 |
| QB PIT is FLAT — this is not a calibration defect | `zm_floor` max-decile-dev **0.0281**, clears the 0.05 bar **8/8** | NF-W7f |
| `direct_points` at QB clears that bar **0/8** (mean **0.0959**) and LOSES CRPS (2.5834 vs 2.5645) | — | NF-W7f |
| the tail lever is CLOSED deterministically | mechanism bounded by a 0.0193 PPR cross-position spread — ~19× short | NF-W8-0b §12.1 |
| a prior-history-fitted per-position POINT constant faces a non-stationarity floor of its own size | 0.511 PPR | NF-W8-0 §12.3a / NF-W8-0b §12.5c |

**The tension this story exists to resolve, stated plainly:** a PIT-flat, best-on-record QB
distribution whose central mass sits ~0.35 PPR below the construction that is better LEVELLED
against realized. ⛔ The tail is measured closed and is **not re-read here**.

⛔ **NF-W8-0's and NF-W8-0b's records are DECIDED.** They are not re-run, re-derived or re-read by
this story; their per-fold figures enter only as REPRODUCTION PINS (§7).

---

## §2 The pinned inputs (nothing here is selected in this story)

- **Fold axis** — NF-W7c's, verbatim: 8 expanding-window half-season folds 2022H1…2025H2 on the
  W6d matrix; gate league `full_ppr`; target `league_fantasy_points`; draws 4000; seed inherited
  (`SA._SEED` + `AVAIL_STREAM_OFFSET`) so the reproduction pins can hit at 1e-9.
- **Ranking point** — NF-W8-0b's DECIDED read: `fp_tail_point.tail_completed_point`, imported by
  reference. ⛔ Not re-litigated; the incumbent grid-mean read is emitted BESIDE it for disclosure
  exactly as NF-W8-0b does.
- **Consumed generators** — `fp_cross_position.CONSUMED_GENERATOR_OF`, imported: QB `zm_floor`
  (Option B), RB `direct_points`, WR `mixall_learned`, TE `single_copula`. The QB incumbent bank
  is built through `run_nf_w8_0_cross_position.build_position_banks` — the predecessors' one code
  path — so the generators keep exactly one implementation (NF-W7d).
- **Gate constants — every one INHERITED BY REFERENCE, un-relaxed (E2.1-r):** PIT bar
  `FA.PIT_MAX_DECILE_DEV = 0.05` · `XP.BH_Q = 0.10` · `XP.ALPHA = 0.05` · `XP.PBO_MAX` ·
  `XP.DSR_MIN = 0.95` · `XP.OS_GAP_TIE_PCT` · `XP.MIN_PRIOR_ROWS = 50`.
- **The QB Option-B caveat and NF-W7c's promote blockers are INHERITED IN FULL.** This story
  re-certifies nothing.

---

## §3 Family A — the DECOMPOSITION (a measurement, not a contest)

Two exact, deterministic decompositions of the assembled QB level. Neither fits anything, so
NF-W8-0 §12.3a's non-stationarity floor cannot apply to either.

### §3.1 The mechanism decomposition (⭐ an exact additive identity)

The assembled total is a LINEAR form in the legs and the realized target is the SAME linear form
(`FA.score_realized` is `raw @ w`). Writing `legmean_i` for the mean over rows and draws of leg
`i`'s mixture draw and `realized_i` for `mean(raw[:, i])`:

> **mean(point) − mean(y) = READ + Σ_i w_i · (legmean_i − realized_i)**

where `READ = mean(point) − Σ_i w_i · legmean_i` is the ranking-point read channel (NF-W8-0b's
truncation + re-weight, reported for continuity, **not re-opened**). The residual of this identity
is floating-point zero **by construction**, and the harness ASSERTS it (`identity_residual ≤
IDENTITY_TOLERANCE`) rather than restating it in prose — NF-W8-0b §12.5(e): when a conclusion
rests on an arithmetic identity, assert the identity against the artifact.

⭐ The leg means come from **`MX.mixture_leg_draws` — the SAME function the scored assembly
calls** — never a re-implementation (NF-W7d: a diagnostic that owns its own copy of the scored
logic passes silently when the scored path breaks).

Each leg's term is split further, exactly, into an AVAILABILITY and a CONDITIONAL-LEVEL part.
With `π̄ = mean(pi_used)`, `ā = mean(QM.activity_indicator(raw))`, `m̄_i = legmean_i / π̄` and
`c̄_i = realized_i / ā`:

> `legmean_i − realized_i = (π̄ − ā) · m̄_i + ā · (m̄_i − c̄_i)`

so the story's question — *"is it a mixture-weight or a per-leg-scale effect?"* — is answered by
which of the two columns carries the mass, per leg. ⚠️ `ā = 0` or `π̄ = 0` makes the split
UNDEFINED for that fold and is reported as such, never zero-filled (NF1.7 (a)).

### §3.2 The band decomposition (where along the quantile function the gap lives)

For the assembled bank `Q_c` and the `direct_points` bank `Q_s` on the IDENTICAL rows, the grid
mean difference is exactly `h · Σ_ℓ (Q_c(ℓ) − Q_s(ℓ))` with `h = 1/199`. Partitioned into **10
contiguous level bands** of the 199-level grid, the band contributions SUM EXACTLY to the
grid-mean gap — asserted, not asserted-in-prose. Reported per band: contribution in PPR, share of
the total gap, and the band's level range. This localises NF-W8-0b's −0.3505 along the quantile
function and is the direct answer to §12.6(1)'s first clause.

⚠️ **Pooling convention, load-bearing (NF1.8, and NF-W8-0b's own headline was first written the
wrong way):** every pooled figure in family A is **Σ over ROWS**, with the mean-of-fold-means
convention reported beside it. A bound quoted from a differently-pooled summary of the same
quantity is a different number wearing the same name.

### §3.3 What family A can and cannot conclude

Family A is a MEASUREMENT. It has no gate and produces no verdict; it NAMES the channel. A
channel carrying < `CHANNEL_MATERIAL_PPR = 0.05` PPR (≈ NF-W8-0b's whole measured tail mechanism,
a design quantity fixed here before any score) is reported as IMMATERIAL — demonstrable ≠ material
(NF-W6).

---

## §4 Family B — the declared REPAIR field (⛔ never trimmed or grown after a score — MH2/MH2.2)

**One coherent family, declared on mechanistic grounds:** every real arm re-levels the SAME
quantity — the assembled QB conditional level — through one of the four channels family A can
name. ⛔ `direct_points` is a DIFFERENT ARCHITECTURE and is therefore **NOT a member of this
field** (MH2 (a): a family gets its own pre-registered field; bundling an unrelated mechanism
over-taxes a real finding through DSR's cross-trial dispersion — NF-W6b-C / NF-W7f). It is scored
as family C, on its own registered clause set.

**Estimator discipline (inherited from NF-W8-0 §4, verbatim in kind):** every arm parameter is fit
on **PRIOR FOLDS' OOF rows only** — for fold k, the test blocks 1…k−1, strictly earlier in time.
Fold 1 (2022H1) has no prior OOF ⇒ **identity by construction**, so the contest runs on the 7
evaluable folds; a fold with < `MIN_PRIOR_ROWS = 50` prior OOF rows keeps identity, flagged. Every
parameter targets the **POINT bias** (the consumer-visible quantity), never the draw mean.

### The four real arms (trials; `declared_field_size = 4`)

| arm | channel | parameter (prior-fold OOF) | what it touches |
|---|---|---|---|
| `cond_shift` | conditional level, additive | `δ = (mean y − mean point) / mean π_used` | the PLAYED total only; the zero atom is untouched |
| `cond_scale` | conditional level, multiplicative | `κ = mean y / mean point` | every priced leg's bank, one shared κ |
| `avail_relevel` | mixture weight | `Δπ = mean π_used · (mean y / mean point − 1)` | π̂ only; every leg bank untouched |
| `leg_scale` | per-leg scale | `κ_i = Σ realized_i / Σ legmean_i` per priced leg | each priced leg's bank separately |

**Admissibility, registered in advance (a violated clause makes the arm INELIGIBLE for that fold,
recorded — never silently clipped, NF1.7 (a)):**
- any `κ ≤ 0` ⇒ **INELIGIBLE outright** (a negative scale inverts a leg — NF-D16/NF-TR2b);
- `κ` outside `[MIN_SCALE, MAX_SCALE] = [0.5, 2.0]` ⇒ for `cond_scale`/`avail_relevel` the arm is
  INELIGIBLE for that fold; for `leg_scale` that LEG keeps `κ_i = 1.0` and is listed in
  `out_of_band_legs`, and the arm is INELIGIBLE for the fold once **more than ⅓ of the priced
  legs** are out of band;
- a leg whose prior-OOF absolute contribution `|w_i · legmean_i|` is below
  `MIN_LEG_CONTRIB_PPR = 0.01` keeps `κ_i = 1.0` — it cannot materially move the level and its
  ratio is noise (the NF-W6 materiality lesson, at the parameter level);
- `Δπ` is applied as `π_adj = clip(π̂ + Δπ, 0, 1)` and then passed through the UNCHANGED
  `MX.clamp_pi`, so the marginal-admissibility floor still binds and is still counted.

**Incumbent / null:** `identity` — the certified `zm_floor` assembly as consumed.

### Anchors (SCORED every run, never trials — excluded from the PBO/DSR trial field, MH2.1 (a))

- **`oracle_<form>` — one per real-arm FORM** (`oracle_cond_shift`, `oracle_cond_scale`,
  `oracle_avail_relevel`, `oracle_leg_scale`): the same form with its parameter fit on the TEST
  fold itself. Each is the CEILING of its own form's level channel, and there is one per form
  because the forms NEST (`cond_scale` ⊂ `leg_scale`) and a single field-wide ceiling would veto a
  legitimately-better nested form as a false inversion (**NF-D16 (g‴)**). Reported: the real arm's
  captured fraction of its own form's ceiling.
  ⚠️ An oracle that FAILS TO FIT is a failed clause, never a pass (NF1.7 (a)).
- **`over_cond_shift`** — `OVER_SCALE = 2.0 × δ`, **registered to LOSE**. ⛔ If it WINS it is left
  FAILING and DECOMPOSED, never re-labelled: that is a refuted MAGNITUDE hypothesis (the fit
  UNDER-corrects), obtainable only because the anchor was SCORED (NF-D20 / NF-D14 (g′)).
- **`permuted_leg_scale`** — the fitted `κ_i` vector cyclically shifted across the PRICED legs,
  deterministic. It preserves the population of corrections and destroys their per-leg assignment:
  it must NOT beat `leg_scale`.
- **`climatology_bank`** — every row's bank is the prior folds' empirical quantiles of realized QB
  points. ⭐ **THE TWO-SIDED ANCHOR (NF1.8):** it achieves ~zero level bias while carrying ZERO
  skill, so it WINS the objective and MUST LOSE CRPS decisively. A criterion this degenerate wins
  is fatal; scoring it every run is what proves the level objective was never promoted into a
  selection criterion.
- **`nihilist_zero`** — bank ≡ 0. Must lose CRPS and the PIT bar decisively (NF-D11: score the
  degenerate, never reason about it).

### Selection + the clause battery

**Objective (the quantity under repair):** the pooled |QB point bias| over the evaluable folds.
**Selection:** the smallest |pooled bias| among arms that are ELIGIBLE and pass the two hard
CONSTRAINTS (`pit_preserved`, `no_crps_harm`). Tie within 1 SE → the registered simplicity order
`cond_shift` → `cond_scale` → `avail_relevel` → `leg_scale` (parameter count, then per-stat
marginal drift). Registered before any score.

⚠️ **The constraints are FLOORS, never targets (E2.1-r / NF1.8).** PIT is not maximised, CRPS is
not maximised; each is a bar an arm must clear to be selectable, and the objective decides among
those that clear.

| clause | rule |
|---|---|
| `pit_preserved` | the arm's randomized-PIT max-decile-dev ≤ **0.05** on EVERY evaluable fold (the incumbent clears 8/8); the pooled mean is reported beside it |
| `no_crps_harm` | paired one-sided t over evaluable folds of (arm − incumbent) CRPS: refused iff p < 0.05 AND mean > 0 |
| `reduces_bias` | paired one-sided p < 0.05 that \|bias_incumbent\| − \|bias_arm\| > 0 per fold |
| `beats_permuted` | pooled \|bias\| strictly below `permuted_leg_scale`'s |
| `degenerates_lose` | `climatology_bank` AND `nihilist_zero` both lose CRPS to the arm, pooled |
| `banks_move_deliberately` | the arm's bank differs from the incumbent's (an arm that cannot ACT is INACTIVE, never a pass — NF-D20) AND the NON-QB banks are byte-identical to the incumbent run |
| `pbo_ok` | PBO < `XP.PBO_MAX` OR Bailey os-gap ≤ `XP.OS_GAP_TIE_PCT` (the NF1.8 tied-field discipline, pre-registered because `cond_scale` and `leg_scale` are near-clones whenever the true artifact is a uniform scale) |
| `dsr_ok` | DSR ≥ **0.95** on the winner-vs-incumbent per-fold \|bias\| deltas, trial Sharpes over the 4 real arms |

**Family structure, stated:** family A = a measurement (no tests). Family B = the repair contest
(one gated comparison: best real arm vs `identity`; `declared_field_size = 4` passed to
`classify_null`, `field_remedy_admissible` READ, not the prose — MH2.7). Family C = ONE
pre-registered architecture comparison on three axes. Family A′ = the cross-position gap re-tested
under the winner, BH q=0.10 over the same 6 pairs — the SAME statistic
(`XP.pairwise_gap_tests`), one implementation (E9.61).

---

## §5 Family C — the hybrid-architecture comparison (`direct_points` for QB)

The story card's first arm, scored HONESTLY and on its own field: this is a CONSUMPTION tradeoff
(ranking level vs distributional calibration), **not a re-certification** and not a member of
family B's trial set.

Axes, all on the identical rows and folds:
1. **PIT** — clears the inherited 0.05 bar on every evaluable fold? (a fold count, reported);
2. **CRPS** — paired one-sided t vs the assembly;
3. **|level bias|** — paired one-sided t vs the assembly.

`architecture_state`, three registered values:
- **`ASSEMBLY_DOMINATES`** — the assembly is no worse on all three axes and strictly better on ≥1;
- **`DIRECT_POINTS_DOMINATES`** — the mirror;
- **`ARCHITECTURE_DISAGREEMENT_UNRESOLVED`** — ⭐ **the classified-null state**: each construction
  wins at least one axis, so **neither may claim the QB slot on this evidence**. It is recorded as
  a genuine disagreement with the trade DISCLOSED, never resolved by preference; the consumption
  decision is a PM call (NF-W8-0 §12.5(3)'s open question, one position deeper).

"No worse" means: not failing the PIT bar where the other passes, and not significantly worse at
`ALPHA` on the paired axis. A tie on every axis is `ARCHITECTURE_DISAGREEMENT_UNRESOLVED` — a tie
is not a win (NF1.8).

---

## §6 The verdict rule (fixed in advance)

1. **`QB_BODY_GAP_CLOSED`** — a family-B winner passes ALL clauses AND, under that winner,
   **neither `QB|WR` nor `QB|TE` is BH-rejected** in family A′. ⇒ the hybrid is cross-rankable:
   **`cross_rankable: true`** (raw-point cross-position surfaces and superflex unblocked at the
   stated MDE).
2. **`QB_HYBRID_INDICATED`** — no family-B winner is admissible, AND `architecture_state ==
   DIRECT_POINTS_DOMINATES`, AND swapping QB's generator to `direct_points` closes family A′.
   ⇒ a PM CONSUMPTION decision is indicated; **`cross_rankable: false`** here, because this story
   ships no consumption change (§9).
3. **`QB_BODY_GAP_PERSISTS`** — otherwise. The QB hybrid architecture stands as-is;
   **`cross_rankable: false`**; the finding is recorded as a classified null with the margin
   stated in the unit that grows.
4. **`UNDEFINED`** — a reproduction pin failed, fewer than 4 evaluable folds, or a position was
   skipped: the harness did not run; never read as any verdict (NF1.7 (a)).

**Null classification.** A refusal resting on anchors/constraints is `CONSTRAINT_REFUSED` with
`binding_half` named and **no data trigger** (NF-D18). One resting on a reachable statistical gate
is classified by `cv_power.classify_null(declared_field_size=4, degenerates_excluded_from_v=True)`,
recorded VERBATIM, with `field_remedy_admissible` read as a machine flag. ⚠️ **A published
`classify_null` trigger describes FAMILY B ONLY** — family A is a deterministic decomposition and
family A′'s bar is inherited; reading a fold trigger onto either would be the NF-D18
misleading-trigger class, and the record says so explicitly.

---

## §7 Reproduction pins (hard clauses, all states)

| pin | target | tolerance |
|---|---|---|
| `generator_reproduces` | each consumed generator's per-fold CRPS vs its §2 record pin (`XP.GENERATOR_RECORD_PINS`) | 1e-9 |
| `qb_incumbent_matches_w7f` | QB `zm_floor` per-fold CRPS **and** PIT max-decile-dev vs the NF-W7f record | 1e-9 |
| `non_qb_bias_matches_w8_0b` | the WR/RB/TE per-fold `bias_identity` on the tail-completed point vs the NF-W8-0b record | 1e-9 |
| `identity_assembly_is_byte_identical` | this story's assembly wrapper at `played_shift = 0` vs `MX.assemble_mixture_bank` | exact (0.0) |

⛔ **FULL PRECISION IS LOAD-BEARING.** Every stored score is written at full precision: a
`round(…, 6)` caps every pin at ~5e-7 against a 1e-9 tolerance and returns UNDEFINED at every
position (the NF-W8-0 smoke's catch, guarded here too). An absent or path-proof record is "the
control DID NOT RUN" — a failed clause, never a pass.

---

## §8 Runtime plan (the >2-min rule)

- **In-session:** SYNTHETIC verification only — the full runner path driven on fabricated banks
  (no lake, no W6d dispatch), every guard, and the RED proof. The marginal dispatch is
  ~370–600 s/fold cold and no bank cache exists on this machine, so a real 1-fold path proof is
  itself an operator command.
- **OPERATOR (laptop):** `--smoke` (1 fold, 300 draws, artifact `_smoke` — path proof, no
  verdict), then the decisive run (8 folds × 4000 draws). Assembly cost measured at ~2.2 s per QB
  bank of ~680 rows at 4000 draws ⇒ ~40 s/fold of NEW work; the run is dominated by the W6d
  marginal dispatch exactly as its predecessors were. `--rewrite-report` re-derives every verdict
  from the stored per-fold arm summaries at zero refit cost.

---

## §9 What this story ships (registered now, so it cannot grow after a result)

- The RECORD (`nf_w8_0c_qb_body.{json,md}`), the `cross_rankable` flag, and the per-fold QB rows.
- ⛔ **NO optimizer input parquet.** NF-W8-0b's shipped input stands untouched; regenerating it
  under a repaired QB generator is a SUCCESSOR's step, named in the record, never a silent side
  effect of this run. ⛔ This runner is REFUSED AT IMPORT if any of its artifact paths would
  collide with NF-W8-0's or NF-W8-0b's decided paths (the NCAAF-P2.1 S1-serve lesson).
- ⛔ No consumption change, no re-certification, no promotion. The board-displacement read on the
  most recent fold is REPORTED (does the repair move ranks at all?) and consumed by nothing.

## §10 Limitations (registered now, so they cannot become post-hoc rescues)

- The four arms correct a LEVEL (and, via the scale forms, a uniform per-leg scale). A
  rank-dependent or covariate-dependent generator artifact is out of scope — a successor's fresh
  registration.
- `leg_scale` and `cond_scale` re-level a CERTIFIED per-stat marginal (NF-W6d). Their per-leg
  marginal drift is measured and DISCLOSED; an admissible win under either form is a win that
  trades a per-stat certification scope for an assembled level, and the record must say so.
- The prior-fold OOF estimator mixes eras (NF-TR2b). Unlike NF-W8-0's point layer, these arms move
  the DISTRIBUTION, so the non-stationarity floor is measured here through the per-form oracles
  (each form's captured fraction of its own ceiling), not assumed away.
- The QB Option-B weaker-footing caveat travels unchanged: `dsr_ok` was never relaxed for QB and
  is not relaxed here.
- Family A′ inherits family A's resolution: a residual gap below the pairwise MDE survives
  undetected at every position equally. A null here is "no residual artifact larger than X PPR",
  never "no artifact" (MH2.6).

---

## §11 BUILD-TIME AMENDMENTS (appended BEFORE any scoring run; §1–§10 untouched)

Recorded here rather than in §12 because they landed while the harness was being BUILT — before
the path proof, before any fold was scored, and therefore before any result could have shaped
them. Both were found by this story's own RED proof, not by review.

**§11.1 ⭐ THE §3.1 IDENTITY WAS TAUTOLOGICAL IN THE FIRST CUT, AND ITS GUARD PASSED ON NOTHING.**
The decomposition first defined the READ channel as `mean(point) − Σ wᵢ·legmeanᵢ` — i.e. as the
RESIDUAL. That makes `identity_holds` **vacuously true for ANY leg means**, including wrong ones:
the clause could not fail, so it tested nothing (the NF-C0e "a test that reads a value back under
the key the code writes" class, inside the very guard written to honour NF-W8-0b §12.5(e)). The
RED half of the guard (`the identity FAILS when the leg means are not the ones the point came
from`) is what exposed it: it stayed GREEN on a deliberately-perturbed leg-mean vector.

**Cure (structural, not another test):** `assemble_qb` now also returns the assembled total's OWN
per-row draw mean — a quantity the decomposition does not construct — and the reported identity is
the LINEARITY residual `Σ wᵢ·legmeanᵢ − mean(total)` beside the arithmetic reconstruction.
`identity_holds` requires BOTH. A wrong leg-mean vector now breaks it, and the RED proof pins that
in two places: the unit fixture AND the real runner path (a leg-mean drift of 1% turns the
end-to-end path proof red). ⇒ **the general rule: a decomposition whose residual term is DEFINED
as the residual has no identity to assert — give it an anchor it did not compute.**

**§11.2 The path proof asserts NON-VACUITY, not merely that it ran.** The synthetic end-to-end
proof additionally asserts that every DECLARED arm was fitted, assembled and ACTED, that every
per-form oracle was formed, and that the comparator and both degenerates were scored — because a
field scored with arms silently absent is not the declared field (MH2 / NF1.7 (a)). The RED proof
carries the matching break (`an_arm_silently_drops_out_of_the_declared_field`).

**§11.3 In-session verification is SYNTHETIC by design (prereg §8, restated).** The real `--smoke`
needs the W6d marginal dispatch (~370–600 s/fold cold; **no bank cache exists on this machine** —
checked, in this worktree and in every sibling checkout), so it is an OPERATOR command under the
repo's >2-min rule. The in-session proof drives the SAME runner functions with only the marginal
banks and the direct-points learner stubbed, and its verdict is necessarily `UNDEFINED` because
synthetic banks cannot reproduce a certified record — which is the fail-closed answer, not a
limitation being excused.
