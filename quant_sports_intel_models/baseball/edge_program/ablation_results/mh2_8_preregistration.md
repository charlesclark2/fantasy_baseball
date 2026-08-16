# MH2.8 — PRE-REGISTRATION (written and committed BEFORE any statistic was computed)

**Story:** MH2.8 · MLB `total_runs` **distributional SHAPE** — does a skew-capable predictive fix the
right-skew defect MH2.6 found in the served symmetric Normal?
**Branch:** `mh2.8` · **`best_alpha = 0`** · **deploy-held**.
**Harness:** `betting_ml/scripts/mh2_8_skew_predictive.py` (Snowflake-free; DuckDB over the S3
lakehouse).

> Everything below is fixed BEFORE any arm, fold or statistic is scored. A choice made after seeing
> a number is window-shopping — the defect the MH2 lineage exists to stop (E2.1-r).

> ⛔ **This is a FRESH pre-registration, not a continuation of MH2.6.** MH2.6 pre-scoped two Phase-2
> branches (σ dynamic range → MH2.5; level/mean → a wide-window retrain) and its own §6 records that
> **neither is the right instrument for the defect it found**. Nothing in MH2.6's Phase-2 scoping
> carries over. What carries over is the *finding* and the *method* (its served-audit harness, its
> vacuity-floor discipline), never its decision rule.

---

## 0. The trigger, stated honestly

MH2.6 (`STANDING_MISCALIBRATION`) measured, on 634 served `total_runs` rows over 2026-06-23 →
2026-08-14:

| | |
|---|---|
| PIT flatness | `pit_mdd` 0.0420 vs a calibrated-null median 0.0215, band [0.0117, 0.0356], p = 0.008 — **OUTSIDE**, in BOTH the FULL and RECENT windows |
| level | `bias` +0.0085 — inside its null |
| scale | `Var(z)` 1.065 — inside its null |
| shape | realized `z` **skew +0.735**, excess kurtosis 0.588 |
| the serving-relevant read | mass below the predictive median **0.573** vs nominal 0.500 (3.7 SE) ⇒ at a line at the model's own mean the model prints `P(over) = 0.500` against a realized 0.427 — **over-stated by ≈7 points at the middle** |

The predictive is a symmetric Normal; realized total runs are right-skewed (a blow-up inning has no
left-hand mirror). It is a **SHAPE** error, and it is **STANDING** — present as strongly in the
earlier window as the recent one, so it is not drift and cannot be fixed by a retrain of the same
family.

**The default verdict of this study is `INCUMBENT_STANDS`.** MH2.6 explicitly declined to claim a
skew-aware predictive would improve the served number; this study is where that claim gets tested,
and it may fail.

---

## 1. LOCK — POPULATION AND WINDOW

### 1a. The CV population (selection)

| lock | value |
|---|---|
| matrix | `edge_e1_training_from2016` — `feature_pregame_game_features` joined to finals, read **Snowflake-free** via the S3 lakehouse (`data_loader.set_s3_mode(True)`) |
| window | **2016–2026**, 2020 KEPT — identical to MH2.1 Lock 1 and MH2.5 Lock 1 |
| target / tier | `total_runs` / `post_lineup` |
| contract | the 13-column SERVED contract (`build_arm_contracts(..., family='mh2_1')['incumbent']`) |
| folds | purged + embargoed (3 days), `make_gate_splitter` — the same splitter MH2.1/MH2.5 used |
| sensitivity | 2020 dropped from BOTH train and eval, run as a declared control, reported whatever it says |

### 1b. ⚠️ DECLARED DEVIATION from MH2.5's matrix — stated before any arm was scored

MH2.5 and MH2.1 read `load_clean_matrix`, which applies two E1 de-leak swaps. **This study applies
NEITHER**, and the reason is a mandate, not a convenience:

- `_swap_stuff_plus_deleaked` requires a live **Snowflake** connection, which this story forbids.
  It rewrites nine `*_starter_*_stuff_plus` / arsenal columns — ⭐ **none of which is in the
  13-column contract**, so skipping it is a **provable no-op for this study**. A guard test pins
  that claim mechanically rather than asserting it (`test_mh2_8_skew_predictive.py`).
