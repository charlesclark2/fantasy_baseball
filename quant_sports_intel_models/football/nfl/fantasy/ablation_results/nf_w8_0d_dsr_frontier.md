# NF-W8-0d — the DSR gate-design FRONTIER for weekly QB (**NO_FEASIBLE_DESIGN_CLEARS**, answer **(b)**)

Generated 2026-08-21T01:00:39.568553+00:00 · position **QB** · source record `nf_w8_0c_qb_body.json` · bar `DSR_MIN` **0.95** (INHERITED) · declared field **4**

⚖️ `best_alpha = 0` · **DEPLOY-HELD** · an INSTRUMENT. ⛔ No model ships, nothing is promoted, no arm is re-scored and **no live gate is relaxed**. Every number is arithmetic on NF-W8-0c's already-published per-fold scores — the EFFECT is held fixed, only the DESIGN moves.

## Verdict

- **NO feasible design point clears `dsr_ok = 0.95`** for a QB weekly level effect of the observed magnitude. Best FEASIBLE point anywhere on the grid: 2022-2025 (SHIPPED) · 12 folds × 458 rows (`averaging`) → median DSR **0.3009**.
- and *a fortiori*, the best point on the whole grid **including the deliberately UNREACHABLE window** is 20 eval seasons · 4 folds × 6873 rows (`averaging`) → median DSR **0.6086** — still short of 0.95.
- ⇒ the gate is **MIS-SPECIFIED for this effect at this design**, and the remedy is a **registered-FORWARD gate-design change** (§6). ⛔ It is NOT applied here and NF-W8-0c's refusal **STANDS** (E2.1-r).
- grid: 80 points (38 feasible) × 2000 replicates each

> The verdict binds on the **MEDIAN**, never on `P(clear)`. A design whose median sits below the bar has not cleared — it only sometimes draws a lucky panel, which is exactly the selection bias DSR exists to deflate. `P(clear)` is reported beside it as spread, never as the criterion (prereg §3).

## The pre-registered decision rule, in order

