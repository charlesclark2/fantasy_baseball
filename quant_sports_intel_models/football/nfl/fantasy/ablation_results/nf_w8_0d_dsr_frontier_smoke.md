# NF-W8-0d — the DSR gate-design FRONTIER for weekly QB (**NO_FEASIBLE_DESIGN_CLEARS**, answer **(b)**)

Generated 2026-08-21T01:00:57.996232+00:00 · position **QB** · source record `nf_w8_0c_qb_body.json` · bar `DSR_MIN` **0.95** (INHERITED) · declared field **4**  ·  ⚠️ **SMOKE**

⚖️ `best_alpha = 0` · **DEPLOY-HELD** · an INSTRUMENT. ⛔ No model ships, nothing is promoted, no arm is re-scored and **no live gate is relaxed**. Every number is arithmetic on NF-W8-0c's already-published per-fold scores — the EFFECT is held fixed, only the DESIGN moves.

## Verdict

- **NO feasible design point clears `dsr_ok = 0.95`** for a QB weekly level effect of the observed magnitude. Best FEASIBLE point anywhere on the grid: 2022-2025 (SHIPPED) · 16 folds × 344 rows (`averaging`) → median DSR **0.3027**.
- and *a fortiori*, the best point on the whole grid **including the deliberately UNREACHABLE window** is 2022-2025 (SHIPPED) · 16 folds × 344 rows (`averaging`) → median DSR **0.3027** — still short of 0.95.
- ⇒ the gate is **MIS-SPECIFIED for this effect at this design**, and the remedy is a **registered-FORWARD gate-design change** (§6). ⛔ It is NOT applied here and NF-W8-0c's refusal **STANDS** (E2.1-r).
- grid: 12 points (12 feasible) × 200 replicates each

> The verdict binds on the **MEDIAN**, never on `P(clear)`. A design whose median sits below the bar has not cleared — it only sometimes draws a lucky panel, which is exactly the selection bias DSR exists to deflate. `P(clear)` is reported beside it as spread, never as the criterion (prereg §3).

## The pre-registered decision rule, in order

| # | clause | measured | verdict |
|---|---|---|---|
| G0 | the instrument reproduces NF-W8-0c's recorded DSR from the published per-fold biases | 0.1654 vs 0.1654, gap 0.00e+00 (tol 1e-09); split-field carrier is a no-op: True | ✅ |
| G1 | the design model brackets the observed DSR at the OBSERVED design | observed 0.1654 inside sim [0.0024, 0.8160] (median 0.2867) | ✅ |
| G2 | the lockstep ladder is LIVE (a proportional change moves the arithmetic) | winner Sharpe strictly monotone in 1/c | ✅ |
| G3 | some FEASIBLE `(m, T)` reaches a **median** projected DSR ≥ bar | best feasible median 0.3027 vs bar 0.95 | ❌ → **(b)** |

## §1 ⭐ The LOCKSTEP invariant — why "a lower-variance design" is not a lever

`deflated_sharpe` reads the winner's Sharpe `SR` **and** the deflation benchmark `SR0 = std(trial Sharpes)·z(N)` — and the winner is one of those trials (NF-W7k). A design change that multiplies **every** arm's per-fold dispersion by a common `c` scales every trial Sharpe by `1/c`, hence `SR0` by `1/c`, hence

> `SR − SR0  ↦  (SR − SR0)/c` — **its SIGN is invariant.**

Clearing the bar needs the DSR statistic `(SR−SR0)·√(T−1)/√denom ≥ Φ⁻¹(0.95) > 0`, hence needs `SR > SR0`. **So a purely proportional dispersion lever can never flip an `SR ≤ SR0` refusal — at any row count, fold count or draw count.** And when `SR < SR0` the gap is negative, so a *sharper* design makes it **more** negative:

| dispersion × | winner Sharpe | `SR0` | `SR − SR0` | DSR |
|---|---|---|---|---|
| 1 | 1.0641 | 1.6652 | -0.6011 | 0.1654 |
| 0.5 | 2.1283 | 3.3304 | -1.2022 | 0.0825 |
| 0.25 | 4.2565 | 6.6609 | -2.4043 | 0.0422 |
| 0.1 | 10.6413 | 16.6522 | -6.0108 | 0.0236 |
| 0.01 | 106.4132 | 166.5215 | -60.1083 | 0.0154 |

- the sign of `SR − SR0` is invariant across the ladder: **True**
- DSR **falls monotonically as the design sharpens**: **True** — a 100×-sharper design takes the gate from 0.1654 to 0.0154.