- `_swap_bullpen_v3` rewrites `{home,away}_bp_eb_uncertainty`, which **ARE 2 of the 13** contract
  columns. It needs per-season `per_reliever_*.parquet` caches which are **gitignored and absent
  from this worktree** (the NF-INFRA1 class) and whose rebuild is a Snowflake-bound backfill.

⇒ **Consequence, stated in advance:** absolute LEVELS here are not directly comparable to MH2.5's,
and the recorded row count will differ from MH2.5's 20,055. The **arm-to-arm comparison — which is
the only thing this study decides on — is unaffected, because every arm reads the identical
matrix.** This is MH2.5's own Lock 9 logic applied to a different perturbation. ⛔ No cross-study
level comparison may be drawn from this record.

### 1c. The SERVED population (validation) — MH2.6's, verbatim

`daily_model_predictions` (S3) joined to `mart_game_results`, `model_version ∈ {v6, pre_lineup_v6}`,
live rows only (no backfills), latest `inserted_at` per `(game_pk, tier)`, `post_lineup` PRIMARY;
the 15 rows stamped `totals_model_version = 'mh2_1'` DROPPED (priced by the rolled-back challenger).

Every served row post-dates the champion's fit (E13.11, 2026-06-23), so **the whole served era is
out of sample** — MH2.1's "split a same-season backtest at the incumbent's fit date" rule is
satisfied by construction, which is what makes the served read decisive rather than confounded.

---

## 2. LOCK — THE FIELD: 8 trials, DECLARED not discovered

MH2 §a: *you get to PRE-REGISTER a family; you do not get to DISCOVER one.* No arm may be dropped
after a score is seen — trimming post hoc UNDER-taxes DSR and is a second layer of the very
selection bias DSR exists to deflate (MH2.2).

The family is **coherent by mechanism**: every arm is a candidate *shape* for the `total_runs`
predictive, and the anchors are the shapes that must lose.

### The four candidates (skew-capable)

| arm | what it is |
|---|---|
| `ngb_lognormal` | NGBoost **LogNormal** over the same 13 features. Right-skewed **by family**, on positive support. |
| `ngb_gamma` | NGBoost **Gamma**. Right-skewed, variance ∝ mean² — the count-like variance law totals actually obey. |
| `lgbm_quantile` | ⭐ a **distributional-quantile learner**: LightGBM pinball regression at a fixed level grid, monotonised, read as an empirical quantile function. Expresses **arbitrary** right skew and is §0.5's required direct-learned foil — it inherits nothing from the incumbent. |
| `skewnorm_recal` | ⭐ a **SHAPE RECALIBRATION** of the incumbent: keep NGBoost's μ and σ, map the standardised residual through an Azzalini **skew-normal** whose α is fitted in-fold on the honest calibration split, moment-matched so the predictive mean and SD are preserved **exactly**. **NESTS the incumbent at α = 0.** |

### The four anchors (all in `n_trials`, all pre-registered to lose)

| arm | role |
|---|---|
| `incumbent` | the NGBoost **Normal** — the served family. **THE BAR.** |
| `normal_recal` | ⭐ **THE MATCHED FOIL** (NF-D15 g′). The identical recalibration machinery with **α clamped to 0** — a pure location/scale refit on the same calibration split. Without it, a skew arm could win by fixing the LEVEL or the SCALE while the story claims it fixed the **SHAPE**. A win must clear this arm or the mechanism is mis-attributed. |
| `climo` | ⚠️ **THE NIHILIST.** The unconditional (climatological) empirical predictive of `total_runs` fitted on the training rows, **ignoring every feature**. **Registered in advance to WIN BOTH PRIMARY METRICS and to LOSE CRPS** — see LOCK 4. |
| `overskew` | the magnitude degenerate (NF-D20 `over_scale`): `skewnorm_recal` with its fitted α **× 3**. Registered to LOSE. If it WINS, the fitted magnitude under-corrects and that is a refuted magnitude hypothesis, not a metric inversion — recorded as such, ⛔ never re-labelled. |

