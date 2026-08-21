# NF-W8-0d — pre-registration: the DSR gate-design / power FRONTIER

**Story** NF-W8-0d · **kind** instrument (§0.5 gate design) · `best_alpha = 0` · **DEPLOY-HELD**
**Predecessors** NF-W8-0c (the 4th `dsr_ok`-alone refusal), NF-W7k (the ceiling method), NF-W7j,
NF-W7h, NF-W7f · **Relates** MH2.7, MH2.5/DSR-CONV, NF-D18, NF-W8-0e

⛔ **THIS STORY SHIPS NO MODEL, PROMOTES NOTHING AND RELAXES NO LIVE GATE.** It re-scores no arm,
re-fits nothing, and writes no optimizer input. `DSR_MIN` stays **0.95**, the declared field stays
**4** (MH2.7-guarded), the folds stay as NF-W8-0c ran them. Every number below is arithmetic on
**already-published** per-fold scores.

---

## §1 Why

FOUR consecutive QB/RB stories — NF-W7f, NF-W7h, NF-W7j, NF-W8-0c — were refused by **`dsr_ok`
ALONE** while passing every other registered clause. NF-W8-0c's winner `cond_shift` CLOSED the
cross-position level gap (QB|WR −0.3621 → −0.0546, QB|TE −0.3106 → −0.0032, neither surviving BH),
held PIT on 7/7 folds where the comparator holds 0/7, and posted PBO 0.0. THREE of the four records
named the same remaining remedy: **"a lower-variance design"**.

At four refusals that is a statement about the **evaluation design**, not about QB. Before another
modelling story is funded into the same wall, the design question gets measured.

NF-W8-0c already narrowed the lever to **rows per fold**: 80.7% of the fold-scale variance of the
corrected quantity is within-fold sampling noise at ~685 rows/fold (observed fold SD 0.2607 PPR vs a
mean within-fold SE of 0.2338, leaving a between-fold SD of 0.1146). Seasons were refuted (the fold
count enters DSR only through `√(n−1)`), the field was refuted (4 is the declared minimum and MH2.7
stamped the shrink remedy SUSPECT), drift was refuted (the sign is stable 8/8 folds).

## §2 The question, and the two admissible answers (fixed BEFORE the sweep)

> Sweep the **(rows-per-fold × fold-count)** grid — on a fixed window they trade against each other —
> and compute the projected DSR at each point for an effect of the OBSERVED magnitude. **Hold the
> EFFECT fixed**: this is a design question, not a re-fit.

- **(a)** a **FEASIBLE** design point clears `dsr_ok = 0.95` ⇒ report it; it unblocks the stalled QB
  stories and is registered FORWARD as their design.
- **(b)** **NO** feasible point clears an effect this size ⇒ the gate is **MIS-SPECIFIED for weekly
  QB**; recommend a **registered-FORWARD** gate-design change, stating it and its rationale.
  ⛔ **Never a post-hoc relaxation (E2.1-r), and it is NOT applied here.**

## §3 Decision rule

| # | clause | passes when |
|---|---|---|
| G0 | **reproduction pin** — the instrument's own DSR path reproduces NF-W8-0c's recorded `0.1654` from the published per-fold biases | max abs gap ≤ `1e-9` |
| G1 | **calibration** — the design model, evaluated AT the observed design, brackets the observed DSR | `0.1654` lies inside the simulated 5th–95th percentile |
| G2 | **the lockstep ladder is live** — a proportional dispersion change actually moves the arithmetic | the winner's Sharpe is strictly monotone in `1/c` over the ladder |
| G3 | **the frontier** — some FEASIBLE `(m, T)` point reaches a **median** projected DSR ≥ `0.95` | ⇒ verdict **(a)**; otherwise verdict **(b)** |

**The verdict binds on the MEDIAN, not on `P(clear)`.** A design whose median sits below the bar
does not clear — it only sometimes gets a lucky draw, which is the selection bias DSR exists to
deflate. `P(clear)` is reported beside it as the spread, never as the criterion.

## §4 The design model, and every declared bias

Per test fold `f`, for arm `a`, with `m` rows in the fold:

```
b_I,f = μ_I,f + ε_f          ε_f ~ N(0, σ_row² / m)          σ_row = the per-row error SD
b_a,f = b_I,f + s_a,f        s_a,f = the arm's fitted level shift
δ_a,f = |b_I,f| − |b_a,f|    ← the statistic the registered gate deflates
```