⇒ the remedy **three** consecutive records prescribed — "a lower-variance design" — is not merely ineffective here, it is **counter-productive**, because the variance reduction is *shared across the field*. That is the generic case: the arms score the same rows with the same draws (common random numbers). A variance lever helps only to the extent it shrinks the WINNER's dispersion **more** than the field's — a residual the frontier below measures rather than asserts.

This generalises NF-W7k (draws) and MH2's `DSR_UNREACHABLE` (folds) to the statement that actually covers the prescription: **any** shared variance lever.

## §2 The rows/fold lever, measured on the statistic the gate READS

NF-W8-0c's decomposition of the **level** reproduces exactly: observed fold SD **0.2607** PPR vs a mean within-fold SE of **0.2338** ⇒ **80.7%** of the fold-scale variance is row sampling at 687 rows/fold, leaving a between-fold SD of **0.1146**.

⚠️ **But the gate does not deflate the level — it deflates the PAIRED statistic** `δ = |b_I| − |b_a|`, and

> `b_I,f − b_a,f = −(1/m)·Σᵢ(pointₐ,ᵢ − point_I,ᵢ)` — **the realized `y` cancels exactly.**

`cond_shift` adds `shift·alive` to every draw, so the per-row point difference is `shift·πᵢ` with `π ∈ [0,1]`; its row SD is bounded by `|shift|/2 ≤ 0.2267` PPR against a per-row error SD of **6.14** PPR. **The paired difference therefore carries at most 0.14% of the level's sampling variance** — an upper bound; the realised share is smaller still.

The level's noise re-enters `δ` **only through the `|·|` KINK**, on the folds where the corrected bias crosses zero (2 of 7 for `cond_shift`). ⇒ **measuring the rows/fold lever on the LEVEL over-states it**; this is NF-W7k's common-random-numbers lesson one axis over — the arms share the same rows, so row-sampling error cancels in the paired delta.

## §3 The frontier — rows/fold × fold count, under the REGISTERED gate

