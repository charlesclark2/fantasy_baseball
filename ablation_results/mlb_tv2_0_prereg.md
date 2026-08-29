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

---

# 12. ⭐ AMENDMENT — the node-2 redesign

**Committed BEFORE any statistic involving a realized outcome was computed on this population.**
Everything below was driven by the POSITIVE CONTROLS on synthetic frames — the real served `(μ, σ)`
and `n` were used (as §9 registers), a realized `y` was not. §9's own clause is what licenses this:
*"A control failure is a design failure, and it is caught before any real-data statistic is read. If
a leg fails to separate, the leg is redesigned and the controls re-run, with the redesign
documented."* The original §3/§4/§7/§9 text above is **retained verbatim**; this section supersedes
it where they differ.

> **The controls FAILED the first design, and that is the most useful thing this story measured.**
> Every fix below is a measured consequence, not a preference.

## 12.1 What the controls found

| finding | measured |
|---|---|
| **`A3_sigma_clairvoyant` is a DEGENERATE, not a ceiling.** Binning by the row's own `\|y−μ\|` decile forces `z ≈ ±1`. | On **CLEAN** data (no defect planted): `scale_cv` **0.745**, `pit_ks` **0.2251** vs the incumbent's 0.0302, `cov50` **0.106**, and a CRPS **below** what a correctly specified model can attain. It bounded nothing, in either direction — NF-W6's *"a row-level peek is a zero-CRPS degenerate, not a ceiling"*, verbatim. |
| **A pooled PIT statistic is near-BLIND to a per-game σ deficit.** | Planting a true σ-CV of **0.35** moved `pit_ks` from 0.0302 to **0.0241** — i.e. not at all, and in the wrong direction. |
| **An UNPAIRED null band is the wrong materiality test.** | On the same frame the incumbent's CRPS sits **inside** its unpaired 95% null band while an oracle beats it by **0.12** on the identical outcomes. |
| **The `\|·\|` fold destroys the asymmetry statistic's power.** `\|g_A1\| − \|g_B2\|` shares the realized over-rate but does not cancel it under the fold. | At `n ≈ 758` the binomial noise in `mean(y > μ)` is SE **0.018**, comparable to the real defect (0.066). `PC_shape` routed correctly **0.40** of the time. |
| **A right-skewed sample masquerades as a scale mixture.** A heavy ONE-sided tail raises BIC's preference for `K = 2` and opens a peek. | The FEATURE lever fired on **20%** of pure-SHAPE draws. |

## 12.2 The four amendments

1. **`A3_sigma_clairvoyant` → `A3_sigma_scalemix`.** A **shrunk Bayes peek**: fit a ZERO-MEAN normal
   scale mixture to the out-of-block `z` (`K ∈ 1..3` by **BIC**, out of block), then give each
   in-block row its posterior mean scale `sqrt(E[s²|z_i])`. Two properties make it a legitimate
   ceiling: under a constant true scale BIC returns `K = 1`, the posterior scale is CONSTANT and
   the oracle collapses onto `A1` — it is INERT, where a binned clairvoyant manufactures dispersion
   out of pure noise; and the mixture is SYMMETRIC, so it cannot absorb skew.