`n_trials = 8` for PBO and DSR. `degenerate_arms = (climo, overskew)` for DSR-CONV (in `n_trials`
for multiplicity, out of `V` — a skill series whose size is fixed BY DESIGN is not a measurement of
how much real configurations disperse). ⚠️ DSR-CONV is FORWARD-ONLY and this story **opts in**
explicitly; the exclusion is non-monotone and an arm qualifies **by design, never by declaration**,
which is why the degenerate list is fixed here and not after the run.

### Diagnostics — ⛔ NEVER trials (MH2.1 (a): the `oracle_floor` DSR-field leak)

Excluded from `n_trials`, from DSR's `V`, and from PBO.

- `oracle_skewnorm`, `oracle_lgbm_quantile` — **PER-FORM** peeking ceilings, fitted on eval rows at
  **MATCHED n** (NF1.7 (b): "peeking can only help" holds only at equal family AND equal
  resolution; NF-D16 g‴: the forms nest, so one field-wide ceiling would falsely veto a
  legitimately-better nested form). ⚠️ A headroom diagnostic, **not a gate** — beating one is a
  capacity effect, not an inversion (NF-D14).
- ⭐ `pit_construction_floor` — **THE INVERSION GATE, and the only thing nothing may beat.** The
  `pit_mdd` a *correctly specified* predictive attains at this n, obtained by simulating outcomes
  from each arm's own predictive. It is a **construction**, not a fit, so an arm beating it is
  mathematically impossible and means the metric is inverted ⇒ **HALT**.
- `perm_shape` — ⚠️ **REGISTERED IN ADVANCE AS STRUCTURALLY INACTIVE for a global-α arm.**
  Permuting one constant α across games is a mathematical no-op, so this anchor is expected to TIE
  **exactly**, and a tie here is an INACTIVE anchor, ⛔ **not a passed test** (NF-D20; NF-D16
  sibling (1)). It is informative only for the per-game-shape arms (`lgbm_quantile`), where the
  shape genuinely varies row to row, and it is read only there.

---

## 3. LOCK — THE METRICS

`total_runs` is an **integer count** and every candidate predictive is continuous, so PIT is taken
with a **continuity correction and randomisation** (E2.1-r: gate a discrete target on randomised-PIT
flatness, never on raw interval coverage, which inclusive integer bounds INFLATE):

```
u = F(y + 0.5) · V + F(y − 0.5) · (1 − V),        V ~ U(0,1)
```

evaluated through **each arm's own CDF** `F`, not through a Normal.

### 3a. PRIMARY (two, both pre-registered)

1. **`pit_mdd`** — max-decile deviation of `u`. This is the statistic that FAILED in MH2.6, in both
   nested windows. Secondary flatness: `pit_ks`.