On a fixed window the two axes trade: `m = N / T`. Both declared scaling laws for the non-sampling fold-scale variance are run at every point (`persistent` = regime variation is real; `averaging` = it is white below the fold and falls as `1/m`, the reading most FAVOURABLE to the lever). **Every declared bias favours the lever, so a NO is conservative** (NF-W7k's discipline).

| window | feasible | folds `T` | rows/fold `m` | block wks | law | median DSR | P(clear) | median `SR` | median `SR0` | P(`SR`>`SR0`) |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022-2025 (SHIPPED) | ✅ | 4 | 1374 | 18.0 | persistent | **0.229** | 0.040 | 2.264 | 2.970 | 0.305 |
| 2022-2025 (SHIPPED) | ✅ | 4 | 1374 | 18.0 | averaging | **0.152** | 0.065 | 3.668 | 4.184 | 0.295 |
| 2022-2025 (SHIPPED) | ✅ | 8 | 687 | 9.0 | persistent | **0.291** | 0.020 | 1.057 | 1.668 | 0.210 |
| 2022-2025 (SHIPPED) | ✅ | 8 | 687 | 9.0 | averaging | **0.274** | 0.020 | 1.115 | 1.756 | 0.180 |
| 2022-2025 (SHIPPED) | ✅ | 16 | 344 | 4.5 | persistent | **0.256** | 0.000 | 0.779 | 1.055 | 0.055 |
| 2022-2025 (SHIPPED) | ✅ | 16 | 344 | 4.5 | averaging | **0.303** | 0.000 | 0.684 | 0.874 | 0.180 |
| 2019-2025 (widest reachable today) | ✅ | 4 | 2406 | 31.5 | persistent | **0.192** | 0.020 | 2.786 | 3.169 | 0.260 |
| 2019-2025 (widest reachable today) | ✅ | 4 | 2406 | 31.5 | averaging | **0.219** | 0.060 | 5.263 | 5.721 | 0.365 |
| 2019-2025 (widest reachable today) | ✅ | 8 | 1203 | 15.8 | persistent | **0.282** | 0.005 | 1.696 | 2.201 | 0.240 |
| 2019-2025 (widest reachable today) | ✅ | 8 | 1203 | 15.8 | averaging | **0.199** | 0.025 | 1.941 | 2.887 | 0.180 |
| 2019-2025 (widest reachable today) | ✅ | 16 | 601 | 7.9 | persistent | **0.207** | 0.005 | 1.018 | 1.450 | 0.065 |
| 2019-2025 (widest reachable today) | ✅ | 16 | 601 | 7.9 | averaging | **0.279** | 0.005 | 0.928 | 1.272 | 0.125 |

⭐ Read the last two numeric columns together: the median `SR0` sits **above** the median `SR` at **12 of 12** design points, and `P(SR > SR0)` never reaches ½ at any FEASIBLE point. That is the lockstep invariant showing up in the sweep rather than in the algebra — the two quantities move together, so the gap barely changes sign.

## §4 WHERE the bar comes from — one MEASURED-INACTIVE arm carries most of `V`

`SR0 = √V · z(N)` and `V` is a **sample variance over the field's Sharpes**, so one arm can set the bar every other arm must clear:

| arm | per-fold Sharpe | share of `Var(trial Sharpes)` |
|---|---|---|
| `cond_shift` | +1.0641 | 5.3% |
| `cond_scale` | +1.5869 | 17.8% |
| `avail_relevel` | -1.9083 | 72.9% |
| `leg_scale` | +0.9838 | 4.1% |

⭐ **`avail_relevel` alone carries 72.9% of the deflation dispersion** — and NF-W8-0c **measured that arm INACTIVE**: its own per-form peeking oracle's ceiling is −0.0018 PPR and the π clamp binds on 88–95% of rows, so the mixture-weight channel is structurally unable to move the level (NF-D20 / NF-W6d). Its whole delta series is ≈ −0.0012 PPR: its Sharpe is the ratio of two numbers at the numerical floor.

⚠️ **And a variance lever cannot fix this, because an inactive arm's Sharpe is scale-free** — shrinking noise shrinks its mean and its sd together, so `|SR|` does not fall. That is precisely why the lockstep ratio `SR0/SR` is flat across the whole frontier.

### Alternatives tested — and the one that LOST

⛔ A labelled DIAGNOSTIC, **not** a re-read of NF-W8-0c: re-scoring a failed gate on a better-looking statistic is the E2.1-r inversion in its most literal form. These rows exist so the recommendation can say what was tried and what failed.

| selection statistic | winner Sharpe | `SR0` | DSR |
|---|---|---|---|
| abs_delta (REGISTERED) | 1.0641 | 1.6652 | 0.1654 |
| squared_delta (kink-free) | 0.9440 | 1.6013 | 0.0410 |

The obvious candidate — removing the `|·|` kink by deflating the **squared**-bias delta — is **WORSE**, not better. The kink is not the binding defect; the field's Sharpe dispersion is. Recorded as losing rather than dropped.

## §5 The verdict-(b) recommendation — registered FORWARD, ⛔ NOT applied here

**R1 — extend DSR-CONV's `V`-exclusion from "pre-registered DEGENERATE" to "pre-registered-TEST-MEASURED INACTIVE".** DSR-CONV (PRs #689/#690) already establishes *degenerate ∈ `n_trials`, ∉ `V`*, on the argument that a lose-by-construction arm's Sharpe is not a draw from the search's Sharpe population. An arm whose **own per-form peeking-oracle ceiling** falls below a pre-registered materiality floor is in exactly that position for exactly that reason — its Sharpe is a ratio of two quantities at the numerical floor. The rule must be:

1. **FORWARD-ONLY and INERT** until a successor story opts in — DSR-CONV's own shape;
2. keyed on the arm's **ANCHOR reading** (the per-form oracle ceiling that NF-D16 (g‴) already requires every §0.5 story to compute), **never on the leaderboard** — you may pre-register a family, you may not discover one (MH2.2), and a trim chosen because an arm LOST can even delete the arm under test (NF-W7h);
3. applied **whichever way it moves the bar** — exclusion is NON-monotone: dropping a near-mean arm *raises* `SR0` (DSR-CONV);
4. reported with BOTH figures, the un-excluded one binding until a story registers the convention forward.

**What it would buy, as a DIAGNOSTIC.** With `avail_relevel` out of `V` and `n_trials` still charged at 4, the OBSERVED design reads DSR **0.8778** — note that this is **still below the bar**, so R1 is not by itself a licence to ship anything.
Across the FEASIBLE grid the best point becomes 2019-2025 (widest reachable today) · 16 folds × 601 rows (`averaging`) → median DSR **0.9605**, and **2** feasible points reach the bar on the median:

| window | folds `T` | rows/fold `m` | block wks | law | median DSR | P(clear) |
|---|---|---|---|---|---|---|
| 2019-2025 (widest reachable today) | 16 | 601 | 7.9 | averaging | **0.961** | 0.660 |
| 2019-2025 (widest reachable today) | 16 | 601 | 7.9 | persistent | **0.954** | 0.575 |

⭐ **The fold-count lever's SIGN flips with the sign of `SR − SR0`.** Under the registered gate `SR < SR0`, so `√(T−1)` multiplies a negative gap and more folds make it *worse* — which is exactly why MH2's `DSR_UNREACHABLE` correctly refused the seasons lever. Once `SR > SR0`, the same `√(T−1)` becomes a real lever, and the clearing designs above are **more folds**, not more rows per fold. ⚠️ That is a statement about the two regimes, not a recommendation to add folds today.

⚠️ **Where the clearing points actually sit, stated rather than glossed.** Every one is at the widest reachable window AND the finest admissible fold granularity (7.9–7.9-week blocks). At the SHIPPED half-season granularity (~9-week blocks) over the same window the best R1 point reads median DSR **0.8779** — so R1 buys the bar only together with a finer fold split, and a successor must register BOTH, not just the convention.

### What a successor actually does with this

1. register R1 FORWARD in its own pre-registration — the inactivity test (a per-form oracle ceiling below a stated materiality floor), the exclusion's direction-blindness, and BOTH DSR figures reported;
2. register the DESIGN in the same document — window and fold count are now design quantities with a measured consequence, not defaults inherited from `weekly_projection.TEST_BLOCKS`;
3. re-run NF-W8-0c's declared 4-arm field UNCHANGED under that registration. ⛔ It does not re-read NF-W8-0c's numbers — a registration written after seeing a gate fail only earns its verdict on a fresh run (MARGIN2→3, NF-W6b-C, W7→W7b: the repo's own CONSTRAINT_REFUSED → fresh-registration → ship pattern);
4. ⚠️ and expect it to be a REAL contest, not a formality — R1 at the observed design reads 0.8778, below the bar. This story says the wall is in the gate's design; it does not say the arm is on the other side of it.

**Not recommended, and why (both scored above, both losing):** a kink-free selection statistic (DSR falls to 0.0410); and any field trim, which is forbidden outright (MH2.2 / NF-W7h) — R1 is a `V`-composition rule keyed on an anchor, **not** a smaller field: the excluded arm keeps paying full multiplicity in `n_trials`.

## §6 Scope, and what this does NOT close

- NF-W8-0c's `dsr_ok` refusal **STANDS**; nothing here re-reads it (E2.1-r). The same is true of NF-W7f / NF-W7h / NF-W7j.
- ⛔ **No re-test trigger in seasons, folds or rows is published.** The lockstep invariant is DETERMINISTIC — no `n` overturns it — so a "come back with more data" trigger would be the actively-misleading direction NF-D18 / MH2 (g″) warns about.
- this closes the **shared-variance** lever (rows/fold, folds, draws, a proportionally sharper estimator). A lever that shrinks the WINNER's dispersion **differentially** is UNTESTED here, not refuted — the frontier measures the residual differential shrinkage this field happens to have and finds it too small, which is a statement about this field, not about every conceivable estimator.
- the scaling law of the non-sampling fold-scale variance is **not identified** from one fold size; both readings are run and reported, and the lever-favouring one does not change the verdict.
- R1 is a **recommendation**, not a change: no live gate, no shared instrument and no registered field is touched by this story.

## Null classification (the shared instrument, verbatim)

- **state** `DSR_UNREACHABLE` · `folds_have` 7 · `max_field_size` 0 · `field_remedy_admissible` None
- **reason** — `qb_abs_level_bias`: the winner's per-fold Sharpe 1.064 sits at or BELOW the 4-arm field's deflated benchmark SR0 1.665, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, PRE-REGISTERED field, not more seasons — and ⛔ only if such a field was pre-registered; this is NOT a licence to re-cut a field you have already scored (MH2.7). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.
- **retest_trigger** — field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)

⚠️⚠️ **READ THE TRIGGER AGAINST §1.** `classify_null` is RIGHT that no fold count and no field size clears — and it then prescribes, verbatim, *"the only lever left is a lower-variance design (more rows per fold / a sharper metric)"*. **That is precisely the lever this story measures, and §1 shows it is VOID** whenever the variance reduction is shared across the field, which is the generic case under common random numbers. The trigger is not wrong about its own axis; it is a prescription the instrument cannot check, and it is the sentence that sent THREE consecutive records (NF-W7f, NF-W7j, NF-W8-0c) at a wall. ⇒ **a second forward recommendation, R2: when `DSR_UNREACHABLE` fires, `classify_null` should compute the lockstep check — `sign(SR − SR0)` under proportional shrinkage — and, when the sign is negative, state that the variance lever is closed too, rather than naming it.** Same shape as MH2.7's own lesson (i): a defect corrected N times downstream is a defect in the INSTRUMENT. ⛔ Not implemented here — `cv_power` is a SHARED instrument pinned by cross-vertical guards (MH2.7 lesson ii), so changing it is a successor's deliberate step.

_runtime 2.6s_