⭐ **The paired shift `s_a,f` carries essentially NO test-row sampling error, and that is the
structural heart of this story.** `b_I,f − b_a,f = −(1/m)·Σᵢ(pointₐ,ᵢ − point_I,ᵢ)` — **the realized
`y` cancels exactly**. `cond_shift` adds `shift · alive` to every draw, so the per-row point
difference is `shift·πᵢ`, whose row SD is bounded by `|shift|·½ ≤ 0.25` PPR against a per-row error
SD of **6.13** PPR. The paired difference therefore carries **≤ 0.2%** of the level's sampling
variance. This is NF-W7k's common-random-numbers lesson one axis over: **the same rows are shared
across arms, so row-sampling error cancels in the paired delta** — it survives only through the
`|·|` KINK, on the folds where the corrected bias crosses zero (2 of 7 for `cond_shift`).

> ⚠️ **SUPERSEDED, kept verbatim above (NF-W7f's discipline: a pre-registration edited after its
> result is no longer one).** The `|shift|·½` step is only exact at `π̄ = 1`: `|shift|` there is the
> RAW shift parameter `S`, while the record carries only the level shift `s_f = S·π̄`, so bounding
> by `s_f/2` is not rigorous for `π̄ < 1`. **The run reports the rigorous form instead** — every
> row's point difference lies in `[0, S]` with mean `s_f`, so Bhatia–Davis gives
> `SD ≤ √(s_f·(S − s_f))`, EVALUATED over a declared `π̄ ∈ {1.0, 0.8, 0.6, 0.4}` grid rather than
> at an assumed `π̄`. The conclusion is unchanged and is now ROBUST rather than contingent: the
> paired share stays **under 1%** across the whole grid. The correction TIGHTENS the argument and
> moves no decision rule (§3 is untouched).

Estimation, all from NF-W8-0c's published per-fold summaries:

- `σ_row` = √mean(sd_err²) over the evaluable folds (**known**, not fitted).
- `μ̄_I` = mean of the identity's per-fold biases; `σ_u²` = Var(b_I) − mean(σ_row²/m₀) (deconvolution).
- `s_a,f` — the observed 7×4 shift matrix, **BOOTSTRAPPED JOINTLY across arms** so the cross-arm
  correlation that drives `SR0` is preserved exactly, and no normality is assumed.

**Declared, unidentified, and bracketed — the scaling law of the non-sampling component.** With only
ONE fold size observed, whether `σ_u` (and the shift's spread) falls as `1/m` is NOT identified.
Both readings are therefore run at every grid point and BOTH are reported:

- `persistent` — regime variation is real and does not average away;
- `averaging` — it is white below the fold and falls as `1/m` (the reading most favourable to the
  rows/fold lever).

**Every declared bias favours the lever, so a NO is conservative** (NF-W7k's discipline): the
feasible windows below are WIDER than the shipped design, the `averaging` law is the lever's best
case, and the model gives the shift no autocorrelation penalty.

## §5 Feasibility — a DESIGN quantity, declared before the sweep

QB rows per season = **2 × 687.3 = 1,374.6** (measured from NF-W8-0c's own folds).

| window | eval seasons | N rows | feasible? |
|---|---|---|---|
| 2022–2025 | 4 | 4,796 (7 evaluable folds) | ✅ **the SHIPPED design** |
| 2019–2025 | 7 | 9,618 | ✅ reachable TODAY (costs train history: 3 seasons of burn-in, not 6) |
| 2019–2030 | 12 | 16,488 | ⏳ calendar-bound (+1 season/year) |
| 20 eval seasons | 20 | 27,480 | ⛔ **UNREACHABLE** — reported only as an *a fortiori* bound |

## §6 What a verdict-(b) recommendation may and may not be

- it is **registered FORWARD**, INERT until a successor story opts in, and ⛔ **not applied to
  NF-W8-0c, whose refusal STANDS** (E2.1-r);
- it may **not** be a field trim — you may pre-register a family, you may not discover one (MH2.2);
  and a trim can delete the arm under test (NF-W7h);
- any exclusion rule must be keyed on a **pre-registered ANCHOR reading**, never on the leaderboard,
  and must be applied **whichever way it moves the bar** (DSR-CONV's non-monotonicity);
- alternatives that were tested and **lost** are reported as losing, not quietly dropped.

## §7 Guards

- the frontier's DSR arithmetic goes through **`nf1_1_model.deflated_sharpe`, BY IDENTITY** — a
  re-implementation would let the projection and the gate drift apart (NF-W7k / NF-C0e).
- the split-field diagnostic (`V` from one set, `n_trials` from another) is expressed as a synthetic
  trial vector fed to **that same function**, and is pinned to agree with it exactly when the two
  sets coincide.
- a known `(effect, design) → DSR` case is pinned with LITERAL inputs and RED-proven.
