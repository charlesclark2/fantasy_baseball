# MLB-TV2-0 — Node 1: PRE-REGISTRATION

**Story:** MLB-TV2-0 — the totals-ceiling diagnosis (which lever binds: dispersion features or distributional shape?).
**Spec:** `plan_specs/mlb/mlb-tv2-0.yaml`. **Date:** 2026-08-25.
**Code twin:** `betting_ml/scripts/mlb_tv2_0_ceiling_diagnosis.py` — every constant below is frozen
*in that module*, and `test_prereg_document_matches_the_registered_battery` pins this document to it
so neither can drift from the other.

> **⛔ COMMITTED BEFORE ANY SCORING.** At the time of this commit **no statistic involving a realized
> outcome `y` has been computed on this population**. The only thing looked at is the POPULATION
> COUNT — row counts, tier, date range, and how many rows carry an off-champion stamp — which a
> population declaration requires and which is reported in §2 below.
>
> `best_alpha = 0` · `bet_paused` stays `true` · **market-blind** · **nothing serves**. This is a
> projection/pricing-quality diagnosis. It contains no edge, win-rate, or ROI claim, and it builds
> **neither** fix — it measures which fix the evidence licenses.

---

## 1. Question

The served `total_runs` predictive is a **symmetric Normal** `(μ_i, σ_i)` from the v6 NGBoost
point-and-scale champion, with **no serve-time calibrator**; `P(over) = norm.sf(line, μ, σ)`.
Its recorded wall is not a mystery of one statistic — it is a wall that **487 features and three
learner classes did not move**. The TV2 epic names two candidate levers:

- **(a) feature TYPE** — everything in the contract predicts the **mean**; nothing carries
  per-game **DISPERSION**. → `TV2-1` (a dispersion feature store).
- **(b) distributional ARCHITECTURE** — a forced **unimodal, symmetric** shape against a
  right-skewed target (MH2.6: realized `z` skew **0.735**; mass below the predictive median
  **0.573** vs a nominal 0.500). → `TV2-2` (a mixture-density head).

**TV2-0 measures which lever binds. It builds neither.** The instrument is a ladder of **oracles**
— transformations of the served `(μ, σ)` against realized `y` — not fitted arms competing to ship.
An oracle bounds what a lever could ever deliver; if the ceiling on a lever is small, no amount of
feature engineering or architecture work inside that lever can be worth funding.

## 2. Population — the SERVED rows

MH2.6's lesson governs the choice: **a backtest cannot see a serving-path defect**, and the routing
decision this story gates is about the **served** `P(over)`. So the population is the rows the app
actually served, joined to realized finals.

| | |
|---|---|
| champion | E13.11 bundle — `v6` (post_lineup) / `pre_lineup_v6` (morning) |
| **PRIMARY tier** | **`post_lineup`** — the final served number |
| SECONDARY tier | `morning` (`pre_lineup_v6`) — a declared replication; see §7 |
| era | champion fit date **2026-06-23** → anchor = newest date carrying finals |
| source | `daily_model_predictions` ⋈ `mart_game_results` (DuckDB over the S3 lakehouse) |
| served row rule | latest `inserted_at` per `(game_pk, prediction_type)`, `is_backfill = FALSE` |
| games | `game_type = 'R'`, final score present (INC-34: the gate's own results source) |
| exclusion | rows whose `totals_model_version` names an **off-champion** model (the 15 MH2.1 rollback rows) |
| **measured n (POPULATION COUNT ONLY)** | post_lineup **773 → 758** after the off-champion drop · morning **765** · era `2026-06-23 → 2026-08-23` · **0** null `(μ, σ)` |

Every served row **post-dates the champion's fit**, so the whole era is out of sample by
construction — MH2.1's "split at the incumbent's fit date" rule holds without a split.

**⛔ MARKET-BLIND.** No odds column is read anywhere in this harness — not
`total_line_consensus`, not `bovada_*`, not `over_prob_consensus`. The serving-relevant probability
statistic is therefore evaluated **at the model's own mean** (MH2.6 §2's construction), which needs
no line. A guard test asserts the SQL and the module contain no market stem.