| # | clause | measured | verdict |
|---|---|---|---|
| G0 | the instrument reproduces NF-W8-0c's recorded DSR from the published per-fold biases | 0.1654 vs 0.1654, gap 0.00e+00 (tol 1e-09); split-field carrier is a no-op: True | ✅ |
| G1 | the design model brackets the observed DSR at the OBSERVED design | observed 0.1654 inside sim [0.0034, 0.8174] (median 0.2747) | ✅ |
| G2 | the lockstep ladder is LIVE (a proportional change moves the arithmetic) | winner Sharpe strictly monotone in 1/c | ✅ |
| G3 | some FEASIBLE `(m, T)` reaches a **median** projected DSR ≥ bar | best feasible median 0.3009 vs bar 0.95 | ❌ → **(b)** |

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
| 2022-2025 (SHIPPED) | ✅ | 3 | 1833 | 24.0 | persistent | **0.175** | 0.086 | 2.667 | 3.823 | 0.302 |
| 2022-2025 (SHIPPED) | ✅ | 3 | 1833 | 24.0 | averaging | **0.073** | 0.077 | 4.120 | 5.900 | 0.301 |
| 2022-2025 (SHIPPED) | ✅ | 4 | 1374 | 18.0 | persistent | **0.214** | 0.042 | 2.300 | 2.886 | 0.276 |
| 2022-2025 (SHIPPED) | ✅ | 4 | 1374 | 18.0 | averaging | **0.130** | 0.049 | 3.141 | 4.027 | 0.278 |
| 2022-2025 (SHIPPED) | ✅ | 5 | 1100 | 14.4 | persistent | **0.242** | 0.030 | 1.820 | 2.437 | 0.252 |
| 2022-2025 (SHIPPED) | ✅ | 5 | 1100 | 14.4 | averaging | **0.162** | 0.034 | 2.062 | 3.070 | 0.235 |
| 2022-2025 (SHIPPED) | ✅ | 6 | 916 | 12.0 | persistent | **0.264** | 0.017 | 1.486 | 2.171 | 0.205 |
| 2022-2025 (SHIPPED) | ✅ | 6 | 916 | 12.0 | averaging | **0.227** | 0.025 | 1.664 | 2.574 | 0.225 |
| 2022-2025 (SHIPPED) | ✅ | 8 | 687 | 9.0 | persistent | **0.270** | 0.009 | 1.130 | 1.780 | 0.178 |
| 2022-2025 (SHIPPED) | ✅ | 8 | 687 | 9.0 | averaging | **0.251** | 0.009 | 1.143 | 1.815 | 0.175 |
| 2022-2025 (SHIPPED) | ✅ | 10 | 550 | 7.2 | persistent | **0.278** | 0.004 | 0.946 | 1.455 | 0.147 |
| 2022-2025 (SHIPPED) | ✅ | 10 | 550 | 7.2 | averaging | **0.287** | 0.005 | 0.932 | 1.367 | 0.165 |
| 2022-2025 (SHIPPED) | ✅ | 12 | 458 | 6.0 | persistent | **0.261** | 0.003 | 0.874 | 1.277 | 0.103 |
| 2022-2025 (SHIPPED) | ✅ | 12 | 458 | 6.0 | averaging | **0.301** | 0.003 | 0.769 | 1.073 | 0.148 |
| 2022-2025 (SHIPPED) | ✅ | 14 | 393 | 5.1 | persistent | **0.260** | 0.002 | 0.797 | 1.103 | 0.086 |
| 2022-2025 (SHIPPED) | ✅ | 14 | 393 | 5.1 | averaging | **0.287** | 0.001 | 0.702 | 0.948 | 0.138 |
| 2022-2025 (SHIPPED) | ✅ | 16 | 344 | 4.5 | persistent | **0.262** | 0.001 | 0.733 | 0.996 | 0.074 |
| 2022-2025 (SHIPPED) | ✅ | 16 | 344 | 4.5 | averaging | **0.300** | 0.001 | 0.616 | 0.820 | 0.118 |
| 2022-2025 (SHIPPED) | ⛔ | 20 | 275 | 3.6 | persistent | **0.242** | 0.001 | 0.661 | 0.907 | 0.043 |
| 2022-2025 (SHIPPED) | ⛔ | 20 | 275 | 3.6 | averaging | **0.294** | 0.000 | 0.532 | 0.702 | 0.124 |
| 2019-2025 (widest reachable today) | ✅ | 3 | 3207 | 42.0 | persistent | **0.194** | 0.091 | 2.968 | 4.027 | 0.327 |
| 2019-2025 (widest reachable today) | ✅ | 3 | 3207 | 42.0 | averaging | **0.140** | 0.089 | 6.938 | 8.852 | 0.367 |
| 2019-2025 (widest reachable today) | ✅ | 4 | 2406 | 31.5 | persistent | **0.225** | 0.055 | 2.738 | 3.137 | 0.313 |
| 2019-2025 (widest reachable today) | ✅ | 4 | 2406 | 31.5 | averaging | **0.151** | 0.054 | 5.246 | 5.729 | 0.349 |
| 2019-2025 (widest reachable today) | ✅ | 5 | 1924 | 25.2 | persistent | **0.276** | 0.041 | 2.464 | 2.745 | 0.314 |
| 2019-2025 (widest reachable today) | ✅ | 5 | 1924 | 25.2 | averaging | **0.173** | 0.062 | 4.034 | 4.621 | 0.333 |
| 2019-2025 (widest reachable today) | ✅ | 6 | 1604 | 21.0 | persistent | **0.283** | 0.030 | 2.044 | 2.486 | 0.282 |
| 2019-2025 (widest reachable today) | ✅ | 6 | 1604 | 21.0 | averaging | **0.181** | 0.042 | 2.975 | 3.789 | 0.291 |
| 2019-2025 (widest reachable today) | ✅ | 8 | 1203 | 15.8 | persistent | **0.283** | 0.019 | 1.685 | 2.233 | 0.243 |
| 2019-2025 (widest reachable today) | ✅ | 8 | 1203 | 15.8 | averaging | **0.217** | 0.022 | 2.034 | 2.973 | 0.233 |
| 2019-2025 (widest reachable today) | ✅ | 10 | 962 | 12.6 | persistent | **0.268** | 0.011 | 1.365 | 1.945 | 0.182 |
| 2019-2025 (widest reachable today) | ✅ | 10 | 962 | 12.6 | averaging | **0.209** | 0.005 | 1.460 | 2.272 | 0.166 |
| 2019-2025 (widest reachable today) | ✅ | 12 | 802 | 10.5 | persistent | **0.256** | 0.004 | 1.193 | 1.747 | 0.149 |
| 2019-2025 (widest reachable today) | ✅ | 12 | 802 | 10.5 | averaging | **0.229** | 0.008 | 1.256 | 1.921 | 0.124 |
| 2019-2025 (widest reachable today) | ✅ | 14 | 687 | 9.0 | persistent | **0.249** | 0.002 | 1.111 | 1.593 | 0.114 |
| 2019-2025 (widest reachable today) | ✅ | 14 | 687 | 9.0 | averaging | **0.248** | 0.003 | 1.097 | 1.581 | 0.119 |
| 2019-2025 (widest reachable today) | ✅ | 16 | 601 | 7.9 | persistent | **0.233** | 0.002 | 0.992 | 1.383 | 0.088 |
| 2019-2025 (widest reachable today) | ✅ | 16 | 601 | 7.9 | averaging | **0.253** | 0.002 | 0.981 | 1.337 | 0.107 |
| 2019-2025 (widest reachable today) | ✅ | 20 | 481 | 6.3 | persistent | **0.207** | 0.001 | 0.892 | 1.209 | 0.060 |
| 2019-2025 (widest reachable today) | ✅ | 20 | 481 | 6.3 | averaging | **0.250** | 0.001 | 0.814 | 1.084 | 0.085 |
| 2019-2030 (calendar-bound) | ⛔ | 3 | 5498 | 72.0 | persistent | **0.187** | 0.095 | 3.174 | 4.204 | 0.327 |
| 2019-2030 (calendar-bound) | ⛔ | 3 | 5498 | 72.0 | averaging | **0.319** | 0.088 | 10.604 | 11.935 | 0.426 |
| 2019-2030 (calendar-bound) | ⛔ | 4 | 4124 | 54.0 | persistent | **0.269** | 0.064 | 2.915 | 3.325 | 0.359 |
| 2019-2030 (calendar-bound) | ⛔ | 4 | 4124 | 54.0 | averaging | **0.395** | 0.074 | 7.556 | 7.959 | 0.455 |
| 2019-2030 (calendar-bound) | ⛔ | 5 | 3299 | 43.2 | persistent | **0.306** | 0.051 | 2.726 | 2.939 | 0.354 |
| 2019-2030 (calendar-bound) | ⛔ | 5 | 3299 | 43.2 | averaging | **0.314** | 0.078 | 6.455 | 6.345 | 0.424 |
| 2019-2030 (calendar-bound) | ⛔ | 6 | 2749 | 36.0 | persistent | **0.340** | 0.051 | 2.592 | 2.729 | 0.376 |
| 2019-2030 (calendar-bound) | ⛔ | 6 | 2749 | 36.0 | averaging | **0.305** | 0.068 | 5.335 | 5.513 | 0.417 |
| 2019-2030 (calendar-bound) | ⛔ | 8 | 2062 | 27.0 | persistent | **0.332** | 0.034 | 2.144 | 2.487 | 0.305 |
| 2019-2030 (calendar-bound) | ⛔ | 8 | 2062 | 27.0 | averaging | **0.200** | 0.041 | 3.499 | 4.358 | 0.335 |
| 2019-2030 (calendar-bound) | ⛔ | 10 | 1650 | 21.6 | persistent | **0.314** | 0.019 | 1.865 | 2.291 | 0.276 |
| 2019-2030 (calendar-bound) | ⛔ | 10 | 1650 | 21.6 | averaging | **0.193** | 0.025 | 2.682 | 3.667 | 0.260 |
| 2019-2030 (calendar-bound) | ⛔ | 12 | 1375 | 18.0 | persistent | **0.284** | 0.004 | 1.593 | 2.077 | 0.215 |
| 2019-2030 (calendar-bound) | ⛔ | 12 | 1375 | 18.0 | averaging | **0.182** | 0.019 | 2.060 | 2.964 | 0.178 |
| 2019-2030 (calendar-bound) | ⛔ | 14 | 1178 | 15.4 | persistent | **0.262** | 0.006 | 1.496 | 2.016 | 0.182 |
| 2019-2030 (calendar-bound) | ⛔ | 14 | 1178 | 15.4 | averaging | **0.187** | 0.009 | 1.739 | 2.535 | 0.139 |
| 2019-2030 (calendar-bound) | ⛔ | 16 | 1031 | 13.5 | persistent | **0.250** | 0.006 | 1.368 | 1.875 | 0.138 |
| 2019-2030 (calendar-bound) | ⛔ | 16 | 1031 | 13.5 | averaging | **0.186** | 0.005 | 1.541 | 2.267 | 0.103 |
| 2019-2030 (calendar-bound) | ⛔ | 20 | 825 | 10.8 | persistent | **0.203** | 0.004 | 1.178 | 1.629 | 0.097 |
| 2019-2030 (calendar-bound) | ⛔ | 20 | 825 | 10.8 | averaging | **0.191** | 0.002 | 1.256 | 1.779 | 0.070 |
| 20 eval seasons | ⛔ | 3 | 9164 | 120.0 | persistent | **0.226** | 0.114 | 3.469 | 4.396 | 0.377 |
| 20 eval seasons | ⛔ | 3 | 9164 | 120.0 | averaging | **0.512** | 0.091 | 14.799 | 16.079 | 0.503 |
| 20 eval seasons | ⛔ | 4 | 6873 | 90.0 | persistent | **0.282** | 0.064 | 3.017 | 3.544 | 0.375 |
| 20 eval seasons | ⛔ | 4 | 6873 | 90.0 | averaging | **0.609** | 0.093 | 11.307 | 10.814 | 0.539 |
| 20 eval seasons | ⛔ | 5 | 5498 | 72.0 | persistent | **0.342** | 0.055 | 2.981 | 3.073 | 0.384 |
| 20 eval seasons | ⛔ | 5 | 5498 | 72.0 | averaging | **0.567** | 0.105 | 9.297 | 8.648 | 0.538 |
| 20 eval seasons | ⛔ | 6 | 4582 | 60.0 | persistent | **0.378** | 0.054 | 2.829 | 2.896 | 0.401 |
| 20 eval seasons | ⛔ | 6 | 4582 | 60.0 | averaging | **0.555** | 0.092 | 8.183 | 7.400 | 0.527 |
| 20 eval seasons | ⛔ | 8 | 3436 | 45.0 | persistent | **0.369** | 0.038 | 2.545 | 2.661 | 0.351 |
| 20 eval seasons | ⛔ | 8 | 3436 | 45.0 | averaging | **0.391** | 0.062 | 5.865 | 6.023 | 0.445 |
| 20 eval seasons | ⛔ | 10 | 2749 | 36.0 | persistent | **0.381** | 0.022 | 2.286 | 2.513 | 0.352 |
| 20 eval seasons | ⛔ | 10 | 2749 | 36.0 | averaging | **0.255** | 0.048 | 4.362 | 5.068 | 0.380 |
| 20 eval seasons | ⛔ | 12 | 2291 | 30.0 | persistent | **0.347** | 0.018 | 2.075 | 2.371 | 0.316 |
| 20 eval seasons | ⛔ | 12 | 2291 | 30.0 | averaging | **0.223** | 0.047 | 3.526 | 4.445 | 0.291 |
| 20 eval seasons | ⛔ | 14 | 1964 | 25.7 | persistent | **0.323** | 0.017 | 1.918 | 2.281 | 0.271 |
| 20 eval seasons | ⛔ | 14 | 1964 | 25.7 | averaging | **0.184** | 0.035 | 2.821 | 3.885 | 0.215 |
| 20 eval seasons | ⛔ | 16 | 1718 | 22.5 | persistent | **0.308** | 0.014 | 1.777 | 2.180 | 0.243 |
| 20 eval seasons | ⛔ | 16 | 1718 | 22.5 | averaging | **0.174** | 0.032 | 2.473 | 3.451 | 0.170 |
| 20 eval seasons | ⛔ | 20 | 1375 | 18.0 | persistent | **0.252** | 0.011 | 1.567 | 1.998 | 0.161 |
| 20 eval seasons | ⛔ | 20 | 1375 | 18.0 | averaging | **0.149** | 0.013 | 1.969 | 2.805 | 0.106 |

