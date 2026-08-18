# NF-W7k — pre-registration: is QB's `dsr_ok` refusal reachable by a LOWER-VARIANCE design?

**Registered 2026-08-18, BEFORE any NF-W7k score exists.** §0.5 · fantasy weekly · `best_alpha = 0` ·
research-only, **DEPLOY-HELD**. Predecessors: NF-W7f (the scores), NF-W7j (the clause decision).

---

## §0 What this story is, and what it is NOT

NF-W7j left QB refused on **`dsr_ok` alone**, null state `DSR_UNREACHABLE`, with exactly one
registered lever named: **a lower-variance design**. NF-W7f measured and closed the other two
candidates — more folds/seasons (`n` enters DSR only through `√(n−1)`: it scales a positive gap and
cannot create one) and a coherent narrower field (V falls 8.8×, DSR reaches only 0.174 against a
0.95 bar).

This story tests the ONE remaining lever: **Monte-Carlo error in the per-fold delta estimates.**
NF-W7f assembled every bank from 4,000 draws; its winner's per-fold delta series has mean 0.0184
and sd 0.0182 (Sharpe 1.013) against `SR0` 5.482. If a material share of that 0.0182 is *draw
noise* rather than season-to-season signal, more draws shrink the sd, raise the Sharpe, and could
clear `dsr_ok`.

⛔ **This is NOT a claim that it will clear.** A null is a valid and, on the arithmetic below, the
likely outcome. ⛔ **This story does not relax the certification bar.** The full NF-W7f gate,
including `dsr_ok`, stands (E2.1-r): WR (NF-W7e, DSR 0.9852) and TE (NF-W7c, DSR 0.9822) cleared it
and RB (NF-W7h) was held to it. Adopting a lower consumption bar after seeing `dsr_ok` fail would be
the E2.1-r inversion; if a lower bar is wanted it is a PM decision to register FORWARD in NF-W8.

### §0.1 Out of scope
- Every other clause. NF-W7f's 22-clause gate and NF-W7j's component decision are untouched.
- Any change to the arms, the field, the folds, the marginals, Σ, π̂, or the joint construction.
  **The only quantity this story varies is the RNG stream and the draw count.**
- RB / WR / TE. This record certifies nothing about them.

---

## §1 The design — a CHEAP GATE that decides whether an expensive run is funded

The gate runs FIRST and **gates** the expensive high-draw re-measurement; it does not follow it.

**Phase A (this run).** Re-score the SAME 8 folds, the SAME 6 eligible labels
(`zm_conditional`, `zm_floor`, `zm_climatology`, `zm_over`, `mixall_learned`, `single_copula`) —
everything held byte-identical — at **S = 5 draw seeds** and **two draw counts**.