2. **ONE PRIMARY PER LEVER — each lever scored on every statistic it can ACT on, and none it
   cannot.** `crps` (a PER-GAME proper score; a marginal shape law is identical across games so it
   cannot recover a per-game scale loss) is admissible for **both** levers. `p_over_gap`
   (the ASYMMETRY around the model's own mean — the error on the quantity the product prints) is
   admissible for the **shape lever only**: a symmetric scale deficit cannot move it, so scoring
   the feature lever there would be a gate the arm cannot move (NF-MARGIN2). `pit_ks` is a reported
   safeguard, not a lever statistic — it is moved by BOTH mechanisms and so cannot separate them.
3. **PAIRED materiality, and an outcome-noise-free ASYMMETRY channel.** Every arm scores the same
   outcomes, so a lever counts only if its **paired row-bootstrap 95% CI excludes 0**
   (`N_BOOT = 400`). The asymmetry channel is read as the **movement of the stated probability**,
   `mean(stated_A1) − mean(stated_B2)`, in which the realized over-rate cancels EXACTLY — gated by
   a precondition that the incumbent's signed gap is itself materially non-zero, without which the
   channel credits a shape law for fitting SAMPLE skew (measured: `PC_dispersion` fell to 0.10).
4. **THE SYMMETRY GATE.** A genuine per-game scale mixture is SYMMETRIC; skew is not. Each side of
   the median is reflected into a symmetric sample of its own and must INDEPENDENTLY prefer
   `K ≥ 2`; otherwise the oracle is forced to `K = 1` and is inert.

Two further registered choices, stated because they are load-bearing:

- **The share denominator is the JOINT CEILING**, not the calibrated-null gap. The gap is reported
  as CONTEXT (how far the incumbent sits from a correctly specified model) but on a planted or a
  genuinely non-Normal world it can go negative, which would zero a real lever's share for a purely
  arithmetic reason.
- **The decomposition stays HIERARCHICAL and conservative toward the EXPENSIVE lever**: the
  architecture lever is scored beyond a plain recalibrator (`imp(B2) − imp(A1)`), and the feature
  lever — the one that needs a whole new data product — must prove it adds BEYOND the best marginal
  shape (`imp(C1) − imp(B2)`). Shared credit goes to the cheaper mechanism.

## 12.3 The controls become RATES, with bars fixed here

A one-draw control conflates *"the legs do not separate"* with *"this draw was quiet"*. Each control
is now **20 replicates**, and the bars are DESIGN quantities fixed in this commit (MH2.8 used the
same shape: 40 clean replicates at a 0.9 bar, 10 positive at 1.0):

| bar | value |
|---|---|
| positive control routes correctly | **≥ 0.80** |
| ...and credits the OTHER lever | **≤ 0.10** |
| clean frame returns `NO_MEASURABLE_DEFECT` | **≥ 0.90** |

## 12.4 Measured operating characteristics of the amended battery

| control | route rate (bar) | wrong-lever rate (bar) | outcomes over 20 replicates | ✓ |
|---|---:|---:|---|---|
| `PC_clean` | **0.90** (0.90) | 0.00 (0.10) | 18 `NO_MEASURABLE_DEFECT`, 2 `IRREDUCIBLE` | ✅ |
| `PC_dispersion` (σ-CV 0.35) | **0.90** (0.80) | **0.00** (0.10) | 18 `FEATURE-BOUND`, 1 `IRREDUCIBLE`, 1 `NO_MEASURABLE_DEFECT` | ✅ |
| `PC_shape` (α = 4) | **0.90** (0.80) | **0.00** (0.10) | 18 `SHAPE-BOUND`, 1 `IRREDUCIBLE`, 1 `NO_MEASURABLE_DEFECT` | ✅ |
| `PC_both` | 0.60 (0.80) | 0.00 (0.10) | 12 `BOTH`, 7 `SHAPE-BOUND`, 1 `NO_MEASURABLE_DEFECT` | ⛔ |

⭐ **The spec's stated control requirement is met.** It asks that *"each diagnostic leg detects ITS
deficit and not the other's"*: the dispersion leg detects its own **0.90** and the shape leg's
**0.00**; the shape leg detects its own **0.90** and the dispersion leg's **0.00**. Cross-detection
is zero in both directions.

⛔ **`PC_both` FAILS its bar at 0.60, and the clause is left FAILING, not re-labelled** (the
precedent is MH2.8's own negative control, recorded at 0.650 against a 0.9 bar and reported as a
failing clause). What it means, stated in advance so it cannot be re-read later:

- When BOTH deficits are present at these magnitudes the battery routes `SHAPE-BOUND` about 35% of
  the time instead of `BOTH` — the two mechanisms partially cancel in the LEFT tail (skew thins it,
  heteroscedasticity fattens it), so the symmetry gate closes.
- **The error is one-directional: it UNDER-credits the feature lever in a mixed world and never
  over-credits it.** 0 of 20 mixed draws routed `FEATURE-BOUND`. For a funding decision that biases
  against the expensive story, which is the safe direction — but it must be read the right way:
  **a `SHAPE-BOUND` verdict on real data does not exclude a co-present dispersion component**, and
  the record states that beside the verdict.

## 12.5 What did NOT change

The population, the era, the tiers, the fold scheme, the market-blindness, the prohibitions, the
outcome names, the routing map, the bars `RULE_MAJORITY = 0.50` / `RULE_MATERIAL = 0.20`, the
`std_pred` flag in §6, and §11. **No real-data statistic informed any of it.**