⭐ Read the last two numeric columns together: the median `SR0` sits **above** the median `SR` at **76 of 80** design points, and `P(SR > SR0)` never reaches ½ at any FEASIBLE point. That is the lockstep invariant showing up in the sweep rather than in the algebra — the two quantities move together, so the gap barely changes sign.

⚠️ **The exceptions, stated rather than smoothed over.** At 4 points the median `SR` does exceed the median `SR0` — differential shrinkage across the field is real, just small — and **0 of them are FEASIBLE**:

| window | feasible | folds `T` | rows/fold `m` | law | median `SR` | median `SR0` | median DSR |
|---|---|---|---|---|---|---|---|
| 2019-2030 (calendar-bound) | ⛔ | 5 | 3299 | averaging | 6.455 | 6.345 | **0.314** |
| 20 eval seasons | ⛔ | 4 | 6873 | averaging | 11.307 | 10.814 | **0.609** |
| 20 eval seasons | ⛔ | 5 | 5498 | averaging | 9.297 | 8.648 | **0.567** |
| 20 eval seasons | ⛔ | 6 | 4582 | averaging | 8.183 | 7.400 | **0.555** |

Every one sits in the **UNREACHABLE** part of the grid, under the lever-FAVOURING `averaging` law, at a fold count of 4–6 — and even there the median DSR tops out at **0.609**. Two things cap it: `√(T−1)` is small at 4 folds, and the DSR statistic's non-normality denominator grows like `SR²`, so once `SR` is large the statistic tends to `(1 − SR0/SR)·√(T−1)·2/√(γ₄−1)` — **bounded**, however sharp the design. Sign-flipping the gap is necessary for the lever; it is nowhere near sufficient.

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
Across the FEASIBLE grid the best point becomes 2019-2025 (widest reachable today) · 20 folds × 481 rows (`averaging`) → median DSR **0.9710**, and **4** feasible points reach the bar on the median:

| window | folds `T` | rows/fold `m` | block wks | law | median DSR | P(clear) |
|---|---|---|---|---|---|---|
| 2019-2025 (widest reachable today) | 20 | 481 | 6.3 | averaging | **0.971** | 0.705 |
| 2019-2025 (widest reachable today) | 20 | 481 | 6.3 | persistent | **0.971** | 0.740 |
| 2019-2025 (widest reachable today) | 16 | 601 | 7.9 | averaging | **0.959** | 0.610 |
| 2019-2025 (widest reachable today) | 16 | 601 | 7.9 | persistent | **0.956** | 0.590 |

⭐ **The fold-count lever's SIGN flips with the sign of `SR − SR0`.** Under the registered gate `SR < SR0`, so `√(T−1)` multiplies a negative gap and more folds make it *worse* — which is exactly why MH2's `DSR_UNREACHABLE` correctly refused the seasons lever. Once `SR > SR0`, the same `√(T−1)` becomes a real lever, and the clearing designs above are **more folds**, not more rows per fold. ⚠️ That is a statement about the two regimes, not a recommendation to add folds today.

⚠️ **Where the clearing points actually sit, stated rather than glossed.** Every one is at the widest reachable window AND the finest admissible fold granularity (6.3–7.9-week blocks). At the SHIPPED half-season granularity (~9-week blocks) over the same window the best R1 point reads median DSR **0.9496** — so R1 buys the bar only together with a finer fold split, and a successor must register BOTH, not just the convention.

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

_runtime 206.3s_