| knob | registered value |
|---|---|
| seeds | `20260818` (NF-W7f's, the BASE) + `base + k × 7_000_003` for k = 1..4 |
| draw counts | **4,000** (NF-W7f's, the primary) and **1,000** (the scaling control) |
| folds | NF-W7f's 8, unchanged |
| labels | `fp_qb_marginal_calibration.ELIGIBLE` (the 6 the DSR field is built from) |

Seed spacing is `7_000_003` because the assembly draws from `seed + row_block_start` and the
availability Bernoulli from `seed + 1_000_000 + row_block_start`; a spacing far above both offsets
makes stream aliasing across seeds impossible, so two "different" seeds cannot silently share a
stream and report zero Monte-Carlo error (the false-STOP direction).

**Phase B (funded only if Phase A says so).** Re-score NF-W7f's FULL field at the draw count
registered in §3 and recompute the whole gate.

---

## §2 The decomposition

For each label pair, per fold *f* and seed *s*, `δ(f,s) = CRPS(best_foil) − CRPS(arm)`.

- `σ²_MC(D)` — pooled WITHIN-fold, ACROSS-seed variance at draw count `D`. This is the
  Monte-Carlo error of a **one-seed** delta estimate — the error NF-W7f's numbers actually carry.
- `σ²_between` — ACROSS-fold variance of the per-fold seed MEAN.
- `σ̂²_het = σ²_between − σ²_MC / S` — genuine season-to-season heterogeneity. **Reported signed**;
  a negative estimate is printed as measured and never clamped to zero in the record.
- MC share of a one-seed delta's variance = `σ²_MC / (σ̂²_het + σ²_MC)`.

**Projection.** At draw multiplier `k` (relative to 4,000), a one-seed delta's sd is
`σ(k) = √(σ̂²_het + σ²_MC / k)`, and `k → ∞` gives the **CEILING** `σ_het`. A projected series is
built by rescaling the BASE-SEED series' centred deviations to the target sd, which preserves the
mean and every standardized shape moment (skew, kurtosis) that `deflated_sharpe` reads. The
projected series is scored by the harness's OWN `nf1_1_model.deflated_sharpe`, by identity — never
a re-implementation.

---

## §3 The pre-registered decision rule

Evaluated in this order. **`G0`–`G2` are validity conditions; `G3` is the decision.**

| # | clause | rule | failure |
|---|---|---|---|
| **G0** | `reproduction_pin` | at the BASE seed / 4,000 draws, every re-scored per-fold CRPS equals NF-W7f's STORED value to ≤ `1e-9` | **RAISE** — the decomposition would describe a re-derivation, not the object NF-W7f scored |
| **G1** | `seed_is_live` | for every label, the across-seed sd is `> 0` on every fold | **RAISE** — a seed that does not reach the draws reports zero MC error, the FALSE-STOP direction |
| **G2** | `mc_variance_scales_as_one_over_draws` | `σ²_MC(1,000) / σ²_MC(4,000)` for the winner's delta lies in **[2.0, 8.0]** (nominal 4.0) | verdict **`UNDEFINED_SCALING`** — the 1/D extrapolation the decision rests on is not valid here; **no decision is issued and nothing is funded** |
| **G3** | `ceiling_clears_the_bar` | the **upper** end of the percentile-bootstrap CI95 on `DSR_ceiling` (k → ∞) is `≥ DSR_MIN = 0.95` | verdict **`MC_LEVER_EXHAUSTED`** — see below |

### The two verdicts

- **`MC_LEVER_EXHAUSTED`** (G3 fails) — no draw count clears `dsr_ok`, because even removing
  *all* Monte-Carlo error leaves the winner's deflated Sharpe below the bar. Phase B is **NOT
  funded**. QB is confirmed `DSR_UNREACHABLE` with the lever exhausted, and ⛔ **no draw/fold/season
  re-test trigger is published** (publishing one would be the NF-D18 misleading direction).
- **`FUND_HIGH_DRAW_RUN`** (G3 passes) — Phase B is funded at **`D2` = the smallest of the ladder
  `{16,000 · 64,000 · 256,000}` whose projected DSR ≥ 0.95**, else 256,000. The ladder and the cap
  are registered HERE, before any score, so the draw count cannot be chosen after seeing the answer.

### §3.1 Precedence — the CEILING binds, the MC SHARE is descriptive
The story's framing asks whether MC error is "a large fraction" of the 0.0182 sd. That share is
**reported**, but it is a PROXY. `G3` asks the exact question — *can any draw count clear
`dsr_ok`?* — so **if the two disagree, `G3` binds.** Registered here, forward, because the
disagreement is foreseeable: `SR0` is built from the dispersion of the four arms' Sharpes and the
winner is itself one of those four trials, so shrinking MC error raises the winner's Sharpe **and**
`SR0` together. Whether the gap closes is an arithmetic question this run answers; it is not
assumable in either direction, and a large MC share alone would not settle it.

### §3.2 A registered no-op identity
`project_dsr` at the OBSERVED sds must return NF-W7f's recorded DSR **exactly** (`0.0`). A
projection that cannot reproduce the unprojected number is not measuring the same object
(the NF-W7f `matched_foil_identity` shape).

### §3.3 Monotonicity control
Removing noise can only raise `|SR|`, so the winner's projected Sharpe must be **non-decreasing in
`k`**. A violation is a coding defect and RAISES rather than being reported as a finding.

---

## §4 What Phase A cannot decide
- It cannot certify QB. `G3` passing funds a MEASUREMENT; only Phase B's full-gate re-score could
  certify, and every other clause would have to hold at the new draw count.
- It says nothing about the OTHER positions, or about NF-W8's consumption question.

## §5 Flagged for a 2nd reader (governance)
A DSR gate re-read is governance-adjacent. Protections registered here: the bar is UNCHANGED at
`DSR_MIN = 0.95`; the field is UNCHANGED (no trim — MH2.2); the folds are UNCHANGED; the decision
rule, the seeds, the draw ladder and the `D2` cap are all fixed BEFORE any score exists; and the
only admissible ship path runs through Phase B's FULL gate, not through this story. A
`MC_LEVER_EXHAUSTED` verdict **closes** the lever — it does not weaken the bar.