2. **`p_over_gap`** — the **serving-relevant** number. For each game take the reference line
   `L = μ_arm` (the arm's own predictive mean), the stated `p = 1 − F(L)`, and the realised
   `o = 1[y > L]`; the statistic is `mean(p) − mean(o)`. The incumbent's is ≈ **+0.073**.
   ⚠️ Measured at the model's own mean this bounds the **SHAPE** error rather than the served error.
   **On the served leg it is ALSO measured at the ACTUAL POSTED LINE** (`total_line_consensus`,
   with `bovada_line` as a declared robustness read) — registered here so the posted-line read
   cannot be mistaken for a post-hoc addition, which is exactly the gap MH2.6 flagged in its own
   §2 and could not close.

### 3b. CONSTRAINTS (⛔ never selection criteria)

- **CRPS non-inferiority** — LOCK 4.
- **Coverage floor** at 80% and 50%. ⛔ **A FLOOR, NEVER A TARGET** (E2.1-r / NF1.8: a coverage
  target is monotone in widening and the `max_width` degenerate wins it outright). Floors are
  derived from a DESIGN quantity — MH2.6's calibrated-null 95% band at the served n, whose lower
  edges were 0.7697 (`cov80`) and 0.4606 (`cov50`) — rounded DOWN to **`cov80 ≥ 0.75`** and
  **`cov50 ≥ 0.45`**, so a correctly-specified predictive clears them with margin at this n.
  ⛔ Never tightened above nominal "for safety" (NF1.8 (a)).

### 3c. SECONDARY (reported, verdict-inert)

CRPS itself; MH2.5's conditional `rms_var_z` — **only on a VALIDATED stratifier** (LOCK 6); realized
`z` skew and excess kurtosis; `mass_below_predictive_median`; `pit_ks`.

---

## 4. ⭐ LOCK — WHY A FLATNESS PRIMARY REQUIRES A SHARPNESS CONSTRAINT

**Both primaries are MARGINAL statistics, and a degenerate wins both by construction.** A predictive
that ignores every feature and emits the unconditional distribution of `total_runs` has a
**perfectly flat PIT** and a **zero `p_over_gap`** while carrying **zero** conditional information.
That is NF1.8's *"a criterion a degenerate WINS is fatal"* in its most literal form, and it is
precisely why `climo` is in the field rather than reasoned about: to make the inversion **visible**.

Two consequences, both fixed here:

1. **`climo` MUST lose the SHIP rule.** It is registered to WIN `pit_mdd` and `p_over_gap`. If it
   nevertheless clears the ship rule, the selection metric is inverted, the run reports
   **`METRIC_INVERTED`**, and **nothing ships** — whatever the leaderboard says.
2. **CRPS enters as a NON-INFERIORITY CONSTRAINT, not as a criterion.** A shipping arm's pooled
   CRPS must be no worse than the incumbent's by more than `MH28_CRPS_TOLERANCE`.
   *Non-inferiority* rather than *must win*, because a genuine shape fix **redistributes** mass and
   a mean-dominated proper score need not reward it (MH2.1's surviving methodological finding: CRPS
   is mean-dominated and PIT-KS is marginal, so each is blind to what the other sees). But an arm
   may not **buy** flatness with sharpness, and this constraint is what forbids it.

---

## 5. LOCK — THE PRACTICALLY-MEANINGFUL EFFECT (all derived from DESIGN quantities, fixed in advance)

A threshold reverse-engineered from the answer is not a threshold (NF1.8).

| constant | value | derivation |
|---|---:|---|
| `MH28_MEANINGFUL_PIT_MDD_GAIN` | **0.012** | the HALF-WIDTH of MH2.6's calibrated-null 95% band for `pit_mdd` at the served n ([0.0117, 0.0356] around a 0.0215 median). An improvement smaller than the null band's own width **on the population that matters** is not distinguishable from sampling noise there, however significant it is on 14k CV rows. |
| `MH28_MEANINGFUL_P_OVER_GAP` | **0.020** | the product prints `P(over)` as a percentage; two points is the resolution at which the displayed number changes for a user, and it is a quarter of the observed 0.073 defect. The winner's `|p_over_gap|` must be at least this much SMALLER than the incumbent's. |
| `MH28_CRPS_TOLERANCE` | **0.020** | **inherited verbatim** from MH2.5's `pre_registered_meaningful_crps_lift = 0.02`, so the non-inferiority band is the program's existing notion of a material CRPS move rather than a new number invented for this study. |

---

## 6. LOCK — THE STRATIFIER IS VALIDATED FIRST, OR NOTHING IS READ OFF IT

The exact defect that caused the MH2.1 rollback: *a conditional-calibration result is a property of
its stratifier.* Bars imported from MH2.5 verbatim, not re-declared: `STRATIFIER_MIN_RHO = 0.30`,
`STRATIFIER_MIN_ENDPOINT_SE = 2.0`, with the full realized-SD-per-bin table (n, mean stratifier,
realized SD, per-bin SE) published **whether it passes or fails**.

| stratifier | role |
|---|---|
| `incumbent_sigma` | PRIMARY |
| `incumbent_mean` | SECONDARY (independent partition; not a σ model at all) |

A partition that fails is **DISQUALIFIED**, `rms_var_z` leaves the verdict family, and the test
count falls accordingly (MH2.6's conditional-membership rule). ⛔ A failed validation is a finding,
not a licence to read the number anyway (NF1.7 (a)).

⚠️ Stated in advance so it is not mistaken for a result: MH2.5 found this partition **fails** when
pooled across 2016–2026 (σ deciles sort largely by ERA), and MH2.6 found it **fails on the RECENT
served window** and needs ≈1,155 served games to be usable. **A disqualification here is the
EXPECTED outcome and carries no information about the skew hypothesis** — `Var(z)` is a scale
instrument and this study is about shape.

---

## 7. ⭐ LOCK — THE VACUITY FLOOR (five controls, all run regardless of the result)

A verdict is worthless if the instrument could not have produced the other one. Carried from MH2.6
and extended to the SELECTION, not just the audit.

1. ⭐ **NEGATIVE CONTROL — clean data must NOT flag.** Re-run the **entire selection** on a synthetic
   frame in which the incumbent Normal is **TRUE** (outcomes redrawn from the incumbent's own
   per-fold predictive, `n` and per-game μ/σ held fixed). **No skew arm may win.** A harness that
   picks a skew arm on Normal data has not found skew in the real data — it has found its own
   preference. Acceptance, pre-stated and two-sided: the selected arm must be `incumbent` or
   `normal_recal` on **≥ 90%** of replicates.
2. **POSITIVE CONTROL — a known defect must fire.** Redraw outcomes from a skew-normal at a
   pre-registered shape and confirm the primaries flag it and a skew arm is selected.
3. **MDE** — the smallest true skew detectable at **80% power**, at BOTH the CV n and the served n,
   **stated in games** (the unit that grows, NF1.8). A null verdict means *"no shape defect larger
   than the MDE"*, and saying so is the difference between a measured null and a shrug.
4. **MULTIPLICITY** — Benjamini–Hochberg at **q = 0.05** across the declared verdict-statistic
   family, per window. MH2.6 measured that omitting this drove the family-wise error to ≈50% and
   produced two wrong verdicts on *clean synthetic frames*; that lesson is imported, not re-learnt.
5. **NON-DEGENERATE MC-p FLOOR** — the Monte-Carlo null uses enough reps that the SMALLEST
   attainable p-value is below the BH cutoff (MH2.6's `min_null_reps`). A p-value that cannot reach
   its own threshold is a vacuous test.

Plus the stratifier validation of LOCK 6, which is the sixth control in everything but name.

---

## 8. LOCK — DEFLATION AND THE CV GATES

| gate | bar |
|---|---|
| PBO | **< 0.2**, computed over the ELIGIBLE field (the 8 declared trials), never over diagnostics |
| DSR | **≥ 0.95**, DSR-CONV convention (degenerates in `n_trials`, out of `V`; the incumbent reference out of `V`) |
| BH-FDR | **q = 0.05** across the verdict family |
| fold consistency | `cv_power.fold_consistency_clause` at the realised fold count — a calibrated clause, never a bare 60% (MH2 H8) |
| design bar | `design_bar(n_folds, n_arms)` **printed BEFORE any fit** — a statement about the DESIGN that no result can contaminate |
| null classification | `cv_power.classify_null(declared_field_size = 8, ...)`; the machine flag **`field_remedy_admissible`** is read, ⛔ never the prose (MH2.7) |

⚠️ Stated in advance: MH2.5 recorded `DSR_UNREACHABLE` on this exact window and field size with a
CRPS metric. If MH2.8 lands there too, that is a statement about the DESIGN — and per MH2.2 the
remedy "a smaller field" is **inadmissible** here because 8 is the DECLARED minimum, which is
exactly what `field_remedy_admissible` exists to say out loud.

---

## 9. ⭐ LOCK — THE SERVED-ROW GATE, AND ITS PRE-REGISTERED ASYMMETRY

MH2.1 was rolled back **precisely because a backtest conclusion did not survive the served
population.** So a CV win is necessary and not sufficient: a winner must also pass MH2.6's
served-calibration audit, on MH2.6's population, re-shaping the **actually-served** (μ, σ).

⚠️ **PRE-REGISTERED ASYMMETRY — stated before any arm was scored so it cannot be mistaken for a
convenient post-hoc restriction.** Only an arm that is a **function of the served (μ, σ)** can be
evaluated on served rows:

| arm | served-evaluable? |
|---|---|
| `skewnorm_recal`, `normal_recal`, `overskew`, `incumbent` | ✅ yes — a transform of the served predictive |
| `ngb_lognormal`, `ngb_gamma`, `lgbm_quantile`, `climo` | ⛔ **`SERVED_UNVALIDATABLE`** |

A learned-family arm would have to be re-scored from features for the served games, and the offline
feature matrix is **NOT point-in-time** (MH2.5 Lock 9: `load_features` reads each game's row as it
exists NOW, post-game-backfilled and dense, while the live serve only ever saw the sparse pre-game
row). A re-score would therefore be a **CEILING, not the served number** — the very substitution
MH2.1's rollback punished. ⇒ **a `SERVED_UNVALIDATABLE` arm CANNOT SHIP.** It may produce a
research finding and scope a successor; it may not change what is served.

**The served gate.** On the served rows the winner must:

1. move `pit_mdd` INSIDE MH2.6's calibrated-null band (i.e. stop being flagged);
2. close `|p_over_gap|` by ≥ `MH28_MEANINGFUL_P_OVER_GAP` at the model's own mean **AND** at the
   actual posted line;
3. hold CRPS non-inferiority within `MH28_CRPS_TOLERANCE`;
4. hold the coverage floors of LOCK 3b.

---

## 10. LOCK — THE SHIP RULE (default verdict: `INCUMBENT_STANDS`)

An arm ships only if **every** clause holds. Each is independently checkable and each is registered
here before the harness computed anything.

| # | clause |
|---|---|
| 1 | ⭐ `climo` did **NOT** clear the ship rule — else **`METRIC_INVERTED`**, ship nothing |
| 2 | nothing beat `pit_construction_floor` — else **HALT** |
| 3 | beats `incumbent` on `pit_mdd` by ≥ `MH28_MEANINGFUL_PIT_MDD_GAIN` |
| 4 | closes `|p_over_gap|` vs `incumbent` by ≥ `MH28_MEANINGFUL_P_OVER_GAP` |
| 5 | ⭐ beats the MATCHED FOIL `normal_recal` on **both** primaries — else the mechanism is level/scale, not SKEW (NF-D15 g′) |
| 6 | CRPS non-inferior within `MH28_CRPS_TOLERANCE` |
| 7 | coverage floors held (`cov80 ≥ 0.75`, `cov50 ≥ 0.45`) |
| 8 | PBO < 0.2 **and** DSR ≥ 0.95 **and** BH-significant |
| 9 | the calibrated fold-consistency clause passes at the realised fold count |
| 10 | ⭐ passes the **SERVED-ROW GATE** (LOCK 9) — a `SERVED_UNVALIDATABLE` arm cannot ship |

Anything else ⇒ **`INCUMBENT_STANDS`**, with the null CLASSIFIED (never shrugged) via
`cv_power.classify_null`, and the margin stated **in the unit that grows**.

---

## 11. ⛔ LOCK — PROMOTION IS DEPLOY-HELD, AND THE MH2.1 LANDMINES ARE RESTATED

Regardless of outcome, **this session ships no registry edit, no pickle, no deploy.** If an arm
clears every clause the record hands the operator a decision, not a fait accompli.

- **A ONE-TARGET SWAP BREAKS BUNDLE-ASSUMING CONSUMERS.** `daily_model_predictions.model_version` is
  stamped from `registry["home_win"]` only; the backfill idempotency key is
  `(game_pk, model_version, retrain_tag)`; `mart_clv_labeled_games` hardcodes `model_version = 'v6'`.
  Promoting `total_runs` alone shows no change in the app, writes nothing on backfill while
  reporting success, and "helpfully" re-pinning the CLV mart matches ZERO rows.
- **SERVE THE OBJECT THAT WAS VALIDATED, NOT A RE-DERIVATION.** A skew layer is a **different
  distributional family**, not a re-parameterisation: `predict_today` / the backfill call NGBoost's
  `pred_dist(X).params` verbatim, so whatever ships must persist exactly what this bake-off scored.
- **A MODEL-REGISTRY CHANGE SHIPS WITH THE BOX IMAGE ON MERGE TO `main`** (`orchestration_cd.yml`
  `COPY . .`) — **merging IS the deploy, with no gate between merge and serve.** That is the
  opposite of the API-Lambda skew rule and it is why this is deploy-held and an explicit operator
  decision.
- **`best_alpha = 0`** — no bet rides on this model. That is what made MH2.1's rollback cost one
  registry edit, and it is the same safety margin here.