### Folds

**K = 5 contiguous DATE blocks**, balanced by row count. Every oracle parameter for block *k* is
estimated on the other K−1 blocks (**cross-fit**), so no row's oracle sees its own outcome. Date
blocking (not random) because the served era is a time series and a random split would leak
same-slate structure.

⚠️ **Why not the 2016–2026 offline matrix (MH2.8's population, 14,813 eval rows).** Stated in
advance so it is a declared deviation, not a convenience: (i) it is **not point-in-time** (MH2.5
Lock 9), so a conclusion drawn there is a *ceiling*, not a statement about the served number — the
exact substitution MH2.1's rollback punished; (ii) reproducing it requires re-assembling the feature
matrix **and re-fitting NGBoost**, which is a fitted arm and sits against this story's prohibition;
(iii) the routing question is about the served `P(over)`. The cost is power, and §8 states it.

## 3. The battery — three legs, all oracles, **μ held EXACTLY at the served value**

Every arm keeps `μ_i` byte-identical to the served `pred_total_runs`. Only the **scale** and the
**shape** of the predictive change. That is what makes "which lever" answerable at all.

### LEG A — DISPERSION (the `TV2-1` lever)

| arm | construction | what it bounds |
|---|---|---|
| `A1_sigma_level` | `σ_i → ĉ·σ_i`, `ĉ = sqrt(mean(z²))` on the out-of-block rows (**1 dof**) | the **global scale** sub-channel — achievable by a **recalibrator**, NOT by features |
| `A2_sigma_mu_binned` | `σ_i →` out-of-block RMS residual within row *i*'s **μ-decile** | heteroscedasticity already implied by the **current** contract (μ is its output) |
| `A3_sigma_clairvoyant` ⛔ | `σ_i →` out-of-block RMS residual within row *i*'s **\|y−μ\|-decile** | ⛔ **UPPER BOUND.** Uses the answer to choose the bin. **If A3 does not close the gap, no dispersion feature ever can.** |
| `A_ctrl_permuted` ⛔ | A3's machinery with the binning driven by a **shuffled** `\|y−μ\|` | matched **row-blind** control — catches a closure bought by capacity rather than information (NF-W7f) |

### LEG B — SHAPE (the `TV2-2` lever)

| arm | construction | what it bounds |
|---|---|---|
| `B1_shape_skewnormal` | out-of-block skew-normal fit to `z`, used as the predictive's standardized law | the specific mechanism MH2.8 identified (its DSR failure is **cited, not re-opened**) |
| `B2_shape_empirical` ⛔ | predictive quantile function `= μ_i + σ_i·Q̂_k(p)`, `Q̂_k` = the **empirical** quantile function of out-of-block `z` (linear-interpolated, tail-extended) | ⛔ **UPPER BOUND.** The best possible shape given a location and a scale — no parametric family assumed. **If B2 does not close the gap, no architecture change can.** |

⭐ **`B2` already contains `A1`.** A pooled empirical `z` law absorbs any global scale error, so
`B2`'s closure is *scale + shape*. The **architecture lever** is therefore measured as
`closure(B2) − closure(A1)` — what shape buys **beyond** what a recalibrator already buys. Stating
this before scoring is what stops a shape verdict from quietly banking a calibrator's work.

### LEG C — IRREDUCIBILITY

| arm | construction |
|---|---|
| `C1_combined` ⛔ | `A3` then `B2` re-estimated on the `A3`-standardized `z` — the **joint** ceiling of both levers |
| `C2_location_probe` ⛔ | a **diagnostic, never a lever**: `SD(μ)` across games, `Var(μ)/Var(y)`, and the two readings of `std_pred` (§6) |

## 4. Metrics

Computed identically for every arm, over each arm's own predictive CDF `F_i`.

- **PIT** — continuity-corrected and randomized, generalized from MH2.6's house instrument to an
  arbitrary `F`: `u_i = F_i(y_i − 0.5) + U·(F_i(y_i + 0.5) − F_i(y_i − 0.5))`. `total_runs` is an
  integer and the predictive is continuous; reading `F(y)` straight off is lumpy, and inclusive
  integer interval bounds inflate coverage (the E2.1-r defect).
- **`pit_ks`** — **PRIMARY.** KS statistic of `u` against Uniform(0,1). Chosen over `pit_mdd` as
  primary because it uses the whole ECDF and is the more powerful of the two at this `n`;
  `pit_mdd` is reported beside it.
- **`p_over_gap`** — **CO-PRIMARY CONFIRMATION.** `stated − realized` where
  `stated = 1 − F_i(μ_i)` and `realized = mean(y_i > μ_i)`, **evaluated at the model's own mean**
  (market-blind). This is the serving-relevant quantity: the product prints `P(total > line)`, a
  CDF read near the middle.
- Reported, never a criterion: `pit_mdd`, `crps` (a **constraint**, never a criterion — E2.1-r),
  `cov80`/`cov50` (**floors**, never targets — NF1.8), `var_z_pooled`, `z_skew`,
  `z_excess_kurtosis`, `mass_below_predictive_median`, `bias`, `rmse`.

CRPS for a non-Normal arm is the shared-grid `2∫pinball` on a **499-level** quantile grid, validated
against the Normal closed form on the incumbent (MH2.8's construction); a `|Δ| > 1e-3` **raises**.

## 5. The yardstick — the calibrated-null floor

A "share of the failure closed" is meaningless without knowing what a **perfect** predictive would
score at this `n`. So, for each statistic `S`:

- **`floor_S`** = the median of `S` under the **calibrated null**: outcomes re-drawn from the served
  predictive itself, `n` and per-game `(μ, σ)` held fixed, rounded to integers (the target is a
  count). `N_NULL = 2000` replicates, seed `42`.
- **`band_S`** = the null's 95% band; **`material_S` = half the band width**. A movement smaller
  than `material_S` is **inside sampling noise** and is recorded as **0 (inactive)** — NF-W6's
  "demonstrable ≠ material", applied to closure.
- **`gap_S` = `S(incumbent) − floor_S`** — the failure the levers are being asked to close.
- **`closed_X` = `(S(incumbent) − S(X)) / gap_S`** — the share of that failure arm `X` closes.

⚠️ **PRECONDITION — the rule does not run on a non-defect.** If `S(incumbent)` for the PRIMARY
statistic lies **inside** its calibrated-null 95% band, there is no measurable failure to attribute
and the verdict is **`NO_MEASURABLE_DEFECT`**. A closure share computed against a `gap` that is
itself noise is the NF1.7 (a) vacuous anchor.

⚠️ An oracle landing **below the floor's lower tail** is flagged **`OVER_PEEKING`**: it is a loose
upper bound (its closure may be cited as "does not bind" but never as "achievable") — NF-W7i.

## 6. ⚠️ FLAGGED BINDING CLAUSE — `std_pred` names two different quantities

The spec's clause reads *"how much of the **std_pred**/PIT failure closes when sigma alone is
fixed?"*. **Flagged, not edited.** This repo uses `std_pred` for two different statistics:

| reading | definition | where | measured value cited by the spec |
|---|---|---|---|
| **mean-spread** | `STDDEV(pred_total_runs)` — the spread of the **point predictions** across games | `betting_ml/scripts/validate_v2_gates.py:34` (the **V2 gate**, bar **≥ 2.0**) | **0.773** ⟵ the spec's number |
| **predictive SD** | `mean(sqrt(μ + μ²/r))` — the mean **per-game predictive scale** | `betting_ml/scripts/train_totals.py:121` (Story 10.2, bar ≥1.5) | 3.73 (the NegBin challenger) |

⭐ **The `0.773 vs ≥2.0` figure the spec cites is the MEAN-SPREAD reading — a property of `μ`.**
Consequently: **a σ-oracle is ARM-INVARIANT for it.** Every arm in this battery holds `μ` fixed by
design, so no leg can move `SD(μ)` — by construction, not by result. Registering a leg against a
statistic it cannot move would ship a gate that is décor (the NF-MARGIN2 rule).

⇒ **Registered treatment.** `std_pred_meanspread` and `std_pred_predictive_sd` are **both**
reported, under distinct names, as **LOCATION-channel diagnostics in `C2`** — never as a leg-A
outcome and never in the decision rule. The PIT/`p_over_gap` half of the spec's clause is what
Leg A is scored on. This is a flag for the PM, and it carries a consequence the record must state
loudly: **if the binding channel is the LOCATION spread, neither TV2-1 nor TV2-2 addresses it.**

## 7. ⭐ THE DECISION RULE — registered forward, before any scoring

Evaluated on the **PRIMARY tier** (`post_lineup`) and the **PRIMARY statistic** (`pit_ks`), with
`p_over_gap` as a **confirmation**. Define on `pit_ks`:

```
closed_calibrator = closed(A1)                                # global scale — a recalibrator, not a feature
closed_feature    = closed(A3) - closed(A1)                    # per-game σ beyond a scale fix  = TV2-1's CEILING
closed_shape      = closed(B2) - closed(A1)                    # shape beyond a scale fix       = TV2-2's CEILING
closed_combined   = closed(C1)                                 # the joint ceiling
```

Each is set to **0** if it is smaller than `material_pit_ks`. Then, **in this order**:

| # | condition | OUTCOME | routing (the spec's, verbatim) |
|---|---|---|---|
| 0 | `pit_ks(incumbent)` inside its calibrated-null band | `NO_MEASURABLE_DEFECT` | nothing funded; report the MDE |
| 1 | `closed_combined < 0.50` | **`IRREDUCIBLE`** | neither TV2-1 nor TV2-2 funded; **E13.6b Part B UN-HOLDS** |
| 2 | `closed_feature ≥ 0.50` **and** `closed_shape < 0.20` | **`FEATURE-BOUND`** | **TV2-1 funded first** |
| 3 | `closed_shape ≥ 0.50` **and** `closed_feature < 0.20` | **`SHAPE-BOUND`** | **TV2-2 funded first** |
| 4 | `closed_feature ≥ 0.20` **and** `closed_shape ≥ 0.20` | **`BOTH`** | TV2-1 **then** TV2-2, the epic's staged order |
| 5 | otherwise | **`INDETERMINATE`** | routes as `IRREDUCIBLE` — no lever demonstrated majority closure |

**CONFIRMATION clause.** A `FEATURE-BOUND`, `SHAPE-BOUND` or `BOTH` verdict additionally requires
that the **winning lever also closes ≥ 0.20 of `gap` on `|p_over_gap|`**. If it does not, the
verdict is demoted to `INDETERMINATE` and the disagreement is reported. This exists so a verdict
cannot be won on a distributional statistic while the quantity the product actually prints does not
move.

**SUB-STATE (a label, not a new route).** Inside `IRREDUCIBLE`, if `closed_calibrator ≥ 0.50`, the
record additionally reports **`CALIBRATOR-SUFFICIENT`**. It maps to the **same registered action**
(neither lever funded, the calibrator un-holds) — it only records that the calibrator route is
licensed *positively* rather than as the residual. ⛔ It is not a fifth route and does not change
what is funded.

**SECONDARY tier.** The `morning` replication is reported in full. A disagreement is reported and
discussed; it **does not change the verdict** — declared here so the primary cannot be swapped for
whichever tier gives the nicer answer (E2.1-r).

**`classify_null`.** Applied to each leg whose closure is null, with the per-block closure series as
the fold record. Where the instrument cannot name the binding gate — specifically the
**arm-invariant** `std_pred_meanspread` of §6 — it is **hand-recorded** as `INACTIVE (structural)`
per the cv_power card's interim rule, never rendered as a fold/season re-test trigger (NF-D18).

## 8. Power, and what a null here would and would not mean

`n ≈ 758` primary rows. Two things are stated in advance:

- The **oracle** legs peek, so they carry far more power than an honest fit would — that is what
  makes a *ceiling* measurable at this `n`. What is NOT available at this `n` is a σ-conditional
  **partition validation**: MH2.6 measured that the served σ's own CV (0.0481) means a 10-quantile
  partition needs **≈1,155 served games** to clear its 2.0-SE bar. ⇒ **no `Var(z)`-by-σ-decile
  number is read in this study**, and none is needed: the oracle ladder answers the ceiling question
  without conditioning on σ.
- An **MDE curve** is computed for both levers by planting deficits of known size (§9's machinery,
  run over a grid) and recording the smallest planted deficit the rule routes correctly. A null is
  then reported as *"no lever larger than the MDE"*, never as a shrug (NF1.8).

## 9. ⭐ POSITIVE CONTROLS — the legs must separate PLANTED causes

Per the standing recipe (HV2-1 ruling 3 / the `cv_power` card's defect 4). Synthetic frames reuse
the **real served `(μ_i, σ_i)`** and `n`; only `y` is planted. All four are RED-proven.

| control | planted truth | required outcome | required NON-outcome |
|---|---|---|---|
| `PC_clean` | `y ~ round(Normal(μ_i, σ_i))` — the served predictive is correct | **`NO_MEASURABLE_DEFECT`** | must NOT route to any lever |
| `PC_dispersion` | `y ~ round(Normal(μ_i, s_i))`, `s_i = σ_i·exp(τ·w_i)/E[·]` with true σ-CV **0.35**; the mean scale preserved | **`FEATURE-BOUND`** | `closed_shape` must be **< 0.20** |
| `PC_shape` | `y = round(μ_i + σ_i·SN*)`, `SN*` = a standardized skew-normal, `α = 4` — correct mean **and** correct per-game SD, wrong SHAPE only | **`SHAPE-BOUND`** | `closed_feature` must be **< 0.20** |
| `PC_both` | both planted together | **`BOTH`** | — |

**A control failure is a design failure, and it is caught before any real-data statistic is read.**
If a leg fails to separate, the leg is redesigned and the controls re-run, with the redesign
documented — the real-data read happens only after the controls pass. That order is the whole point
of putting node 2 before node 3.

**RED-proofs** (`betting_ml/tests/mlb_tv2_0_red_proof.py`), each asserting the mutation **landed on
disk** and that the asserted predicate **moved** (#682 / #815 / the byte-identical-tail trap):
1. break the σ oracle → `PC_dispersion` must stop routing `FEATURE-BOUND`.
2. break the shape oracle → `PC_shape` must stop routing `SHAPE-BOUND`.
3. delete the materiality floor → `PC_clean` must stop returning `NO_MEASURABLE_DEFECT`.
4. delete the cross-fitting → the row-blind control `A_ctrl_permuted` must stop being inert.
5. delete the market-blind assertion → the guard must go red.

## 10. Disciplines

- **Reproduction pin `1e-9`** on a committed synthetic fixture (`mlb_tv2_0_fixture.json`), so the
  whole battery is bit-reproducible from a seed on data that ships with the repo.
- **Tolerance-scoped comparisons** anywhere a stochastic draw is involved; ⛔ no bitwise artifact
  comparison.
- **Runtime**: a small slice is timed first; anything expected > 2 min is handed to the operator
  paste-ready with runtime / artifact / success criteria.
- **Prohibitions honoured**: no fitted arm competes to ship (every non-incumbent arm is an ⛔ oracle
  or ⛔ control); no serve-time change; MH2.8's DSR failure is **cited as evidence, never re-scored**;
  **no odds-store read of any kind**.

## 11. What this study cannot say

- Nothing about **edge, win rate, ROI or CLV**. `best_alpha = 0`; no bet rode on this model.
- An oracle ceiling is **what a lever could at most deliver**, never what it will. A large ceiling
  licenses **funding a story**, not a shipped improvement.
- The verdict is about the **served post_lineup** population in a **2-month** window under **one**
  champion. It does not generalise to a different champion, and the record says so.
